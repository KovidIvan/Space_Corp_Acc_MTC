"""Call summarizer generating Russian summaries for CallResult and notices."""

from __future__ import annotations

import logging
from pathlib import Path

from app.interfaces import LLM
from app.schemas import CallSlots, TranscriptSegment

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parent.parent.parent / "prompts" / "summary.ru.md"


def _load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8").strip()
    return (
        "Ты аналитик входящих телефонных звонков для руководителя компании.\n"
        "Составь краткое резюме звонка на русском языке (1-2 предложения):\n"
        "кто звонил, компания, суть обращения и договоренности.\n"
        'Верни JSON: {"summary": "..."}'
    )


def heuristic_summary(slots: CallSlots, transcript: list[TranscriptSegment]) -> str:
    """Deterministic fallback summary from extracted slots and dialogue text."""
    parts: list[str] = []
    who = slots.name or "Собеседник"
    if slots.company:
        who += f" ({slots.company})"
    parts.append(who)

    if slots.reason:
        parts.append(f"вопрос: {slots.reason}")
    if slots.callback_number:
        parts.append(f"обратный телефон: {slots.callback_number}")
    if slots.deadline:
        parts.append(f"срок: {slots.deadline}")

    if len(parts) > 1:
        return "; ".join(parts) + "."

    caller_texts = [s.text.strip() for s in transcript if s.who == "caller" and s.text.strip()]
    if caller_texts:
        snippet = caller_texts[-1][:120]
        return f"{who}: «{snippet}»."

    return "Звонок завершен без содержательного сообщения."


async def summarize_call(
    transcript: list[TranscriptSegment],
    slots: CallSlots,
    llm: LLM | None = None,
) -> str:
    """Generate a concise Russian summary of the call session."""
    if not transcript and not any([slots.name, slots.reason, slots.callback_number]):
        return "Звонок без сообщений."

    if llm is not None:
        try:
            system_prompt = _load_system_prompt()
            dialogue_text = "\n".join(f"{s.who}: {s.text}" for s in transcript)
            user_prompt = f"Диалог:\n{dialogue_text}\n\nСлоты: {slots.model_dump(exclude_none=True)}"
            schema = {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            }
            res = await llm.json(system_prompt, user_prompt, schema)
            summary = str(res.get("summary", "")).strip()
            if summary:
                return summary
        except Exception as exc:
            logger.warning("LLM summarization failed, falling back to heuristics: %s", exc)

    return heuristic_summary(slots, transcript)
