"""FastAPI app entrypoint.

Run with: uvicorn app.main:app --reload

At startup (see `lifespan` below), runs the full ml/ pipeline exactly
once via ml.pipeline.run_full_pipeline() and caches its output on
app.state -- every route reads from that cache, never from ml/ or the
mock JSON directly, so a request is always fast (the pipeline itself
takes tens of seconds and must never run per-request).

If the pipeline fails for any reason (e.g. the gitignored dataset files
aren't present locally), this falls back to serving
mock_data/cases_mock.json rather than crashing the server -- see
mock_data/README.md for why that fallback exists and how to use it
deliberately (e.g. during a live demo if the real pipeline breaks).
"""

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router

logger = logging.getLogger("app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
MOCK_DATA_PATH = BACKEND_DIR / "mock_data" / "cases_mock.json"

# ml/ lives at the repo root, a sibling of backend/ -- not importable from
# a process started with `cd backend && uvicorn app.main:app` unless the
# repo root is added to sys.path explicitly.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TIER_PRIORITY = {"str_ready": 0, "review": 1, "monitor": 2}

# Used only if the real pipeline fails and mock_data/cases_mock.json
# doesn't carry its own metrics fallback values (it doesn't -- metrics
# aren't part of that file's shape).
_MOCK_METRICS = {
    "baseline": {"precision": 0.41, "recall": 0.58, "f1": 0.48},
    "candidate": {"precision": 0.73, "recall": 0.69, "f1": 0.71},
}


def _sort_case_summaries(cases: list[dict]) -> list[dict]:
    """Sort by risk_tier priority (str_ready, review, monitor), then risk_score descending."""
    return sorted(cases, key=lambda c: (_TIER_PRIORITY.get(c["risk_tier"], 99), -c["risk_score"]))


def _load_mock_fallback() -> dict:
    with MOCK_DATA_PATH.open() as f:
        data = json.load(f)
    return {
        "cases": _sort_case_summaries(data["cases"]),
        "case_details": data["case_details"],
        "metrics": _MOCK_METRICS,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from ml.pipeline import run_full_pipeline

        logger.info("Running full ml/ pipeline at startup (this takes tens of seconds)...")
        result = run_full_pipeline()

        app.state.cases = _sort_case_summaries(result["cases"])
        app.state.case_details = result["case_details"]
        app.state.metrics = result["metrics"]
        app.state.data_source = "pipeline"

        tiers = result["tier_counts"]
        logger.info(
            "Pipeline ready: %d cases loaded (monitor=%d, review=%d, str_ready=%d)",
            len(app.state.cases), tiers.get("monitor", 0), tiers.get("review", 0), tiers.get("str_ready", 0),
        )
    except Exception:
        logger.exception(
            "Full ml/ pipeline failed at startup; falling back to mock_data/cases_mock.json "
            "(see backend/mock_data/README.md)"
        )
        fallback = _load_mock_fallback()
        app.state.cases = fallback["cases"]
        app.state.case_details = fallback["case_details"]
        app.state.metrics = fallback["metrics"]
        app.state.data_source = "mock"
        logger.info("Mock fallback ready: %d cases loaded", len(app.state.cases))

    yield


app = FastAPI(title="Financial Crime Detection API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def health_check(request: Request):
    return {"status": "ok", "data_source": getattr(request.app.state, "data_source", "unknown")}
