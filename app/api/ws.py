"""WebSocket call-start consent gate and session dispatcher."""

from fastapi import APIRouter, WebSocket
from sqlalchemy import select

from app.core import db as database
from app.core.consent import has_current_owner_consent
from app.models import AgentConfig as AgentConfigRecord
from app.voice.session import CallSession

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/call")
async def call(websocket: WebSocket) -> None:
    """Reject call starts without current consent and report the unavailable voice pipeline."""
    if not websocket.app.state.settings.dashboard_configured:
        await websocket.close(code=1013, reason="Local dashboard is not configured")
        return

    with database.SessionLocal() as db_session:
        consent_exists = has_current_owner_consent(db_session)
        config_exists = db_session.scalar(select(AgentConfigRecord.id).limit(1)) is not None

    if not consent_exists or not config_exists:
        await websocket.close(code=1008, reason="Current consent and AgentConfig are required")
        return

    await websocket.accept()
<<<<<<< HEAD
=======
    from app.voice.session import CallSession

>>>>>>> 34da9783c58be4a772b28c0903a9f8be978ea23a
    session = CallSession(websocket)
    await session.run()
