# STATUS (update at the end of every work session)

Last sync: Dev B B5 CallResult ingest/notification trigger implemented and locally validated (2026-10-06)

## Current implementation snapshot
- Dev B B2 adds a Russian Jinja2 dashboard, signed owner login, call filters/detail, locally vendored HTMX, and five synthetic encrypted demo calls.
- Dev B B3 adds a five-step setup wizard with persisted duration, AgentConfig GET/POST/PUT and audited current-version rollback, HMAC-hashed VIP numbers, consent capture/versioning, and a consent/config guard on `/ws/call`.
- Dev B B4 adds a one-time, 10-minute Telegram owner deep link (only its hash is stored), masked Telegram notices through `safe_http`, and a linked-chat-only, audited “mark handled” callback. The adapter uses SafeHttpClient-backed Bot API polling and is managed by the FastAPI lifespan.
- Dev B B5 adds loopback-only `POST /api/calls/ingest`; CallResults are validated, encrypted and audited before B4 `Channel.notify()` is invoked. Duplicate IDs are idempotent; `no_record` calls retain only an encrypted callback number when present.
- Dashboard bootstrap settings are documented in `.env.example`; the owner account is created only when dashboard settings are complete and is not overwritten on later starts.
- Both Prompt A copies request `scripts/download_models.py` for explicit setup-time voice model downloads; the script is still pending.
- `python -m compileall -q app tests` passed; `python -m pytest -q`: 48 passed (one upstream Starlette/httpx deprecation warning); `python -m ruff check app tests`: passed.
- `git -c core.whitespace=cr-at-eol diff --check` passed. `make` remains unavailable in this PowerShell environment.
- FR-11 remains open until Telegram is verified with a configured live bot and the actual test call is available from Dev A. FR-08 implementation is present but its demo-arrival criterion has not been live-tested. FR-09 remains unchecked because call editing is pending B6.

## Task board
Dev A: [ ] A1 bench  [ ] A2 VAD+STT  [ ] A3 TTS+cache  [ ] A4 NLU+dialog  [ ] A5 WS session+caller page  [ ] A6 router+handoff+summary  [ ] A7 eval  [ ] A8 chat offer / extras
Dev B: [x] B1 core+security  [x] B2 dashboard shell  [x] B3 wizard+config+consent  [x] B4 Telegram  [x] B5 ingest+notify  [ ] B6 editing+audit  [ ] B7 editors  [ ] B8 stats+settings+offline test

## Requirements progress
P0: FR-01 [ ] FR-02 [ ] FR-03 [ ] FR-04 [ ] FR-05 [ ] FR-06 [ ] FR-07 [x] FR-08 [ ] FR-09 [ ] FR-10 [ ] FR-11 [ ] FR-12 [x] FR-13 [ ] FR-14 [ ]
P1: FR-15 [ ] FR-16 [ ] FR-17 [ ] FR-18 [ ] FR-19 [ ] FR-20 [x] FR-21 [ ]
P2: FR-22 [ ] FR-23 [ ] FR-24 [ ] FR-25 [ ] FR-26 [ ] FR-27

## Chosen profile and measured numbers
(filled by A1: PROFILE, whisper size, LLM model, TTS, latency p50)

## Requests between developers
(format: from -> to: what is needed, why, date)
- Dev B -> Dev A: Bootstrap added docstring-only stubs under `app/voice/` and `app/agent/` per user-approved exception; confirm handoff before feature implementation, 2026-10-06.
- Dev B -> Dev A: Implement `scripts/download_models.py`; `make setup-voice` invokes it, and Prompt A now specifies profile-selected local voice model downloads, 2026-10-06.
- Dev B -> Dev A: `.env.example` now documents owner/session/encryption settings for B2; its five demo calls are synthetic and live in `app/core/demo_data.py` because `fixtures/` has no CallResult files, 2026-10-06.
- Dev B -> Dev A: `/ws/call` now rejects starts without current consent; with consent it returns 1013 until the voice pipeline is implemented. Please connect the call workflow here when ready, 2026-10-06.
- Dev B -> Dev A: Submit the completed, contract-shaped CallResult to local `POST /api/calls/ingest` after call completion. It accepts loopback requests without dashboard cookies, returns 201 for new and 200 for duplicate call IDs; B5 invokes B4 `Channel.notify()` after commit. For `no_record`, only `slots.callback_number` is retained, encrypted; transcript, summary and other slots are discarded. FR-17 offer_chat remains separate for A8 coordination, 2026-10-06.

## Blocked / risks
- The installed Starlette TestClient emits a deprecation warning about httpx; tests pass. `make` command itself is unavailable, so equivalent Python module commands were used.
- Local `safe_http` guard denies automatic redirects; its mocked redirect test passes.
- The caller page and voice WebSocket pipeline remain stubs; B3 only enforces consent at the call-start boundary. A real test-call is not yet available.
- Telegram behavior was verified with synthetic data and mocked Bot API responses only; live bot linking and delivery were not tested in this session.
- B5 ingestion and notification trigger are tested locally with a fake channel; the Dev A CallResult producer and end-to-end S1 flow are not yet connected. FR-08 remains unchecked until a live Telegram notice is confirmed. FR-21 storage handling is implemented, but S8 voice-path behavior still depends on Dev A.
- `make setup-voice` remains incomplete until `scripts/download_models.py` is added.
