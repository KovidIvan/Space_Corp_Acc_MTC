<<<<<<< HEAD
# Dev B Handoff — Blocking Tasks for Sync Point S1

**Sender:** Dev A  
**Date:** 2026-10-07  
**Context:** Code review completed. Five critical blockers identified. Dev A tests now pass (124/124). These tasks unlock FR-01, FR-02, FR-03, FR-04, FR-07, FR-08, FR-09, FR-13, FR-14 (all P0).

---

## CRITICAL BLOCKERS (must complete for S1)

### 1. Wire `CallSession` into `/ws/call` endpoint
**Why:** Currently endpoint accepts connection and immediately closes with code 1013. Browser caller page cannot start any call. Blocks FR-01 entirely.

**File:** `app/api/ws.py`

**Current code (lines 12–28):**
```python
@router.websocket("/call")
async def call(websocket: WebSocket) -> None:
	"""Reject call starts without current consent and report the unavailable voice pipeline."""
	if not websocket.app.state.settings.dashboard_configured:
		await websocket.close(code=1013, reason="Local dashboard is not configured")
		return

	with database.SessionLocal() as db_session:
		consent_exists = has_current_owner_consent(db_session)
		config_exists = db_session.scalar(select(AgentConfigRecord.id).limit(1)) is not None

	if not consent_exists or not config_exists:
		await websocket.close(code=1008, reason="Current consent and AgentConfig are required")
		return

	await websocket.accept()
	await websocket.close(code=1013, reason="Voice call processing is not available")
```

**What to do:**
- Keep checks for `dashboard_configured`, `consent_exists`, `config_exists`.
- After `await websocket.accept()` (line 25), replace lines 26–27 with:
  ```python
  from app.voice.session import CallSession
  session = CallSession(websocket)
  await session.run()
  ```
- Test: browser caller page should play greeting audio when `/ws/call` connects.

**Notes:**
- `CallSession.__init__` signature: `CallSession(websocket: WebSocket) -> None`
- `run()` method handles all dialogue, transcription, routing, and call completion.
- Session closes the WebSocket itself when finished (no need to close in handler).

---

### 2. Attach `PiiMaskFilter` to runtime logging handlers
**Why:** `PiiMaskFilter` exists in `app/core/logging.py` but is never attached. Runtime logs leak phone numbers, emails, and long digit runs. Violates AGENTS.md Hard Rule #5.

**File:** `app/main.py`

**Location:** In the `create_app()` function, after the `application = FastAPI(...)` line (around line 48).

**Add this code block:**
```python
# Attach PII mask filter to all logging handlers
import logging
from app.core.logging import PiiMaskFilter

pii_filter = PiiMaskFilter()
for handler in logging.root.handlers:
	handler.addFilter(pii_filter)
# Also secure the basicConfig for any future loggers
logging.basicConfig(handlers=[
	h for h in logging.root.handlers if isinstance(h, logging.StreamHandler)
])
for handler in logging.root.handlers:
	if not any(isinstance(f, PiiMaskFilter) for f in handler.filters):
		handler.addFilter(PiiMaskFilter())
```

**Test:**
- Start the app
- Run a test call (even a short one)
- Check logs: phone numbers should appear as `[PHONE]`, emails as `[EMAIL]`, digit runs as `[DIGITS]`

**Notes:**
- If the above approach doesn't catch all handlers, alternatively configure logging in `app/core/config.py` or a dedicated logging setup module.
- Critical: this must be done before any voice/agent loggers are created.

---

### 3. Fix Caller.hash schema validation (already started by Dev A)
**Why:** Pydantic v2 strict validation rejects `hash=None` even though field has default.

**File:** `app/schemas.py` line 78

**Current:**
```python
class Caller(ContractModel):
	masked: str
	hash: str = Field(default=None)
	is_vip: bool = Field(default=None)
```

**Should be:**
```python
class Caller(ContractModel):
	masked: str
	hash: str | None = None
	is_vip: bool = Field(default=None)
```

**Status:** Dev A likely already fixed this. Verify: run `python -m pytest -q` and check that `test_voice_session.py` passes.

---

### 4. Resolve 5 Ruff violations in router and test files (started by Dev A)
**Why:** Blocks workspace linting clean state. Violations in `app/agent/router.py` and `tests/test_agent.py`.

**Status:** Dev A likely ran `python -m ruff check app tests --fix`. Verify: run `python -m ruff check app tests` and confirm 0 findings.

---

## VERIFICATION CHECKLIST

After completing the above, run:

```bash
# 1. All tests pass
python -m pytest -q

# 2. No linting violations
python -m ruff check app tests

# 3. Python syntax OK
python -m compileall -q app tests
```

**Expected outcome:**
- 124 tests passing
- 0 ruff findings
- All Python files compilable

---

## END-TO-END TEST (after all blockers fixed)

