"""Voice WebSocket protocol definitions and message schemas.

Follows contracts/ws_protocol.md (v1):
- Control messages are JSON text frames: {"type": "...", ...}
- Audio frames are mono PCM16 16 kHz little-endian binary frames
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ProtocolMessage(BaseModel):
    """Base model for protocol messages."""

    model_config = ConfigDict(extra="ignore")
    type: str


# ── Client to Server ─────────────────────────────────────────────────────────


class ClientStart(ProtocolMessage):
    type: Literal["start"] = "start"
    caller_number: str = "+375000000000"
    protocol: int = 1


class ClientEnd(ProtocolMessage):
    type: Literal["end"] = "end"


class ClientTestAudio(ProtocolMessage):
    type: Literal["test_audio"] = "test_audio"
    fixture: str = "s1_urgent_client"


# ── Server to Client ─────────────────────────────────────────────────────────


class ServerState(ProtocolMessage):
    type: Literal["state"] = "state"
    state: str


class ServerTranscript(ProtocolMessage):
    type: Literal["transcript"] = "transcript"
    who: Literal["caller", "agent"]
    text: str
    final: bool = True


class ServerPlayback(ProtocolMessage):
    type: Literal["playback"] = "playback"
    action: Literal["start", "stop"]


class ServerChatOffer(ProtocolMessage):
    type: Literal["chat_offer"] = "chat_offer"
    deep_link: str


class ServerHandoff(ProtocolMessage):
    type: Literal["handoff"] = "handoff"
    number: str
    reason: str = "wants_human"


class ServerEnd(ProtocolMessage):
    type: Literal["end"] = "end"
    call_id: str
    reason: Literal["completed", "handoff", "timeout", "error"]


class ServerError(ProtocolMessage):
    type: Literal["error"] = "error"
    code: Literal["consent_missing", "busy", "internal"]
    message: str


def parse_client_message(
    raw: str | dict[str, Any],
) -> ClientStart | ClientEnd | ClientTestAudio | None:
    """Parse an incoming JSON text frame from the client."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict):
            return None
        msg_type = data.get("type")
        if msg_type == "start":
            return ClientStart.model_validate(data)
        if msg_type == "end":
            return ClientEnd.model_validate(data)
        if msg_type == "test_audio":
            return ClientTestAudio.model_validate(data)
        return None
    except Exception:
        return None
