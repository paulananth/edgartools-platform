"""Idempotent provisioning for the Change Ledger (acquisition) Postgres tables.

Applies the existing MDM-owned SQL migrations that create the source-fetch,
processing, registry, and evidence-import tables (013, 014, 015, 017, 018)
against a dedicated engine. This is the Change Ledger counterpart of
``provision_bookkeeping_schema.py``.

It does not apply MDM domain/registry migrations or graph-generation DDL
(016, 019–022). Those stay on the MDM database.

Usage:
    uv run python infra/scripts/provision_change_ledger_schema.py \
        --database-url "$CHANGE_LEDGER_DATABASE_URL"
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text
from sqlalchemy.engine import Engine

from edgar_warehouse.acquisition.database import get_engine
from edgar_warehouse.mdm.migrations.runtime import (
    _apply_acquisition_ledger_migration,
    _apply_exclusion_and_evidence_import_migration,
    _apply_source_evidence_conflict_migration,
    _apply_source_fetch_validators_migration,
    _apply_source_registry_migration,
)

CHANGE_LEDGER_TABLES: tuple[str, ...] = (
    "source_observation_cursor",
    "source_fetch_decision",
    "source_fetch_work",
    "source_fetch_transition",
    "source_revision",
    "source_processing_decision",
    "source_expected_producer",
    "source_registry_version",
    "source_registry_coverage",
    "source_evidence_conflict",
    "source_evidence_import",
)


def provision(engine: Engine) -> None:
    """Apply Change Ledger migrations. Idempotent on PostgreSQL."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    _apply_acquisition_ledger_migration(engine)
    _apply_source_registry_migration(engine)
    _apply_source_evidence_conflict_migration(engine)
    _apply_exclusion_and_evidence_import_migration(engine)
    _apply_source_fetch_validators_migration(engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN; defaults to CHANGE_LEDGER_DATABASE_URL, then MDM_DATABASE_URL.",
    )
    args = parser.parse_args(argv)

    engine = get_engine(args.database_url)
    provision(engine)
    sys.stderr.write(f"Provisioned {len(CHANGE_LEDGER_TABLES)} Change Ledger tables.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
