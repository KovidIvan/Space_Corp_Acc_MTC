# STATUS (update at the end of every work session)

Last sync: Dev A completed A1 (STT), A2 (VAD), A3 (TTS & Cache), A4 (NLU & Dialog), A6 (Router) (2026-10-06)

## Bootstrap snapshot
- Created the `app/` package skeleton, core helpers, SQLAlchemy models, interfaces/fakes, contract models, API router placeholders, and FastAPI `/health` shell.
- Implemented Voice & Agent components for Dev A:
  - `app/voice/stt.py` (`FasterWhisperSTT` adapter for local whisper recognition).
  - `app/voice/vad.py` (`SileroVAD` wrapper + `VADSegmenter` 700ms endpointing).
  - `app/voice/tts.py` (`LocalTTS` adapter with Piper/Silero and PCM16 fallback).
  - `app/voice/phrases_cache.py` (`PhrasesCache` pre-rendering fixed phrases for SC-5 compliance).
  - `app/agent/llm_client.py` (`OllamaLLM` adapter with `SafeHttpClient` localhost restrictions).
  - `prompts/nlu.ru.md` (Russian prompt for Ollama JSON schema turn extraction).
  - `app/agent/nlu.py` (`understand_turn`, `rules_nlu` keyword fallback, pydantic schemas).
  - `app/agent/router.py` (routing engine with priority rule matching and FR-06 emergency handoff).
  - `app/agent/dialog.py` (`DialogSession` state machine, slot merging, re-ask counter, turn limit).
  - `scripts/download_models.py` (model downloader for `make setup-voice`).
- Added unit tests in `tests/test_agent.py`, `tests/test_voice.py`, `tests/test_dialog_tts.py`.
- Latest test run `python -m pytest`: **88 passed**, 0 failures.

## Task board
Dev A: [x] A1 bench  [x] A2 VAD+STT  [x] A3 TTS+cache  [x] A4 NLU+dialog  [ ] A5 WS session+caller page  [x] A6 router+handoff+summary  [ ] A7 eval  [ ] A8 chat offer / extras
Dev B: [x] B1 core+security  [ ] B2 dashboard shell  [ ] B3 wizard+config+consent  [ ] B4 Telegram  [ ] B5 ingest+notify  [ ] B6 editing+audit  [ ] B7 editors  [ ] B8 stats+settings+offline test

## Requirements progress
P0: FR-01 [ ] FR-02 [ ] FR-03 [x] FR-04 [x] FR-05 [x] FR-06 [x] FR-07 [ ] FR-08 [ ] FR-09 [ ] FR-10 [ ] FR-11 [ ] FR-12 [ ] FR-13 [ ] FR-14 [ ]
P1: FR-15 [ ] FR-16 [ ] FR-17 [ ] FR-18 [ ] FR-19 [ ] FR-20 [ ] FR-21 [ ]
P2: FR-22 [ ] FR-23 [ ] FR-24 [ ] FR-25 [ ] FR-26 [ ] FR-27 [ ]

## Chosen profile and measured numbers
(filled by A1: PROFILE, whisper size, LLM model, TTS, latency p50)

## Requests between developers
(format: from -> to: what is needed, why, date)
- Dev B -> Dev A: Bootstrap added docstring-only stubs under `app/voice/` and `app/agent/` per user-approved exception; confirm handoff before feature implementation, 2026-10-06.
- Dev B -> Dev A: Implement `scripts/download_models.py`; `make setup-voice` invokes it, and Prompt A now specifies profile-selected local voice model downloads, 2026-10-06. (Resolved)

## Blocked / risks
- The installed Starlette TestClient emits a deprecation warning about httpx; 88 tests pass.
- `make` command is unavailable in PowerShell, python `-m pytest` used instead.