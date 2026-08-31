# cases_mock.json — demo-day fallback

This file is a deliberate fallback, not dead code left over from before
the real `ml/` pipeline existed.

Since `feat/backend-real-api`, the backend runs the full pipeline
(`ml.pipeline.run_full_pipeline()`) once at startup and serves real
computed cases from it. `backend/app/main.py`'s startup handler wraps
that call in a try/except: if it raises for any reason (most likely the
gitignored dataset files under `ml/data/` aren't present on whatever
machine you're demoing from, or the cached graph is missing/corrupt and
rebuilding fails), the server logs the error and falls back to serving
this file's contents instead of crashing.

This exists specifically as live-demo risk mitigation: if the real
pipeline breaks in front of an audience, the API still comes up and
returns plausible, well-formed data rather than a 500 or a dead server.

## Keeping it in sync

This file's shape must keep matching `docs/api-contract.md` exactly
(same as the real pipeline's output does), since the frontend can't tell
which source is currently backing a response. It does NOT need to match
the real pipeline's actual numbers -- it's a demo fallback, not a golden
test fixture.

## Forcing the fallback deliberately

To test the fallback path (or to intentionally demo off mock data), rename
or temporarily move `ml/data/HI-Small_Trans.csv` so `run_full_pipeline()`
fails at startup, then start the server as usual. Check `GET /` --
`data_source` in the response tells you which path served the currently
running instance ("pipeline" or "mock").
