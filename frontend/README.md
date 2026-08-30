# Frontend

React + Vite frontend for Financial Crime Detection.

## Run

```
npm install
npm run dev
```

## Data source

This currently points at static mock data in [public/mock/cases.json](public/mock/cases.json)
(a copy of `backend/mock_data/cases_mock.json`) instead of a live backend — see
[src/api/cases.js](src/api/cases.js).

To swap to the real API once the backend is ready, set `VITE_API_BASE_URL` in a
`.env` file (e.g. `VITE_API_BASE_URL=http://localhost:8000`) and update
`fetchCases` in `src/api/cases.js` to fetch from `` `${API_BASE_URL}/cases` ``
instead of the mock file. `API_BASE_URL` is already exported from
[src/config.js](src/config.js) for this purpose — the response shape matches
`GET /cases` per [docs/api-contract.md](../docs/api-contract.md), so no other
code should need to change.
