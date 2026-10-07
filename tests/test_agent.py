"""Tests for NLU keyword rules, LLM parsing, and the routing engine.

These tests use only deterministic fakes — no real LLM or network calls.
"""

import pytest

from app.agent.nlu import (
    TurnUnderstanding,
    _parse_llm_response,
    rules_nlu,
    understand_turn,
)
from app.agent.router import route
from app.interfaces import FakeLLM
from app.schemas import RoutingRule, RuleWhen

# ───────────────────── Rules NLU: intent detection ─────────────────────


class TestRulesNLUIntent:
    def test_client_intent_on_contract_mention(self) -> None:
        result = rules_nlu("Здравствуйте, звоню по поводу договора на обслуживание")
        assert result.intent == "client"

    def test_partner_intent(self) -> None:
        result = rules_nlu("Добрый день, хотели бы обсудить сотрудничество")
        assert result.intent == "partner"

    def test_vendor_sales_intent(self) -> None:
        result = rules_nlu("Предлагаем вам выгодные условия закупки оборудования")
        assert result.intent == "vendor_sales"

    def test_spam_intent(self) -> None:
        result = rules_nlu("Поздравляем! Вы выиграли в розыгрыше!")
        assert result.intent == "spam"

    def test_job_candidate_intent(self) -> None:
        result = rules_nlu("Здравствуйте, я отправлял резюме на вакансию разработчика")
        assert result.intent == "job_candidate"

    def test_unclear_intent_on_ambiguous_text(self) -> None:
        result = rules_nlu("Алло, здравствуйте")
        assert result.intent == "unclear"

    def test_empty_text_returns_unclear(self) -> None:
        result = rules_nlu("")
        assert result.intent == "unclear"


# ───────────────────── Rules NLU: urgency ─────────────────────


class TestRulesNLUUrgency:
    def test_high_urgency_on_deadline(self) -> None:
        result = rules_nlu("Это срочно, нужно до пятницы подписать контракт")
        assert result.urgency == "high"

    def test_low_urgency_for_spam(self) -> None:
        result = rules_nlu("Реклама нового товара")
        assert result.urgency == "low"

    def test_normal_urgency_default(self) -> None:
        result = rules_nlu("Хотели бы обсудить сотрудничество")
        assert result.urgency == "normal"


# ───────────────────── Rules NLU: flags ─────────────────────


class TestRulesNLUFlags:
    def test_wants_human_on_soedini(self) -> None:
        result = rules_nlu("Соедините меня с менеджером")
        assert result.wants_human is True

    def test_wants_human_on_zhivoy_chelovek(self) -> None:
        result = rules_nlu("Я хочу говорить с живым человеком")
        assert result.wants_human is True

    def test_wants_chat_on_napishite(self) -> None:
        result = rules_nlu("Лучше напишите мне в чат")
        assert result.wants_chat is True

    def test_no_record_on_explicit_request(self) -> None:
        result = rules_nlu("Не записывайте этот разговор пожалуйста")
        assert result.no_record is True

    def test_flags_false_by_default(self) -> None:
        result = rules_nlu("Добрый день, звоню по проекту")
        assert result.wants_human is False
        assert result.wants_chat is False
        assert result.no_record is False


# ───────────────────── Rules NLU: FAQ detection ─────────────────────


class TestRulesNLUFaq:
    def test_faq_working_hours(self) -> None:
        result = rules_nlu("Подскажите часы работы офиса")
        assert result.faq_id == "working_hours"

    def test_faq_address(self) -> None:
        result = rules_nlu("Скажите адрес вашего офиса")
        assert result.faq_id == "address"

    def test_faq_pricing(self) -> None:
        result = rules_nlu("Сколько стоит разработка сайта?")
        assert result.faq_id == "pricing"

    def test_no_faq_for_regular_call(self) -> None:
        result = rules_nlu("Звоню по поводу заказа")
        assert result.faq_id is None


# ───────────────────── Rules NLU: phone extraction ─────────────────────


