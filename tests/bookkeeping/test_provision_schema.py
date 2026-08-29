from __future__ import annotations

from sqlalchemy import create_engine, inspect

from infra.scripts.provision_bookkeeping_schema import provision
from edgar_warehouse.bookkeeping.models import BOOKKEEPING_TABLES


def test_provision_creates_all_11_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    provision(engine)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    assert set(BOOKKEEPING_TABLES) <= existing


def test_provision_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    provision(engine)
    provision(engine)  # must not raise on the second call
    inspector = inspect(engine)
    assert set(BOOKKEEPING_TABLES) <= set(inspector.get_table_names())


def test_provision_skips_grants_on_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    # A role that obviously doesn't exist -- proves grants are skipped
    # entirely for non-Postgres dialects rather than attempting (and
    # failing on) a GRANT statement SQLite doesn't support.
    provision(engine, grant_role="nonexistent_role")
