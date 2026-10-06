# Prompts for Antigravity (and any other coding AI)

Open the repository folder as the workspace so the agent can read the context files. If your IDE supports a rules or instructions file, point it to `AGENTS.md` (GEMINI.md already does). Paste one prompt at a time.

## Prompt 0: bootstrap (run once, on one machine)

```
You are the lead engineer bootstrapping a 2-day hackathon project: a local, Russian-speaking AI assistant that answers incoming phone calls for a business owner (Ivan Petrov) and reports to him via Telegram and a dashboard.

Read these files fully, in this order, before doing anything: AGENTS.md, docs/REQUIREMENTS.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, contracts/ws_protocol.md, contracts/*.schema.json, docs/WORK_PLAN.md, docs/STATUS.md.

TASK: create the project skeleton only. Stubs and tests, no feature logic beyond what is listed.
1. Package `app/` with the layout from ARCHITECTURE.md section 2 (empty modules with docstrings are fine).
2. Use the provided pyproject.toml, Makefile, .env.example, .gitignore. Extend only if needed; keep heavy ML packages in the optional extra `voice`; do not install them in this step.
3. app/core: config.py (pydantic-settings, PROFILE and the settings from ARCHITECTURE section 7), logging.py (PII mask filter for phones, emails, long digit runs, with tests), safe_http.py (allowlist of localhost and api.telegram.org, with tests), security.py (Fernet helpers, password hashing), audit.py (SHA-256 hash chain with a verify function, with tests), db.py and app/models.py (data model from ARCHITECTURE section 5).
4. app/interfaces.py with the Protocols STT, TTS, LLM, Channel, Telephony and Fake* implementations for tests.
5. app/schemas.py: pydantic v2 models mirroring contracts/*.schema.json, plus a test that sample objects validate against the JSON schemas.
6. app/main.py: FastAPI app with /health, static and templates mounted, empty routers for the modules in app/api.
7. tests that pass with `make test`.

RULES: follow AGENTS.md hard rules. Do not touch contracts/ or docs/ except docs/STATUS.md and docs/handoff/. No network calls other than package installation. Do not invent features. If a document is ambiguous or contradicts another, list it instead of guessing silently.

DONE WHEN: `make setup && make test` passes, `make run` serves /health, the work is committed, docs/STATUS.md is updated and a handoff note is written to docs/handoff/. Finish by printing a short summary, what you did NOT verify, and the list of ambiguities.
```

## Prompt A: Dev A kickoff (voice and agent)

```
You are working as Dev A (voice and agent) on this project. Start with the session protocol in AGENTS.md. You may edit only the directories owned by Dev A.

Today's tasks, in order (see docs/WORK_PLAN.md for details and docs/REQUIREMENTS.md for ids):
1. A1: write scripts/bench.py that measures, on this machine, faster-whisper (small, medium), the configured Ollama model (JSON output time for a typical NLU prompt), and the TTS options (time to first audio for a 10-word phrase). Print a table and recommend PROFILE. Run only with synthetic text and audio.
2. A2: app/voice/vad.py and stt.py: silero-vad endpointing (about 700 ms silence), faster-whisper transcription per utterance with word probabilities, a Transcript type; test with wav files from fixtures/.
3. A3: app/voice/tts.py and phrases_cache.py: TTS behind the interface, 16 kHz PCM16 output, pre-rendered cache for greeting, disclosure and fixed phrases.
4. Create `scripts/download_models.py`, called by `make setup-voice`, to download the `PROFILE`-selected Whisper, TTS, and other required voice model assets into `models/` for offline use after setup. Downloads must happen only when this setup command is explicitly run; runtime inference stays local.
Keep every component behind the interfaces in app/interfaces.py and cover pure logic with unit tests. Do not change contracts/. Put anything you need from Dev B in docs/STATUS.md under Requests.
At the end: update STATUS.md, write the handoff note, and state clearly what was not run or tested.
```

## Prompt B: Dev B kickoff (platform and UX)

```
You are working as Dev B (platform and UX) on this project. Start with the session protocol in AGENTS.md. You may edit only the directories owned by Dev B.

Today's tasks, in order (see docs/WORK_PLAN.md for details and docs/REQUIREMENTS.md for ids):
1. B1: finish and harden app/core (config, security, audit chain with a verify command, safe_http, log masking) so that FR-13 and FR-14 tests pass.
2. B2: dashboard shell with Jinja2 + HTMX (vendor htmx into app/web/static, no CDN): login, call list with filters, call detail with transcript and summary. Seed the database with 5 fake CallResults from fixtures so the UI works without the voice side. All user-facing text in Russian.
3. B3: setup wizard (5 steps from FR-11) with a visible timer stored in wizard_run, AgentConfig save as per contracts/agent_config.schema.json, consent step that is enforced (FR-12).
Do not change contracts/. Needs from Dev A go to docs/STATUS.md under Requests.
At the end: update STATUS.md, write the handoff note, and state clearly what was not run or tested.
```

## Session start (any AI, any developer)

```
Read AGENTS.md, then docs/STATUS.md, then the last two files in docs/handoff/, then the parts of docs/REQUIREMENTS.md and docs/ARCHITECTURE.md relevant to this task. Confirm in two sentences what you understood and which requirement ids you will work on. Do not start coding before that.
```

## Session end (any AI, any developer)

```
Update docs/STATUS.md (task board, requirement checkboxes, requests, blockers). Write docs/handoff/<dev>-<YYYYMMDD-HHMM>.md with: what changed, decisions made (also add to docs/DECISIONS.md if they affect the other developer), open questions, next steps, and what was NOT run or tested. Run make test and report the result honestly. Commit.
```

## Cross-review (ask a second AI, for example Gemini after Claude)

```
Review the latest diff against docs/REQUIREMENTS.md and AGENTS.md hard rules. List: violations of the rules (especially data leaving the machine or PII in logs), requirement ids that are claimed but not actually satisfied, missing tests for pure logic, and anything that conflicts with contracts/. Do not rewrite code; output a prioritized list with file paths.
```

## Using DeepSeek or a chat-only AI
Run `make context` (or `python -m scripts.make_context --lite`) and paste the generated `context_bundle.txt` as the first message. Use the same session start and end prompts. Paste its code output back into the repository yourself and run `make test`.
