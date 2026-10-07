"""WebSocket call-start consent gate and session dispatcher."""

from fastapi import APIRouter, WebSocket
from sqlalchemy import select

from app.core import db as database
from app.core.consent import has_current_owner_consent
from app.models import AgentConfig as AgentConfigRecord
from app.voice.protocol import ServerError
from app.voice.session import CallSession

router = APIRouter(prefix="/ws", tags=["websocket"])


async def _reject_call(websocket: WebSocket, error: ServerError, close_code: int, reason: str) -> None:
    await websocket.accept()
    await websocket.send_text(error.model_dump_json())
    await websocket.close(code=close_code, reason=reason)


@router.websocket("/call")
async def call(websocket: WebSocket) -> None:
    """Reject call starts without current consent and report the unavailable voice pipeline."""
    if not websocket.app.state.settings.dashboard_configured:
        await _reject_call(
            websocket,
            ServerError(code="internal", message="Сервис не настроен. Завершите локальную настройку."),
            1013,
            "Local dashboard is not configured",
        )
        return

    with database.SessionLocal() as db_session:
        consent_exists = has_current_owner_consent(db_session)
        config_exists = db_session.scalar(select(AgentConfigRecord.id).limit(1)) is not None

    if not consent_exists:
        await _reject_call(
            websocket,
            ServerError(
                code="consent_missing",
                message="Согласие владельца не сохранено. Завершите шаг согласия в мастере настройки.",
            ),
            1008,
            "Current consent is required",
        )
        return

    if not config_exists:
        await _reject_call(
            websocket,
            ServerError(
                code="internal",
                message="Конфигурация ассистента не найдена. Завершите мастер настройки.",
            ),
            1008,
            "AgentConfig is required",
        )
        return

    await websocket.accept()
    session = CallSession(websocket)
    await session.run()
