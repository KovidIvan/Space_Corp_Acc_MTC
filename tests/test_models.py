"""Tests for SQLAlchemy model registration."""

from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.core.db import Base, init_db


def test_all_architecture_tables_are_registered() -> None:
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    assert set(inspect(engine).get_table_names()) == {
        "owner",
        "agent_config",
        "consent",
        "call",
        "audit_event",
        "telegram_link",
        "chat_thread",
        "wizard_run",
    }
    Base.metadata.drop_all(engine)
