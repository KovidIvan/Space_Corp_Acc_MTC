"""SQLAlchemy engine, sessions, and metadata setup."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    """Base class for application ORM models."""


def _create_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
    if url.get_backend_name() == "sqlite" and url.database not in {None, ":memory:"}:
        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path
        database_path = database_path.resolve()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(database_path))
    return create_engine(url, connect_args=connect_args)


engine = _create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(target_engine: Engine | None = None) -> None:
    """Create tables declared by the application ORM models."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for a request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
