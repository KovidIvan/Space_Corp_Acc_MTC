# Decisions log (short ADRs)
Format: id, decision, why, alternatives, status. Add new entries at the bottom. Contract changes must be logged here.

- ADR-001 Python 3.11 for everything. Why: local speech/LLM ecosystem, one language for two devs. Alternatives: TypeScript, Go. Status: accepted.
- ADR-002 Audio over WebSocket (PCM16 16 kHz mono), not WebRTC. Why: simple, reusable for SIP adapters (Asterisk AudioSocket). Status: accepted.
- ADR-003 VAD endpointing + faster-whisper per utterance instead of true streaming ASR. Why: better Russian accuracy, word probabilities for the trust feature. Status: accepted, revisit after bench.
- ADR-004 LLM only for understanding and summary; replies from scenario templates. Why: latency, hallucination control. Status: accepted.
- ADR-005 SQLite with field-level Fernet encryption. Why: zero setup; Postgres is the scale story. Status: accepted.
- ADR-006 Dashboard with Jinja2 + HTMX, assets vendored locally. Why: no frontend build, works offline. Status: accepted.
- ADR-007 Telegram receives only masked notices (default minimal detail). Why: Telegram is a foreign service; full data stays local. Status: accepted, open question for MTS.
- ADR-008 Local-first runtime; cloud AI only for coding with synthetic data. Why: personal data localization expectations (see COMPLIANCE.md). Status: accepted.
- ADR-009 SIP via Asterisk AudioSocket is a P2 spike. Why: no provider number available. Status: accepted.
