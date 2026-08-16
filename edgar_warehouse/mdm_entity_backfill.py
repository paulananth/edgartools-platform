"""Backfill mdm_entity_id on already-resolved silver rows.

mdm-ahead-of-silver map (.scratch/mdm-ahead-of-silver/map.md): parse writes
mdm_entity_id = NULL immediately; this module is the independent sweep that
finds those NULL rows and backfills the real value once MDM has resolved
them. Deliberately read-only against MDM -- it looks up
edgar_warehouse.mdm.database.MdmSourceRef (populated by the existing
resolvers via BaseResolver._register_source) rather than triggering
resolution itself, so it never duplicates run_companies/run_persons/etc.'s
own work. A NULL row with no MdmSourceRef match yet (not resolved by the
most recent MdmRun) is left NULL for a later sweep to pick up.

The 6 target tables' (entity_type, source_system, source_id) conventions
below are copied from the exact values each resolver registers today
(edgar_warehouse/mdm/resolvers/{company,person,security}.py,
edgar_warehouse/mdm/adv_bulk.py, edgar_warehouse/mdm/pipeline.py's
run_companies/run_persons/run_securities call sites) -- if any resolver's
source_id shape changes, this module's _TABLE_SPECS must change with it,
or the lookup silently stops matching and rows never backfill.

SAFETY -- NOT SAFE TO RUN CONCURRENTLY WITH A SHARD WRITER:
_publish_shard_if_remote's ETag guard only protects the instant between its
own baseline read and its promote call, not the whole hydrate-modify-
publish lifecycle a caller like this sweep spans (the baseline is re-read
fresh right before promoting, so it always "matches" trivially unless
something changes in that narrow final window). A window write
(bootstrap/daily-incremental/etc.) landing on the same shard between this
sweep's hydrate and its publish would be silently clobbered, not caught as
a conflict. The caller MUST hold the sec_fetch_active lease (or equivalent
mutual exclusion against the 5 SEC-fetching commands) for this sweep's
entire duration -- see the mdm-ahead-of-silver map, Phase B wiring ticket.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


def _text_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _company_source_id(row: dict) -> str:
    return str(int(row["cik"]))


def _reporting_owner_source_id(row: dict) -> str:
    return f"{row['accession_number']}:{row['owner_index']}"


def _non_derivative_txn_source_id(row: dict) -> str:
    return f"{row['accession_number']}:{row['owner_index']}:{row['txn_index']}"


def _derivative_txn_source_id(row: dict) -> str:
    return f"{row['accession_number']}:derivative:{row['owner_index']}:{row['txn_index']}"


def _adv_filing_source_id(row: dict) -> str:
    return str(row["accession_number"])


def _adv_private_fund_source_id(row: dict) -> str:
    return _text_id(row.get("private_fund_id")) or f"{row['accession_number']}:{row['fund_index']}"


@dataclass(frozen=True)
class _TableSpec:
    table: str
    key_columns: tuple[str, ...]
    select_columns: tuple[str, ...]
    entity_type: str
    source_system: str
    source_id: Callable[[dict], str]


_TABLE_SPECS: tuple[_TableSpec, ...] = (
    _TableSpec(
        table="sec_company",
        key_columns=("cik",),
        select_columns=("cik",),
        entity_type="company",
        source_system="edgar_cik",
        source_id=_company_source_id,
    ),
    _TableSpec(
        table="sec_ownership_reporting_owner",
        key_columns=("accession_number", "owner_index"),
        select_columns=("accession_number", "owner_index"),
        entity_type="person",
        source_system="ownership_filing",
        source_id=_reporting_owner_source_id,
    ),
    _TableSpec(
        table="sec_ownership_non_derivative_txn",
        key_columns=("accession_number", "owner_index", "txn_index"),
        select_columns=("accession_number", "owner_index", "txn_index"),
        entity_type="security",
        source_system="ownership_filing",
        source_id=_non_derivative_txn_source_id,
    ),
    _TableSpec(
        table="sec_ownership_derivative_txn",
        key_columns=("accession_number", "owner_index", "txn_index"),
        select_columns=("accession_number", "owner_index", "txn_index"),
        entity_type="security",
        source_system="ownership_filing",
        source_id=_derivative_txn_source_id,
    ),
    _TableSpec(
        table="sec_adv_filing",
        key_columns=("accession_number",),
        select_columns=("accession_number",),
        entity_type="adviser",
        source_system="adv_filing",
        source_id=_adv_filing_source_id,
    ),
    _TableSpec(
        table="sec_adv_private_fund",
        key_columns=("accession_number", "fund_index"),
        select_columns=("accession_number", "fund_index", "private_fund_id"),
        entity_type="fund",
        source_system="adv_filing",
        source_id=_adv_private_fund_source_id,
    ),
)

MDM_ENTITY_ID_TABLES: tuple[str, ...] = tuple(spec.table for spec in _TABLE_SPECS)

_LOOKUP_CHUNK_SIZE = 500


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _lookup_entity_ids(
    session: Any, *, entity_type: str, source_system: str, source_ids: list[str]
) -> dict[str, str]:
    """Bulk (source_id -> entity_id) lookup against MdmSourceRef, scoped to
    one entity_type + source_system pair (the constant for one table spec).

    Chunked to bound a single IN clause's size, matching the precedent in
    edgar_warehouse/mdm/adv_bulk.py's _existing_source_ids.
    """
    if not source_ids:
        return {}
    from sqlalchemy import select

    from edgar_warehouse.mdm.database import MdmEntity, MdmSourceRef

    result: dict[str, str] = {}
    for chunk in _chunks(source_ids, _LOOKUP_CHUNK_SIZE):
        rows = session.execute(
            select(MdmSourceRef.source_id, MdmSourceRef.entity_id)
            .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
            .where(MdmSourceRef.source_system == source_system)
            .where(MdmSourceRef.source_id.in_(chunk))
            .where(MdmEntity.entity_type == entity_type)
        ).all()
        result.update({source_id: entity_id for source_id, entity_id in rows})
    return result


def backfill_shard_mdm_entity_ids(db: Any, session: Any) -> dict[str, int]:
    """Backfill mdm_entity_id on one open shard's 6 target tables.

    ``db`` is an open SilverDatabase (or any object exposing a DuckDB
    ``._conn``); ``session`` is an open MDM SQLAlchemy Session. Returns
    rows-updated-per-table -- a table absent from the dict, or present with
    0, both mean nothing changed on that table for this shard.
    """
    from edgar_warehouse.silver_support.access import get_connection

    conn = get_connection(db)

    updated_counts: dict[str, int] = {}
    for spec in _TABLE_SPECS:
        cols_sql = ", ".join(_quote_ident(c) for c in spec.select_columns)
        pending = conn.execute(
            f"SELECT {cols_sql} FROM {_quote_ident(spec.table)} WHERE mdm_entity_id IS NULL"
        ).fetchall()
        if not pending:
            updated_counts[spec.table] = 0
            continue

        rows = [dict(zip(spec.select_columns, values)) for values in pending]
        keyed_rows = [(spec.source_id(row), row) for row in rows]
        lookup = _lookup_entity_ids(
            session,
            entity_type=spec.entity_type,
            source_system=spec.source_system,
            source_ids=[source_id for source_id, _ in keyed_rows],
        )

        where_sql = " AND ".join(f"{_quote_ident(k)} = ?" for k in spec.key_columns)
        update_sql = f"UPDATE {_quote_ident(spec.table)} SET mdm_entity_id = ? WHERE {where_sql}"
        updated = 0
        for source_id, row in keyed_rows:
            entity_id = lookup.get(source_id)
            if entity_id is None:
                continue
            conn.execute(update_sql, [entity_id] + [row[k] for k in spec.key_columns])
            updated += 1
        updated_counts[spec.table] = updated
    return updated_counts


def _remaining_null_counts(conn: Any) -> dict[str, int]:
    """COUNT(*) WHERE mdm_entity_id IS NULL per target table, taken right
    after a backfill pass on the same connection. Feeds the
    mdm_entity_backfill_completed event's remaining_null_count -- the signal
    the mdm-ahead-of-silver map's stuck-NULL alarm (ticket 05) watches."""
    counts: dict[str, int] = {}
    for spec in _TABLE_SPECS:
        (count,) = conn.execute(
            f"SELECT COUNT(*) FROM {_quote_ident(spec.table)} WHERE mdm_entity_id IS NULL"
        ).fetchone()
        counts[spec.table] = int(count)
    return counts


