# AGENTS.md: project context for every AI assistant (Claude, Gemini, DeepSeek, Antigravity)

This file is the single source of truth. Tool-specific files (CLAUDE.md, GEMINI.md) only point here.

## What we are building
A local, Russian-speaking AI assistant that answers incoming calls for Ivan Petrov (42, owner of a small IT company). He is in meetings and on the road all day, cannot answer unknown numbers, but any of them may be a client or partner.
Ivan's goals: miss no important call; spend little time sorting calls; every caller is treated professionally.

Hackathon: Space CorpAcc with MTS, Track 1 (CJM 1). Judges look, in this order:
1. Does the prototype solve Ivan's problem end to end?
2. Are all mandatory ToR items closed (setup <= 5 min, voice-or-chat routing, trustworthy transcription, control UI, confidentiality)?
3. Only then: scaling (operator integration, billing, monetization, compliance awareness).
A working prototype beats slides. Team: 2 developers (Dev A: voice and agent, Dev B: platform and UX). Duration: 2 days.

## Hard rules
1. Runtime is local. No call audio, transcripts or summaries leave the machine. The only external host allowed at runtime is api.telegram.org, and only for masked notices. All outgoing HTTP goes through `app/core/safe_http.py` (allowlist).
2. Cloud AIs (you included) may see only synthetic data from `fixtures/`. Never put real recordings, phone numbers or names into any chat or prompt.
3. `contracts/` is frozen after sync S0. Change it only with both devs agreeing and an entry in `docs/DECISIONS.md`.
4. Stay inside your directories (ownership below). Need a change elsewhere? Add it to `docs/STATUS.md` under "Requests". Do not edit it yourself.
5. No PII in logs. Use the mask filter in `app/core/logging.py`.
6. User-facing text is Russian. Code, comments, docs are English.
7. Scope discipline: P0 before P1 before P2 (see `docs/REQUIREMENTS.md`). No feature outside the requirements without a DECISIONS entry.
8. Never fabricate results. If something was not run or tested, say so in the handoff note.

## Stack
Python 3.11+, FastAPI, Jinja2 + HTMX, SQLAlchemy 2 + SQLite, pydantic v2, aiogram 3, faster-whisper, silero-vad, Piper or Silero TTS, Ollama for the local LLM, pytest, ruff.

## Commands (or run the underlying `python -m` command if `make` is unavailable)
`make setup` | `make setup-voice` | `make run` | `make test` | `make eval` | `make bench` | `make context`

## Ownership
- Dev A: `app/voice/` (incl. `app/voice/client/` caller page), `app/agent/`, `prompts/`, `fixtures/`, `scripts/bench.py`, `scripts/eval.py`
- Dev B: `app/web/`, `app/api/`, `app/channels/`, `app/core/`, `app/models.py`, `docs/COMPLIANCE.md`
- Shared (announce before editing): `contracts/`, `docs/`, `pyproject.toml`, `app/interfaces.py`, `app/schemas.py`

## Session protocol
Start: read AGENTS.md, then `docs/STATUS.md`, then the last 2 files in `docs/handoff/`, then the parts of REQUIREMENTS and ARCHITECTURE you are working on.
End: update `docs/STATUS.md` (done / in progress / blocked / requests), write `docs/handoff/<dev>-<YYYYMMDD-HHMM>.md` (changed, decisions, open questions, next steps, what was NOT tested), commit and push.

## Code conventions
Type hints; pydantic models at boundaries; async I/O; small modules; docstrings on public functions; unit tests for pure logic (router, masking, audit chain, NLU parsing). Configuration only through `app/core/config.py`. No hard-coded paths or secrets.
