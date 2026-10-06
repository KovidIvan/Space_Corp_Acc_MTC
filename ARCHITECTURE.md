# Architecture

## 1. Overview
```
 Caller (browser page now, SIP later)
   |  WebSocket: PCM16 16 kHz mono frames + JSON events
   v
 +---------------- app/voice ----------------+      +------------- app/agent -------------+
 | CallSession: VAD endpointing -> STT        | text | Dialog state machine                |
 |              <- TTS (cached + on demand)   |<---->| NLU (LLM, JSON) -> Router (rules)   |
 +--------------------------------------------+      | Summarizer (LLM, JSON)              |
                      |                              +-------------------------------------+
                      | CallResult (contracts/)
                      v
 +---------------------------- app (platform) ---------------------------------+
 | API + dashboard (FastAPI, Jinja2, HTMX) | SQLite + field encryption | audit  |
 | Wizard, config, rules | Channels: Telegram adapter | safe_http allowlist     |
 +------------------------------------------------------------------------------+
        Local LLM: Ollama (HTTP on localhost)    Telegram: masked notices only
```

## 2. Repository layout
```
app/
  main.py                 FastAPI app, router mounting
  interfaces.py           Protocols: STT, TTS, LLM, Channel, Telephony (+ Fake* for tests)
  schemas.py              pydantic models mirroring contracts/
  models.py               SQLAlchemy models
  core/    config.py logging.py safe_http.py security.py audit.py db.py jobs.py
  voice/   session.py vad.py stt.py tts.py phrases_cache.py protocol.py
           client/        caller page (HTML + JS, AudioWorklet)
  agent/   dialog.py nlu.py router.py summarizer.py llm_client.py masking.py
  channels/ base.py telegram.py
  api/     calls.py config.py wizard.py auth.py stats.py audit.py ws.py
  web/     templates/ static/ (htmx vendored locally)
contracts/ agent_config.schema.json call_result.schema.json ws_protocol.md
prompts/   nlu.ru.md summary.ru.md ANTIGRAVITY_PROMPTS.md
fixtures/  scripts/*.json (call scripts) audio/ (generated)
scripts/   bench.py eval.py download_models.py make_context.py
tests/
```

## 3. Technology choices
| Part | Choice | Why | Alternative |
|---|---|---|---|
| Language | Python 3.11 | All local speech and LLM tooling is Python-first; one language for two developers | TypeScript: good for UI, weak local ML. Go/Rust: only for a production media gateway, not needed now |
| Web | FastAPI + Jinja2 + HTMX | No separate frontend build, Python-only team | React/Vite SPA: more setup, no benefit in 2 days |
| Audio transport | WebSocket with PCM16 | Simple, same protocol later reused by SIP adapters | WebRTC (aiortc): ICE and codecs cost time |
| VAD | silero-vad | Accurate endpointing, runs on CPU | webrtcvad: lighter, less accurate |
| STT | faster-whisper per utterance after VAD endpointing; word probabilities give confidence | Good Russian quality, local | Vosk: true streaming, lower accuracy; GigaAM: open Russian model, check setup effort |
| LLM | Ollama, JSON schema constrained output, base URL configurable (OpenAI-compatible servers also work) | Local, simple | llama.cpp server, vLLM on a GPU server |
| TTS | Silero (default if available) or Piper, both Russian, local | Quality vs speed trade-off, selectable | Check model licenses before commercial claims |
| DB | SQLite + SQLAlchemy 2, Fernet field encryption | Zero setup | Postgres for the scale story |
| Telegram | aiogram 3 in polling mode | Works behind NAT | Webhook needs public URL |

## 4. Call flow
1. Caller page opens `/ws/call`, sends `start` (consent already stored, else rejected).
2. Server plays the cached greeting + disclosure (pre-rendered audio, no model latency).
3. Loop: VAD detects end of utterance (about 700 ms silence) -> STT -> NLU JSON -> state machine picks the next phrase -> TTS (cached template or synthesized per sentence) -> audio streamed back.
4. Router rules choose an action after enough information is gathered, or at once on `wants_human`.
5. On end: summarizer builds the Russian summary; CallResult is saved encrypted; audit event; notice goes to the Channel adapter.

