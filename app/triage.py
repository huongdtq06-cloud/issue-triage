"""Application-controlled Issue Triage workflow."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol
from uuid import uuid4

from openai import OpenAI
from pydantic import ValidationError

from app.models import IssueTriage, TraceStep, TriageResponse
from app.prompts import SYSTEM_PROMPT, build_messages, build_user_prompt
from app.tools import (
    Environment,
    TOOL_SCHEMA,
    get_component_owner,
    normalize_component,
    validate_component_owner_arguments,
)

DEFAULT_ENVIRONMENT: Environment = "production"


class StructuredTriageClient(Protocol):
    """Small protocol used by tests to mock the LLM call."""

    def classify(self, issue: str) -> Any:
        """Return an IssueTriage-compatible object or dict."""

    def request_owner_tool_call(self, component: str, environment: Environment) -> dict[str, Any]:
        """Return a model-generated get_component_owner tool request."""


class OpenAITriageClient:
    """OpenAI-compatible structured-output client."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self.model = model
        self.base_url = base_url or ""
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_environment(cls) -> "OpenAITriageClient":
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required.")
        if not model:
            raise RuntimeError("OPENAI_MODEL is required.")
        return cls(api_key=api_key, model=model, base_url=base_url)

    def classify(self, issue: str) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=build_messages(issue),
            response_format={"type": "json_object"},
            max_tokens=500,
            **self._request_options(),
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Model returned empty content.")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Model JSON output must be an object.")
        return parsed

    def request_owner_tool_call(self, component: str, environment: Environment) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You must call get_component_owner exactly once using the supplied "
                        "component and environment. Do not answer with normal text."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"component": component, "environment": environment},
                        ensure_ascii=False,
                    ),
                },
            ],
            tools=[TOOL_SCHEMA],
            tool_choice={
                "type": "function",
                "function": {"name": "get_component_owner"},
            },
            max_tokens=200,
            **self._request_options(),
        )
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise ValueError("Model returned no tool call.")
        tool_call = tool_calls[0]
        return {
            "id": tool_call.id,
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        }

    def _request_options(self) -> dict[str, Any]:
        if "deepseek.com" in self.base_url:
            return {
                "reasoning_effort": "low",
                "extra_body": {"thinking": {"type": "disabled"}},
            }
        return {}


def _final_response(triage: IssueTriage, owner_team: str) -> str:
    severity = triage.severity or "N/A"
    urgent = "Yes" if triage.needs_urgent_response else "No"
    component = triage.component or "Unknown"
    return (
        f"Issue classified as {severity}.\n\n"
        f"Status: {triage.status}\n"
        f"Component: {component}\n"
        f"Team: {owner_team}\n"
        f"Urgent response: {urgent}\n\n"
        f"Reason:\n{triage.reason}"
    )


def triage_issue(
    issue: str,
    llm_client: StructuredTriageClient,
    environment: Environment = DEFAULT_ENVIRONMENT,
) -> TriageResponse:
    """Run the full triage workflow and return response plus trace."""
    normalized_issue = issue.strip()
    trace_id = uuid4().hex[:12]
    trace: list[TraceStep] = [
        TraceStep(name="input", data=normalized_issue),
        TraceStep(
            name="prompt",
            data={"system": SYSTEM_PROMPT, "user": build_user_prompt(normalized_issue)},
        ),
    ]

    if not normalized_issue:
        raise ValueError("Issue is required.")

    try:
        raw_triage = llm_client.classify(normalized_issue)
        trace.append(TraceStep(name="llm_response", data=_jsonable(raw_triage)))
    except Exception as error:
        trace.append(TraceStep(name="llm_response", status="error", data=str(error)))
        raise RuntimeError("Unable to process the issue right now.") from error

    try:
        triage = IssueTriage.model_validate(_resolve_component(raw_triage))
        validation_data: dict[str, Any] = {"status": "success"}
        raw_component = raw_triage.get("component") if isinstance(raw_triage, dict) else None
        if triage.component and raw_component != triage.component:
            validation_data["component_resolved"] = {
                "from": raw_component,
                "to": triage.component,
            }
        trace.append(TraceStep(name="validation", data=validation_data))
    except ValidationError as error:
        trace.append(TraceStep(name="validation", status="error", data=error.errors()))
        raise ValueError("Triage validation failed.") from error

    # The owner lookup depends only on the component. Status describes how
    # complete the triage is, which is a separate question - gating on it here
    # discarded components the model had already identified.
    if not triage.component:
        trace.append(
            TraceStep(
                name="tool_call",
                status="skipped",
                data="No component owner lookup for unclassified or component-less issue.",
            )
        )
        owner_team = "Unknown Team"
    else:
        try:
            tool_request = llm_client.request_owner_tool_call(triage.component, environment)
            if tool_request["name"] != "get_component_owner":
                raise ValueError(f"Tool is not allowed: {tool_request['name']}")
            tool_arguments = validate_component_owner_arguments(tool_request["arguments"])
            trace.append(
                TraceStep(
                    name="tool_call",
                    data={
                        "id": tool_request["id"],
                        "name": tool_request["name"],
                        "arguments": tool_arguments,
                    },
                )
            )
            owner_team = get_component_owner(
                tool_arguments["component"],
                tool_arguments["environment"],  # type: ignore[arg-type]
            )
            trace.append(
                TraceStep(
                    name="application_execution",
                    data=(
                        "get_component_owner("
                        f"component={tool_arguments['component']!r}, "
                        f"environment={tool_arguments['environment']!r})"
                    ),
                )
            )
            trace.append(TraceStep(name="tool_result", data={"owner_team": owner_team}))
        except Exception as error:
            trace.append(TraceStep(name="application_execution", status="error", data=str(error)))
            raise RuntimeError(
                "Issue was triaged, but the component owner could not be determined."
            ) from error

    final_response = _final_response(triage, owner_team)
    trace.append(TraceStep(name="final_response", data=final_response))
    return TriageResponse(
        trace_id=trace_id,
        triage=triage,
        owner_team=owner_team,
        final_response=final_response,
        trace=trace,
    )


def _resolve_component(raw: Any) -> Any:
    """Fold a free-form component onto the canonical vocabulary before validation.

    The model answers with phrases like "Payment Gateway" or "product search".
    Resolving them here enforces the strict IssueTriage contract without turning
    every near-miss into a 422.
    """
    if not isinstance(raw, dict) or "component" not in raw:
        return raw
    return {**raw, "component": normalize_component(raw["component"])}


def _jsonable(value: Any) -> Any:
    if isinstance(value, IssueTriage):
        return value.model_dump()
    return value
