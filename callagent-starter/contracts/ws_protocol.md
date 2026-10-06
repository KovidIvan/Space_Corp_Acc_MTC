# Call session WebSocket protocol (`/ws/call`), version 1

Audio: PCM16 little-endian, mono, 16 kHz. Binary frames of 20 ms (640 bytes) from the caller; agent audio comes back as binary frames of any size (server resamples TTS to 16 kHz).
All control messages are JSON text frames: `{"type": "...", ...}`.

Client to server
- `start`: `{"type":"start","caller_number":"+375XXXXXXXXX","protocol":1}`. Rejected with `error` code `consent_missing` if the owner has not given consent.
- `end`: caller hung up.
- `test_audio`: `{"type":"test_audio","fixture":"s1_urgent_client"}` plays a fixture wav as the caller (demo fallback).

Server to client
- `state`: `{"type":"state","state":"ASK_REASON"}` dialog state changes.
- `transcript`: `{"type":"transcript","who":"caller|agent","text":"...","final":true}`.
- `playback`: `{"type":"playback","action":"start|stop"}`; `stop` is sent on barge-in.
- `chat_offer`: `{"type":"chat_offer","deep_link":"https://t.me/<bot>?start=<token>"}`.
- `handoff`: `{"type":"handoff","number":"+375...","reason":"wants_human|vip|urgent_rule"}`.
- `end`: `{"type":"end","call_id":"...","reason":"completed|handoff|timeout|error"}`.
- `error`: `{"type":"error","code":"consent_missing|busy|internal","message":"..."}`.

Rules: max one active call in demo mode (`MAX_CONCURRENT_CALLS`); idle timeout 30 s without speech; changes to this protocol follow the contract-change rule in AGENTS.md.
