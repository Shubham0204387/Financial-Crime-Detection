"""FastAPI app entrypoint.

Run with: uvicorn app.main:app --reload
Serves all endpoints from mock_data/cases_mock.json. Has zero dependency
on ml/ actually working yet.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router

app = FastAPI(title="Financial Crime Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def health_check():
    return {"status": "ok"}