1. Start the application (e.g., `python -m uvicorn app.main:app --reload`)
2. Open browser: http://localhost:8000/call
3. **Verify caller page loads** (should show "Звонок" title, start button, transcript area)
4. **Click "Начать звонок" (Start Call)**
5. **Verify greeting audio plays** (should hear: greeting + disclosure in Russian)
6. **Say something or skip** (page should show transcript bubbles, agent responses)
7. **End call** (should see notification about call completion)
8. **Check dashboard**: http://localhost:8000/dashboard
   - Login (owner credentials)
   - Call should appear in call list
   - Click call detail → transcript should be decrypted and visible
9. **Check Telegram** (if mock mode or real token configured): notice should arrive within 10 s

---

## WHAT WAS NOT TESTED (Dev A)

- Real WebSocket integration (stub endpoint prevented this)
- End-to-end audio streaming (microphone capture + agent response)
- Telegram notice delivery (route was never reached)
- Live LLM/STT/TTS latency (unit tests use mocks)
- Browser compatibility (only design/stub tested)

---

## OPEN QUESTIONS FOR DEV B

1. Should `CallSession` catch exceptions and return a graceful error message to the client, or let them propagate to the WebSocket close handler?
2. Is the logging setup in `app/main.py` the right place, or should it be in a separate `app/core/logging_config.py`?
3. For the end-to-end test: do we have a test Telegram bot token configured in `.env`? Should we use a mock adapter for CI/CD?

---

## NEXT STEPS AFTER S1

- A5 (full): complete A1 bench.py, A7 eval, A8 chat/extras
- B7: editors for scenario and routing rules
- B8: stats and settings pages
- Full compliance audit against requirements

---

## FILES TO CHANGE

| File | Lines | What | Owner |
|------|-------|------|-------|
| `app/api/ws.py` | 26–27 | Replace 1013 close with CallSession.run() | Dev B |
| `app/main.py` | ~48 | Add PiiMaskFilter attach code | Dev B |
| `app/schemas.py` | 78 | Change `hash: str = Field(default=None)` to `hash: str \| None = None` | Dev A (likely done) |
| `app/agent/router.py` + `tests/test_agent.py` | various | Resolve 5 Ruff violations | Dev A (likely done) |

---

**Estimated time for Dev B:** 1–2 hours (wire-up + testing)  
**Blockers to communicate back:** any issues with CallSession import, logging config, or test infrastructure  
**Success signal:** browser caller page works end-to-end and dashboard shows encrypted call data

=======
# Dev B Handoff — Blocking Tasks for Sync Point S1

**Sender:** Dev A  
**Date:** 2026-10-07  
**Context:** Code review completed. Five critical blockers identified. Dev A tests now pass (124/124). These tasks unlock FR-01, FR-02, FR-03, FR-04, FR-07, FR-08, FR-09, FR-13, FR-14 (all P0).

---

## CRITICAL BLOCKERS (must complete for S1)

### 1. Wire `CallSession` into `/ws/call` endpoint
**Why:** Currently endpoint accepts connection and immediately closes with code 1013. Browser caller page cannot start any call. Blocks FR-01 entirely.

**File:** `app/api/ws.py`

**Current code (lines 12–28):**
```python
@router.websocket("/call")
async def call(websocket: WebSocket) -> None:
	"""Reject call starts without current consent and report the unavailable voice pipeline."""
	if not websocket.app.state.settings.dashboard_configured:
		await websocket.close(code=1013, reason="Local dashboard is not configured")
		return

	with database.SessionLocal() as db_session:
		consent_exists = has_current_owner_consent(db_session)
		config_exists = db_session.scalar(select(AgentConfigRecord.id).limit(1)) is not None

	if not consent_exists or not config_exists:
		await websocket.close(code=1008, reason="Current consent and AgentConfig are required")
		return

	await websocket.accept()
	await websocket.close(code=1013, reason="Voice call processing is not available")
```

**What to do:**
- Keep checks for `dashboard_configured`, `consent_exists`, `config_exists`.
- After `await websocket.accept()` (line 25), replace lines 26–27 with:
  ```python
  from app.voice.session import CallSession
  session = CallSession(websocket)
  await session.run()
  ```
- Test: browser caller page should play greeting audio when `/ws/call` connects.

**Notes:**
- `CallSession.__init__` signature: `CallSession(websocket: WebSocket) -> None`
- `run()` method handles all dialogue, transcription, routing, and call completion.
- Session closes the WebSocket itself when finished (no need to close in handler).

---

### 2. Attach `PiiMaskFilter` to runtime logging handlers
**Why:** `PiiMaskFilter` exists in `app/core/logging.py` but is never attached. Runtime logs leak phone numbers, emails, and long digit runs. Violates AGENTS.md Hard Rule #5.

**File:** `app/main.py`

**Location:** In the `create_app()` function, after the `application = FastAPI(...)` line (around line 48).

