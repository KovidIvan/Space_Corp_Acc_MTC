"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.api import audit, auth, calls, config, dashboard, stats, wizard, ws
from app.channels.telegram import TelegramChannel
from app.core import db as database
from app.core.bootstrap import ensure_owner_account
from app.core.config import Settings, settings
from app.core.demo_data import seed_demo_calls

WEB_DIR = Path(__file__).parent / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

def create_app(runtime_settings: Settings = settings) -> FastAPI:
    """Create the dashboard application with local-only account bootstrap."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runtime_settings.dashboard_configured:
            database.init_db()
            with database.SessionLocal() as db_session:
                ensure_owner_account(db_session, runtime_settings)
                encryption_key = runtime_settings.data_encryption_key
                if encryption_key is not None:
                    seed_demo_calls(db_session, encryption_key.get_secret_value())
            telegram_channel = application.state.telegram_channel
            if telegram_channel is not None:
                await telegram_channel.start()
        try:
            yield
        finally:
            telegram_channel = application.state.telegram_channel
            if telegram_channel is not None and runtime_settings.dashboard_configured:
                await telegram_channel.stop()

    application = FastAPI(title="Локальный помощник звонков", lifespan=lifespan)
    application.state.settings = runtime_settings
    telegram_token = runtime_settings.telegram_bot_token
    application.state.telegram_channel = (
        TelegramChannel(telegram_token.get_secret_value(), session_factory=database.SessionLocal)
        if telegram_token is not None and telegram_token.get_secret_value()
        else None
    )
    application.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    if runtime_settings.session_secret and runtime_settings.session_secret.get_secret_value():
        application.add_middleware(
            SessionMiddleware,
            secret_key=runtime_settings.session_secret.get_secret_value(),
            same_site="strict",
            https_only=False,
        )

    for api_router in (
        dashboard.router,
        calls.router,
        config.router,
        wizard.router,
        auth.router,
        wizard.web_router,
        stats.router,
        audit.router,
        ws.router,
    ):
        application.include_router(api_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        """Return the process liveness status."""
        return {"status": "ok"}

    return application


app = create_app()
