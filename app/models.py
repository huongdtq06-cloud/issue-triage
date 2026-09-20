"""Pydantic schemas for the Issue Triage app."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.tools import Component


class IssueTriage(BaseModel):
    """Structured output contract returned by the LLM."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["classified", "insufficient_data", "out_of_scope"]
    severity: Literal["P0", "P1", "P2", "P3"] | None
    component: Component | None
    needs_urgent_response: bool
    reason: str


class TriageRequest(BaseModel):
    """Request body for POST /api/triage."""

    issue: str = Field(min_length=1)


class TraceStep(BaseModel):
    """One visible workflow step in the request trace."""

    name: str
    status: Literal["success", "error", "skipped"] = "success"
    data: Any


class TriageResponse(BaseModel):
    """Response body for POST /api/triage."""

    trace_id: str
    triage: IssueTriage
    owner_team: str
    final_response: str
    trace: list[TraceStep]
