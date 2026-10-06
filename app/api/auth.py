"""Local owner authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_owner
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.core.security import verify_password
from app.models import Owner

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Authenticate the configured local owner and start a signed session."""
    if not request.app.state.settings.dashboard_configured or "session" not in request.scope:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Заполните настройки владельца и секреты в файле .env."},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    owner = db.scalar(select(Owner).where(Owner.name == username))
    if owner is None or not verify_password(password, owner.password_hash):
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Неверное имя или пароль."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session.clear()
    request.session["owner_id"] = owner.id
    record_audit_event(db, owner.id, "login", "dashboard")
    db.commit()
    return RedirectResponse("/calls", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(
    request: Request,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    """End the owner's signed dashboard session."""
    record_audit_event(db, owner.id, "logout", "dashboard")
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
