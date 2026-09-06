"""Gold layer builders and Parquet export helpers for the warehouse."""

from __future__ import annotations

import gc
import hashlib
import json
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Any

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyArrow is required for the gold layer. "
        "Install with: pip install 'edgartools[warehouse]'"
    ) from exc

from edgar_warehouse.infrastructure.dataset_path_catalog import (
    default_capture_spec_factory,
)
from edgar_warehouse.serving.gold_schema_registry import GOLD_SCHEMAS

# Gold schemas are externalized in config/gold_schemas.yaml (Issue 5).
_DIM_COMPANY_SCHEMA = GOLD_SCHEMAS['_DIM_COMPANY_SCHEMA']
_DIM_TICKER_REFERENCE_SCHEMA = GOLD_SCHEMAS['_DIM_TICKER_REFERENCE_SCHEMA']
_DIM_FORM_SCHEMA = GOLD_SCHEMAS['_DIM_FORM_SCHEMA']
_DIM_DATE_SCHEMA = GOLD_SCHEMAS['_DIM_DATE_SCHEMA']
_DIM_FILING_SCHEMA = GOLD_SCHEMAS['_DIM_FILING_SCHEMA']
_FACT_FILING_ACTIVITY_SCHEMA = GOLD_SCHEMAS['_FACT_FILING_ACTIVITY_SCHEMA']
_DIM_PARTY_SCHEMA = GOLD_SCHEMAS['_DIM_PARTY_SCHEMA']
_DIM_SECURITY_SCHEMA = GOLD_SCHEMAS['_DIM_SECURITY_SCHEMA']
_DIM_OWNERSHIP_TXN_TYPE_SCHEMA = GOLD_SCHEMAS['_DIM_OWNERSHIP_TXN_TYPE_SCHEMA']
_DIM_GEOGRAPHY_SCHEMA = GOLD_SCHEMAS['_DIM_GEOGRAPHY_SCHEMA']
_DIM_DISCLOSURE_CATEGORY_SCHEMA = GOLD_SCHEMAS['_DIM_DISCLOSURE_CATEGORY_SCHEMA']
_DIM_PRIVATE_FUND_SCHEMA = GOLD_SCHEMAS['_DIM_PRIVATE_FUND_SCHEMA']
_FACT_OWNERSHIP_TRANSACTION_SCHEMA = GOLD_SCHEMAS['_FACT_OWNERSHIP_TRANSACTION_SCHEMA']
_FACT_OWNERSHIP_HOLDING_SNAPSHOT_SCHEMA = GOLD_SCHEMAS['_FACT_OWNERSHIP_HOLDING_SNAPSHOT_SCHEMA']
_FACT_ADV_OFFICE_SCHEMA = GOLD_SCHEMAS['_FACT_ADV_OFFICE_SCHEMA']
_FACT_ADV_DISCLOSURE_SCHEMA = GOLD_SCHEMAS['_FACT_ADV_DISCLOSURE_SCHEMA']
_FACT_ADV_PRIVATE_FUND_SCHEMA = GOLD_SCHEMAS['_FACT_ADV_PRIVATE_FUND_SCHEMA']
_SEC_FINANCIAL_FACT_SCHEMA = GOLD_SCHEMAS['_SEC_FINANCIAL_FACT_SCHEMA']
_SEC_THIRTEENF_HOLDING_SCHEMA = GOLD_SCHEMAS['_SEC_THIRTEENF_HOLDING_SCHEMA']
_SEC_FINANCIAL_DERIVED_SCHEMA = GOLD_SCHEMAS['_SEC_FINANCIAL_DERIVED_SCHEMA']
_FACT_EARNINGS_RELEASE_SCHEMA = GOLD_SCHEMAS['_FACT_EARNINGS_RELEASE_SCHEMA']
_FACT_EXECUTIVE_RECORD_SCHEMA = GOLD_SCHEMAS['_FACT_EXECUTIVE_RECORD_SCHEMA']
_FACT_ACCOUNTING_FLAG_SCHEMA = GOLD_SCHEMAS['_FACT_ACCOUNTING_FLAG_SCHEMA']
_SEC_SUBSIDIARY_EVIDENCE_SCHEMA = GOLD_SCHEMAS['_SEC_SUBSIDIARY_EVIDENCE_SCHEMA']
_SEC_AUDITOR_REPORT_EVIDENCE_SCHEMA = GOLD_SCHEMAS['_SEC_AUDITOR_REPORT_EVIDENCE_SCHEMA']
_SEC_EMPLOYMENT_EVENT_SCHEMA = GOLD_SCHEMAS['_SEC_EMPLOYMENT_EVENT_SCHEMA']
_SEC_ADV_FIRM_ROSTER_SCHEMA = GOLD_SCHEMAS['_SEC_ADV_FIRM_ROSTER_SCHEMA']
_SEC_ADV_PRIVATE_FUND_PASSTHROUGH_SCHEMA = GOLD_SCHEMAS['_SEC_ADV_PRIVATE_FUND_PASSTHROUGH_SCHEMA']
_FACT_EARNINGS_CALENDAR_SCHEMA = GOLD_SCHEMAS['_FACT_EARNINGS_CALENDAR_SCHEMA']
_FACT_GUIDANCE_SCHEMA = GOLD_SCHEMAS['_FACT_GUIDANCE_SCHEMA']
_FACT_CONSENSUS_ESTIMATE_SCHEMA = GOLD_SCHEMAS['_FACT_CONSENSUS_ESTIMATE_SCHEMA']
_FACT_TRANSCRIPT_EVENT_SCHEMA = GOLD_SCHEMAS['_FACT_TRANSCRIPT_EVENT_SCHEMA']


