# Financial Crime Detection

A hackathon project that flags financial accounts and transaction chains
for potential financial crime (money laundering patterns like cycles and
scatter-gather structuring), scores them by risk, and surfaces the
evidence an analyst needs to decide whether to file a Suspicious
Transaction Report (STR).

## Folder structure

```
backend/    FastAPI service exposing the case API (see docs/api-contract.md)
frontend/   Frontend app (owned by the frontend teammate, their choice of framework)
ml/         Graph-based detection: preprocessing, pattern detection, evaluation
docs/       API contract shared between backend and frontend
```

## Team split

- **Person A (ML/graph + backend):** builds detection logic in `ml/`
  (cycle detection, scatter-gather detection, risk scoring) and wires it
  into `backend/app/routes.py`, replacing the mock data reads.
- **Person B (frontend):** builds the UI in `frontend/` against the
  contract in [docs/api-contract.md](docs/api-contract.md). Can build
  entirely independently — no need to wait on the backend.

## Running the backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Serves at `http://localhost:8000`, currently backed by
`backend/mock_data/cases_mock.json`.

## Frontend

Point the frontend at `http://localhost:8000` once the backend is
running, or skip the backend entirely for standalone dev by reading
`backend/mock_data/cases_mock.json` directly — its shape matches the API
responses documented in [docs/api-contract.md](docs/api-contract.md).
