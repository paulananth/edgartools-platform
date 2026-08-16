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

Ticket 06 (.scratch/mdm-ahead-of-silver/issues/06-narrow-backfill-storage-target.md):
Snowflake only, full-row re-emission -- DuckDB is no longer read or written
by this sweep at all. Reads pending rows (mdm_entity_id IS NULL) directly
from the collapsed EDGARTOOLS_SILVER dynamic tables (the same view gold/dbt
consumes), looks up the resolved entity_id from MDM Postgres (unchanged),
and re-emits a COMPLETE row (every column, not just the key) with
mdm_entity_id filled, via the same LandingExportBuffer/Snowpipe append-only
path every other silver write uses. Full-row, not thin: a thin append would
rely on the dbt collapse being column-wise for mdm_entity_id, and it isn't
-- QUALIFY row_number()=1 still picks exactly one winning row for every
column not itself wrapped in LAST_VALUE(...IGNORE NULLS), so a thin row
still nulls out every other column once it has the newest parse_sequence.
See .scratch/silver-landing-coalesce-bug/issues/01-thin-backfill-nulls-other-columns.md
for the empirical reproduction of why that's unsafe (found live in
sec_accounting_flag's own partial-score backfill, independent of this map).

The 6 target tables' (entity_type, source_system, source_id) conventions
below are copied from the exact values each resolver registers today
(edgar_warehouse/mdm/resolvers/{company,person,security}.py,
edgar_warehouse/mdm/adv_bulk.py, edgar_warehouse/mdm/pipeline.py's
run_companies/run_persons/run_securities call sites) -- if any resolver's
source_id shape changes, this module's _TABLE_SPECS must change with it,
or the lookup silently stops matching and rows never backfill.

Residual race, accepted not solved (ticket 06's Answer): the SELECT (read
pending rows) and the later Snowpipe-ingested INSERT are not atomic. A
genuinely concurrent write to the same business key in that window could
have its data staled-over by this sweep's re-emission (this sweep's row
gets mdm_entity_id right but wins the QUALIFY collapse with column values
read before the concurrent write). Mitigated by keeping the window short
(no work between the SELECT and the flush beyond the fast Postgres lookup),
not solved with a lock -- matching this repo's existing "accept a narrow,
bounded risk over new distributed locking infrastructure" precedent
(snowflake-daily-load-trigger map, ticket 02).
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from datetime import UTC, datetime
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
    entity_type: str
    source_system: str
    source_id: Callable[[dict], str]


_TABLE_SPECS: tuple[_TableSpec, ...] = (
    _TableSpec(
        table="sec_company",
        entity_type="company",
        source_system="edgar_cik",
        source_id=_company_source_id,
    ),
    _TableSpec(
        table="sec_ownership_reporting_owner",
        entity_type="person",
        source_system="ownership_filing",
        source_id=_reporting_owner_source_id,
    ),
    _TableSpec(
        table="sec_ownership_non_derivative_txn",
        entity_type="security",
        source_system="ownership_filing",
        source_id=_non_derivative_txn_source_id,
    ),
    _TableSpec(
        table="sec_ownership_derivative_txn",
        entity_type="security",
        source_system="ownership_filing",
        source_id=_derivative_txn_source_id,
    ),
    _TableSpec(
        table="sec_adv_filing",
        entity_type="adviser",
        source_system="adv_filing",
        source_id=_adv_filing_source_id,
    ),
    _TableSpec(
        table="sec_adv_private_fund",
        entity_type="fund",
        source_system="adv_filing",
        source_id=_adv_private_fund_source_id,
    ),
)

MDM_ENTITY_ID_TABLES: tuple[str, ...] = tuple(spec.table for spec in _TABLE_SPECS)

_LOOKUP_CHUNK_SIZE = 500


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


def _silver_connection_settings() -> Any:
    """Snowflake connection settings for the EDGARTOOLS_SILVER schema.

    Reuses mdm/export.py's env/secret resolution (MDM_SNOWFLAKE_* /
    DBT_SNOWFLAKE_* / ~/.snowflake/connections.toml) -- that module's own
    default schema is EDGARTOOLS_GOLD (the MDM export target), so this
    overrides just the schema to the silver landing zone's dbt target
    (DBT_SILVER_SCHEMA, matching dbt_project.yml's own default).
    """
    from edgar_warehouse.mdm.export import SnowflakeConnectionSettings

    settings = SnowflakeConnectionSettings.from_env()
    silver_schema = os.environ.get("DBT_SILVER_SCHEMA", "EDGARTOOLS_SILVER")
    return dataclasses.replace(settings, schema=silver_schema)