def _empty(schema: pa.Schema) -> pa.Table:
    return pa.table({field.name: pa.array([], type=field.type) for field in schema}, schema=schema)


def _release_source_export_memory() -> None:
    """Return unused Python and Arrow allocations between export loads.

    This is intentionally independent of the source reader implementation.
    The caller owns the reader/connection lifetime; this hook only releases
    objects that the completed export load no longer references.
    """
    gc.collect()
    pa.default_memory_pool().release_unused()


def _table_from_records(schema: pa.Schema, records: list[dict[str, Any]]) -> pa.Table:
    if not records:
        return _empty(schema)
    return pa.table(
        {
            field.name: pa.array([record.get(field.name) for record in records], type=field.type)
            for field in schema
        },
        schema=schema,
    )


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _fetch_snowflake_silver_rows(query: str) -> list[dict[str, Any]]:
    """Run `query` against the live EDGARTOOLS_SILVER Snowflake schema and
    return every row as a dict with lowercased column names (Snowflake's
    connector returns uppercase names for unquoted identifiers by default) --
    same pattern as mdm_entity_backfill.py's _fetch_pending_rows.

    Used only by the 5 orphan evidence-table builders below (dbt-gold-
    silver-rewiring map, Ticket 06): those tables have no dbt gold model at
    all -- nothing downstream ref()s them -- so unlike Tickets 02-05 there is
    no dbt cutover path for them. This repoints their read from local DuckDB
    silver to Snowflake's EDGARTOOLS_SILVER directly instead, independent of
    the dbt batches. Opens and closes its own connection per call rather
    than sharing the local-DuckDB `conn` threaded through every other
    builder in _source_export_table_builders() -- these 5 are the only builders in
    this file reading Snowflake instead of DuckDB.
    """
    from edgar_warehouse.mdm.export import silver_connection_settings

    connection = silver_connection_settings().connect()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()
    finally:
        connection.close()


