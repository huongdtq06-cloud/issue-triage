from fastapi.testclient import TestClient

from app.main import app
from app.models import IssueTriage


class FakeLLM:
    def __init__(self, result):
        self.result = result

    def classify(self, issue: str):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def request_owner_tool_call(self, component: str, environment: str):
        return {
            "id": "call_test",
            "name": "get_component_owner",
            "arguments": f'{{"component":"{component}","environment":"{environment}"}}',
        }


def client_with_llm(monkeypatch, result):
    import app.main as main

    monkeypatch.setattr(
        main.OpenAITriageClient,
        "from_environment",
        staticmethod(lambda: FakeLLM(result)),
    )
    return TestClient(app)


def test_valid_issue(monkeypatch):
    client = client_with_llm(
        monkeypatch,
        IssueTriage(
            status="classified",
            severity="P1",
            component="payment",
            needs_urgent_response=True,
            reason="Payment fails for all Visa cards.",
        ),
    )

    response = client.post("/api/triage", json={"issue": "Payment is down."})

    assert response.status_code == 200
    body = response.json()
    assert body["triage"]["component"] == "payment"
    assert body["owner_team"] == "Payment Team"
    assert body["trace_id"]
    assert body["trace"][4]["data"]["id"] == "call_test"
    assert body["trace"][4]["data"]["name"] == "get_component_owner"
    assert [step["name"] for step in body["trace"]] == [
        "input",
        "prompt",
        "llm_response",
        "validation",
        "tool_call",
        "application_execution",
        "tool_result",
        "final_response",
    ]


def test_missing_issue(monkeypatch):
    client = client_with_llm(monkeypatch, {})

    response = client.post("/api/triage", json={"issue": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing issue."


def test_llm_failure(monkeypatch):
    client = client_with_llm(monkeypatch, RuntimeError("provider unavailable"))

    response = client.post("/api/triage", json={"issue": "Payment is down."})

    assert response.status_code == 502
    assert response.json()["detail"] == "Unable to process the issue right now."


def test_validation_failure(monkeypatch):
    client = client_with_llm(monkeypatch, {"status": "invalid"})

    response = client.post("/api/triage", json={"issue": "Payment is down."})

    assert response.status_code == 422
    assert response.json()["detail"] == "Triage validation failed."


def test_tool_failure(monkeypatch):
    import app.triage as triage_module

    client = client_with_llm(
        monkeypatch,
        IssueTriage(
            status="classified",
            severity="P1",
            component="payment",
            needs_urgent_response=True,
            reason="Payment fails.",
        ),
    )

    def broken_tool(component, environment):
        raise RuntimeError("tool unavailable")

    monkeypatch.setattr(triage_module, "get_component_owner", broken_tool)
    response = client.post("/api/triage", json={"issue": "Payment is down."})

    assert response.status_code == 502
    assert (
        response.json()["detail"]
        == "Issue was triaged, but the component owner could not be determined."
    )
