"""Tests for the minimal FastAPI application shell."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_assets_and_templates_are_configured() -> None:
    assert any(route.path == "/static" for route in app.routes)
    assert app.state.templates is not None
