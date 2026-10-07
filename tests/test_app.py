"""Tests for the minimal FastAPI application shell."""

import io
import logging

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app, create_app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_assets_and_templates_are_configured() -> None:
    assert any(route.path == "/static" for route in app.routes)
    assert app.state.templates is not None


def test_application_installs_pii_filter_on_existing_logger_handlers() -> None:
    logger = logging.getLogger("test.runtime-pii-filter")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    old_level = logger.level
    old_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        create_app(Settings(_env_file=None))
        logger.info("caller=%s email=%s code=%s", "+7 (000) 123-45-67", "synthetic@example.test", "1234567890")
        output = stream.getvalue()
        assert "[PHONE]" in output
        assert "[EMAIL]" in output
        assert "[DIGITS]" in output
        assert "+7 (000) 123-45-67" not in output
        assert "synthetic@example.test" not in output
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(old_level)
        logger.propagate = old_propagate
