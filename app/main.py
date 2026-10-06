"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import audit, auth, calls, config, stats, wizard, ws

WEB_DIR = Path(__file__).parent / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="Локальный помощник звонков")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)

for api_router in (calls.router, config.router, wizard.router, auth.router, stats.router, audit.router, ws.router):
    app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the process liveness status."""
    return {"status": "ok"}
