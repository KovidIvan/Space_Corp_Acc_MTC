"""Versioned AgentConfig API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_owner
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.core.security import hash_vip_number
from app.models import AgentConfig as AgentConfigRecord
from app.models import Owner
from app.schemas import AgentConfig

router = APIRouter(prefix="/api/config", tags=["config"])


def save_agent_config_version(
    db: Session,
    config: AgentConfig,
    encryption_key: str,
) -> AgentConfigRecord:
    """Append a validated AgentConfig version with VIP numbers stored as keyed hashes."""
    latest = db.scalar(select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1))
    version = latest.version + 1 if latest else 1
    config_data: dict[str, Any] = config.model_dump(mode="json", exclude_none=True)
    config_data["version"] = version
    try:
        config_data["vip_numbers"] = [
            hash_vip_number(number, encryption_key) for number in config_data.get("vip_numbers", [])
        ]
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    config_record = AgentConfigRecord(version=version, config_json=config_data)
    db.add(config_record)
    db.flush()
    return config_record


@router.get("")
def get_agent_config(
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Return the latest saved AgentConfig version."""
    config = db.scalar(select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1))
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AgentConfig is not configured")
    record_audit_event(db, owner.id, "view", "agent_config", {"version": config.version})
    db.commit()
    return config.config_json


@router.post("", status_code=status.HTTP_201_CREATED)
@router.put("")
def create_agent_config(
    config: AgentConfig,
    request: Request,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Create a new immutable version of the validated AgentConfig."""
    key = request.app.state.settings.data_encryption_key
    if key is None or not key.get_secret_value():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Encryption is not configured")

    saved = save_agent_config_version(db, config, key.get_secret_value())
    record_audit_event(db, owner.id, "config_change", "agent_config", {"version": saved.version})
    db.commit()
    return saved.config_json


@router.delete("/{version}")
def delete_agent_config_version(
    version: int,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    """Remove the current config version, allowing an audited rollback to its predecessor."""
    config = db.scalar(select(AgentConfigRecord).where(AgentConfigRecord.version == version))
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AgentConfig version not found")

    latest = db.scalar(select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1))
    if latest is None or latest.version != version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only the current AgentConfig version can be removed",
        )

    db.delete(config)
    record_audit_event(db, owner.id, "config_change", "agent_config", {"deleted_version": version})
    db.commit()
    return {"deleted_version": version}