class TestRulesNLUPhone:
    def test_extracts_phone_number(self) -> None:
        result = rules_nlu("Перезвоните мне на +7 925 123-45-67")
        assert result.slots.callback_number is not None
        assert "925" in result.slots.callback_number

    def test_no_phone_when_absent(self) -> None:
        result = rules_nlu("Здравствуйте")
        assert result.slots.callback_number is None


# ───────────────────── LLM response parsing ─────────────────────


class TestLLMParsing:
    def test_valid_response_parsed_correctly(self) -> None:
        raw = {
            "intent": "client",
            "urgency": "high",
            "wants_human": False,
            "wants_chat": False,
            "no_record": False,
            "faq_id": None,
            "slots": {
                "name": "Алексей",
                "company": "ТехноСофт",
                "reason": "Обсудить договор",
                "callback_number": "+79251234567",
                "deadline": "до пятницы",
            },
        }
        result = _parse_llm_response(raw)
        assert result.intent == "client"
        assert result.urgency == "high"
        assert result.slots.name == "Алексей"
        assert result.slots.company == "ТехноСофт"
        assert result.slots.deadline == "до пятницы"

    def test_unknown_intent_defaults_to_unclear(self) -> None:
        raw = {"intent": "alien", "urgency": "normal", "slots": {}}
        result = _parse_llm_response(raw)
        assert result.intent == "unclear"

    def test_unknown_urgency_defaults_to_normal(self) -> None:
        raw = {"intent": "client", "urgency": "CRITICAL", "slots": {}}
        result = _parse_llm_response(raw)
        assert result.urgency == "normal"

    def test_missing_slots_gives_empty(self) -> None:
        raw = {"intent": "client", "urgency": "normal"}
        result = _parse_llm_response(raw)
        assert result.slots.name is None
        assert result.slots.company is None


# ───────────────────── understand_turn with FakeLLM ─────────────────────


class TestUnderstandTurn:
    @pytest.mark.asyncio
    async def test_rules_mode_skips_llm(self) -> None:
        result = await understand_turn(
            "Соедините с менеджером", mode="rules"
        )
        assert result.wants_human is True
        assert result.intent == "unclear"  # rules don't infer intent from this text

    @pytest.mark.asyncio
    async def test_llm_mode_with_fake_llm(self) -> None:
        fake = FakeLLM(
            response={
                "intent": "client",
                "urgency": "high",
                "wants_human": False,
                "wants_chat": False,
                "no_record": False,
                "faq_id": None,
                "slots": {"name": "Иван", "reason": "договор"},
            }
        )
        result = await understand_turn("Звоню по договору", llm=fake, mode="llm")
        assert result.intent == "client"
        assert result.urgency == "high"
        assert result.slots.name == "Иван"

    @pytest.mark.asyncio
    async def test_llm_mode_falls_back_when_no_llm(self) -> None:
        result = await understand_turn("Срочно, контракт до пятницы", llm=None, mode="llm")
        # Falls back to rules because llm is None
        assert result.urgency == "high"
        assert result.intent == "client"

    @pytest.mark.asyncio
    async def test_empty_text_returns_defaults(self) -> None:
        result = await understand_turn("", mode="rules")
        assert result.intent == "unclear"
        assert result.urgency == "normal"


# ───────────────────── Router ─────────────────────


def _make_rules() -> list[RoutingRule]:
    """Create a representative set of routing rules for testing."""
    return [
        RoutingRule(
            id="handoff_urgent",
            priority=1,
            action="handoff",
            when=RuleWhen(urgency=["high"]),
        ),
        RoutingRule(
            id="decline_spam",
            priority=2,
            action="decline",
            when=RuleWhen(intent=["spam", "vendor_sales"]),
        ),
        RoutingRule(
            id="faq_answer",
            priority=3,
            action="answer_faq",
            when=RuleWhen(intent=["client", "other"]),
        ),
        RoutingRule(
            id="offer_chat",
            priority=4,
            action="offer_chat",
            when=RuleWhen(wants_chat=True),
        ),
        RoutingRule(
            id="catch_all",
            priority=100,
            action="take_message",
        ),
    ]


