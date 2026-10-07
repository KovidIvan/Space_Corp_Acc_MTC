"""Tests for database engine configuration."""

from pathlib import Path

import pytest

from app.core.db import _create_engine


def test_relative_sqlite_url_is_resolved_from_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    engine = _create_engine("sqlite:///./data/callagent.db")
    try:
        expected_path = Path(__file__).resolve().parents[1] / "data" / "callagent.db"
        assert Path(engine.url.database).resolve() == expected_path.resolve()
    finally:
        engine.dispose()
