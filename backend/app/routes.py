"""API routes matching docs/api-contract.md.

Case data and metrics are computed once at startup by backend/app/main.py's
lifespan handler (via ml.pipeline.run_full_pipeline(), or the documented
mock fallback if that fails) and cached on app.state. Routes only ever
read that cache -- never ml/ or the mock JSON directly -- so every
request is fast regardless of which source is backing it.
"""

from fastapi import APIRouter, HTTPException, Request

from app.schemas import CaseDetail, CaseSummary, EscalateRequest, EscalateResponse, MetricsResponse

router = APIRouter()


@router.get("/cases", response_model=list[CaseSummary])
def list_cases(request: Request):
    # Pre-sorted (risk_tier priority, then risk_score descending) once at
    # startup by main.py's _sort_case_summaries -- nothing to do here.
    return request.app.state.cases


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, request: Request):
    case = request.app.state.case_details.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return case


@router.post("/cases/{case_id}/escalate", response_model=EscalateResponse)
def escalate_case(case_id: str, body: EscalateRequest, request: Request):
    if case_id not in request.app.state.case_details:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    # In-memory only, per spec -- an analyst decision here doesn't need
    # to persist across restarts for this stage of the project.
    status = "confirmed" if body.decision == "confirm" else "dismissed"
    return {"case_id": case_id, "status": status}


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(request: Request):
    return request.app.state.metrics
