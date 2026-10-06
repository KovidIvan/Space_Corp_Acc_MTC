# STATUS (update at the end of every work session)

Last sync: Bootstrap skeleton created and locally validated (2026-10-06)

## Bootstrap snapshot
- Created the `app/` package skeleton, core helpers, SQLAlchemy models, interfaces/fakes, contract models, API router placeholders, and FastAPI `/health` shell.
- Added tests for core helpers, contract samples/null parity, ORM table registration, redirect guard, and the health endpoint; latest `python -m pytest -q`: 29 passed.
- `python -m pip install -e ".[dev]"` succeeded; Ruff passed; local Uvicorn `/health` returned `{"status":"ok"}`. `make` is unavailable in this PowerShell environment.
- Product requirements remain unchecked; no call, dashboard, consent, or Telegram workflows were implemented. HTMX has not been vendored yet.

## Task board
Dev A: [ ] A1 bench  [ ] A2 VAD+STT  [ ] A3 TTS+cache  [ ] A4 NLU+dialog  [ ] A5 WS session+caller page  [ ] A6 router+handoff+summary  [ ] A7 eval  [ ] A8 chat offer / extras
Dev B: [x] B1 core+security  [ ] B2 dashboard shell  [ ] B3 wizard+config+consent  [ ] B4 Telegram  [ ] B5 ingest+notify  [ ] B6 editing+audit  [ ] B7 editors  [ ] B8 stats+settings+offline test

## Requirements progress
P0: FR-01 [ ] FR-02 [ ] FR-03 [ ] FR-04 [ ] FR-05 [ ] FR-06 [ ] FR-07 [ ] FR-08 [ ] FR-09 [ ] FR-10 [ ] FR-11 [ ] FR-12 [ ] FR-13 [ ] FR-14
P1: FR-15 [ ] FR-16 [ ] FR-17 [ ] FR-18 [ ] FR-19 [ ] FR-20 [ ] FR-21
P2: FR-22 [ ] FR-23 [ ] FR-24 [ ] FR-25 [ ] FR-26 [ ] FR-27

## Chosen profile and measured numbers
(filled by A1: PROFILE, whisper size, LLM model, TTS, latency p50)

## Requests between developers
(format: from -> to: what is needed, why, date)
- Dev B -> Dev A: Bootstrap added docstring-only stubs under `app/voice/` and `app/agent/` per user-approved exception; confirm handoff before feature implementation, 2026-10-06.

## Blocked / risks
- The installed Starlette TestClient emits a deprecation warning about httpx; tests pass. `make` command itself is unavailable, so equivalent Python module commands were used.
- Local `safe_http` guard denies automatic redirects; its mocked redirect test passes.
