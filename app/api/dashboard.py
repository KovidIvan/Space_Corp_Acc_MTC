"""Server-rendered dashboard pages."""

import json
from typing import Annotated

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit import collect_audit_log
from app.api.calls import _call_query
from app.api.stats import collect_call_stats
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.core.security import decrypt_text
from app.models import AgentConfig as AgentConfigRecord
from app.models import CallRecord, Owner

router = APIRouter(tags=["dashboard"])

INTENT_LABELS = {
    "client": "Клиент",
    "partner": "Партнёр",
    "vendor_sales": "Продажи",
    "spam": "Спам",
    "job_candidate": "Кандидат",
    "other": "Другое",
    "unclear": "Не определено",
}
URGENCY_LABELS = {"high": "Высокая", "normal": "Обычная", "low": "Низкая"}
ACTION_LABELS = {
    "answer_faq": "Ответ на вопрос",
    "take_message": "Принять сообщение",
    "offer_chat": "Предложить чат",
    "handoff": "Передать менеджеру",
    "decline": "Вежливый отказ",
}


def _owner_or_login(request: Request, db: Session) -> Owner | RedirectResponse:
    if "session" not in request.scope:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    owner_id = request.session.get("owner_id")
    owner = db.get(Owner, owner_id) if owner_id else None
    if owner is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return owner


def _handled_filter(value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _render_call_rows(request: Request, db: Session, urgency: str | None, intent: str | None, handled: str | None):
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    calls = _call_query(db, urgency, intent, _handled_filter(handled))
    record_audit_event(db, owner.id, "view", "calls")
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="call_rows.html",
        context={"request": request, "calls": calls, "intent_labels": INTENT_LABELS, "urgency_labels": URGENCY_LABELS},
    )


@router.get("/", include_in_schema=False)
def home(request: Request) -> RedirectResponse:
    """Send the visitor to the login page or the call list."""
    if "session" in request.scope and request.session.get("owner_id"):
        return RedirectResponse("/calls", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> HTMLResponse:
    """Render the local owner login page."""
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "owner": None, "configured": request.app.state.settings.dashboard_configured},
    )


@router.get("/calls", response_class=HTMLResponse, include_in_schema=False)
def calls_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    urgency: str | None = None,
    intent: str | None = None,
    handled: str | None = None,
) -> Response:
    """Render the filtered local call list."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    calls = _call_query(db, urgency, intent, _handled_filter(handled))
    record_audit_event(db, owner.id, "view", "calls")
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="calls.html",
        context={
            "request": request,
            "owner": owner,
            "calls": calls,
            "call_count": len(calls),
            "urgency": urgency or "",
            "intent": intent or "",
            "handled": handled or "",
            "intent_labels": INTENT_LABELS,
            "urgency_labels": URGENCY_LABELS,
        },
    )


@router.get("/audit", response_class=HTMLResponse, include_in_schema=False)
def audit_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render the recent audit log and verify the complete hash chain."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    record_audit_event(db, owner.id, "view", "audit")
    db.flush()
    audit_log = collect_audit_log(db)
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="audit.html",
        context={"request": request, "owner": owner, "audit_log": audit_log},
    )


@router.get("/calls/rows", response_class=HTMLResponse, include_in_schema=False)
def calls_rows(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    urgency: str | None = None,
    intent: str | None = None,
    handled: str | None = None,
) -> Response:
    """Render the call-list fragment requested by HTMX."""
    return _render_call_rows(request, db, urgency, intent, handled)


@router.get("/calls/{call_id}", response_class=HTMLResponse, include_in_schema=False)
def call_detail(
    call_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render one call with its locally decrypted transcript and summary."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    call = db.get(CallRecord, call_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    encryption_key = request.app.state.settings.data_encryption_key
    if encryption_key is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Dashboard is not configured")
    try:
        transcript = json.loads(decrypt_text(call.transcript_enc, encryption_key.get_secret_value())) if call.transcript_enc else []
        summary = decrypt_text(call.summary_enc, encryption_key.get_secret_value()) if call.summary_enc else ""
    except (InvalidToken, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Call data could not be read") from error

    record_audit_event(db, owner.id, "view", call.id)
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="call_detail.html",
        context={
            "request": request,
            "owner": owner,
            "call": call,
            "transcript": transcript,
            "summary": summary,
            "intent_labels": INTENT_LABELS,
            "urgency_labels": URGENCY_LABELS,
            "action_labels": ACTION_LABELS,
        },
    )


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render authenticated scenario and routing editors for the active config."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    config = db.scalar(select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1))
    if config is None:
        return RedirectResponse("/setup", status_code=status.HTTP_303_SEE_OTHER)

    record_audit_event(db, owner.id, "view", "agent_config", {"version": config.version})
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "request": request,
            "owner": owner,
            "config": config.config_json,
            "config_version": config.version,
        },
    )


@router.get("/stats", response_class=HTMLResponse, include_in_schema=False)
def stats_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render aggregate call statistics for the authenticated owner."""
    owner = _owner_or_login(request, db)
    if isinstance(owner, RedirectResponse):
        return owner
    stats = collect_call_stats(db)
    record_audit_event(db, owner.id, "view", "stats")
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={
            "request": request,
            "owner": owner,
            "stats": stats,
            "intent_labels": INTENT_LABELS,
            "urgency_labels": URGENCY_LABELS,
        },
    )
