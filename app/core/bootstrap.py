"""Local owner-account bootstrap for the dashboard."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models import Owner


def ensure_owner_account(db: Session, settings: Settings) -> Owner:
    """Create the local owner account once, without overwriting existing credentials."""
    owner = db.scalar(select(Owner).order_by(Owner.created_at).limit(1))
    if owner is not None:
        if owner.name != settings.owner_name:
            raise RuntimeError("OWNER_NAME does not match the existing local owner account")
        return owner

    if not settings.owner_name or not settings.owner_company or settings.owner_password is None:
        raise RuntimeError("Set OWNER_NAME, OWNER_COMPANY, and OWNER_PASSWORD in .env")

    owner = Owner(
        name=settings.owner_name,
        company=settings.owner_company,
        password_hash=hash_password(settings.owner_password.get_secret_value()),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner
