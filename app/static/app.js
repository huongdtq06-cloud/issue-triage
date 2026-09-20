const form = document.querySelector("#triage-form");
const errorBox = document.querySelector("#error");
const traceList = document.querySelector("#trace");

const fields = {
  status: document.querySelector("#status"),
  severity: document.querySelector("#severity"),
  component: document.querySelector("#component"),
  urgent: document.querySelector("#urgent"),
  team: document.querySelector("#team"),
  reason: document.querySelector("#reason"),
  traceId: document.querySelector("#trace-id"),
};

function setText(element, value) {
  element.textContent = value || "-";
}

function renderTrace(trace) {
  traceList.innerHTML = "";
  for (const step of trace) {
    const item = document.createElement("li");
    item.className = `trace-step ${step.status}`;

    const title = document.createElement("strong");
    title.textContent = step.name;

    const status = document.createElement("span");
    status.textContent = step.status;

    const pre = document.createElement("pre");
    pre.textContent =
      typeof step.data === "string" ? step.data : JSON.stringify(step.data, null, 2);

    item.append(title, status, pre);
    traceList.appendChild(item);
  }
}

function resetResult() {
  errorBox.hidden = true;
  errorBox.textContent = "";
  for (const key of Object.keys(fields)) {
    setText(fields[key], "-");
  }
  traceList.innerHTML = "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetResult();

  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Triaging...";

  try {
    const issue = new FormData(form).get("issue");
    const response = await fetch("/api/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ issue }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Unable to process the issue right now.");
    }

    setText(fields.traceId, `TRACE ${payload.trace_id}`);
    setText(fields.status, payload.triage.status);
    setText(fields.severity, payload.triage.severity || "N/A");
    setText(fields.component, payload.triage.component || "Unknown");
    setText(fields.urgent, payload.triage.needs_urgent_response ? "Yes" : "No");
    setText(fields.team, payload.owner_team);
    setText(fields.reason, payload.triage.reason);
    renderTrace(payload.trace);
  } catch (error) {
    errorBox.hidden = false;
    errorBox.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Triage Issue";
  }
});
