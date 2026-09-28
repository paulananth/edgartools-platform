"""Retired Bookkeeping connection boundary; archive data is read externally."""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def get_engine(url: str | None = None) -> Engine:
    raise RuntimeError(
        "The Bookkeeping legacy store is retired; use BOOKKEEPING_CLEAN_DATABASE_URL"
    )


def get_session(engine: Engine) -> Session:
    return Session(engine)
