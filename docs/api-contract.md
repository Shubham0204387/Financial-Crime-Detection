# API Contract

This is the contract between backend and frontend for the hackathon. Backend
currently serves all responses from `backend/mock_data/cases_mock.json` —
no real detection logic runs yet. The shapes below are final; only the data
source changes when ML/graph detection lands.

Base URL (local dev): `http://localhost:8000`

Frontend devs: you can build against this contract using
`backend/mock_data/cases_mock.json` directly, without running the backend
at all. The JSON file's `cases` array matches the list returned by
`GET /cases` (minus fields specific to detail view), and each entry under
`case_details` matches `GET /cases/{case_id}`.

---

## GET /cases

Returns the list of all cases, summary view.

**Response** `200 OK`

```json
[
  {
    "case_id": "string",
    "risk_tier": "monitor" | "review" | "str_ready",
    "risk_score": 0-100,
    "account_count": "integer",
    "flagged_at": "ISO8601 timestamp"
  }
]
```

---

## GET /cases/{case_id}

Returns full detail for one case, including the transaction graph.

**Response** `200 OK`

```json
{
  "case_id": "string",
  "risk_tier": "monitor" | "review" | "str_ready",
  "risk_score": 0-100,
  "sub_scores": {
    "velocity": 0-100,
    "fan_ratio": 0-100,
    "cycle_match": 0-100
  },
  "pattern_type": "cycle" | "scatter_gather" | "unclassified",
  "nodes": [
    { "id": "string", "label": "string" }
  ],
  "edges": [
    { "source": "string", "target": "string", "amount": "number", "timestamp": "ISO8601 timestamp" }
  ],
  "evidence_text": "string",
  "str_deadline": "ISO8601 timestamp"
}
```

**Response** `404 Not Found` if `case_id` does not exist.

---

## POST /cases/{case_id}/escalate

Records an analyst decision on a case.

**Request body**

```json
{ "decision": "confirm" | "dismiss" }
```

**Response** `200 OK`

```json
{ "case_id": "string", "status": "string" }
```

**Response** `404 Not Found` if `case_id` does not exist.

---

## GET /metrics

Returns model performance metrics: the naive/rule-based baseline vs. the
current candidate detection model.

**Response** `200 OK`

```json
{
  "baseline": { "precision": 0-1, "recall": 0-1, "f1": 0-1 },
  "candidate": { "precision": 0-1, "recall": 0-1, "f1": 0-1 }
}
```