**Add this code block:**
```python
# Attach PII mask filter to all logging handlers
import logging
from app.core.logging import PiiMaskFilter

pii_filter = PiiMaskFilter()
for handler in logging.root.handlers:
	handler.addFilter(pii_filter)
# Also secure the basicConfig for any future loggers
logging.basicConfig(handlers=[
	h for h in logging.root.handlers if isinstance(h, logging.StreamHandler)
])
for handler in logging.root.handlers:
	if not any(isinstance(f, PiiMaskFilter) for f in handler.filters):
		handler.addFilter(PiiMaskFilter())
```

**Test:**
- Start the app
- Run a test call (even a short one)
- Check logs: phone numbers should appear as `[PHONE]`, emails as `[EMAIL]`, digit runs as `[DIGITS]`

**Notes:**
- If the above approach doesn't catch all handlers, alternatively configure logging in `app/core/config.py` or a dedicated logging setup module.
- Critical: this must be done before any voice/agent loggers are created.

---

### 3. Fix Caller.hash schema validation (already started by Dev A)
**Why:** Pydantic v2 strict validation rejects `hash=None` even though field has default.

**File:** `app/schemas.py` line 78

**Current:**
```python
class Caller(ContractModel):
	masked: str
	hash: str = Field(default=None)
	is_vip: bool = Field(default=None)
```

**Should be:**
```python
class Caller(ContractModel):
	masked: str
	hash: str | None = None
	is_vip: bool = Field(default=None)
```

**Status:** Dev A likely already fixed this. Verify: run `python -m pytest -q` and check that `test_voice_session.py` passes.

---

### 4. Resolve 5 Ruff violations in router and test files (started by Dev A)
**Why:** Blocks workspace linting clean state. Violations in `app/agent/router.py` and `tests/test_agent.py`.

**Status:** Dev A likely ran `python -m ruff check app tests --fix`. Verify: run `python -m ruff check app tests` and confirm 0 findings.

---

## VERIFICATION CHECKLIST

After completing the above, run:

```bash
# 1. All tests pass
python -m pytest -q

# 2. No linting violations
python -m ruff check app tests

# 3. Python syntax OK
python -m compileall -q app tests
```

**Expected outcome:**
- 124 tests passing
- 0 ruff findings
- All Python files compilable

---

## END-TO-END TEST (after all blockers fixed)

1. Start the application (e.g., `python -m uvicorn app.main:app --reload`)
2. Open browser: http://localhost:8000/call
3. **Verify caller page loads** (should show "Звонок" title, start button, transcript area)
4. **Click "Начать звонок" (Start Call)**
5. **Verify greeting audio plays** (should hear: greeting + disclosure in Russian)
6. **Say something or skip** (page should show transcript bubbles, agent responses)
7. **End call** (should see notification about call completion)
8. **Check dashboard**: http://localhost:8000/dashboard
   - Login (owner credentials)
   - Call should appear in call list
   - Click call detail → transcript should be decrypted and visible
9. **Check Telegram** (if mock mode or real token configured): notice should arrive within 10 s

---

## WHAT WAS NOT TESTED (Dev A)

- Real WebSocket integration (stub endpoint prevented this)
- End-to-end audio streaming (microphone capture + agent response)
- Telegram notice delivery (route was never reached)
- Live LLM/STT/TTS latency (unit tests use mocks)
- Browser compatibility (only design/stub tested)

---

## OPEN QUESTIONS FOR DEV B

1. Should `CallSession` catch exceptions and return a graceful error message to the client, or let them propagate to the WebSocket close handler?
2. Is the logging setup in `app/main.py` the right place, or should it be in a separate `app/core/logging_config.py`?
3. For the end-to-end test: do we have a test Telegram bot token configured in `.env`? Should we use a mock adapter for CI/CD?

---

## NEXT STEPS AFTER S1

- A5 (full): complete A1 bench.py, A7 eval, A8 chat/extras
- B7: editors for scenario and routing rules
- B8: stats and settings pages
- Full compliance audit against requirements

---

## FILES TO CHANGE

| File | Lines | What | Owner |
|------|-------|------|-------|
| `app/api/ws.py` | 26–27 | Replace 1013 close with CallSession.run() | Dev B |
| `app/main.py` | ~48 | Add PiiMaskFilter attach code | Dev B |
| `app/schemas.py` | 78 | Change `hash: str = Field(default=None)` to `hash: str \| None = None` | Dev A (likely done) |
| `app/agent/router.py` + `tests/test_agent.py` | various | Resolve 5 Ruff violations | Dev A (likely done) |

---

**Estimated time for Dev B:** 1–2 hours (wire-up + testing)  
**Blockers to communicate back:** any issues with CallSession import, logging config, or test infrastructure  
**Success signal:** browser caller page works end-to-end and dashboard shows encrypted call data

>>>>>>> 34da9783c58be4a772b28c0903a9f8be978ea23a
