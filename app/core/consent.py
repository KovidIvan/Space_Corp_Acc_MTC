"""Owner-consent policy shared by setup and call-start boundaries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Consent

OWNER_CONSENT_VERSION = "owner-consent-v1"
OWNER_CONSENT_TEXT = (
    "Я, как владелец бизнеса, разрешаю ассистенту обрабатывать данные входящих звонков "
    "локально на этом устройстве и сохранять необходимые сведения согласно настройкам хранения. "
    "Я понимаю, что ассистент не будет отвечать на звонки без этого согласия."
)


def has_current_owner_consent(db: Session) -> bool:
    """Return whether the owner accepted the currently active consent text version."""
    return (
        db.scalar(
            select(Consent.id)
            .where(Consent.text_version == OWNER_CONSENT_VERSION)
            .order_by(Consent.accepted_at.desc())
            .limit(1)
        )
        is not None
    )
