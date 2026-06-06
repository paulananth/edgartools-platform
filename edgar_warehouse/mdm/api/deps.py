"""Shared FastAPI dependencies: DB session."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import get_engine, get_session


_engine = None


def get_db() -> Iterator[Session]:
    global _engine
    if _engine is None:
        _engine = get_engine()
    s = get_session(_engine)
    try:
        yield s
    finally:
        s.close()