State machine: GREET -> ASK_NAME_COMPANY -> ASK_REASON -> ROUTE -> (FAQ_ANSWER | TAKE_MESSAGE | OFFER_CHAT | HANDOFF | DECLINE) -> CONFIRM -> CLOSE.
Interrupts: `wants_human` from any state goes to HANDOFF; `no_record` switches to metadata-only mode; two failed understandings go to TAKE_MESSAGE; turn limit goes to CLOSE.

LLM is used for understanding and summary only. Replies come from scenario templates with slot filling; FAQ answers are selected by `faq_id`. This keeps latency and hallucination low.

NLU output per turn:
`{intent, urgency, wants_human, wants_chat, no_record, faq_id|null, slots{name, company, reason, callback_number, deadline}}`
intent values: client, partner, vendor_sales, spam, job_candidate, other, unclear. urgency: low, normal, high.

## 5. Data model (SQLite)
- owner(id, name, company, password_hash, created_at)
- agent_config(id, version, json, created_at); consent(id, text_version, accepted_at)
- call(id, started_at, ended_at, caller_masked, caller_hash, status, intent, urgency, action, handled, edited, no_record, transcript_enc, summary_enc, slots_enc)
- audit_event(id, ts, actor, action, target, details, prev_hash, hash), hash = SHA-256 over previous hash + event fields
- telegram_link(chat_id, linked_at); chat_thread(call_id, messages_enc) for FR-17
- wizard_run(started_at, finished_at, seconds) for SC-1

## 6. Interfaces (app/interfaces.py)
```python
class STT(Protocol):
    def transcribe(self, pcm16: bytes, sample_rate: int) -> Transcript: ...   # words with probability
class TTS(Protocol):
    def synth(self, text: str) -> bytes: ...                                   # PCM16 16 kHz mono
class LLM(Protocol):
    async def json(self, system: str, user: str, schema: dict) -> dict: ...
class Channel(Protocol):
    async def notify(self, notice: Notice) -> None: ...
class Telephony(Protocol):                                                     # simulator now, AudioSocket later
    async def frames(self) -> AsyncIterator[bytes]: ...
    async def play(self, pcm16: bytes) -> None: ...
    async def transfer(self, number: str) -> None: ...
```
Every interface has a Fake implementation for tests.

## 7. Configuration and hardware profiles
`PROFILE=cpu_light`: whisper small (int8), LLM about 3B quantized, Piper. `PROFILE=gpu_mid` (about 8 GB VRAM): whisper medium or large-v3, LLM about 7B, Silero. Task A1 (`make bench`) measures real latency and picks the profile. Other settings: `OFFLINE_MODE`, `NLU_MODE=llm|rules`, `LLM_BASE_URL`, `LLM_MODEL`, `MAX_CONCURRENT_CALLS`, `NOTICE_DETAIL=minimal|names`, `PUBLIC_BASE_URL`, keys through `.env`.

## 8. Latency design
Pre-rendered audio for greeting, disclosure and fixed phrases; per-sentence TTS streaming; STT and LLM calls in executors with a semaphore; constrained JSON output and a small model; rules fallback; filler phrase ("Секунду, уточняю…") if a turn exceeds 2.5 s.

## 9. Security and privacy
Field-level Fernet encryption; key from `.env`; password hashing; session cookie; audit hash chain with a verify command; log mask filter for phones, emails, long digit runs; `safe_http` allowlist (localhost, api.telegram.org); audio not stored unless toggled; retention job; delete-all.
Telegram notice (Russian) with default `minimal` detail: urgency, intent, one-line summary without names, masked phone, link to the dashboard as text (Telegram may reject localhost URL buttons). `names` mode adds initials. The trade-off is listed in COMPLIANCE.md.

## 10. Operator mapping (for slides)
Telephony adapter = SIP/VoIP gateway of the operator; Channel adapter = MTS bot/app/personal account; billing hook = usage events (minutes, calls) emitted per call for the operator's billing; inference = operator data center; sessions are stateless and horizontally scalable behind a queue; DB moves to Postgres.

## 11. Failure modes
STT fails: apologize, collect callback number by script. LLM slow or down: switch to `rules` NLU. TTS fails: use cached phrases only. Telegram down: notice stays in the dashboard, retried later. Model too slow on the demo machine: lower profile, shorten replies.
