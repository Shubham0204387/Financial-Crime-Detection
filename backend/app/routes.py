"""API routes matching docs/api-contract.md.

All data is served from mock_data/cases_mock.json for now. No real
detection logic runs here yet -- this will be swapped for calls into
ml/detection.py once that's implemented.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas import CaseDetail, CaseSummary, EscalateRequest, EscalateResponse, MetricsResponse

router = APIRouter()

MOCK_DATA_PATH = Path(__file__).resolve().parent.parent / "mock_data" / "cases_mock.json"


def _load_mock_data() -> dict:
    with MOCK_DATA_PATH.open() as f:
        return json.load(f)


# Hardcoded placeholder until ml/evaluate.py produces real numbers.
_MOCK_METRICS = {
    "baseline": {"precision": 0.41, "recall": 0.58, "f1": 0.48},
    "candidate": {"precision": 0.73, "recall": 0.69, "f1": 0.71},
}


@router.get("/cases", response_model=list[CaseSummary])
def list_cases():
    data = _load_mock_data()
    return data["cases"]


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: str):
    data = _load_mock_data()
    case = data["case_details"].get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return case


@router.post("/cases/{case_id}/escalate", response_model=EscalateResponse)
def escalate_case(case_id: str, body: EscalateRequest):
    data = _load_mock_data()
    if case_id not in data["case_details"]:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    status = "confirmed" if body.decision == "confirm" else "dismissed"
    return {"case_id": case_id, "status": status}


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    return _MOCK_METRICS
