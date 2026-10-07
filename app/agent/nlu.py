"""Per-turn call understanding: LLM-based extraction with keyword rules fallback.

Architecture (§4 Call flow):
    STT transcript → NLU → ``TurnUnderstanding`` → Router → action

Two modes controlled by ``settings.nlu_mode``:
- ``"llm"``: Send the transcript to Ollama via ``LLM.json()`` with a Russian prompt
  and a constrained JSON schema.  On failure, fall back to keyword rules automatically.
- ``"rules"``: Skip the LLM entirely and use only keyword matching.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.interfaces import LLM
from app.schemas import Intent, Urgency

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# NLU output model
# ──────────────────────────────────────────────────────────────────────

class Slots(BaseModel):
    """Extracted caller information slots."""

    name: str | None = None
    company: str | None = None
    reason: str | None = None
    callback_number: str | None = None
    deadline: str | None = None


class TurnUnderstanding(BaseModel):
    """Structured result of per-turn NLU.

    Fields mirror the architecture spec (§4):
    ``{intent, urgency, wants_human, wants_chat, no_record, faq_id, slots}``
    """

    intent: Intent = "unclear"
    urgency: Urgency = "normal"
    wants_human: bool = False
    wants_chat: bool = False
    no_record: bool = False
    faq_id: str | None = None
    slots: Slots = Field(default_factory=Slots)


# ──────────────────────────────────────────────────────────────────────
# JSON schema for Ollama constrained output
# ──────────────────────────────────────────────────────────────────────

_NLU_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": list(Intent.__args__),  # type: ignore[attr-defined]
        },
        "urgency": {
            "type": "string",
            "enum": list(Urgency.__args__),  # type: ignore[attr-defined]
        },
        "wants_human": {"type": "boolean"},
        "wants_chat": {"type": "boolean"},
        "no_record": {"type": "boolean"},
        "faq_id": {"type": ["string", "null"]},
        "slots": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "company": {"type": ["string", "null"]},
                "reason": {"type": ["string", "null"]},
                "callback_number": {"type": ["string", "null"]},
                "deadline": {"type": ["string", "null"]},
            },
        },
    },
    "required": [
        "intent",
        "urgency",
        "wants_human",
        "wants_chat",
        "no_record",
        "faq_id",
        "slots",
    ],
}

# ──────────────────────────────────────────────────────────────────────
# Prompt loading
# ──────────────────────────────────────────────────────────────────────

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "nlu.ru.md"

_cached_prompt: str | None = None


def _load_prompt() -> str:
    """Read the NLU system prompt from ``prompts/nlu.ru.md``.  Cached after first call."""
    global _cached_prompt
    if _cached_prompt is None:
        _cached_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _cached_prompt


# ──────────────────────────────────────────────────────────────────────
# Keyword rules fallback  (NLU_MODE=rules or LLM failure)
# ──────────────────────────────────────────────────────────────────────

_HANDOFF_PATTERNS = re.compile(
    r"соедини|переключи|позови|хочу.{0,20}(человек|менеджер|иван)|говорить.{0,15}(человек|менеджер)",
    re.IGNORECASE,
)
_CHAT_PATTERNS = re.compile(
    r"напиши|лучше.{0,10}чат|отправь.{0,10}ссылк",
    re.IGNORECASE,
)
_NO_RECORD_PATTERNS = re.compile(
    r"не записыв|без записи",
    re.IGNORECASE,
)
_HIGH_URGENCY_PATTERNS = re.compile(
    r"срочно|до пятниц|сегодня|критичн|горит|немедленно|deadline|дедлайн",
    re.IGNORECASE,
)
_SPAM_PATTERNS = re.compile(
    r"реклам|акци[яи]|скидк|бесплатн|предложени[ея].{0,20}(услуг|товар)|розыгрыш",
    re.IGNORECASE,
)
_VENDOR_PATTERNS = re.compile(
    r"предлага[ею]|продаж|закуп|поставщик|оптов",
    re.IGNORECASE,
)
_CLIENT_PATTERNS = re.compile(
    r"заказ|проект|договор|контракт|оплат|счёт|счет|услуг|работ[аы]|задач",
    re.IGNORECASE,
)
_PARTNER_PATTERNS = re.compile(
    r"партнёр|партнер|сотруднич|совместн",
    re.IGNORECASE,
)
_JOB_PATTERNS = re.compile(
    r"вакансия|резюме|собеседован|устроиться|ищу работу|HR",
    re.IGNORECASE,
)
_FAQ_HOURS = re.compile(r"час[ыа].{0,10}работ|режим.{0,10}работ|когда.{0,10}(открыт|работает)", re.IGNORECASE)
_FAQ_ADDRESS = re.compile(r"адрес|где.{0,10}(находи|располож)|как.{0,10}доехать", re.IGNORECASE)
_FAQ_PRICE = re.compile(r"цен[аы]|стоимость|прайс|сколько.{0,10}стоит|тариф", re.IGNORECASE)

_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-()]{7,}\d")


def rules_nlu(text: str) -> TurnUnderstanding:
    """Keyword-based NLU fallback.  Fast, deterministic, no model needed."""
    wants_human = bool(_HANDOFF_PATTERNS.search(text))
    wants_chat = bool(_CHAT_PATTERNS.search(text))
    no_record = bool(_NO_RECORD_PATTERNS.search(text))

    # Intent detection (ordered by specificity)
    intent: Intent = "unclear"
    if _SPAM_PATTERNS.search(text):
        intent = "spam"
    elif _JOB_PATTERNS.search(text):
        intent = "job_candidate"
    elif _VENDOR_PATTERNS.search(text):
        intent = "vendor_sales"
    elif _PARTNER_PATTERNS.search(text):
        intent = "partner"
    elif _CLIENT_PATTERNS.search(text):
        intent = "client"

    # Urgency
    urgency: Urgency = "normal"
    if _HIGH_URGENCY_PATTERNS.search(text):
        urgency = "high"
    elif intent in ("spam", "vendor_sales"):
        urgency = "low"

    # FAQ
    faq_id: str | None = None
    if _FAQ_HOURS.search(text):
        faq_id = "working_hours"
    elif _FAQ_ADDRESS.search(text):
        faq_id = "address"
    elif _FAQ_PRICE.search(text):
        faq_id = "pricing"

    # Phone extraction
    phone_match = _PHONE_PATTERN.search(text)
    callback_number = phone_match.group(0).strip() if phone_match else None

    slots = Slots(
        callback_number=callback_number,
        reason=text[:200] if text.strip() else None,
    )

    return TurnUnderstanding(
        intent=intent,
        urgency=urgency,
        wants_human=wants_human,
        wants_chat=wants_chat,
        no_record=no_record,
        faq_id=faq_id,
        slots=slots,
    )


# ──────────────────────────────────────────────────────────────────────
# LLM-based NLU
# ──────────────────────────────────────────────────────────────────────


def _parse_llm_response(raw: dict[str, Any]) -> TurnUnderstanding:
    """Validate and coerce the raw LLM JSON into a ``TurnUnderstanding``.

    Unknown or invalid values are silently replaced with safe defaults so
    a slightly malformed LLM output never crashes the call flow.
    """
    # Coerce intent
    intent_val = raw.get("intent", "unclear")
    valid_intents = set(Intent.__args__)  # type: ignore[attr-defined]
    if intent_val not in valid_intents:
        intent_val = "unclear"

    # Coerce urgency
    urgency_val = raw.get("urgency", "normal")
    valid_urgencies = set(Urgency.__args__)  # type: ignore[attr-defined]
    if urgency_val not in valid_urgencies:
        urgency_val = "normal"

    raw_slots = raw.get("slots") or {}
    slots = Slots(
        name=raw_slots.get("name"),
        company=raw_slots.get("company"),
        reason=raw_slots.get("reason"),
        callback_number=raw_slots.get("callback_number"),
        deadline=raw_slots.get("deadline"),
    )

    return TurnUnderstanding(
        intent=intent_val,
        urgency=urgency_val,
        wants_human=bool(raw.get("wants_human", False)),
        wants_chat=bool(raw.get("wants_chat", False)),
        no_record=bool(raw.get("no_record", False)),
        faq_id=raw.get("faq_id"),
        slots=slots,
    )


async def llm_nlu(text: str, llm: LLM) -> TurnUnderstanding:
    """Extract turn understanding via the local LLM.

    On any failure (network, timeout, bad JSON) the function logs a warning
    and falls back to ``rules_nlu`` so the call flow is never interrupted.
    """
    if not text.strip():
        return TurnUnderstanding()

    system_prompt = _load_prompt()

    try:
        raw = await llm.json(system_prompt, text, _NLU_JSON_SCHEMA)
        return _parse_llm_response(raw)
    except (RuntimeError, ValueError, TypeError, TimeoutError):
        logger.warning("LLM NLU failed, falling back to keyword rules")
        return rules_nlu(text)


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────


async def understand_turn(
    text: str,
    *,
    llm: LLM | None = None,
    mode: Literal["llm", "rules"] = "llm",
) -> TurnUnderstanding:
    """Analyse one caller turn and return structured understanding.

    Args:
        text: Transcribed caller speech for this turn.
        llm: LLM adapter instance.  Required when *mode* is ``"llm"``.
        mode: ``"llm"`` uses the local model with keyword fallback;
              ``"rules"`` skips the model entirely.

    Returns:
        ``TurnUnderstanding`` with intent, urgency, flags and slots.
    """
    if mode == "rules" or llm is None:
        return rules_nlu(text)
    return await llm_nlu(text, llm)