def _fetch_pending_rows(connection: Any, spec: _TableSpec) -> list[dict[str, Any]]:
    """Every column of every row where mdm_entity_id IS NULL, read from the
    already-collapsed EDGARTOOLS_SILVER dynamic table -- the same view
    gold/dbt reads, so "pending" here matches what downstream consumers
    actually see today. Column names lowercased to match this module's
    source_id functions (row["cik"]-style) -- Snowflake's connector returns
    uppercase names for unquoted identifiers by default.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT * FROM {spec.table.upper()} WHERE mdm_entity_id IS NULL")
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def backfill_pending_rows(connection: Any, session: Any, landing_export: Any) -> dict[str, dict[str, int]]:
    """One pass over all 6 target tables: read pending (mdm_entity_id IS
    NULL) rows from Snowflake, resolve against MDM, record full-row
    (mdm_entity_id filled) re-emissions into landing_export for whatever
    matched.

    Returns {table: {"pending": N, "resolved": N}} -- resolved <= pending;
    the gap is rows with no MdmSourceRef match yet (left NULL for the next
    pass).
    """
    counts: dict[str, dict[str, int]] = {}
    for spec in _TABLE_SPECS:
        rows = _fetch_pending_rows(connection, spec)
        counts[spec.table] = {"pending": len(rows), "resolved": 0}
        if not rows:
            continue

        keyed_rows = [(spec.source_id(row), row) for row in rows]
        lookup = _lookup_entity_ids(
            session,
            entity_type=spec.entity_type,
            source_system=spec.source_system,
            source_ids=[source_id for source_id, _ in keyed_rows],
        )

        resolved_rows = []
        for source_id, row in keyed_rows:
            entity_id = lookup.get(source_id)
            if entity_id is None:
                continue
            resolved_rows.append({**row, "mdm_entity_id": entity_id})
        if resolved_rows:
            landing_export.record(spec.table, resolved_rows)
        counts[spec.table]["resolved"] = len(resolved_rows)
    return counts


def run_mdm_entity_backfill_sweep(context: Any, run_id: str) -> dict[str, Any]:
    """Sweep the Snowflake silver tables, backfilling mdm_entity_id from
    MDM's already-resolved MdmSourceRef rows.

    Snowflake-only (ticket 06): no DuckDB shard is read or written, no
    sec_fetch_active lease is required. Needs MDM_DATABASE_URL (the Postgres
    lookup) and context.silver_landing_export_root (where the full-row
    re-emission is written -- picked up by Snowpipe asynchronously, same
    lag characteristics as every other silver write in this pipeline).
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        WarehouseRuntimeError,
        _emit_pipeline_event,
        _resolve_export_business_date,
    )
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
    from edgar_warehouse.serving.silver_landing_writer import write_landing_export

    mdm_url = os.environ.get("MDM_DATABASE_URL", "").strip()
    if not mdm_url:
        raise WarehouseRuntimeError("MDM_DATABASE_URL is required for backfill-mdm-entity-ids")
    if context.silver_landing_export_root is None:
        raise WarehouseRuntimeError(
            "SILVER_LANDING_EXPORT_ROOT is required for backfill-mdm-entity-ids -- "
            "Snowflake is this command's only backfill target (ticket 06)."
        )
    from sqlalchemy.orm import Session

    engine = get_engine(mdm_url)
    started_at = datetime.now(UTC)

    connection = _silver_connection_settings().connect()
    try:
        landing_export = LandingExportBuffer()
        with Session(engine) as session:
            counts = backfill_pending_rows(connection, session, landing_export)
    finally:
        connection.close()

    now = datetime.now(UTC)
    business_date = _resolve_export_business_date(
        command_name="backfill-mdm-entity-ids", scope={}, now=now
    )
    landing_export_counts = write_landing_export(
        landing_export,
        context.silver_landing_export_root,
        run_id=run_id,
        business_date=business_date,
        command_name="backfill-mdm-entity-ids",
        environment_name=context.environment_name,
        now=now,
    )

    remaining_by_table = {
        table: table_counts["pending"] - table_counts["resolved"] for table, table_counts in counts.items()
    }
    remaining_null_count = sum(remaining_by_table.values())
    totals = {table: table_counts["resolved"] for table, table_counts in counts.items()}

    _emit_pipeline_event(
        "mdm_entity_backfill_completed",
        run_id=run_id,
        totals=totals,
        remaining_null_count=remaining_null_count,
        remaining_by_table=remaining_by_table,
    )

    return {
        "command": "backfill-mdm-entity-ids",
        "run_id": run_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "pending": {table: table_counts["pending"] for table, table_counts in counts.items()},
        "totals": totals,
        "remaining_null_count": remaining_null_count,
        "remaining_by_table": remaining_by_table,
        "landing_export": landing_export_counts,
    }
