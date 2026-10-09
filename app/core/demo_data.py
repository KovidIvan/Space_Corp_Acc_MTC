"""Synthetic local dashboard records for an offline demonstration."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import encrypt_text
from app.models import AuditEvent, CallRecord

_DEMO_CALLS: tuple[dict[str, Any], ...] = (
    {
        "caller_masked": "+7 *** ***-12-34",
        "intent": "client",
        "urgency": "high",
        "action": "take_message",
        "handled": False,
        "summary": "Клиенту нужно обсудить договор до пятницы. Просит перезвонить.",
        "slots": {"name": "Синтетический клиент", "reason": "Обсудить договор", "deadline": "пятница"},
        "transcript": [
            {
                "who": "caller",
                "text": "Здравствуйте, звоню по договору, нужно обсудить до пятницы.",
                "words": [
                    {"w": "Здравствуйте,", "p": 0.98},
                    {"w": "звоню", "p": 0.95},
                    {"w": "по", "p": 0.97},
                    {"w": "договору,", "p": 0.91},
                    {"w": "нужно", "p": 0.9},
                    {"w": "обсудить", "p": 0.88},
                    {"w": "до", "p": 0.94},
                    {"w": "пятницы.", "p": 0.52},
                ],
            },
            {"who": "agent", "text": "Передам сообщение и попрошу перезвонить."},
        ],
    },
    {
        "caller_masked": "+7 *** ***-23-45",
        "intent": "vendor_sales",
        "urgency": "low",
        "action": "decline",
        "handled": True,
        "summary": "Предложение услуг. Срочного ответа не требуется.",
        "slots": {"reason": "Коммерческое предложение"},
        "transcript": [
            {"who": "caller", "text": "Предлагаем услуги продвижения для вашей компании."},
            {"who": "agent", "text": "Спасибо, сейчас это неактуально."},
        ],
    },
    {
        "caller_masked": "+7 *** ***-34-56",
        "intent": "partner",
        "urgency": "normal",
        "action": "take_message",
        "handled": False,
        "summary": "Партнёр предлагает согласовать время встречи на следующей неделе.",
        "slots": {"reason": "Согласовать встречу", "deadline": "следующая неделя"},
        "transcript": [
            {"who": "caller", "text": "Давайте согласуем встречу на следующей неделе."},
            {"who": "agent", "text": "Записал, передам просьбу владельцу."},
        ],
    },
    {
        "caller_masked": "+7 *** ***-45-67",
        "intent": "unclear",
        "urgency": "low",
        "action": "offer_chat",
        "handled": True,
        "summary": "Причина звонка не распознана; предложено продолжить общение в чате.",
        "slots": {"reason": "Не удалось определить"},
        "transcript": [
            {
                "who": "caller",
                "text": "Я по тому вопросу, который обсуждали раньше.",
                "words": [
                    {"w": "Я", "p": 0.94},
                    {"w": "по", "p": 0.91},
                    {"w": "тому", "p": 0.57},
                    {"w": "вопросу,", "p": 0.92},
                    {"w": "который", "p": 0.89},
                    {"w": "обсуждали", "p": 0.86},
                    {"w": "раньше.", "p": 0.93},
                ],
            },
            {"who": "agent", "text": "Можно написать подробнее в чате."},
        ],
    },
    {
        "caller_masked": "+7 *** ***-56-78",
        "intent": "client",
        "urgency": "high",
        "action": "handoff",
        "handled": False,
        "summary": "Клиент просит срочно соединить с менеджером.",
        "slots": {"reason": "Запрос менеджера"},
        "transcript": [
            {"who": "caller", "text": "Соедините меня с менеджером, пожалуйста."},
            {"who": "agent", "text": "Понял, передаю срочный запрос."},
        ],
    },
)


def seed_demo_calls(db: Session, encryption_key: str) -> int:
    """Seed demo calls only for a fresh database that has never explicitly purged calls."""
    if db.scalar(select(CallRecord.id).limit(1)) is not None or db.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.target == "calls",
            AuditEvent.action.in_(["delete", "retention_delete"]),
        )
        .limit(1)
    ) is not None:
        return 0

    now = datetime.now(UTC)
    for index, item in enumerate(_DEMO_CALLS):
        started_at = now - timedelta(minutes=(index + 1) * 17)
        transcript = json.dumps(item["transcript"], ensure_ascii=False)
        slots = json.dumps(item["slots"], ensure_ascii=False)
        db.add(
            CallRecord(
                id=f"demo-call-{index + 1}",
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=2 + index),
                caller_masked=item["caller_masked"],
                status="completed",
                intent=item["intent"],
                urgency=item["urgency"],
                action=item["action"],
                handled=item["handled"],
                edited=False,
                no_record=False,
                transcript_enc=encrypt_text(transcript, encryption_key),
                summary_enc=encrypt_text(item["summary"], encryption_key),
                slots_enc=encrypt_text(slots, encryption_key),
            )
        )
    db.commit()
    return len(_DEMO_CALLS)