def _build_sec_subsidiary_evidence() -> pa.Table:
    rows = _fetch_snowflake_silver_rows(
        """
        SELECT
            accession_number,
            registrant_cik,
            document_name,
            document_type,
            row_ordinal,
            legal_name,
            jurisdiction,
            parent_scope,
            immediate_parent_known,
            effective_date,
            row_locator,
            source_sha256,
            parser_version
        FROM SEC_SUBSIDIARY_EVIDENCE
        """
    )
    records = [
        {
            "accession_number": row.get("accession_number"),
            "registrant_cik": _coerce_int(row.get("registrant_cik")),
            "document_name": row.get("document_name"),
            "document_type": row.get("document_type"),
            "row_ordinal": _coerce_int(row.get("row_ordinal")),
            "legal_name": row.get("legal_name"),
            "jurisdiction": row.get("jurisdiction"),
            "parent_scope": row.get("parent_scope"),
            "immediate_parent_known": row.get("immediate_parent_known"),
            "effective_date": _coerce_date(row.get("effective_date")),
            "row_locator": row.get("row_locator"),
            "source_sha256": row.get("source_sha256"),
            "parser_version": row.get("parser_version"),
        }
        for row in rows
    ]
    records.sort(
        key=lambda r: (
            r["registrant_cik"] or 0,
            r["accession_number"] or "",
            r["document_name"] or "",
            r["row_ordinal"] or 0,
        )
    )
    return _table_from_records(_SEC_SUBSIDIARY_EVIDENCE_SCHEMA, records)


def _build_sec_auditor_report_evidence() -> pa.Table:
    rows = _fetch_snowflake_silver_rows(
        """
        SELECT
            accession_number,
            registrant_cik,
            form_type,
            document_name,
            audited_period_end,
            report_date,
            principal_firm_name,
            principal_firm_location,
            pcaob_firm_id,
            evidence_source,
            raw_locator,
            source_sha256,
            evidence_fingerprint,
            form_ap_filing_id,
            original_form_ap_filing_id,
            latest_amendment,
            parser_version
        FROM SEC_AUDITOR_REPORT_EVIDENCE
        """
    )
    records = [
        {
            "accession_number": row.get("accession_number"),
            "registrant_cik": _coerce_int(row.get("registrant_cik")),
            "form_type": row.get("form_type"),
            "document_name": row.get("document_name"),
            "audited_period_end": _coerce_date(row.get("audited_period_end")),
            "report_date": _coerce_date(row.get("report_date")),
            "principal_firm_name": row.get("principal_firm_name"),
            "principal_firm_location": row.get("principal_firm_location"),
            "pcaob_firm_id": row.get("pcaob_firm_id"),
            "evidence_source": row.get("evidence_source"),
            "raw_locator": row.get("raw_locator"),
            "source_sha256": row.get("source_sha256"),
            "evidence_fingerprint": row.get("evidence_fingerprint"),
            "form_ap_filing_id": row.get("form_ap_filing_id"),
            "original_form_ap_filing_id": row.get("original_form_ap_filing_id"),
            "latest_amendment": row.get("latest_amendment"),
            "parser_version": row.get("parser_version"),
        }
        for row in rows
    ]
    records.sort(
        key=lambda r: (
            r["registrant_cik"] or 0,
            r["accession_number"] or "",
            r["evidence_fingerprint"] or "",
        )
    )
    return _table_from_records(_SEC_AUDITOR_REPORT_EVIDENCE_SCHEMA, records)


def _build_sec_employment_event() -> pa.Table:
    rows = _fetch_snowflake_silver_rows(
        """
        SELECT
            accession_number,
            event_index,
            cik,
            event_type,
            person_name,
            exec_role,
            previous_role,
            compensation_amount,
            effective_date,
            parser_version
        FROM SEC_EMPLOYMENT_EVENT
        """
    )
    records = [
        {
            "accession_number": row.get("accession_number"),
            "event_index": _coerce_int(row.get("event_index")),
            "cik": _coerce_int(row.get("cik")),
            "event_type": row.get("event_type"),
            "person_name": row.get("person_name"),
            "exec_role": row.get("exec_role"),
            "previous_role": row.get("previous_role"),
            "compensation_amount": _coerce_float(row.get("compensation_amount")),
            "effective_date": _coerce_date(row.get("effective_date")),
            "parser_version": row.get("parser_version"),
        }
        for row in rows
    ]
    records.sort(
        key=lambda r: (
            r["cik"] or 0,
            r["accession_number"] or "",
            r["event_index"] or 0,
        )
    )
    return _table_from_records(_SEC_EMPLOYMENT_EVENT_SCHEMA, records)


