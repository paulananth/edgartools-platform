"""SQLAlchemy models for the 11 operational bookkeeping tables.

Ported from the DuckDB DDL in edgar_warehouse.silver_store's `_DDL` string
(DuckDB Retirement Cutover Ticket 02). Type mapping: DuckDB `TIMESTAMPTZ` ->
Postgres `TIMESTAMP WITH TIME ZONE` (SQLAlchemy `TIMESTAMP(timezone=True)`,
matching edgar_warehouse.mdm.database's own convention); everything else
(TEXT, BIGINT, INTEGER, SMALLINT, DATE, BOOLEAN) maps directly, no DuckDB-only
types appear in this table set (no STRUCT/LIST/MAP, no sequences).

JSON-bearing columns on `pipeline_run` stay TEXT with manual
json.dumps(...)-on-write (see store.py's `_json_text`), not a native
SQLAlchemy JSON column type -- this preserves the exact current read
contract (callers get the raw JSON string back, never auto-parsed), which
matters for Ticket 03's caller repointing to stay mechanical rather than
also needing to update every reader for a new parsed-vs-raw return shape.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from edgar_warehouse.bookkeeping.database import Base


class StgDailyIndexFiling(Base):
    __tablename__ = "stg_daily_index_filing"

    business_date: Mapped[object] = mapped_column(Date, primary_key=True)
    accession_number: Mapped[str] = mapped_column(Text, primary_key=True)
    sync_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_object_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_year: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    source_quarter: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # BIGINT, not INTEGER -- a per-file sequence/index column, exactly the
    # shape CLAUDE.md's "Schema conventions" targets (see the sec_adv_
    # private_fund.fund_index overflow incident documented there).
    row_ordinal: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    form: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cik: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    filing_date: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filing_txt_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    record_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    staged_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class SecDailyIndexCheckpoint(Base):
    __tablename__ = "sec_daily_index_checkpoint"

    business_date: Mapped[object] = mapped_column(Date, primary_key=True)
    source_name: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'daily_form_index'")
    )
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    expected_available_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    first_attempt_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # BIGINT, not INTEGER -- CLAUDE.md's "Schema conventions": any integer
    # column derived from counting real-world SEC records must use BIGINT,
    # never SMALLINT/INTEGER, regardless of today's expected magnitude.
    attempt_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    raw_object_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    distinct_cik_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    distinct_accession_count: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    finalized_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_success_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class DiscoveryCheckpoint(Base):
    __tablename__ = "discovery_checkpoint"
    __table_args__ = (PrimaryKeyConstraint("scope_type", "scope_key"),)

    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    updated_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PipelineRunLease(Base):
    __tablename__ = "pipeline_run_lease"

    lease_name: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'idle'")
    )
    run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acquired_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    backstop_overdue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    updated_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )


class SecParseRun(Base):
    __tablename__ = "sec_parse_run"

    parse_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    accession_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parser_name: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    target_form_family: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # BIGINT, not INTEGER -- same "any count-derived value" rule as above.
    rows_written: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class SecSyncRun(Base):
    __tablename__ = "sec_sync_run"

    sync_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sync_mode: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    completed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # BIGINT, not INTEGER -- same "any count-derived value" rule as above.
    rows_inserted: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    rows_updated: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    rows_deleted: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    rows_skipped: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_run"

    pipeline_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    command_name: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_mode: Mapped[str] = mapped_column(Text, nullable=False)
    environment_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    completed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    arguments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bronze_root: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_root: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    silver_root: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    serving_export_root: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    writes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_writes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    verification_report_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )


class GoldManifest(Base):
    __tablename__ = "gold_manifest"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "storage_layer", "table_name"),
    )

    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    command_name: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_layer: Mapped[str] = mapped_column(Text, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parquet_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    previous_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_row_count: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    previous_parquet_sha256: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    row_count_delta: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    parquet_changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )


class SecSourceCheckpoint(Base):
    __tablename__ = "sec_source_checkpoint"
    __table_args__ = (PrimaryKeyConstraint("source_name", "source_key"),)

    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    raw_object_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_success_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_etag: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_modified_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_acceptance_datetime_seen: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_accession_number_seen: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # Not present in silver_store.py's bare _DDL string -- added there via a
    # runtime `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` schema-evolution
    # step. upsert_source_checkpoint writes it, so it must be a real column
    # here from the start (see Ticket 02's DDL/method mismatch note).
    bronze_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SecCompanySyncState(Base):
    __tablename__ = "sec_company_sync_state"

    cik: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tracking_status: Mapped[str] = mapped_column(Text, nullable=False)
    bootstrap_completed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_main_sync_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_main_raw_object_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    last_main_sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latest_filing_date_seen: Mapped[Optional[object]] = mapped_column(
        Date, nullable=True
    )
    latest_acceptance_datetime_seen: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # BIGINT, not INTEGER -- same "any count-derived value" rule as above.
    pagination_files_expected: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    pagination_files_loaded: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    pagination_completed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    next_sync_after: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SecReconcileFinding(Base):
    __tablename__ = "sec_reconcile_finding"
    __table_args__ = (
        PrimaryKeyConstraint(
            "reconcile_run_id",
            "cik",
            "scope_type",
            "object_type",
            "object_key",
            "drift_type",
        ),
    )

    reconcile_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    cik: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    drift_type: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual_value_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    resync_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


#: The 11 in-scope table names, in dependency-free (no FKs between them)
#: alphabetical-ish grouping order -- used by the provisioning script and by
#: BookkeepingStore.get_table_counts' narrow (11-table) implementation.
BOOKKEEPING_TABLES: tuple[str, ...] = (
    "sec_company_sync_state",
    "sec_source_checkpoint",
    "pipeline_run",
    "pipeline_run_lease",
    "sec_sync_run",
    "sec_parse_run",
    "discovery_checkpoint",
    "sec_daily_index_checkpoint",
    "stg_daily_index_filing",
    "gold_manifest",
    "sec_reconcile_finding",
)
