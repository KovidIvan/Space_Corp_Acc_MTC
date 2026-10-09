"""Retention-policy integration tests using an isolated SQLite database."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.audit import collect_audit_log
from app.core import db as database
from app.core.retention import delete_expired_calls
from app.models import AgentConfig as AgentConfigRecord
from app.models import AuditEvent, CallRecord, ChatThread


def test_retention_deletes_expired_calls_and_related_chat_but_keeps_audit() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.init_db(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2025, 1, 31, tzinfo=UTC)
    with sessions() as db_session:
        db_session.add(AgentConfigRecord(version=1, config_json={"retention_days": 7}))
        db_session.add_all(
            [
                CallRecord(
                    id="expired-call",
                    started_at=now - timedelta(days=10),
                    ended_at=now - timedelta(days=9),
                    status="completed",
                ),
                CallRecord(
                    id="recent-call",
                    started_at=now - timedelta(days=3),
                    ended_at=now - timedelta(days=2),
                    status="completed",
                ),
                CallRecord(
                    id="unfinished-call",
                    started_at=now - timedelta(days=20),
                    ended_at=None,
                    status="active",
                ),
            ]
        )
        db_session.flush()
        db_session.add(ChatThread(call_id="expired-call", messages_enc="synthetic-encrypted-chat"))
        db_session.commit()

        assert delete_expired_calls(db_session, now) == 1
        remaining_ids = set(db_session.scalars(select(CallRecord.id)))
        assert remaining_ids == {"recent-call", "unfinished-call"}
        assert db_session.get(ChatThread, "expired-call") is None
        event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "retention_delete"))
        assert event is not None
        assert event.details == {"deleted_count": 1, "retention_days": 7}
        assert collect_audit_log(db_session)["chain_valid"] is True

    engine.dispose()
