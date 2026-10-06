# Requirements (Track 1: AI agent for incoming calls)

Priorities: P0 = must work in the demo, P1 = mandatory ToR items that complete the product, P2 = enhancers and scale material.
Targets marked (initial) are revised after `make bench`.

## 1. Success criteria
| Id | Criterion | Target |
|---|---|---|
| SC-1 | Setup time in the wizard, measured by its timer, by someone who did not build it | <= 5:00 |
| SC-2 | Intent and urgency accuracy on 20 synthetic calls | >= 85% each (initial) |
| SC-3 | Key slots (name, reason) extracted correctly | >= 80% (initial) |
| SC-4 | Speech recognition error rate (WER) on fixtures | reported; <= 20% on synthetic audio (initial) |
| SC-5 | End of caller speech to first agent audio, non-cached reply | p50 <= 3 s GPU, <= 5 s CPU (initial); cached phrases <= 1 s |
| SC-6 | "Connect me to a manager" triggers handoff within one turn | 100% on test set |
| SC-7 | External requests at runtime other than the allowlist | 0 (tested) |

## 2. Functional requirements
| Id | Pri | Requirement | Done when | CJM stage |
|---|---|---|---|---|
| FR-01 | P0 | Browser caller page streams microphone audio to the server and plays agent audio | A 2-minute conversation works in Chrome | 4 |
| FR-02 | P0 | Agent opens with the scenario greeting that names Ivan and the company, and states it is an AI assistant and that the call is recorded and processed | Greeting plays on every call, cannot be disabled | 1 |
| FR-03 | P0 | Dialogue collects caller name, company, reason, callback number; confirms; ends politely. Max 8 turns. Silence or unclear speech: re-ask twice, then keep what it has | Scenarios S1-S8 pass | 4, 5 |
| FR-04 | P0 | Per-turn understanding returns intent, urgency, slots, wants_human, wants_chat, faq_id, no_record as JSON | Parsing is validated, invalid output falls back to rules | 5 |
| FR-05 | P0 | Routing engine applies ordered rules to pick an action: answer_faq, take_message, offer_chat, handoff, decline | Unit tests cover rule order and conditions | 5 |
| FR-06 | P0 | Emergency handoff: phrases like "соедините с менеджером", a VIP number, or an urgent rule triggers handoff (simulated forward in the demo); call is still logged | SC-6 met | 5 |
| FR-07 | P0 | After the call a CallResult is saved: transcript with word confidence, intent, urgency, slots, Russian summary, action | Matches `contracts/call_result.schema.json` | 4 |
| FR-08 | P0 | Telegram notice with masked data within 10 s of call end | Notice arrives in the demo | 4, 5 |
| FR-09 | P0 | Dashboard: login, call list with filters (urgency, intent, handled), call detail with transcript, words below confidence 0.6 highlighted, summary | Demo shows an edit of a flagged word | 4 |
| FR-10 | P0 | Edit transcript segments, summary and classification; edited calls are marked; every edit is audited | Audit shows the edit | 4 |
| FR-11 | P0 | Setup wizard in 5 steps with a visible timer: business profile, scenario template, rules (VIP, handoff number, hours), Telegram link, consent plus test call | AgentConfig saved, timer result stored | 3 |
| FR-12 | P0 | Consent is recorded (timestamp, text version); the agent does not answer calls before consent | Test: no consent, call rejected | 3 |
| FR-13 | P0 | Transcripts, summaries and slots encrypted at rest; audit log with hash chain for login, view, edit, export, delete, config change | Chain verification test passes | 3, 5 |
| FR-14 | P0 | Offline guard: all outgoing HTTP via allowlist | SC-7 test passes | 3 |
| FR-15 | P1 | Scenario editor: greeting, FAQ items, closing; cached audio is regenerated on save | Edit changes the next call | 5 |
| FR-16 | P1 | Routing rules editor with priorities, conditions, actions; VIP list, working hours, handoff number | Rule change changes routing | 5 |
| FR-17 | P1 | offer_chat: caller page shows a Telegram deep link or QR; the bot relays the caller's text to Ivan with call context | Message reaches Ivan | 5 |
| FR-18 | P1 | Stats page: calls, by intent, by urgency, handled vs unhandled, estimated minutes saved | Numbers match the database | 6 |
| FR-19 | P1 | Settings: retention days (job deletes expired calls), store-audio toggle (default off), delete-all button; audit log page | Retention job tested | 3, 5 |
| FR-20 | P1 | Telegram "mark handled" button updates the call | Dashboard shows handled | 5 |
| FR-21 | P1 | Caller says not to record: call flagged, transcript not stored, only metadata and callback request | S8 passes | 3 |
| FR-22 | P2 | Example dialogs added by the user are used as few-shot examples in understanding | Example changes a classification | 4 |
| FR-23 | P2 | Opening screen with time-saved estimate from the user's own call numbers | Screen exists | 2 |
| FR-24 | P2 | Request-type breakdown chart; CSV export (audited) | Export works | 6 |
| FR-25 | P2 | Barge-in: caller can interrupt the agent | Playback stops | 4 |
| FR-26 | P2 | SIP: Asterisk AudioSocket adapter feeding the same call session | Softphone call reaches the agent | 2 |
| FR-27 | P2 | `make eval` writes `docs/EVAL_REPORT.md` with SC numbers for the pitch | Report generated | 4 |

## 3. Non-functional requirements
- NFR-01 Local runtime. STT, LLM, TTS, storage run on the demo machine. `OFFLINE_MODE=true` by default.
- NFR-02 Resilience. If STT, LLM or TTS fails, the agent apologizes, collects a callback number with a fixed script and logs the failure. `NLU_MODE=rules` is a keyword fallback when the LLM is unavailable or too slow.
- NFR-03 Privacy by default. Audio is not stored. PII is masked in logs and notices. Caller numbers are stored masked plus an HMAC hash for VIP matching.
- NFR-04 Reproducibility. `make setup` and `make setup-voice` prepare everything; models are downloaded by a script and work offline afterwards.
- NFR-05 Hardware profiles via config (see ARCHITECTURE section 7).
- NFR-06 Testability. Synthetic fixtures, deterministic fake STT/TTS/LLM for unit tests.
- NFR-07 Scale story (documented, not built): stateless call workers, queue, database swap to Postgres, inference on operator GPUs.

## 4. Acceptance scenarios (all synthetic)
- S1 Urgent client: "contract by Friday" -> intent client, urgency high, Telegram notice, callback requested.
- S2 Vendor sales -> polite decline, logged as low urgency.
- S3 FAQ question (working hours, address) -> answered from FAQ, no handoff.
- S4 Long or complex request -> offer_chat with deep link.
- S5 "Соедините с менеджером" -> handoff in one turn.
- S6 VIP number -> handoff or priority notice per rule.
- S7 Unclear or silent caller -> two re-asks, then message taken.
- S8 "Не записывайте разговор" -> no transcript stored.

## 5. Out of scope
Real PSTN number, billing integration, CRM and email modules, multi-user roles, outbound calls, Belarusian language, mobile app. These appear only as roadmap or architecture slides.
