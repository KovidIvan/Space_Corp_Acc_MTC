"""Five-step business setup wizard and consent capture."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.config import save_agent_config_version
from app.api.dependencies import require_owner
from app.core.audit import record_audit_event
from app.core.consent import OWNER_CONSENT_TEXT, OWNER_CONSENT_VERSION
from app.core.db import get_db
from app.models import AgentConfig as AgentConfigRecord
from app.models import Consent, Owner, WizardRun
from app.schemas import AgentConfig

router = APIRouter(prefix="/api/wizard", tags=["wizard"])
web_router = APIRouter(tags=["setup-wizard"])


class WizardCompletion(BaseModel):
    """Validated wizard submission with an explicit owner-consent decision."""

    agent_config: AgentConfig
    consent_accepted: bool


def _owner_or_login(request: Request, db: Session) -> Owner | RedirectResponse:
    if "session" not in request.scope:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    owner_id = request.session.get("owner_id")
    owner = db.get(Owner, owner_id) if owner_id else None
    if owner is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return owner


def _start_wizard_run(request: Request, db: Session) -> WizardRun:
    run_id = request.session.get("wizard_run_id")
    run = db.get(WizardRun, run_id) if run_id else None
    if run is None or run.finished_at is not None:
        run = WizardRun(started_at=datetime.now(UTC))
        db.add(run)
        db.commit()
        db.refresh(run)
        request.session["wizard_run_id"] = run.id
    return run


def _elapsed_seconds(run: WizardRun, finished_at: datetime) -> float:
    started_at = run.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return max(0.0, round((finished_at - started_at).total_seconds(), 2))


@web_router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
def setup_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render the five-step setup wizard and persist its start time."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner

    run = _start_wizard_run(request, db)
    latest = db.scalar(select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1))
    saved = latest.config_json if latest else {}
    business_owner = saved.get("owner", {})
    working_hours = saved.get("working_hours", {}) or {}
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="setup_wizard.html",
        context={
            "request": request,
            "owner": owner,
            "wizard_run_id": run.id,
            "wizard_seconds": _elapsed_seconds(run, datetime.now(UTC)),
            "consent_text": OWNER_CONSENT_TEXT,
            "consent_version": OWNER_CONSENT_VERSION,
            "values": {
                "owner_name": business_owner.get("name", owner.name),
                "owner_company": business_owner.get("company", owner.company),
                "owner_role": business_owner.get("role", ""),
                "template": saved.get("template", "small_business"),
                "greeting": saved.get("greeting", "Здравствуйте! Вы позвонили в компанию. Чем могу помочь?"),
                "disclosure": saved.get(
                    "disclosure",
                    "Я ИИ-ассистент. Разговор записывается и обрабатывается локально для передачи сообщения владельцу.",
                ),
                "closing": saved.get("closing", "Спасибо за звонок. Всего доброго!"),
                "handoff_number": saved.get("handoff_number", ""),
                "vip_numbers": "",
                "saved_vip_hashes": saved.get("vip_numbers", []),
                "timezone": working_hours.get("tz", "Europe/Minsk"),
                "work_start": working_hours.get("start", "09:00"),
                "work_end": working_hours.get("end", "18:00"),
                "working_days": working_hours.get("days", [1, 2, 3, 4, 5]),
                "working_hours": working_hours,
            },
        },
    )


@web_router.get("/setup/complete", response_class=HTMLResponse, include_in_schema=False)
def setup_complete_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Show setup completion and the locally recorded duration."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    latest_run = db.scalar(select(WizardRun).order_by(WizardRun.started_at.desc()).limit(1))
    latest_config = db.scalar(
        select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1)
    )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="setup_complete.html",
        context={
            "request": request,
            "owner": owner,
            "seconds": latest_run.seconds if latest_run and latest_run.seconds is not None else 0,
            "config_version": latest_config.version if latest_config else 0,
            "consent_text": OWNER_CONSENT_TEXT,
        },
    )


@router.post("/start")
def start_wizard(
    request: Request,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Start or resume an unfinished timed wizard run."""
    run = _start_wizard_run(request, db)
    return {"run_id": run.id, "started_at": run.started_at.isoformat()}


@router.post("/complete")
def complete_wizard(
    submission: WizardCompletion,
    request: Request,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | float | int]:
    """Save a validated config, accepted consent, and the persisted wizard duration."""
    if not submission.consent_accepted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Необходимо принять согласие, чтобы завершить настройку.",
        )

    run_id = request.session.get("wizard_run_id")
    run = db.get(WizardRun, run_id) if run_id else None
    if run is None or run.finished_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Сессия мастера настройки не найдена")

    encryption_key = request.app.state.settings.data_encryption_key
    if encryption_key is None or not encryption_key.get_secret_value():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Encryption is not configured")

    config_record = save_agent_config_version(db, submission.agent_config, encryption_key.get_secret_value())
    finished_at = datetime.now(UTC)
    run.finished_at = finished_at
    run.seconds = _elapsed_seconds(run, finished_at)
    db.add(
        Consent(
            text_version=OWNER_CONSENT_VERSION,
            accepted_at=finished_at,
        )
    )
    record_audit_event(db, owner.id, "config_change", "agent_config", {"version": config_record.version})
    db.flush()
    record_audit_event(db, owner.id, "consent", OWNER_CONSENT_VERSION, {"accepted": True})
    db.commit()
    request.session.pop("wizard_run_id", None)
    return {
        "redirect_url": "/setup/complete",
        "seconds": run.seconds,
        "config_version": config_record.version,
    }
