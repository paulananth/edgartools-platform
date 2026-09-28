"""Retired Change Ledger connection boundary; archive data is read externally."""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def get_engine(url: str | None = None) -> Engine:
    raise RuntimeError(
        "The Change Ledger connection is retired; submit frozen source/feed work "
        "through Rules, Bookkeeping and Change Journal"
    )


def get_session(engine: Engine) -> Session:
    return Session(engine)