class TestRouter:
    def test_wants_human_overrides_all_rules(self) -> None:
        """FR-06: 'соедините с менеджером' triggers handoff in one turn."""
        turn = TurnUnderstanding(intent="client", urgency="normal", wants_human=True)
        action = route(turn, _make_rules())
        assert action == "handoff"

    def test_vip_gets_handoff_by_default(self) -> None:
        """FR-06: VIP number triggers handoff."""
        turn = TurnUnderstanding(intent="client", urgency="normal")
        action = route(turn, _make_rules(), is_vip=True)
        assert action == "handoff"

    def test_high_urgency_matches_first_rule(self) -> None:
        turn = TurnUnderstanding(intent="client", urgency="high")
        action = route(turn, _make_rules())
        assert action == "handoff"

    def test_spam_gets_declined(self) -> None:
        turn = TurnUnderstanding(intent="spam", urgency="low")
        action = route(turn, _make_rules())
        assert action == "decline"

    def test_vendor_sales_gets_declined(self) -> None:
        turn = TurnUnderstanding(intent="vendor_sales", urgency="low")
        action = route(turn, _make_rules())
        assert action == "decline"

    def test_client_gets_faq_answer(self) -> None:
        turn = TurnUnderstanding(intent="client", urgency="normal")
        action = route(turn, _make_rules())
        assert action == "answer_faq"

    def test_catch_all_returns_take_message(self) -> None:
        turn = TurnUnderstanding(intent="unclear", urgency="normal")
        action = route(turn, _make_rules())
        assert action == "take_message"

    def test_empty_rules_returns_take_message(self) -> None:
        turn = TurnUnderstanding(intent="client", urgency="normal")
        action = route(turn, [])
        assert action == "take_message"

    def test_priority_order_is_respected(self) -> None:
        """Lower priority number is evaluated first."""
        rules = [
            RoutingRule(id="low_pri", priority=99, action="take_message"),
            RoutingRule(id="high_pri", priority=1, action="handoff"),
        ]
        turn = TurnUnderstanding(intent="client", urgency="normal")
        action = route(turn, rules)
        # Both match (no conditions), but priority=1 wins
        assert action == "handoff"


# ───────────────────── STT unit tests (pure logic, no model) ─────────────────────


class TestSTTPureFunctions:
    def test_pcm16_to_float32_converts_correctly(self) -> None:
        import numpy as np

        from app.voice.stt import pcm16_to_float32

        # Max positive int16 should map to ~1.0
        pcm = np.array([32767], dtype="<i2").tobytes()
        result = pcm16_to_float32(pcm)
        assert abs(result[0] - 1.0) < 0.001

    def test_pcm16_to_float32_handles_silence(self) -> None:
        import numpy as np

        from app.voice.stt import pcm16_to_float32

        pcm = np.zeros(100, dtype="<i2").tobytes()
        result = pcm16_to_float32(pcm)
        assert all(v == 0.0 for v in result)

    def test_stt_rejects_wrong_sample_rate(self) -> None:
        from app.voice.stt import FasterWhisperSTT

        # Inject a fake model to bypass model loading
        class FakeModel:
            pass

        stt = FasterWhisperSTT(model=FakeModel())
        with pytest.raises(ValueError, match="16000 Hz"):
            stt.transcribe(b"\x00\x00", sample_rate=8000)

    def test_stt_rejects_odd_byte_count(self) -> None:
        from app.voice.stt import FasterWhisperSTT

        class FakeModel:
            pass

        stt = FasterWhisperSTT(model=FakeModel())
        with pytest.raises(ValueError, match="even number"):
            stt.transcribe(b"\x00", sample_rate=16000)

    def test_stt_empty_audio_returns_empty_transcript(self) -> None:
        from app.voice.stt import FasterWhisperSTT

        class FakeModel:
            pass

        stt = FasterWhisperSTT(model=FakeModel())
        result = stt.transcribe(b"", sample_rate=16000)
        assert result.text == ""
        assert result.words == ()

    def test_stt_requires_model_or_path(self) -> None:
        from app.voice.stt import FasterWhisperSTT

        with pytest.raises(ValueError, match="model_path is required"):
            FasterWhisperSTT()
