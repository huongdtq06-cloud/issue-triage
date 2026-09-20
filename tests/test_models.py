import pytest
from pydantic import ValidationError

from app.models import IssueTriage


def test_valid_classified_triage():
    triage = IssueTriage.model_validate(
        {
            "status": "classified",
            "severity": "P1",
            "component": "payment",
            "needs_urgent_response": True,
            "reason": "Payment fails for all Visa cards.",
        }
    )

    assert triage.status == "classified"


def test_valid_insufficient_data():
    triage = IssueTriage.model_validate(
        {
            "status": "insufficient_data",
            "severity": None,
            "component": None,
            "needs_urgent_response": False,
            "reason": "No impact or component is provided.",
        }
    )

    assert triage.severity is None


def test_valid_out_of_scope():
    triage = IssueTriage.model_validate(
        {
            "status": "out_of_scope",
            "severity": None,
            "component": None,
            "needs_urgent_response": False,
            "reason": "The input is not a software issue.",
        }
    )

    assert triage.status == "out_of_scope"


def test_invalid_status():
    with pytest.raises(ValidationError):
        IssueTriage.model_validate(
            {
                "status": "done",
                "severity": "P1",
                "component": "payment",
                "needs_urgent_response": True,
                "reason": "Invalid status.",
            }
        )


def test_invalid_severity():
    with pytest.raises(ValidationError):
        IssueTriage.model_validate(
            {
                "status": "classified",
                "severity": "P9",
                "component": "payment",
                "needs_urgent_response": True,
                "reason": "Invalid severity.",
            }
        )


def test_missing_required_field():
    with pytest.raises(ValidationError):
        IssueTriage.model_validate(
            {
                "status": "classified",
                "severity": "P1",
                "component": "payment",
                "needs_urgent_response": True,
            }
        )
