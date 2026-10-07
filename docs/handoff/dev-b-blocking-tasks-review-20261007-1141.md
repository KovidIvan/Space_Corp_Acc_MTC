# Dev B Review Report for Dev A — 2026-10-07 11:41

## Summary
Reviewed `docs/handoff/devB-handoff-blocking-tasks.md` against the current workspace. The WebSocket dispatcher and runtime PII masking are implemented; the schema-nullability suggestion conflicts with the frozen contract and must be handled at the CallResult producer; Dev A's Ruff findings and voice-runtime gaps remain open.

## Blocker review

### 1. `/ws/call` → `CallSession`: implemented; runtime E2E still unverified
- `app/api/ws.py` retains the dashboard configuration, consent, and AgentConfig checks.
- After accepting the socket, it constructs `CallSession(websocket)` and awaits `session.run()`; it no longer closes every valid call with 1013.
- `tests/test_wizard.py` verifies dispatch after consent/config using a mocked `CallSession.run`; the full suite passes.
- No browser-driven greeting/audio test or unmocked call-session integration test was run. `tests/test_voice_session.py` is absent.

### 2. Runtime PII masking: implemented and tested
- `app/core/logging.py` exposes idempotent `install_pii_mask_filter()`, attaching `PiiMaskFilter` to configured root/named logger handlers and `logging.lastResort` without reconfiguring handlers with `basicConfig`.
- `app/main.py:create_app()` installs it during application creation.
- `tests/test_app.py` verifies a real stream handler masks synthetic phone, email, and long digit data.

### 3. `Caller.hash`: handoff instruction conflicts with the frozen contract
- `contracts/call_result.schema.json` declares `caller.hash` optional, with type `string`; explicit `null` is invalid.
- `tests/test_schemas.py::test_optional_nonnullable_fields_reject_null` enforces this.
- I temporarily tried `hash: str | None = None`; the full suite then failed that contract test. The schema change and a null-ingestion test were reverted. Current full pytest passes with the contract-compatible schema.

**Request to Dev A:** Keep the contract strict. In `app/voice/session.py`, do not pass `hash=None` when constructing `Caller`; omit the field when there is no hash. Serialize the `CallResult` using `model_dump(mode="json", exclude_none=True)` so optional fields with `None` are absent rather than emitted as JSON null. Add a regression test proving the resulting payload validates against both `CallResult` and the frozen JSON Schema when no hash is available.

### 4. Ruff violations: still open in Dev A-owned files
- Full `python -m ruff check app tests` reports **33 findings**.
- Targeted Ruff on `app/agent/router.py` and `tests/test_agent.py` confirms five findings remain:
  - `app/agent/router.py`: `UP035` (`Sequence` import), `SIM103`, `SIM102`.
  - `tests/test_agent.py`: `I001` import order and `F401` unused `Slots` import.
- Dev B did not edit Dev A-owned files. Ruff passes for the Dev B modules checked after this work.

**Request to Dev A:** Resolve the five findings above and run full Ruff; the expected final result for the handoff checklist is zero findings across `app tests`.

## Additional runtime gap relevant to B7 / FR-16
`app/voice/session.py` currently passes `outside_hours=False` in both `_process_utterance()` and `_handle_test_audio()`. As a result, saved working hours and routing rules conditioned on `outside_hours` cannot affect call routing.

**Request to Dev A:** Compute `outside_hours` from the active `AgentConfig.working_hours` (configured timezone, ISO weekday, and start/end times) and pass it to `route()` in both paths. Add tests for inside/outside hours, including a timezone boundary; verify an edited working-hours config changes the next call's selected action.

## Scenario/cache integration note
`CallSession` loads the latest AgentConfig at call start and creates/preloads its `PhrasesCache` for that session. This should refresh phrase audio for the next new call after a config edit, but no test currently proves it.

**Request to Dev A:** Add a session regression test that saves/loads a changed greeting and disclosure, then verifies the next session uses the updated text/audio. If the product requires regeneration immediately on save rather than on the next call, coordinate a config-save hook with Dev B before adding shared lifecycle behavior.

## Verification performed
- `python -m pytest -q`: **121 passed**, 1 upstream Starlette/httpx deprecation warning.
- `python -m compileall -q app tests`: passed.
- Ruff on Dev B scope: passed.
- Full Ruff: 33 findings; targeted Dev A files: 5 findings above.

## Not tested
- Real browser microphone/audio end-to-end flow.
- Real STT/TTS/LLM model operation or latency.
- Live Telegram delivery; no real bot token was used.
- Audio-cache behavior after editing a scenario in a live call.
