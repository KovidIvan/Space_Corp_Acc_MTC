# Work plan (2 developers, 2 days)

Dev A = voice and agent. Dev B = platform and UX. Hardware is unknown until task A1 runs, so everything model-related is profile-based.
Rule of the plan: finish the core loop (call -> agent -> saved result -> Telegram notice) on day 1, because that alone already solves Ivan's problem. Everything else wraps around it.

## Sync points
- S0 (hour 1): repo created, skeleton bootstrapped, `contracts/` frozen, Telegram bot token and Ollama installed on the demo machine.
- S1 (end of day 1): vertical slice works on one machine: simulated call -> CallResult -> Telegram notice -> visible in dashboard.
- S2 (day 2, midday): all P0 done, P1 in progress, feature list reviewed against REQUIREMENTS.
- S3 (day 2, T-5h before submission): feature freeze. Only fixes, eval numbers, deck, video.

## Day 1
| Block | Dev A | Dev B |
|---|---|---|
| 0:00 to 1:00 (together) | Run the bootstrap prompt (prompts/ANTIGRAVITY_PROMPTS.md, prompt 0) on one machine; review the skeleton; agree contracts (S0) | same |
| 1:00 to 2:00 | A1 `make bench`: faster-whisper, Ollama model, Silero/Piper latency on this hardware; choose PROFILE; write result to docs/DECISIONS.md | B1 config, DB models, security (Fernet, password), audit hash chain, safe_http, log masking, with tests |
| 2:00 to 4:00 | A2 VAD endpointing + STT on wav files, word probabilities; fixtures script format | B2 dashboard shell: login, call list, call detail reading seeded fake CallResults |
| 4:00 to 6:00 | A3 TTS interface, pre-rendered phrase cache, 16 kHz resampling; generate fixture audio from scripts | B3 wizard (5 steps, timer), AgentConfig CRUD, consent enforcement |
| 6:00 to 8:00 | A4 NLU (prompt, JSON schema, rules fallback) + dialog state machine, tested on text only | B4 Telegram adapter: owner linking by deep link, masked notice, "mark handled" |
| 8:00 to 10:00 | A5 WebSocket session wiring + caller page; end-to-end with B's CallResult endpoint | B5 CallResult ingest endpoint, notification trigger, join with A for S1 |
| S1 | Run S1 together; record what is slow or broken in STATUS.md | same |

## Day 2
| Block | Dev A | Dev B |
|---|---|---|
| 0:00 to 2:00 | A6 router integration, handoff and wants_human, no_record mode, summarizer and slots | B6 call detail editing (segments, summary, classification) + audit entries; low-confidence highlighting |
| 2:00 to 4:00 | A7 fixtures: 20 synthetic call scripts, `make eval` (WER, intent, urgency, slots, latency) -> docs/EVAL_REPORT.md | B7 scenario editor, routing rules editor, VIP, working hours, cache regeneration trigger |
| S2 | Review all P0/P1 statuses against REQUIREMENTS; decide what is cut | same |
| 4:00 to 6:00 | A8 offer_chat link flow with B; barge-in only if time; optional SIP spike (AudioSocket) in a separate branch | [x] B8 stats page, settings (retention job, store-audio toggle, delete-all), audit page, offline guard test |
| S3 | Feature freeze. Rehearse demo twice. Record backup video of a full successful run | Deck: Ivan's journey (4 min) + scale and compliance (1 min); README; screenshots |
| Last block | Fix-only. Final eval numbers into the deck. Tag the release | Video editing, submission package |

## Definition of done (per task)
Code runs; unit tests for pure logic pass (`make test`); the related requirement id is ticked in STATUS.md; handoff note written; nothing real or personal in fixtures or logs.

## Fallbacks (decide early, do not improvise on demo day)
- STT too slow: smaller whisper size, or Vosk.
- LLM too slow or poor Russian JSON: `NLU_MODE=rules` for the demo, LLM only for the summary.
- TTS quality or latency problem: switch Silero <-> Piper, lean on cached phrases.
- Telegram unreachable at the venue: show the dashboard notice and a pre-recorded Telegram clip.
- Live microphone trouble: caller page has "play test audio" that sends a fixture wav.

## Git rules
`main` is always runnable. Branches `a/<topic>` and `b/<topic>`; merge to main after `make test` passes; pull before every AI session; commit at least hourly; no force-push. Never commit `.env`, models, data, or real audio.

## Deliverables checklist
Working prototype (runs with `make run`); demo script; deck; video (full flow, under 3 minutes); README with setup; docs/EVAL_REPORT.md; compliance and open-questions slide from docs/COMPLIANCE.md.
