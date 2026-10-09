from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Self

import pytest

from app.agent.nlu import Slots, TurnUnderstanding
from app.agent.summarizer import heuristic_summary
from app.core.config import Settings
from app.interfaces import FakeLLM, FakeSTT, FakeTTS, Transcript, Word
from app.schemas import AgentConfig, CallSlots, TranscriptSegment
from app.voice.phrases_cache import PhrasesCache, opening_phrases
from app.voice.protocol import parse_client_message
from app.voice.session import CallSession, mask_phone_number


def _agent_config() -> AgentConfig:
    return AgentConfig(
        version=1,
        owner={"name": "Иван", "company": "Синтетическая компания"},
        greeting="Здравствуйте! Вы позвонили в компанию.",
        disclosure="Разговор записывается и обрабатывается локально.",
        closing="До свидания.",
        routing=[],
        handoff_number="+375000000001",
    )


class FakeWebSocket:
    def __init__(self, incoming: list[dict[str, Any]] | None = None) -> None:
        self.incoming = list(incoming or [])
        self.sent_text: list[str] = []
        self.sent_bytes: list[bytes] = []
        self.closed = False

    async def receive_text(self) -> str:
        return json.dumps({"type": "start", "caller_number": "+375291234567", "protocol": 1})

    async def receive(self) -> dict[str, Any]:
        return self.incoming.pop(0)

    async def send_text(self, message: str) -> None:
        self.sent_text.append(message)

    async def send_bytes(self, message: bytes) -> None:
        self.sent_bytes.append(message)

    async def close(self, **_: Any) -> None:
        self.closed = True


class FakeDb:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def scalar(self, _statement: Any) -> SimpleNamespace:
        return SimpleNamespace(config_json=self.config.model_dump(mode="json"))


def _make_session(
    websocket: FakeWebSocket,
    config: AgentConfig,
    *,
    stt: FakeSTT | None = None,
) -> CallSession:
    tts = FakeTTS(audio=b"\x00\x00")
    return CallSession(
        websocket,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, nlu_mode="rules"),
        stt=stt or FakeSTT(),
        tts=tts,
        vad=lambda _pcm, _sample_rate: 0.0,
        llm=FakeLLM(),
        phrases_cache=PhrasesCache(tts),
        session_factory=lambda: FakeDb(config),  # type: ignore[arg-type]
        ingest_url="http://127.0.0.1:8000/api/calls/ingest",
    )


def test_start_handshake_greeting_test_audio_and_end(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _agent_config()
    websocket = FakeWebSocket(
        incoming=[
            {"text": json.dumps({"type": "test_audio", "fixture": "s1_urgent_client"})},
            {"text": json.dumps({"type": "end"})},
        ]
    )
    monkeypatch.setattr("app.voice.session.has_current_owner_consent", lambda _db: True)
    session = _make_session(websocket, config)
    ingested: list[Any] = []

    async def capture_result(result: Any) -> None:
        ingested.append(result)

    session._ingest_call_result = capture_result  # type: ignore[method-assign]

    asyncio.run(session.run())

    messages = [json.loads(message) for message in websocket.sent_text]
    opening = next(message["text"] for message in messages if message.get("type") == "transcript")
    assert "Иван" in opening
    assert "Синтетическая компания" in opening
    assert "ИИ" in opening
    assert "записывается" in opening
    assert "обрабатывается локально" in opening
    assert any(message.get("type") == "end" for message in messages)
    assert websocket.closed
    assert len(ingested) == 1
    assert any("Нам нужно согласовать договор" in message.get("text", "") for message in messages)


def test_no_record_call_does_not_retain_or_ingest_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = FakeWebSocket()
    stt = FakeSTT(
        Transcript(
            text="Не записывайте. Конфиденциальный текст.",
            words=(Word(w="Конфиденциальный", p=0.99),),
        )
    )
    session = _make_session(websocket, _agent_config(), stt=stt)
    session.transcript_segments.append(
        TranscriptSegment(who="caller", text="Earlier private content")
    )

    async def recognize_no_record(*_args: Any, **_kwargs: Any) -> TurnUnderstanding:
        return TurnUnderstanding(
            no_record=True,
            slots=Slots(name="Private Name", callback_number="+375291234567"),
        )

    monkeypatch.setattr("app.voice.session.understand_turn", recognize_no_record)
    ingested: list[Any] = []

    async def capture_result(result: Any) -> None:
        ingested.append(result)

    session._ingest_call_result = capture_result  # type: ignore[method-assign]

    assert asyncio.run(session._process_utterance(b"\x00\x00"))
    asyncio.run(session._finalize_call("completed"))

    assert session.transcript_segments == []
    assert all("Конфиденциальный текст" not in message for message in websocket.sent_text)
    assert len(ingested) == 1
    result = ingested[0]
    assert result.no_record is True
    assert result.transcript == []
    assert result.summary_ru == ""
    assert result.slots == CallSlots(callback_number="+375291234567")


def test_lazy_silero_failure_falls_back_to_energy_vad(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingSileroVAD:
        def speech_probability(self, _pcm: bytes, _sample_rate: int) -> float:
            raise RuntimeError("optional Silero dependencies are unavailable")

    monkeypatch.setattr("app.voice.session.SileroVAD", FailingSileroVAD)
    session = _make_session(FakeWebSocket(), _agent_config())
    session._vad = None

    session._init_adapters()

    assert callable(session._vad)
    assert session._vad(bytes(1024), 16000) == 0.0
    assert session._vad(b"\x01\x00" * 512, 16000) == 0.8


def test_opening_phrases_enforce_identity_and_disclosure() -> None:
    config = _agent_config()
    config.greeting = "Здравствуйте!"
    config.disclosure = ""

    greeting, disclosure = opening_phrases(config)

    assert "Иван" in greeting
    assert "Синтетическая компания" in greeting
    assert "ИИ" in disclosure
    assert "записывается" in disclosure
    assert "обрабатывается локально" in disclosure


def test_parse_client_start_requires_contract_fields_and_version() -> None:
    assert parse_client_message({"type": "start"}) is None
    assert parse_client_message(
        {"type": "start", "caller_number": "+375291234567", "protocol": 2}
    ) is None
    assert parse_client_message(
        {"type": "start", "caller_number": "+375291234567", "protocol": 1}
    ) is not None


def test_mask_phone_number_and_heuristic_summary_are_deterministic() -> None:
    assert mask_phone_number("+375291234567") == "+375 *** ***-**-67"
    summary = heuristic_summary(
        CallSlots(name="Synthetic Caller", reason="Synthetic request"),
        [TranscriptSegment(who="caller", text="Synthetic transcript")],
    )
    assert summary == "Synthetic Caller; вопрос: Synthetic request."
