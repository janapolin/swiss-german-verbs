"""Engine/session factory (§3). SQLite single-file DB; ORM wraps all access (§2)
so a later move to Postgres is a config change, not a rewrite.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "app.db"


def database_url(db_path: Path | str | None = None) -> str:
    """The SQLAlchemy URL to use — `SWISSVERB_DB_PATH` env var overrides the default (§15)."""
    if db_path is None:
        db_path = os.environ.get("SWISSVERB_DB_PATH", str(DEFAULT_DB_PATH))
    return f"sqlite:///{db_path}"


def make_engine(db_path: Path | str | None = None) -> Engine:
    url = database_url(db_path)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Module-level defaults the app wires up at startup; tests build their own via
# make_engine()/make_session_factory() against a temp/in-memory DB instead.
engine: Engine = make_engine()
SessionLocal: sessionmaker[Session] = make_session_factory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session, committing on success, rolling back
    on error, and always closing — so routes/services never have to manage
    transactions themselves (§15: routes are thin)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
