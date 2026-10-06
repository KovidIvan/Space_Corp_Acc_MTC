# STATUS (update at the end of every work session)

Last sync: Dev A (A2, A3, A4, router part of A6) and Dev B (B1–B6) implemented and locally validated (2026-10-06). Approaching Sync Point S1.

## Current implementation snapshot
- Dev B completed B1–B5:
  - B1: Core configuration, safe_http outbound allowlist (localhost and api.telegram.org), PII log mask filter, Fernet encryption at rest, SHA-256 tamper-evident audit hash chain, and SQLAlchemy models.
  - B2: Russian Jinja2 dashboard shell, signed owner authentication, call list with filters (urgency, intent, handled), call detail with decrypted content, vendored local HTMX, and 5 synthetic encrypted demo calls.
  - B3: Five-step business setup wizard with persisted elapsed duration (`WizardRun`), `AgentConfig` versioned CRUD with audited current-version rollback, HMAC-hashed VIP numbers, consent capture and text versioning, and consent guard on `/ws/call`.
  - B4: Telegram owner deep link (one-time, 10-minute token stored as SHA-256 hash), masked Telegram notices through `safe_http`, and linked-chat-only, audited "mark handled" callback. SafeHttpClient-backed Bot API polling managed by FastAPI lifespan.
  - B5: Loopback-only `POST /api/calls/ingest`; CallResults are validated against schema, encrypted, and audited before B4 `Channel.notify()` is triggered. Duplicate call IDs are idempotent; `no_record` calls retain only encrypted callback numbers.
- Dev B completed B6: authenticated call editing for transcript segments, summary, and classification; private fields remain encrypted, edited calls are marked, and edits are audited without copying private content into audit details. `no_record` calls cannot be edited.
- Dev A completed A2, A3, A4, download script, and A6 router:
  - A2: `app/voice/vad.py` (Silero VAD wrapper, `VADSegmenter` with 700 ms silence detection) and `app/voice/stt.py` (`FasterWhisperSTT` adapter using CTranslate2 int8 local model, returning word probabilities).
  - A3: `app/voice/tts.py` (`LocalTTS` adapter supporting Piper/Silero and silent PCM fallback) and `app/voice/phrases_cache.py` (`PhrasesCache` pre-rendering greeting, disclosure, and fixed phrases for zero initial latency).
  - `scripts/download_models.py`: Offline model downloader downloading faster-whisper and Silero VAD into `models/` for `make setup-voice`.
  - A4: `app/agent/llm_client.py` (`OllamaLLM` adapter using `SafeHttpClient` restricted to localhost), `prompts/nlu.ru.md` (Russian prompt for structured JSON extraction), `app/agent/nlu.py` (`understand_turn` with Ollama structured extraction and `rules_nlu` keyword fallback), and `app/agent/dialog.py` (`DialogSession` state machine, slot merging, re-ask limit <= 2, turn limit <= 8, polite closing).
  - A6 (partial): `app/agent/router.py` evaluating ordered `RoutingRule` priority (FR-05) and emergency handoff on `wants_human` / VIP (FR-06). `app/agent/summarizer.py` and `prompts/summary.ru.md` remain pending.
- Current test suite: **116 passed** (`python -m pytest -q`), 1 upstream Starlette/httpx deprecation warning.
- `python -m compileall -q app tests`: passed.
- `python -m ruff check app tests`: 12 lint errors detected in newly added Dev A modules (formatting/imports/exceptions).
- `make` remains unavailable in this Windows PowerShell environment; Python module commands (`python -m ...`) are used.

## Task board
Dev A: [ ] A1 bench  [x] A2 VAD+STT  [x] A3 TTS+cache  [x] A4 NLU+dialog  [ ] A5 WS session+caller page  [ ] A6 router+handoff+summary (router done, summarizer pending)  [ ] A7 eval  [ ] A8 chat offer / extras
Dev B: [x] B1 core+security  [x] B2 dashboard shell  [x] B3 wizard+config+consent  [x] B4 Telegram  [x] B5 ingest+notify  [x] B6 editing+audit  [ ] B7 editors  [ ] B8 stats+settings+offline test

## Requirements progress
P0: FR-01 [ ] FR-02 [ ] FR-03 [ ] FR-04 [x] FR-05 [x] FR-06 [x] FR-07 [x] FR-08 [ ] FR-09 [ ] FR-10 [x] FR-11 [ ] FR-12 [x] FR-13 [x] FR-14 [x]
P1: FR-15 [ ] FR-16 [ ] FR-17 [ ] FR-18 [ ] FR-19 [ ] FR-20 [x] FR-21 [ ]
P2: FR-22 [ ] FR-23 [ ] FR-24 [ ] FR-25 [ ] FR-26 [ ] FR-27 [ ]

## Chosen profile and measured numbers
(filled by A1: PROFILE, whisper size, LLM model, TTS, latency p50 - awaiting `scripts/bench.py`)

## Requests between developers
(format: from -> to: what is needed, why, date)
- [RESOLVED] Dev B -> Dev A: Implement `scripts/download_models.py`; `make setup-voice` invokes it, 2026-10-06. (Resolved by Dev A in 22:31 commit).
- [RESOLVED] Dev B -> Dev A: Stubs under `app/voice/` and `app/agent/` replaced with implementations for VAD, STT, TTS, phrases cache, NLU, dialog, and router, 2026-10-06.
- Dev B -> Dev A: Wire `/ws/call` WebSocket session (`app/voice/session.py`, `app/voice/protocol.py`, `app/voice/client/`) and connect CallResult output to `POST /api/calls/ingest` to complete Sync Point S1 (vertical slice), 2026-10-06.
- Dev B -> Dev A: Implement `app/agent/summarizer.py` and `prompts/summary.ru.md` so that CallResult has an accurate Russian summary before ingestion, 2026-10-06.
- Dev B -> Dev A: Implement `scripts/bench.py` (A1) to benchmark Whisper/Ollama/TTS latency and record the chosen PROFILE in `docs/DECISIONS.md`, 2026-10-06.
- Dev A -> Dev B / Dev A: Clean up 12 ruff lint issues in `app/agent/` and `app/voice/` modules, 2026-10-06.

## Blocked / risks
- Sync Point S1 is blocked on A5: `app/voice/session.py`, `app/voice/protocol.py`, and `app/voice/client/` are stubs. `/ws/call` rejects actual voice sessions with code 1013 until session wiring is implemented.
- `app/agent/summarizer.py` is a stub; completed calls need a summary to populate `CallResult.summary_ru` before ingestion.
- `scripts/bench.py` (A1) has not been run; hardware profile is not formally calibrated.
- Telegram adapter was verified against mocked Bot API responses; live bot token and delivery in a real test call are pending.
- `make` is unavailable on Windows PowerShell; documentation and scripts should use `python -m` commands where appropriate.
- 12 ruff lint errors in `app/agent/` and `app/voice/` need fixing to keep codebase clean.