def _build_sec_adv_firm_roster() -> pa.Table:
    rows = _fetch_snowflake_silver_rows(
        """
        SELECT
            adviser_crd_number,
            dataset_period,
            private_funds_reported,
            private_fund_count_7b1,
            any_hedge_funds,
            hedge_fund_count,
            any_pe_funds,
            pe_fund_count,
            total_gross_assets_private_funds,
            private_fund_count_7b2,
            source_sha256,
            parser_version
        FROM SEC_ADV_FIRM_ROSTER
        """
    )
    records = [
        {
            "adviser_crd_number": row.get("adviser_crd_number"),
            "dataset_period": row.get("dataset_period"),
            "private_funds_reported": row.get("private_funds_reported"),
            "private_fund_count_7b1": _coerce_int(row.get("private_fund_count_7b1")),
            "any_hedge_funds": row.get("any_hedge_funds"),
            "hedge_fund_count": _coerce_int(row.get("hedge_fund_count")),
            "any_pe_funds": row.get("any_pe_funds"),
            "pe_fund_count": _coerce_int(row.get("pe_fund_count")),
            "total_gross_assets_private_funds": _coerce_float(row.get("total_gross_assets_private_funds")),
            "private_fund_count_7b2": _coerce_int(row.get("private_fund_count_7b2")),
            "source_sha256": row.get("source_sha256"),
            "parser_version": row.get("parser_version"),
        }
        for row in rows
    ]
    records.sort(key=lambda r: (r["adviser_crd_number"] or "", r["dataset_period"] or ""))
    return _table_from_records(_SEC_ADV_FIRM_ROSTER_SCHEMA, records)


def _build_sec_adv_private_fund_passthrough() -> pa.Table:
    rows = _fetch_snowflake_silver_rows(
        """
        SELECT
            accession_number,
            fund_index,
            filing_id,
            adviser_crd_number,
            private_fund_id,
            reference_id,
            schedule_section,
            reporting_role,
            filing_action,
            fund_name,
            fund_type,
            jurisdiction,
            aum_amount,
            effective_date,
            source_dataset_period,
            source_sha256,
            parser_version
        FROM SEC_ADV_PRIVATE_FUND
        """
    )
    records = [
        {
            "accession_number": row.get("accession_number"),
            "fund_index": _coerce_int(row.get("fund_index")),
            "filing_id": row.get("filing_id"),
            "adviser_crd_number": row.get("adviser_crd_number"),
            "private_fund_id": row.get("private_fund_id"),
            "reference_id": row.get("reference_id"),
            "schedule_section": row.get("schedule_section"),
            "reporting_role": row.get("reporting_role"),
            "filing_action": row.get("filing_action"),
            "fund_name": row.get("fund_name"),
            "fund_type": row.get("fund_type"),
            "jurisdiction": row.get("jurisdiction"),
            "aum_amount": _coerce_float(row.get("aum_amount")),
            "effective_date": _coerce_date(row.get("effective_date")),
            "source_dataset_period": row.get("source_dataset_period"),
            "source_sha256": row.get("source_sha256"),
            "parser_version": row.get("parser_version"),
        }
        for row in rows
    ]
    records.sort(key=lambda r: (r["accession_number"] or "", r["fund_index"] or 0))
    return _table_from_records(_SEC_ADV_PRIVATE_FUND_PASSTHROUGH_SCHEMA, records)


