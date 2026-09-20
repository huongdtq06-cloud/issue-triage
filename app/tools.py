"""Application-owned tools for deterministic business logic."""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

Environment = Literal["production", "staging", "development"]

# Canonical component vocabulary. This table is the single source of truth:
# `Component` below is generated from it, so adding a component here widens
# the LLM contract, the Pydantic validation and the owner lookup at once.
#
# Ownership is currently the same in every environment, so the table is keyed
# by component alone. If a team ever differs per environment, reintroduce the
# environment dimension here and select on it in `get_component_owner`.
COMPONENT_TEAMS: dict[str, str] = {
    "payment": "Payment Team",
    "checkout": "Checkout Team",
    "authentication": "Identity Team",
    "identity": "Identity Team",
    "notification": "Messaging Team",
    "search": "Search Team",
}

# Written out rather than generated from COMPONENT_TEAMS: a dynamic
# Literal[*COMPONENT_TEAMS] works at runtime but static checkers reject a
# variable inside a type expression. `test_component_type_matches_table`
# keeps the two in sync.
Component = Literal[
    "payment",
    "checkout",
    "authentication",
    "identity",
    "notification",
    "search",
]

# Unambiguous synonyms the model reaches for. Deliberately short: anything
# requiring a business judgement call belongs in COMPONENT_TEAMS instead.
COMPONENT_ALIASES: dict[str, str] = {
    "auth": "authentication",
    "login": "authentication",
    "signin": "authentication",
    "sso": "authentication",
    "oauth": "authentication",
    "email": "notification",
    "messaging": "notification",
}

logger = logging.getLogger(__name__)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(value: str) -> list[str]:
    """Split a free-form label into lowercase word tokens."""
    return [token for token in _TOKEN_SPLIT.split(value.lower()) if token]


def normalize_component(raw: object) -> Component | None:
    """Map a free-form model string onto the canonical component vocabulary.

    The model routinely answers with phrases such as "Payment Gateway",
    "payment_gateway" or "product search". Resolving them here keeps the
    vocabulary enforced without discarding an otherwise usable answer.

    Returns None when nothing matches, so callers treat the component as
    unresolved rather than guessing at it.
    """
    if not isinstance(raw, str):
        return None

    tokens = _tokens(raw)
    if not tokens:
        return None

    # An exact canonical name anywhere in the phrase wins outright, so
    # "Google login authentication" resolves to authentication, not login.
    for token in tokens:
        if token in COMPONENT_TEAMS:
            return token  # type: ignore[return-value]

    for token in tokens:
        if token in COMPONENT_ALIASES:
            return COMPONENT_ALIASES[token]  # type: ignore[return-value]

    # Singular/plural only. Broader prefix matching would let short tokens
    # ("pay", "sea") collide with unrelated components.
    for token in tokens:
        for name in COMPONENT_TEAMS:
            if token == f"{name}s" or name == f"{token}s":
                return name  # type: ignore[return-value]

    return None


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_component_owner",
        "description": "Get the team responsible for a software component in a specific environment.",
        "parameters": {
            "type": "object",
            "properties": {
                "component": {"type": "string", "enum": list(COMPONENT_TEAMS)},
                "environment": {
                    "type": "string",
                    "enum": ["production", "staging", "development"],
                },
            },
            "required": ["component", "environment"],
            "additionalProperties": False,
        },
    },
}


def get_component_owner(component: str, environment: Environment) -> str:
    """Return the owner team for a component/environment pair.

    An unresolved component returns "Unknown Team" rather than raising, so a
    triage result is still produced. Genuinely unmapped values are logged, so
    a gap in the vocabulary surfaces instead of failing silently.
    """
    canonical = normalize_component(component)
    if canonical is None:
        if isinstance(component, str) and component.strip():
            logger.warning(
                "Unmapped component %r (environment=%r); add it to COMPONENT_TEAMS.",
                component,
                environment,
            )
        return "Unknown Team"
    return COMPONENT_TEAMS[canonical]


def validate_component_owner_arguments(raw_arguments: str) -> dict[str, str]:
    """Validate model-generated tool arguments before application execution."""
    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")

    if set(arguments) != {"component", "environment"}:
        raise ValueError("Tool arguments must contain component and environment only.")

    component = arguments["component"]
    environment = arguments["environment"]
    if not isinstance(component, str) or not isinstance(environment, str):
        raise ValueError("Tool arguments component and environment must be strings.")
    if environment not in ("production", "staging", "development"):
        raise ValueError("Tool argument environment is invalid.")

    return {"component": component, "environment": environment}
