"""Protocols and deterministic fake adapters for external capabilities."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Word:
    """Recognized word and confidence probability."""

    w: str
    p: float


@dataclass(frozen=True)
class Transcript:
    """Speech recognition result."""

    text: str = ""
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class Notice:
    """Minimal masked call notice sent to an owner."""

    call_id: str
    urgency: str
    intent: str
    summary: str
    caller_masked: str


class STT(Protocol):
    """Speech-to-text adapter contract."""

    def transcribe(self, pcm16: bytes, sample_rate: int) -> Transcript: ...


class TTS(Protocol):
    """Text-to-speech adapter contract."""

    def synth(self, text: str) -> bytes: ...


class LLM(Protocol):
    """Local language model adapter contract."""

    async def json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class Channel(Protocol):
    """Notification channel contract."""

    async def notify(self, notice: Notice) -> None: ...


class Telephony(Protocol):
    """Audio transport and handoff contract."""

    def frames(self) -> AsyncIterator[bytes]: ...

    async def play(self, pcm16: bytes) -> None: ...

    async def transfer(self, number: str) -> None: ...


class FakeSTT:
    """Deterministic STT implementation for tests."""

    def __init__(self, transcript: Transcript | None = None) -> None:
        self.transcript = transcript or Transcript()

    def transcribe(self, pcm16: bytes, sample_rate: int) -> Transcript:
        return self.transcript


class FakeTTS:
    """Deterministic TTS implementation for tests."""

    def __init__(self, audio: bytes = b"") -> None:
        self.audio = audio

    def synth(self, text: str) -> bytes:
        return self.audio


class FakeLLM:
    """Configured JSON response fake for tests."""

    def __init__(self, response: Mapping[str, Any] | None = None) -> None:
        self.response = dict(response or {})

    async def json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return dict(self.response)


class FakeChannel:
    """In-memory channel fake for tests."""

    def __init__(self) -> None:
        self.notices: list[Notice] = []

    async def notify(self, notice: Notice) -> None:
        self.notices.append(notice)


class FakeTelephony:
    """In-memory telephony fake for tests."""

    def __init__(self, frames: tuple[bytes, ...] = ()) -> None:
        self._frames = frames
        self.played: list[bytes] = []
        self.transfers: list[str] = []

    async def frames(self) -> AsyncIterator[bytes]:
        for frame in self._frames:
            yield frame

    async def play(self, pcm16: bytes) -> None:
        self.played.append(pcm16)

    async def transfer(self, number: str) -> None:
        self.transfers.append(number)