def _timed(name: str, fn: Callable[[], pa.Table]) -> pa.Table:
    t0 = datetime.now(UTC)
    print(json.dumps({"event": "gold_table_started", "table": name,
                      "emitted_at": t0.isoformat().replace("+00:00", "Z")}),
          file=sys.stderr, flush=True)
    result = fn()
    duration = (datetime.now(UTC) - t0).total_seconds()
    print(json.dumps({"event": "gold_table_completed", "table": name,
                      "rows": len(result), "duration_seconds": round(duration, 2),
                      "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}),
          file=sys.stderr, flush=True)
    return result


def _source_export_table_builders() -> list[tuple[str, Callable[[], pa.Table]]]:
    # Every table here has no dbt gold model of its own, so it still reads
    # Snowflake's EDGARTOOLS_SILVER directly instead of a local DuckDB
    # `conn` -- see _fetch_snowflake_silver_rows.
    return [
        ("sec_subsidiary_evidence",        lambda: _build_sec_subsidiary_evidence()),
        ("sec_auditor_report_evidence",    lambda: _build_sec_auditor_report_evidence()),
        ("sec_employment_event",           lambda: _build_sec_employment_event()),
        # Firm Roster completeness cross-check (ticket 03). "sec_adv_private_fund"
        # here is a distinct name from "fact_adv_private_fund" above -- that one
        # is the existing CIK-keyed dimensional PRIVATE_FUNDS gold table; this
        # one is a raw CRD-keyed passthrough export of the same silver table,
        # added because the dimensional table has no CRD column.
        ("sec_adv_firm_roster",            lambda: _build_sec_adv_firm_roster()),
        ("sec_adv_private_fund",           lambda: _build_sec_adv_private_fund_passthrough()),
    ]


def iter_source_export_tables() -> Iterator[tuple[str, pa.Table]]:
    """Yield each gold table one at a time instead of materializing the whole
    gold layer in memory simultaneously.

    Memory-critical callers — anything in SOURCE_EXPORT_COMMANDS — must use
    this and write+discard each table before building the next, rather than
    build_source_export(), which holds every table alive at once and OOM'd
    daily_incremental in prod (2026-07-30) building the ~6.8M-row
    sec_thirteenf_holding table on top of ~7M rows of already-built
    predecessor tables still held in the dict.
    """
    # Drop unreachable allocations left by the preceding ingestion phase before
    # the first export load. The source reader itself remains caller-owned.
    _release_source_export_memory()
    for name, fn in _source_export_table_builders():
        table = _timed(name, fn)
        try:
            yield name, table
        finally:
            # The consumer has finished writing/exporting this table. Remove
            # the generator's own reference before asking the Python and Arrow
            # allocators to release unused memory ahead of the next load.
            del table
            _release_source_export_memory()


def build_source_export() -> dict[str, pa.Table]:
    """Materialize the whole gold layer as a dict.

    Holds every gold table in memory simultaneously — only safe for callers
    that need random access across the full set (e.g. data-quality
    validation, tests). See iter_source_export_tables() for why memory-critical
    callers must not use this.
    """
    return dict(iter_source_export_tables())


def _write_parquet(table: pa.Table, storage_root: Any, relative_path: str) -> dict[str, Any]:
    buffer = pa.BufferOutputStream()
    pq.write_table(table, buffer)
    payload = buffer.getvalue().to_pybytes()
    path = storage_root.write_bytes(relative_path, payload)
    return {
        "path": path,
        "relative_path": relative_path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_size": len(payload),
    }


def write_source_export_to_storage(tables: dict[str, pa.Table], storage_root: Any, run_id: str) -> dict[str, int]:
    manifest = write_source_export_to_storage_manifest(tables, storage_root, run_id)
    return {entry["table_name"]: entry["row_count"] for entry in manifest}


def write_source_export_table_manifest_entry(
    table_name: str,
    table: pa.Table,
    storage_root: Any,
    run_id: str,
) -> dict[str, Any]:
    """Write a single gold table to storage and return its manifest entry.

    Extracted from write_source_export_to_storage_manifest so memory-critical callers
    (paired with iter_source_export_tables()) can write and discard one table at a
    time instead of writing the whole dict at once.
    """
    capture_specs = default_capture_spec_factory()
    output_spec = capture_specs.gold_table_output(table_name, run_id)
    write_record = _write_parquet(table, storage_root, output_spec.relative_path)
    return {
        "table_name": table_name,
        "storage_layer": "warehouse_gold",
        "relative_path": write_record["relative_path"],
        "storage_path": write_record["path"],
        "row_count": int(table.num_rows),
        "parquet_sha256": write_record["sha256"],
        "byte_size": write_record["byte_size"],
    }


def write_source_export_to_storage_manifest(
    tables: dict[str, pa.Table],
    storage_root: Any,
    run_id: str,
) -> list[dict[str, Any]]:
    return [
        write_source_export_table_manifest_entry(table_name, table, storage_root, run_id)
        for table_name, table in tables.items()
    ]


def build_ticker_reference_table(
    universe_rows: list[dict[str, Any]], sync_run_id: str
) -> pa.Table:
    """Project seed-universe rows into the TICKER_REFERENCE gold schema."""
    records: list[dict[str, Any]] = []
    for row in universe_rows:
        cik = row.get("cik")
        ticker = row.get("ticker")
        if cik is None or not ticker:
            continue
        records.append(
            {
                "cik": int(cik),
                "ticker": str(ticker),
                "exchange": row.get("exchange"),
                "last_sync_run_id": sync_run_id,
            }
        )
    return _table_from_records(_DIM_TICKER_REFERENCE_SCHEMA, records)


def build_earnings_calendar_table_from_rows(
    rows: list[dict[str, Any]],
) -> pa.Table:
    """Build ERDP-03 gold table from normalized or raw calendar rows.

    Thin wrapper so serving export paths can import from ``source_dimensional_export``
    alongside other builders.  Implementation lives in
    ``edgar_warehouse.explore.earnings_calendar``.
    """
    from edgar_warehouse.explore.earnings_calendar import build_earnings_calendar_table

    table = build_earnings_calendar_table(rows)
    if table.schema.equals(_FACT_EARNINGS_CALENDAR_SCHEMA):
        return table
    return table.cast(_FACT_EARNINGS_CALENDAR_SCHEMA)


def build_consensus_estimates_table_from_rows(
    rows: list[dict[str, Any]],
) -> pa.Table:
    """Build ERDP-01 gold table from normalized or raw consensus rows.

    Thin wrapper so serving export paths can import from ``source_dimensional_export``
    alongside other builders.  Implementation lives in
    ``edgar_warehouse.explore.consensus_estimates``.
    """
    from edgar_warehouse.explore.consensus_estimates import (
        build_consensus_estimates_table,
    )

    table = build_consensus_estimates_table(rows)
    if table.schema.equals(_FACT_CONSENSUS_ESTIMATE_SCHEMA):
        return table
    return table.cast(_FACT_CONSENSUS_ESTIMATE_SCHEMA)


def build_transcript_events_table_from_rows(
    rows: list[dict[str, Any]],
) -> pa.Table:
    """Build ERDP-04 gold table from normalized or raw transcript event rows.

    Thin wrapper so serving export paths can import from ``source_dimensional_export``
    alongside other builders.  Implementation lives in
    ``edgar_warehouse.explore.transcript_events``.
    """
    from edgar_warehouse.explore.transcript_events import build_transcript_events_table

    table = build_transcript_events_table(rows)
    if table.schema.equals(_FACT_TRANSCRIPT_EVENT_SCHEMA):
        return table
    return table.cast(_FACT_TRANSCRIPT_EVENT_SCHEMA)