def run_mdm_entity_backfill_sweep(context: Any, run_id: str) -> dict[str, Any]:
    """Sweep every shard (or the monolith, when unsharded), backfilling
    mdm_entity_id from MDM's already-resolved MdmSourceRef rows.

    Caller contract: see this module's docstring -- the caller MUST hold
    the sec_fetch_active lease (or equivalent) for the full duration of
    this call, since a concurrent window write to the same shard is not
    otherwise safely detected.
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        WarehouseRuntimeError,
        _emit_pipeline_event,
        _hydrate_all_shards,
        _publish_shard_if_remote,
        _read_shard_manifest,
    )
    from edgar_warehouse.infrastructure.object_storage import PromotionConflictError
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.silver_support.access import get_connection
    from edgar_warehouse.silver_support.session import open_silver_database, open_silver_shard

    mdm_url = os.environ.get("MDM_DATABASE_URL", "").strip()
    if not mdm_url:
        raise WarehouseRuntimeError(
            "MDM_DATABASE_URL is required for backfill-mdm-entity-ids"
        )
    from sqlalchemy.orm import Session

    engine = get_engine(mdm_url)

    started_at = datetime.now(UTC)
    per_shard: list[dict[str, Any]] = []
    totals: dict[str, int] = {table: 0 for table in MDM_ENTITY_ID_TABLES}
    remaining_totals: dict[str, int] = {table: 0 for table in MDM_ENTITY_ID_TABLES}
    conflicts: list[int] = []

    if not context.storage_root.is_remote:
        # Local/dev: single monolith, no shard manifest.
        with Session(engine) as session:
            db = open_silver_database(context.silver_root)
            try:
                counts = backfill_shard_mdm_entity_ids(db, session)
                remaining = _remaining_null_counts(get_connection(db))
            finally:
                db.close()
        for table, count in counts.items():
            totals[table] = totals.get(table, 0) + count
        for table, count in remaining.items():
            remaining_totals[table] = remaining_totals.get(table, 0) + count
        per_shard.append({"shard_index": None, "updated": counts})
        remaining_null_count = sum(remaining_totals.values())
        _emit_pipeline_event(
            "mdm_entity_backfill_completed",
            run_id=run_id,
            totals=totals,
            remaining_null_count=remaining_null_count,
            remaining_by_table=remaining_totals,
            conflicts=len(conflicts),
        )
        return {
            "command": "backfill-mdm-entity-ids",
            "run_id": run_id,
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "shards": per_shard,
            "totals": totals,
            "remaining_null_count": remaining_null_count,
            "remaining_by_table": remaining_totals,
            "conflicts": conflicts,
        }

    manifest = _read_shard_manifest(context)
    shard_paths = _hydrate_all_shards(context)

    with Session(engine) as session:
        for shard_index, local_path in enumerate(shard_paths):
            if local_path is None:
                continue
            db = open_silver_shard(local_path)
            try:
                counts = backfill_shard_mdm_entity_ids(db, session)
                remaining = _remaining_null_counts(get_connection(db))
            finally:
                db.close()
            any_updated = any(counts.values())
            publish_result = None
            if any_updated:
                try:
                    publish_result = _publish_shard_if_remote(context, shard_index)
                except PromotionConflictError:
                    # A concurrent writer touched this shard between our
                    # hydrate and this publish. Our local UPDATE is lost for
                    # this shard this run -- the next sweep re-selects the
                    # same still-NULL rows and retries. Do not abort the
                    # whole sweep over one shard's conflict.
                    conflicts.append(shard_index)
                    publish_result = None
            for table, count in counts.items():
                totals[table] = totals.get(table, 0) + count
            for table, count in remaining.items():
                remaining_totals[table] = remaining_totals.get(table, 0) + count
            per_shard.append(
                {
                    "shard_index": shard_index,
                    "updated": counts,
                    "published": publish_result is not None,
                }
            )

    remaining_null_count = sum(remaining_totals.values())
    _emit_pipeline_event(
        "mdm_entity_backfill_completed",
        run_id=run_id,
        totals=totals,
        remaining_null_count=remaining_null_count,
        remaining_by_table=remaining_totals,
        conflicts=len(conflicts),
    )
    return {
        "command": "backfill-mdm-entity-ids",
        "run_id": run_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "shard_count": manifest.get("shard_count"),
        "shards": per_shard,
        "totals": totals,
        "remaining_null_count": remaining_null_count,
        "remaining_by_table": remaining_totals,
        "conflicts": conflicts,
    }
