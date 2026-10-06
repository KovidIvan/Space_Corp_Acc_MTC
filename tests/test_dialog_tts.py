"""Tests for dialogue state machine, phrases cache, and TTS adapter."""

from app.agent.dialog import DialogSession, DialogState
from app.agent.nlu import Slots, TurnUnderstanding
from app.interfaces import FakeTTS
from app.voice.phrases_cache import PhrasesCache
from app.voice.tts import LocalTTS


class TestDialogSession:
    def test_initial_state_is_greet(self) -> None:
        session = DialogSession()
        assert session.state == DialogState.GREET
        assert session.turns_count == 0

    def test_asks_for_name_when_missing(self) -> None:
        session = DialogSession()
        turn = TurnUnderstanding(intent="client")
        res = session.process_turn(turn)
        assert res.next_state == DialogState.ASK_NAME_COMPANY
        assert "Представьтесь" in res.agent_phrase

    def test_advances_to_ask_reason_when_name_provided(self) -> None:
        session = DialogSession()
        turn = TurnUnderstanding(intent="client", slots=Slots(name="Алексей"))
        res = session.process_turn(turn)
        assert res.next_state == DialogState.ASK_REASON
        assert session.slots.name == "Алексей"

    def test_reasks_twice_on_unclear_speech(self) -> None:
        session = DialogSession()
        unclear_turn = TurnUnderstanding(intent="unclear")

        # First re-ask
        res1 = session.process_turn(unclear_turn)
        assert res1.reask_count == 1
        assert "плохо вас слышно" in res1.agent_phrase

        # Second re-ask
        res2 = session.process_turn(unclear_turn)
        assert res2.reask_count == 2

    def test_immediate_handoff_on_wants_human(self) -> None:
        session = DialogSession()
        turn = TurnUnderstanding(wants_human=True)
        res = session.process_turn(turn)
        assert res.next_state == DialogState.HANDOFF
        assert res.action == "handoff"
        assert res.is_terminal is True

    def test_turn_limit_forces_close(self) -> None:
        session = DialogSession(max_turns=2)
        turn = TurnUnderstanding(intent="client", slots=Slots(name="Иван", reason="Заказ"))
        session.process_turn(turn)
        res = session.process_turn(turn)  # 2nd turn hits limit
        assert res.next_state == DialogState.CLOSE
        assert res.is_terminal is True


class TestPhrasesCache:
    def test_preloads_and_returns_cached_phrases(self) -> None:
        fake_tts = FakeTTS(audio=b"\x01\x02\x03\x04")
        cache = PhrasesCache(fake_tts)
        cache.preload()

        audio = cache.get("greeting")
        assert audio == b"\x01\x02\x03\x04"

    def test_fallback_synthesizes_on_demand(self) -> None:
        fake_tts = FakeTTS(audio=b"\x00\x00")
        cache = PhrasesCache(fake_tts)

        audio = cache.get("unknown_key", fallback_text="Привет")
        assert audio == b"\x00\x00"


class TestLocalTTS:
    def test_fallback_synth_returns_pcm_padding(self) -> None:
        tts = LocalTTS()
        audio = tts.synth("Тестовая фраза")
        assert isinstance(audio, bytes)
        assert len(audio) > 0
        assert len(audio) % 2 == 0  # Even length for PCM16

    def test_empty_string_returns_empty_bytes(self) -> None:
        tts = LocalTTS()
        assert tts.synth("") == b""
