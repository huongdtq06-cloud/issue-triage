"""FastAPI entry point for the Issue Triage mini-app."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import TriageRequest, TriageResponse
from app.triage import OpenAITriageClient, triage_issue

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Issue Triage Mini-App")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/triage", response_model=TriageResponse)
def triage_endpoint(request: TriageRequest) -> TriageResponse:
    if not request.issue.strip():
        raise HTTPException(status_code=400, detail="Missing issue.")

    try:
        return triage_issue(request.issue, OpenAITriageClient.from_environment())
    except ValueError as error:
        status = 400 if str(error) == "Issue is required." else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
