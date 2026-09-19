"""SQLAlchemy engine plumbing for the Change Ledger (acquisition ledger).

Mirrors ``edgar_warehouse.bookkeeping.database``: a dedicated connection
for operational ledger tables that are not MDM entities.

Production still hosts these tables on the MDM Postgres instance, so
``CHANGE_LEDGER_DATABASE_URL`` falls back to ``MDM_DATABASE_URL`` when
unset. Local work can point the Change Ledger at its own database.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def get_engine(url: str | None = None) -> Engine:
    """Create the Change Ledger engine.

    Resolution order: explicit ``url``, then ``CHANGE_LEDGER_DATABASE_URL``,
    then ``MDM_DATABASE_URL`` (the production co-hosted layout).
    """
    url = url or os.environ.get("CHANGE_LEDGER_DATABASE_URL") or os.environ["MDM_DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def get_session(engine: Engine) -> Session:
    return Session(engine)
