"""SQLAlchemy engine/session plumbing for the bookkeeping store.

Mirrors edgar_warehouse.mdm.database's skeleton (Base, connection-settings-
from-env, session factory) -- not its models. See that module for the
precedent this deliberately follows.

Instantiation convention for application code (DuckDB Retirement Cutover
Ticket 03): this module deliberately exposes only the bare get_engine/
get_session primitives, no shared factory -- matching edgar_warehouse.mdm.
database's own convention, which also has none at this level. Every module
consuming BookkeepingStore should define its own tiny, module-local
one-liner, mirroring edgar_warehouse/mdm/cli.py's existing
`def _session() -> Session: return get_session(get_engine())`:

    def _bookkeeping_store() -> BookkeepingStore:
        return BookkeepingStore(get_session(get_engine()))

Not a new shared cross-module utility, not a DI container -- each
consuming module gets its own minimal wrapper, the same way MDM's own CLI
handlers each define their own `_session()` rather than importing a shared
one.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def get_engine(url: str | None = None) -> Engine:
    """Create the bookkeeping store's engine.

    Pool sizing intentionally uses SQLAlchemy's own defaults (pool_size=5,
    max_overflow=10) rather than mirroring MDM's tuned 40/20 -- MDM's pool was
    raised specifically for its 16-way-concurrent entity-resolution worker
    pools (see edgar_warehouse.mdm.database.get_engine's own comment); this
    store has no equivalent concurrency requirement today.
    """
    url = url or os.environ["BOOKKEEPING_DATABASE_URL"]
    kwargs: dict = {"pool_pre_ping": True}
    engine = create_engine(url, **kwargs)
    # Deliberately no install_mdm_sql_logging(engine) call here (unlike
    # edgar_warehouse.mdm.database.get_engine) -- that hook emits
    # mdm_sql_started/mdm_sql_completed events under the MDM_SQL_CALL_LOGGING
    # env var, genuinely scoped to MDM's own observability, not a generic
    # SQL-logging utility this store could reuse without mislabeling events.
    return engine


def get_session(engine: Engine) -> Session:
    return Session(engine)
