# Backend

FastAPI service serving the case/detection API. Currently returns mock
data from `mock_data/cases_mock.json` — see [docs/api-contract.md](../docs/api-contract.md)
for the full contract.

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Server starts at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

## Endpoints

- `GET /cases`
- `GET /cases/{case_id}`
- `POST /cases/{case_id}/escalate`
- `GET /metrics`
