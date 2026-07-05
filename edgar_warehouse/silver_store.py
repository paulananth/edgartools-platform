"""Silver layer DuckDB management for the SEC EDGAR warehouse."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

try:
    import duckdb
except ImportError as exc:
    raise ImportError(
        "DuckDB is required for the silver layer. "
        "Install with: pip install 'edgartools[warehouse]'"
    ) from exc


logger = logging.getLogger(__name__)


_DDL = """

CREATE TABLE IF NOT EXISTS sec_company (
    cik                        BIGINT PRIMARY KEY,
    entity_name                TEXT,
    entity_type                TEXT,
    sic                        TEXT,
    sic_description            TEXT,
    state_of_incorporation     TEXT,
    state_of_incorporation_desc TEXT,
    fiscal_year_end            TEXT,
    ein                        TEXT,
    description                TEXT,
    category                   TEXT,
    first_sync_run_id          TEXT,
    last_sync_run_id           TEXT,
    last_synced_at             TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_company_address (
    cik             BIGINT,
    address_type    TEXT,
    street1         TEXT,
    street2         TEXT,
    city            TEXT,
    state_or_country TEXT,
    zip_code        TEXT,
    country         TEXT,
    last_sync_run_id TEXT,
    last_synced_at  TIMESTAMPTZ,
    PRIMARY KEY (cik, address_type)
);

CREATE TABLE IF NOT EXISTS sec_company_former_name (
    cik             BIGINT,
    former_name     TEXT,
    date_changed    DATE,
    ordinal         INTEGER,
    last_sync_run_id TEXT,
    PRIMARY KEY (cik, ordinal)
);

CREATE TABLE IF NOT EXISTS sec_company_submission_file (
    cik             BIGINT,
    file_name       TEXT,
    filing_count    INTEGER,
    filing_from     DATE,
    filing_to       DATE,
    last_sync_run_id TEXT,
    last_synced_at  TIMESTAMPTZ,
    PRIMARY KEY (cik, file_name)
);

CREATE TABLE IF NOT EXISTS sec_company_filing (
    accession_number    TEXT PRIMARY KEY,
    cik                 BIGINT,
    form                TEXT,
    filing_date         DATE,
    report_date         DATE,
    acceptance_datetime TEXT,
    act                 TEXT,
    file_number         TEXT,
    film_number         TEXT,
    items               TEXT,
    size                BIGINT,
    is_xbrl             BOOLEAN,
    is_inline_xbrl      BOOLEAN,
    primary_document    TEXT,
    primary_doc_desc    TEXT,
    last_sync_run_id    TEXT,
    last_synced_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_company_ticker (
    cik                 BIGINT,
    ticker              TEXT,
    exchange            TEXT,
    source_name         TEXT NOT NULL DEFAULT 'company_tickers_exchange',
    source_rank         INTEGER,
    last_sync_run_id    TEXT,
    last_synced_at      TIMESTAMPTZ,
    PRIMARY KEY (cik, ticker, source_name)
);

CREATE TABLE IF NOT EXISTS sec_current_filing_feed (
    accession_number    TEXT PRIMARY KEY,
    cik                 BIGINT,
    form                TEXT,
    company_name        TEXT,
    filing_date         DATE,
    accepted_at         TIMESTAMPTZ,
    filing_href         TEXT,
    index_href          TEXT,
    summary             TEXT,
    source_url          TEXT,
    feed_published_at   TIMESTAMPTZ,
    raw_object_id       TEXT,
    last_sync_run_id    TEXT,
    last_synced_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_ownership_reporting_owner (
    accession_number    TEXT,
    owner_index         SMALLINT,
    owner_cik           BIGINT,
    owner_name          TEXT,
    is_director         BOOLEAN,
    is_officer          BOOLEAN,
    is_ten_percent_owner BOOLEAN,
    is_other            BOOLEAN,
    officer_title       TEXT,
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, owner_index)
);

CREATE TABLE IF NOT EXISTS sec_ownership_non_derivative_txn (
    accession_number    TEXT,
    owner_index         SMALLINT,
    txn_index           SMALLINT,
    security_title      TEXT,
    transaction_date    DATE,
    transaction_code    TEXT,
    transaction_shares  DECIMAL(28,8),
    transaction_price   DECIMAL(28,8),
    acquired_disposed_code TEXT,
    shares_owned_after  DECIMAL(28,8),
    ownership_nature    TEXT,
    ownership_direct_indirect TEXT,
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, owner_index, txn_index)
);

CREATE TABLE IF NOT EXISTS sec_ownership_derivative_txn (
    accession_number    TEXT,
    owner_index         SMALLINT,
    txn_index           SMALLINT,
    security_title      TEXT,
    transaction_date    DATE,
    transaction_code    TEXT,
    transaction_shares  DECIMAL(28,8),
    transaction_price   DECIMAL(28,8),
    acquired_disposed_code TEXT,
    shares_owned_after  DECIMAL(28,8),
    ownership_nature    TEXT,
    ownership_direct_indirect TEXT,
    conversion_or_exercise_price DECIMAL(28,8),
    exercise_date       DATE,
    expiration_date     DATE,
    underlying_security_title TEXT,
    underlying_security_shares DECIMAL(28,8),
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, owner_index, txn_index)
);

CREATE TABLE IF NOT EXISTS sec_adv_filing (
    accession_number    TEXT PRIMARY KEY,
    cik                 BIGINT,
    form                TEXT,
    adviser_name        TEXT,
    sec_file_number     TEXT,
    crd_number          TEXT,
    effective_date      DATE,
    filing_status       TEXT,
    source_format       TEXT,
    parser_version      TEXT,
    last_sync_run_id    TEXT
);

CREATE TABLE IF NOT EXISTS sec_adv_office (
    accession_number    TEXT,
    office_index        SMALLINT,
    office_name         TEXT,
    city                TEXT,
    state_or_country    TEXT,
    country             TEXT,
    is_headquarters     BOOLEAN,
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, office_index)
);

CREATE TABLE IF NOT EXISTS sec_adv_disclosure_event (
    accession_number    TEXT,
    event_index         SMALLINT,
    disclosure_category TEXT,
    event_date          DATE,
    is_reported         BOOLEAN,
    description         TEXT,
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, event_index)
);

CREATE TABLE IF NOT EXISTS sec_adv_private_fund (
    accession_number    TEXT,
    fund_index          SMALLINT,
    fund_name           TEXT,
    fund_type           TEXT,
    jurisdiction        TEXT,
    aum_amount          DECIMAL(28,2),
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, fund_index)
);

CREATE TABLE IF NOT EXISTS stg_daily_index_filing (
    sync_run_id         TEXT,
    raw_object_id       TEXT,
    source_name         TEXT,
    source_url          TEXT,
    business_date       DATE,
    source_year         SMALLINT,
    source_quarter      SMALLINT,
    row_ordinal         INTEGER,
    form                TEXT,
    company_name        TEXT,
    cik                 BIGINT,
    filing_date         DATE,
    file_name           TEXT,
    accession_number    TEXT,
    filing_txt_url      TEXT,
    record_hash         TEXT,
    staged_at           TIMESTAMPTZ,
    PRIMARY KEY (business_date, accession_number)
);

CREATE TABLE IF NOT EXISTS sec_daily_index_checkpoint (
    business_date             DATE PRIMARY KEY,
    source_name               TEXT NOT NULL DEFAULT 'daily_form_index',
    source_key                TEXT NOT NULL,
    source_url                TEXT NOT NULL,
    expected_available_at     TIMESTAMPTZ NOT NULL,
    first_attempt_at          TIMESTAMPTZ,
    last_attempt_at           TIMESTAMPTZ,
    attempt_count             INTEGER NOT NULL DEFAULT 0,
    raw_object_id             TEXT,
    last_sha256               TEXT,
    row_count                 INTEGER,
    distinct_cik_count        INTEGER,
    distinct_accession_count  INTEGER,
    status                    TEXT NOT NULL DEFAULT 'pending',
    error_message             TEXT,
    finalized_at              TIMESTAMPTZ,
    last_success_at           TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_raw_object (
    raw_object_id       TEXT PRIMARY KEY,
    source_type         TEXT,
    cik                 BIGINT,
    accession_number    TEXT,
    form                TEXT,
    source_url          TEXT        NOT NULL,
    storage_path        TEXT        NOT NULL,
    content_type        TEXT,
    content_encoding    TEXT,
    byte_size           BIGINT,
    sha256              TEXT        NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL,
    http_status         INTEGER     NOT NULL,
    source_last_modified TIMESTAMPTZ,
    source_etag         TEXT
);

CREATE TABLE IF NOT EXISTS sec_filing_attachment (
    accession_number    TEXT,
    sequence_number     TEXT,
    document_name       TEXT,
    document_type       TEXT        NOT NULL,
    document_description TEXT,
    document_url        TEXT        NOT NULL,
    is_primary          BOOLEAN     NOT NULL,
    raw_object_id       TEXT,
    last_sync_run_id    TEXT,
    PRIMARY KEY (accession_number, document_name)
);

CREATE TABLE IF NOT EXISTS sec_filing_text (
    accession_number    TEXT        NOT NULL,
    text_version        TEXT        NOT NULL,
    source_document_name TEXT       NOT NULL,
    text_storage_path   TEXT        NOT NULL,
    text_sha256         TEXT        NOT NULL,
    char_count          INTEGER     NOT NULL,
    extracted_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (accession_number, text_version)
);

CREATE TABLE IF NOT EXISTS sec_parse_run (
    parse_run_id       TEXT NOT NULL PRIMARY KEY,
    accession_number   TEXT,
    parser_name        TEXT NOT NULL,
    parser_version     TEXT NOT NULL,
    target_form_family TEXT NOT NULL,
    status             TEXT NOT NULL,
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    error_code         TEXT,
    error_message      TEXT,
    rows_written       INTEGER
);

CREATE TABLE IF NOT EXISTS sec_sync_run (
    sync_run_id        TEXT PRIMARY KEY,
    sync_mode          TEXT NOT NULL,
    scope_type         TEXT NOT NULL,
    scope_key          TEXT,
    started_at         TIMESTAMPTZ NOT NULL,
    completed_at       TIMESTAMPTZ,
    status             TEXT NOT NULL,
    rows_inserted      INTEGER,
    rows_updated       INTEGER,
    rows_deleted       INTEGER,
    rows_skipped       INTEGER,
    error_message      TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_run (
    pipeline_run_id          TEXT PRIMARY KEY,
    command_name             TEXT NOT NULL,
    runtime_mode             TEXT NOT NULL,
    environment_name         TEXT,
    started_at               TIMESTAMPTZ NOT NULL,
    completed_at             TIMESTAMPTZ,
    status                   TEXT NOT NULL,
    arguments_json           TEXT,
    scope_json               TEXT,
    bronze_root              TEXT,
    storage_root             TEXT,
    silver_root              TEXT,
    serving_export_root      TEXT,
    writes_json              TEXT,
    raw_writes_json          TEXT,
    metrics_json             TEXT,
    error_message            TEXT,
    verification_status      TEXT,
    last_verified_at         TIMESTAMPTZ,
    verification_report_json TEXT
);

CREATE TABLE IF NOT EXISTS sec_source_checkpoint (
    source_name                    TEXT,
    source_key                     TEXT,
    raw_object_id                  TEXT,
    last_success_at                TIMESTAMPTZ,
    last_sha256                    TEXT,
    last_etag                      TEXT,
    last_modified_at               TIMESTAMPTZ,
    last_acceptance_datetime_seen  TIMESTAMPTZ,
    last_accession_number_seen     TEXT,
    PRIMARY KEY (source_name, source_key)
);

CREATE TABLE IF NOT EXISTS sec_company_sync_state (
    cik                            BIGINT PRIMARY KEY,
    tracking_status                TEXT NOT NULL,
    bootstrap_completed_at         TIMESTAMPTZ,
    last_main_sync_at              TIMESTAMPTZ,
    last_main_raw_object_id        TEXT,
    last_main_sha256               TEXT,
    latest_filing_date_seen        DATE,
    latest_acceptance_datetime_seen TIMESTAMPTZ,
    pagination_files_expected      INTEGER,
    pagination_files_loaded        INTEGER,
    pagination_completed_at        TIMESTAMPTZ,
    next_sync_after                TIMESTAMPTZ,
    last_error_message             TEXT
);

CREATE TABLE IF NOT EXISTS sec_reconcile_finding (
    reconcile_run_id      TEXT,
    cik                   BIGINT,
    scope_type            TEXT,
    object_type           TEXT,
    object_key            TEXT,
    drift_type            TEXT,
    expected_value_hash   TEXT,
    actual_value_hash     TEXT,
    severity              TEXT,
    recommended_action    TEXT,
    status                TEXT,
    detected_at           TIMESTAMPTZ,
    resolved_at           TIMESTAMPTZ,
    resync_run_id         TEXT,
    PRIMARY KEY (reconcile_run_id, cik, scope_type, object_type, object_key, drift_type)
);

-- ==========================================================================
-- FUNDAMENTALS TABLES  (same SEC silver database as Branch A)
-- Branch B bootstrap forms: 8-K earnings, DEF 14A, 10-K/10-Q XBRL, 13F-HR
-- ==========================================================================

CREATE TABLE IF NOT EXISTS sec_financial_fact (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    fiscal_period       TEXT NOT NULL,   -- FY | Q1 | Q2 | Q3 | Q4
    period_end          DATE NOT NULL,
    period_start        DATE NOT NULL,   -- sentinel 0001-01-01 for instant (no-duration) facts
    form_type           TEXT NOT NULL,   -- 10-K | 10-Q
    concept             TEXT NOT NULL,   -- XBRL concept name (e.g. us-gaap/Revenues)
    value               DOUBLE,
    unit                TEXT,            -- USD | shares | pure
    decimals            INTEGER,
    segment             TEXT NOT NULL DEFAULT 'consolidated',  -- 'consolidated' or JSON-encoded dimension key
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    -- period_end is part of the PK because the SEC companyfacts API reports
    -- both the current-period and comparative prior-period value for the
    -- same (accn, concept, fiscal_period, segment) -- omitting period_end
    -- collapses these into one row with a Frankenstein period_end/value pair.
    -- period_start additionally disambiguates QTD vs. YTD duration facts that
    -- share the same period_end (e.g. "3 months ended" vs "6 months ended").
    PRIMARY KEY (cik, accession_number, concept, fiscal_period, segment, period_end, period_start)
);

CREATE TABLE IF NOT EXISTS sec_financial_derived (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    fiscal_period       TEXT NOT NULL,   -- FY | Q1 | Q2 | Q3 | Q4
    period_end          DATE NOT NULL,
    form_type           TEXT NOT NULL,
    -- Income metrics
    revenue             DOUBLE,
    gross_profit        DOUBLE,
    ebitda              DOUBLE,
    ebit                DOUBLE,
    net_income          DOUBLE,
    eps_diluted         DOUBLE,
    -- Balance sheet
    total_assets        DOUBLE,
    total_liabilities   DOUBLE,
    total_equity        DOUBLE,
    cash_and_equivalents DOUBLE,
    total_debt          DOUBLE,
    current_assets      DOUBLE,
    current_liabilities DOUBLE,
    accounts_receivable DOUBLE,
    inventory           DOUBLE,
    selling_general_admin_expense DOUBLE,
    retained_earnings   DOUBLE,
    depreciation_amortization DOUBLE,
    property_plant_equipment_net DOUBLE,
    shares_outstanding  DOUBLE,
    -- Cash flow
    operating_cash_flow DOUBLE,
    capex               DOUBLE,
    free_cash_flow      DOUBLE,
    -- Margins (0.0–1.0)
    gross_margin        DOUBLE,
    ebitda_margin       DOUBLE,
    net_margin          DOUBLE,
    -- Returns
    roic                DOUBLE,
    roe                 DOUBLE,
    roa                 DOUBLE,
    -- NOTE: Forensic scores (Beneish M / Altman Z / Piotroski F) live exclusively on
    -- sec_accounting_flag. They are annual constructs computed cross-period and would
    -- be misleading to denormalise to per-quarter rows here.
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    -- period_end is part of the PK for the same reason as sec_financial_fact:
    -- a single accession can yield multiple derived rows for the same
    -- fiscal_period (current vs. comparative prior period), each with a
    -- distinct period_end.
    PRIMARY KEY (cik, accession_number, fiscal_period, period_end)
);

CREATE TABLE IF NOT EXISTS sec_earnings_release (
    cik                     BIGINT NOT NULL,
    accession_number        TEXT NOT NULL,
    filing_date             DATE NOT NULL,
    fiscal_year             INTEGER,
    fiscal_quarter          INTEGER,     -- 1–4; NULL for annual releases
    period_end              DATE,
    -- GAAP results (validated via edgartools EarningsRelease.get_key_metrics())
    revenue_gaap            DOUBLE,
    net_income_gaap         DOUBLE,
    eps_gaap_diluted        DOUBLE,
    -- Presence flags (high-confidence: edgartools detects table presence reliably)
    has_non_gaap            BOOLEAN NOT NULL DEFAULT FALSE,
    has_guidance            BOOLEAN NOT NULL DEFAULT FALSE,
    -- NOTE: Specific guidance ranges (revenue/EPS low/high), non-GAAP EPS value,
    -- and beat/miss flags are NOT stored here. They require either validated
    -- per-company extraction logic (guidance ranges) or cross-period comparison
    -- (beat/miss). When those extractors land, columns will be added via forward
    -- migration with population in the same change.
    parser_version          TEXT,
    ingested_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number)
);

CREATE TABLE IF NOT EXISTS sec_accounting_flag (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    period_end          DATE,
    form_type           TEXT NOT NULL,  -- always 10-K
    -- Auditor identity (from XBRL DEI facts)
    auditor_name        TEXT,           -- dei_AuditorName
    auditor_pcaob_id    TEXT,           -- dei_AuditorFirmId (PCAOB numeric ID)
    auditor_location    TEXT,           -- dei_AuditorLocation
    icfr_attestation    BOOLEAN,        -- dei_IcfrAuditorAttestationFlag
    auditor_changed     BOOLEAN,        -- TRUE if auditor_pcaob_id differs from prior fiscal year
    -- Forensic scores (computed cross-period by accounting_flags.backfill_accounting_flags;
    -- this table is the single source of truth — they are NOT denormalised to
    -- sec_financial_derived because they are annual constructs).
    beneish_m_score     DOUBLE,
    altman_z_score      DOUBLE,
    piotroski_f_score   INTEGER,
    -- NOTE: audit_opinion (unqualified/qualified/adverse/disclaimer) is NOT stored here.
    -- It requires parsing the auditor's report section of the 10-K, for which
    -- no validated extractor exists yet. A forward migration will add the column
    -- in the same change that lands the extractor.
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number)
);

CREATE TABLE IF NOT EXISTS sec_executive_record (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    exec_name           TEXT NOT NULL,
    exec_role           TEXT,           -- CEO | CFO | COO | President | etc.
    -- Compensation table columns (from edgartools extract_summary_compensation)
    total_comp          DOUBLE,
    base_salary         DOUBLE,
    bonus               DOUBLE,
    stock_awards        DOUBLE,
    option_awards       DOUBLE,
    non_equity_incentive DOUBLE,
    -- NOTE: deferred_comp, other_comp, exec_person_entity_id, tenure_start_year are
    -- NOT stored here:
    --   deferred_comp / other_comp — edgartools extract_summary_compensation does not
    --     return these SCT columns. When that capability lands upstream, columns will
    --     be added via forward migration with population in the same change.
    --   exec_person_entity_id — entity resolution is MDM's responsibility; the
    --     resolved entity_id lives on mdm_relationship_instance (source_entity_id),
    --     not denormalised to silver.
    --   tenure_start_year — computed cross-filing by MDM's _derive_employed_by from
    --     the EMPLOYED_BY relationship history; stored on the relationship's
    --     properties JSON, not on silver.
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number, exec_name)
);

CREATE TABLE IF NOT EXISTS sec_thirteenf_holding (
    cik                 BIGINT NOT NULL,     -- 13F filing manager CIK
    accession_number    TEXT NOT NULL,
    holding_index       BIGINT NOT NULL,     -- 1-based row position within the filing (parser-assigned)
    period_of_report    DATE NOT NULL,       -- quarter-end date from 13F header
    cusip               TEXT,               -- may be absent in some filings
    issuer_name         TEXT,
    security_title      TEXT,
    -- Quantity (shares / principal amount for bonds)
    shares_held         DOUBLE,
    -- Market value: 13F reports in $000s pre-Q4 2022, $1 units after — parser normalises to USD
    market_value        DOUBLE,
    -- Classification
    security_class      TEXT,               -- equity | etf_fund | fixed_income | warrant | unknown_security
    put_call            TEXT,               -- Put | Call | NULL (options only)
    discretion_type     TEXT,               -- Sole | Shared | None
    -- Voting authority columns (reported separately in 13F XML)
    voting_auth_sole    DOUBLE,
    voting_auth_shared  DOUBLE,
    voting_auth_none    DOUBLE,
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number, holding_index)
);
"""


# Tables whose primary key gained `period_end` in PR #57 (the period_end PK
# fix for sec_financial_fact / sec_financial_derived). Stores created before
# that change retain the old PK; _ensure_schema_evolution detects and repairs
# them via _migrate_financial_period_end_pk.
_FINANCIAL_TABLES_REQUIRING_PERIOD_END_PK = ("sec_financial_fact", "sec_financial_derived")

# Sentinel period_start for "instant" (no-duration) XBRL facts -- e.g. balance
# sheet concepts, which the SEC companyfacts API reports with only an "end"
# date and no "start". Keeps period_start NOT NULL so it can sit in the
# sec_financial_fact primary key (added in Stage 2 of the period_end PK fix).
_INSTANT_FACT_PERIOD_START_SENTINEL = "0001-01-01"

_SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS = {
    "current_assets": "DOUBLE",
    "current_liabilities": "DOUBLE",
    "accounts_receivable": "DOUBLE",
    "inventory": "DOUBLE",
    "selling_general_admin_expense": "DOUBLE",
    "retained_earnings": "DOUBLE",
    "depreciation_amortization": "DOUBLE",
    "property_plant_equipment_net": "DOUBLE",
    "shares_outstanding": "DOUBLE",
}


class SilverDatabase:
    """Manages the silver-layer DuckDB instance for a warehouse root."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._conn.execute(_DDL)
        self._ensure_schema_evolution()

    def _ensure_schema_evolution(self) -> None:
        self._migrate_financial_period_end_pk()
        self._migrate_financial_fact_period_start_pk()

        migration_statements = [
            "ALTER TABLE sec_parse_run ADD COLUMN IF NOT EXISTS rows_written INTEGER",
            "ALTER TABLE sec_source_checkpoint ADD COLUMN IF NOT EXISTS bronze_path TEXT",
            *[
                f"ALTER TABLE sec_financial_derived ADD COLUMN IF NOT EXISTS {column} {column_type}"
                for column, column_type in _SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS.items()
            ],
        ]
        for statement in migration_statements:
            self._conn.execute(statement)

    def _migrate_financial_period_end_pk(self) -> None:
        """Drop and recreate financial tables whose PK predates PR #57.

        ``CREATE TABLE IF NOT EXISTS`` does not alter an existing table's
        constraints, so a store created before the period_end PK fix
        retains the old PK and the ``ON CONFLICT (..., period_end)``
        targets in ``merge_financial_facts``/``merge_financial_derived``
        raise a binder error. These tables are re-bootstrappable from SEC
        bronze data, so old rows are discarded; ``_DDL`` recreates the
        dropped tables below with the current (period_end-inclusive) PK.
        """
        tables_to_recreate = []
        for table in _FINANCIAL_TABLES_REQUIRING_PERIOD_END_PK:
            row = self._conn.execute(
                """
                SELECT constraint_column_names
                FROM duckdb_constraints()
                WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'
                """,
                [table],
            ).fetchone()
            if row is not None and "period_end" not in row[0]:
                tables_to_recreate.append(table)

        for table in tables_to_recreate:
            logger.warning(
                "Migrating %s to the period_end primary key (PR #57): "
                "dropping and recreating with no rows. Re-bootstrap to repopulate.",
                table,
            )
            self._conn.execute(f"DROP TABLE {table}")

        if tables_to_recreate:
            self._conn.execute(_DDL)

    def _migrate_financial_fact_period_start_pk(self) -> None:
        """Drop and recreate sec_financial_fact if its PK predates Stage 2
        of the period_end PK fix (period_start added to the PK).

        Same rationale and drop+recreate pattern as
        ``_migrate_financial_period_end_pk``: a store whose sec_financial_fact
        PK already includes period_end (Stage 1) but not period_start (Stage 2)
        would otherwise raise a binder error on the first
        ``merge_financial_facts`` call, since its
        ``ON CONFLICT (..., period_start)`` target has no backing constraint.
        A store still on the pre-Stage-1 PK is handled by
        ``_migrate_financial_period_end_pk`` above, which recreates it via the
        current (Stage-2) ``_DDL`` -- making this check a no-op for it.
        """
        row = self._conn.execute(
            """
            SELECT constraint_column_names
            FROM duckdb_constraints()
            WHERE table_name = 'sec_financial_fact' AND constraint_type = 'PRIMARY KEY'
            """
        ).fetchone()
        if row is not None and "period_start" not in row[0]:
            logger.warning(
                "Migrating sec_financial_fact to the period_start primary key "
                "(Stage 2 of the period_end PK fix): dropping and recreating "
                "with no rows. Re-bootstrap to repopulate."
            )
            self._conn.execute("DROP TABLE sec_financial_fact")
            self._conn.execute(_DDL)

    def close(self) -> None:
        self._conn.close()

    def fetch(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dicts.

        API-compatible with ``ShardedSilverReader.fetch`` so CIK-level
        post-processors (e.g. ``accounting_flags.backfill_accounting_flags``)
        can read from either a single writable shard or a multi-shard reader.

        Parameters
        ----------
        sql:
            SQL query string.
        params:
            Optional list of positional query parameters.
        """
        rows = self._conn.execute(sql, params or []).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, r)) for r in rows]

    @contextmanager
    def _shard_advisory_lock(self) -> Iterator[None]:
        """Serialize composite shard writes from concurrent local writers."""
        lock_path = Path(f"{self._path}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_handle:
            try:
                import fcntl
            except ImportError:
                yield
                return

            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def reconcile_shards(
        shard_paths: list[str],
        *,
        table_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compare per-table row counts and newest sync timestamps across shards."""
        if not shard_paths:
            raise ValueError("At least one shard path is required")

        tables = table_names or SilverDatabase._reconciliation_table_names(shard_paths)
        table_reports: dict[str, Any] = {}
        divergences: list[dict[str, Any]] = []

        for table_name in tables:
            shard_reports = [
                SilverDatabase._reconcile_table_for_shard(index, path, table_name)
                for index, path in enumerate(shard_paths)
            ]
            row_count_diverged = SilverDatabase._metric_diverged(shard_reports, "row_count")
            timestamp_diverged = SilverDatabase._metric_diverged(
                shard_reports, "newest_last_synced_at"
            )
            table_diverged = row_count_diverged or timestamp_diverged or any(
                shard["error"] for shard in shard_reports
            )

            table_reports[table_name] = {
                "shards": shard_reports,
                "row_count_diverged": row_count_diverged,
                "newest_last_synced_at_diverged": timestamp_diverged,
                "diverged": table_diverged,
            }
            if row_count_diverged:
                divergences.append(
                    SilverDatabase._divergence(
                        table_name, "row_count", shard_reports
                    )
                )
            if timestamp_diverged:
                divergences.append(
                    SilverDatabase._divergence(
                        table_name, "newest_last_synced_at", shard_reports
                    )
                )
            for shard_report in shard_reports:
                if shard_report["error"]:
                    divergences.append(
                        {
                            "table": table_name,
                            "metric": "error",
                            "values": {shard_report["shard_path"]: shard_report["error"]},
                        }
                    )

        return {
            "shard_count": len(shard_paths),
            "shard_paths": list(shard_paths),
            "tables": table_reports,
            "divergences": divergences,
        }

    @staticmethod
    def _reconciliation_table_names(shard_paths: list[str]) -> list[str]:
        names: set[str] = set()
        for shard_path in shard_paths:
            conn = duckdb.connect(shard_path, read_only=True)
            try:
                rows = conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                      AND table_type = 'BASE TABLE'
                    """
                ).fetchall()
            finally:
                conn.close()
            names.update(row[0] for row in rows)
        return sorted(names)

    @staticmethod
    def _reconcile_table_for_shard(
        shard_index: int,
        shard_path: str,
        table_name: str,
    ) -> dict[str, Any]:
        report = {
            "shard_index": shard_index,
            "shard_path": shard_path,
            "row_count": None,
            "newest_last_synced_at": None,
            "error": None,
        }
        conn = duckdb.connect(shard_path, read_only=True)
        try:
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'main'
                  AND table_name = ?
                  AND table_type = 'BASE TABLE'
                """,
                [table_name],
            ).fetchone()[0]
            if not table_exists:
                report["error"] = "missing table"
                return report

            quoted_table = SilverDatabase._quote_identifier(table_name)
            report["row_count"] = conn.execute(
                f"SELECT COUNT(*) FROM {quoted_table}"
            ).fetchone()[0]
            columns = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'main'
                      AND table_name = ?
                    """,
                    [table_name],
                ).fetchall()
            }
            if "last_synced_at" in columns:
                newest = conn.execute(
                    f"SELECT MAX(last_synced_at) FROM {quoted_table}"
                ).fetchone()[0]
                report["newest_last_synced_at"] = (
                    newest.isoformat() if isinstance(newest, datetime) else newest
                )
            return report
        except Exception as exc:  # pragma: no cover - exercised through report data
            report["error"] = str(exc)
            return report
        finally:
            conn.close()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _metric_diverged(shard_reports: list[dict[str, Any]], metric: str) -> bool:
        values = {shard[metric] for shard in shard_reports if shard["error"] is None}
        return len(values) > 1

    @staticmethod
    def _divergence(
        table_name: str,
        metric: str,
        shard_reports: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "table": table_name,
            "metric": metric,
            "values": {
                shard["shard_path"]: shard[metric]
                for shard in shard_reports
                if shard["error"] is None
            },
        }


    # ------------------------------------------------------------------
    # sec_company_ticker
    # ------------------------------------------------------------------

    def replace_company_tickers(
        self,
        rows: list[dict[str, Any]],
        sync_run_id: str,
        *,
        source_name: str = "company_tickers_exchange",
    ) -> int:
        now = datetime.now(UTC)
        self._conn.execute(
            "DELETE FROM sec_company_ticker WHERE source_name = ?",
            [source_name],
        )
        count = 0
        for ordinal, row in enumerate(rows, start=1):
            ticker = row.get("ticker")
            cik = row.get("cik")
            if cik is None or not ticker:
                continue
            self._conn.execute(
                """
                INSERT INTO sec_company_ticker
                    (cik, ticker, exchange, source_name, source_rank,
                     last_sync_run_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    cik,
                    ticker,
                    row.get("exchange"),
                    source_name,
                    ordinal,
                    sync_run_id,
                    now,
                ],
            )
            count += 1
        return count

    def get_company_tickers(self, cik: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM sec_company_ticker
            WHERE cik = ?
            ORDER BY source_name, source_rank, ticker
            """,
            [cik],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_company (silver merge)
    # ------------------------------------------------------------------

    def merge_company(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        """Upsert staged company rows into sec_company. Returns row count."""
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO sec_company
                    (cik, entity_name, entity_type, sic, sic_description,
                     state_of_incorporation, state_of_incorporation_desc,
                     fiscal_year_end, ein, description, category,
                     first_sync_run_id, last_sync_run_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (cik) DO UPDATE SET
                    entity_name = excluded.entity_name,
                    entity_type = excluded.entity_type,
                    sic = excluded.sic,
                    sic_description = excluded.sic_description,
                    state_of_incorporation = excluded.state_of_incorporation,
                    state_of_incorporation_desc = excluded.state_of_incorporation_desc,
                    fiscal_year_end = excluded.fiscal_year_end,
                    ein = excluded.ein,
                    description = excluded.description,
                    category = excluded.category,
                    last_sync_run_id = excluded.last_sync_run_id,
                    last_synced_at = excluded.last_synced_at
                """,
                [
                    row["cik"],
                    row.get("entity_name"),
                    row.get("entity_type"),
                    row.get("sic"),
                    row.get("sic_description"),
                    row.get("state_of_incorporation"),
                    row.get("state_of_incorporation_desc"),
                    row.get("fiscal_year_end"),
                    row.get("ein"),
                    row.get("description"),
                    row.get("category"),
                    row.get("first_sync_run_id", sync_run_id),
                    sync_run_id,
                    now,
                ],
            )
            count += 1
        return count

    def get_company(self, cik: int) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_company WHERE cik = ?", [cik]
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    # ------------------------------------------------------------------
    # sec_company_address
    # ------------------------------------------------------------------

    def merge_addresses(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO sec_company_address
                    (cik, address_type, street1, street2, city,
                     state_or_country, zip_code, country,
                     last_sync_run_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (cik, address_type) DO UPDATE SET
                    street1 = excluded.street1,
                    street2 = excluded.street2,
                    city = excluded.city,
                    state_or_country = excluded.state_or_country,
                    zip_code = excluded.zip_code,
                    country = excluded.country,
                    last_sync_run_id = excluded.last_sync_run_id,
                    last_synced_at = excluded.last_synced_at
                """,
                [
                    row["cik"],
                    row["address_type"],
                    row.get("street1"),
                    row.get("street2"),
                    row.get("city"),
                    row.get("state_or_country"),
                    row.get("zip_code"),
                    row.get("country"),
                    sync_run_id,
                    now,
                ],
            )
            count += 1
        return count

    def get_addresses(self, cik: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM sec_company_address WHERE cik = ?", [cik]
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_company_former_name
    # ------------------------------------------------------------------

    def merge_former_names(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO sec_company_former_name
                    (cik, former_name, date_changed, ordinal, last_sync_run_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (cik, ordinal) DO UPDATE SET
                    former_name = excluded.former_name,
                    date_changed = excluded.date_changed,
                    last_sync_run_id = excluded.last_sync_run_id
                """,
                [
                    row["cik"],
                    row["former_name"],
                    row.get("date_changed"),
                    row["ordinal"],
                    sync_run_id,
                ],
            )
            count += 1
        return count

    def get_former_names(self, cik: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM sec_company_former_name WHERE cik = ? ORDER BY ordinal",
            [cik],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_company_submission_file
    # ------------------------------------------------------------------

    def merge_submission_files(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO sec_company_submission_file
                    (cik, file_name, filing_count, filing_from, filing_to,
                     last_sync_run_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (cik, file_name) DO UPDATE SET
                    filing_count = excluded.filing_count,
                    filing_from = excluded.filing_from,
                    filing_to = excluded.filing_to,
                    last_sync_run_id = excluded.last_sync_run_id,
                    last_synced_at = excluded.last_synced_at
                """,
                [
                    row["cik"],
                    row["file_name"],
                    row.get("filing_count"),
                    row.get("filing_from"),
                    row.get("filing_to"),
                    sync_run_id,
                    now,
                ],
            )
            count += 1
        return count

    def get_submission_files(self, cik: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM sec_company_submission_file WHERE cik = ?", [cik]
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_company_filing
    # ------------------------------------------------------------------

    def merge_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        """Bulk UPSERT into sec_company_filing.

        A single CIK's full filing history can be hundreds to low-thousands of
        rows (first-load recovery stages a company's entire "recent" + all
        pagination-file filings at once, not just a day's worth). The previous
        row-by-row execute() loop was the dominant cost of bronze_seed_silver_gold's
        BatchSilver stage (~93% of per-batch time, measured live) -- per-statement
        parse/plan/exec overhead repeated per row against a growing table, not
        anything sharding would fix. _merge_rows_bulk (already used by
        merge_financial_facts/merge_financial_derived) stages all rows in one
        executemany() then applies the upsert as two set-based SQL statements.
        """
        if not rows:
            return 0
        now = datetime.now(UTC)
        return self._merge_rows_bulk(
            staging_table="stg_sec_company_filing",
            staging_ddl="""
                CREATE TEMP TABLE IF NOT EXISTS stg_sec_company_filing (
                    seq                 BIGINT,
                    accession_number    TEXT,
                    cik                 BIGINT,
                    form                TEXT,
                    filing_date         DATE,
                    report_date         DATE,
                    acceptance_datetime TEXT,
                    act                 TEXT,
                    file_number         TEXT,
                    film_number         TEXT,
                    items               TEXT,
                    size                BIGINT,
                    is_xbrl             BOOLEAN,
                    is_inline_xbrl      BOOLEAN,
                    primary_document    TEXT,
                    primary_doc_desc    TEXT,
                    last_sync_run_id    TEXT,
                    last_synced_at      TIMESTAMPTZ
                )
            """,
            insert_first_sql="""
                INSERT INTO sec_company_filing
                    (accession_number, cik, form, filing_date, report_date,
                     acceptance_datetime, act, file_number, film_number, items,
                     size, is_xbrl, is_inline_xbrl, primary_document,
                     primary_doc_desc, last_sync_run_id, last_synced_at)
                SELECT accession_number, cik, form, filing_date, report_date,
                       acceptance_datetime, act, file_number, film_number, items,
                       size, is_xbrl, is_inline_xbrl, primary_document,
                       primary_doc_desc, last_sync_run_id, last_synced_at
                FROM stg_sec_company_filing
                QUALIFY ROW_NUMBER() OVER (PARTITION BY accession_number ORDER BY seq ASC) = 1
                ON CONFLICT (accession_number) DO NOTHING
            """,
            insert_last_sql="""
                INSERT INTO sec_company_filing
                    (accession_number, cik, form, filing_date, report_date,
                     acceptance_datetime, act, file_number, film_number, items,
                     size, is_xbrl, is_inline_xbrl, primary_document,
                     primary_doc_desc, last_sync_run_id, last_synced_at)
                SELECT accession_number, cik, form, filing_date, report_date,
                       acceptance_datetime, act, file_number, film_number, items,
                       size, is_xbrl, is_inline_xbrl, primary_document,
                       primary_doc_desc, last_sync_run_id, last_synced_at
                FROM stg_sec_company_filing
                QUALIFY ROW_NUMBER() OVER (PARTITION BY accession_number ORDER BY seq DESC) = 1
                ON CONFLICT (accession_number) DO UPDATE SET
                    form = excluded.form,
                    filing_date = excluded.filing_date,
                    report_date = excluded.report_date,
                    acceptance_datetime = excluded.acceptance_datetime,
                    size = excluded.size,
                    is_xbrl = excluded.is_xbrl,
                    is_inline_xbrl = excluded.is_inline_xbrl,
                    primary_document = excluded.primary_document,
                    primary_doc_desc = excluded.primary_doc_desc,
                    last_sync_run_id = excluded.last_sync_run_id,
                    last_synced_at = excluded.last_synced_at
            """,
            rows=rows,
            values_fn=lambda row: [
                row["accession_number"],
                row["cik"],
                row.get("form"),
                row.get("filing_date"),
                row.get("report_date"),
                row.get("acceptance_datetime"),
                row.get("act"),
                row.get("file_number"),
                row.get("film_number"),
                row.get("items"),
                row.get("size"),
                row.get("is_xbrl"),
                row.get("is_inline_xbrl"),
                row.get("primary_document"),
                row.get("primary_doc_desc"),
                sync_run_id,
                now,
            ],
        )

    def get_filing_count(self, cik: int) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM sec_company_filing WHERE cik = ?", [cik]
        ).fetchone()[0]

    def get_filing(self, accession_number: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_company_filing WHERE accession_number = ?",
            [accession_number],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    def get_filings_for_cik(self, cik: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sec_company_filing
            WHERE cik = ?
            ORDER BY filing_date DESC, accession_number DESC
            """,
            [cik],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # Submission staging (composite operation)
    # ------------------------------------------------------------------

    def stage_submission(
        self,
        *,
        cik: int,
        main_payload: dict[str, Any],
        pagination_payloads: list[tuple[str, dict[str, Any]]],
        sync_run_id: str,
        raw_object_id: str,
        load_mode: str,
        recent_limit: int | None = None,
    ) -> dict[str, Any]:
        """Stage one company's full submission into silver: reset lists, run loaders, merge all tables."""
        with self._shard_advisory_lock():
            return self._stage_submission_locked(
                cik=cik,
                main_payload=main_payload,
                pagination_payloads=pagination_payloads,
                sync_run_id=sync_run_id,
                raw_object_id=raw_object_id,
                load_mode=load_mode,
                recent_limit=recent_limit,
            )

    def _stage_submission_locked(
        self,
        *,
        cik: int,
        main_payload: dict[str, Any],
        pagination_payloads: list[tuple[str, dict[str, Any]]],
        sync_run_id: str,
        raw_object_id: str,
        load_mode: str,
        recent_limit: int | None = None,
    ) -> dict[str, Any]:
        from edgar_warehouse.loaders.bronze_submission_extractors import (
            stage_address_loader,
            stage_company_loader,
            stage_former_name_loader,
            stage_manifest_loader,
            stage_pagination_filing_loader,
            stage_recent_filing_loader,
        )

        company_rows = stage_company_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        address_rows = stage_address_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        former_name_rows = stage_former_name_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        manifest_rows = stage_manifest_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        recent_rows = stage_recent_filing_loader(
            main_payload, cik, sync_run_id, raw_object_id, load_mode, recent_limit=recent_limit
        )

        self._conn.execute("DELETE FROM sec_company_former_name WHERE cik = ?", [cik])
        self._conn.execute("DELETE FROM sec_company_submission_file WHERE cik = ?", [cik])

        rows_written = 0
        rows_written += self.merge_company(company_rows, sync_run_id)
        rows_written += self.merge_addresses(address_rows, sync_run_id)
        rows_written += self.merge_former_names(former_name_rows, sync_run_id)
        rows_written += self.merge_submission_files(manifest_rows, sync_run_id)

        # Collect recent + all pagination-file rows and merge in ONE bulk call
        # instead of one call per pagination file (a well-filed company can
        # have 50+ pagination files). merge_filings' staged-bulk upsert already
        # dedupes correctly when the same accession_number appears more than
        # once across recent/pagination rows, so combining is safe and avoids
        # paying per-call staging-table overhead dozens of times per CIK.
        all_filing_rows = list(recent_rows)
        pagination_accessions: list[str] = []
        for _file_name, pagination_payload in pagination_payloads:
            pagination_rows = stage_pagination_filing_loader(
                pagination_payload, cik, sync_run_id, raw_object_id, load_mode
            )
            all_filing_rows.extend(pagination_rows)
            pagination_accessions.extend(
                row["accession_number"] for row in pagination_rows if row.get("accession_number")
            )
        rows_written += self.merge_filings(all_filing_rows, sync_run_id)

        return {
            "rows_written": rows_written,
            "recent_rows": recent_rows,
            "manifest_rows": manifest_rows,
            "recent_accessions": [
                row["accession_number"] for row in recent_rows if row.get("accession_number")
            ],
            "pagination_accessions": pagination_accessions,
        }

    # ------------------------------------------------------------------
    # sec_current_filing_feed
    # ------------------------------------------------------------------

    def merge_current_filing_feed(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            if not row.get("accession_number"):
                continue
            self._conn.execute(
                """
                INSERT INTO sec_current_filing_feed
                    (accession_number, cik, form, company_name, filing_date,
                     accepted_at, filing_href, index_href, summary, source_url,
                     feed_published_at, raw_object_id, last_sync_run_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (accession_number) DO UPDATE SET
                    cik = excluded.cik,
                    form = excluded.form,
                    company_name = excluded.company_name,
                    filing_date = excluded.filing_date,
                    accepted_at = excluded.accepted_at,
                    filing_href = excluded.filing_href,
                    index_href = excluded.index_href,
                    summary = excluded.summary,
                    source_url = excluded.source_url,
                    feed_published_at = excluded.feed_published_at,
                    raw_object_id = excluded.raw_object_id,
                    last_sync_run_id = excluded.last_sync_run_id,
                    last_synced_at = excluded.last_synced_at
                """,
                [
                    row["accession_number"],
                    row.get("cik"),
                    row.get("form"),
                    row.get("company_name"),
                    row.get("filing_date"),
                    row.get("accepted_at"),
                    row.get("filing_href"),
                    row.get("index_href"),
                    row.get("summary"),
                    row.get("source_url"),
                    row.get("feed_published_at"),
                    row.get("raw_object_id"),
                    sync_run_id,
                    now,
                ],
            )
            count += 1
        return count

    def get_current_filing_feed(self, accession_number: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_current_filing_feed WHERE accession_number = ?",
            [accession_number],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    # ------------------------------------------------------------------
    # ownership and ADV parser tables
    # ------------------------------------------------------------------

    def merge_ownership_reporting_owners(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_ownership_reporting_owner
                (accession_number, owner_index, owner_cik, owner_name, is_director,
                 is_officer, is_ten_percent_owner, is_other, officer_title,
                 parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, owner_index) DO UPDATE SET
                owner_cik = excluded.owner_cik,
                owner_name = excluded.owner_name,
                is_director = excluded.is_director,
                is_officer = excluded.is_officer,
                is_ten_percent_owner = excluded.is_ten_percent_owner,
                is_other = excluded.is_other,
                officer_title = excluded.officer_title,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row["owner_index"],
                row.get("owner_cik"),
                row.get("owner_name"),
                row.get("is_director"),
                row.get("is_officer"),
                row.get("is_ten_percent_owner"),
                row.get("is_other"),
                row.get("officer_title"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    def merge_ownership_non_derivative_txns(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_ownership_non_derivative_txn
                (accession_number, owner_index, txn_index, security_title, transaction_date,
                 transaction_code, transaction_shares, transaction_price, acquired_disposed_code,
                 shares_owned_after, ownership_nature, ownership_direct_indirect,
                 parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, owner_index, txn_index) DO UPDATE SET
                security_title = excluded.security_title,
                transaction_date = excluded.transaction_date,
                transaction_code = excluded.transaction_code,
                transaction_shares = excluded.transaction_shares,
                transaction_price = excluded.transaction_price,
                acquired_disposed_code = excluded.acquired_disposed_code,
                shares_owned_after = excluded.shares_owned_after,
                ownership_nature = excluded.ownership_nature,
                ownership_direct_indirect = excluded.ownership_direct_indirect,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row["owner_index"],
                row["txn_index"],
                row.get("security_title"),
                row.get("transaction_date"),
                row.get("transaction_code"),
                row.get("transaction_shares"),
                row.get("transaction_price"),
                row.get("acquired_disposed_code"),
                row.get("shares_owned_after"),
                row.get("ownership_nature"),
                row.get("ownership_direct_indirect"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    def merge_ownership_derivative_txns(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_ownership_derivative_txn
                (accession_number, owner_index, txn_index, security_title, transaction_date,
                 transaction_code, transaction_shares, transaction_price, acquired_disposed_code,
                 shares_owned_after, ownership_nature, ownership_direct_indirect,
                 conversion_or_exercise_price, exercise_date, expiration_date,
                 underlying_security_title, underlying_security_shares, parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, owner_index, txn_index) DO UPDATE SET
                security_title = excluded.security_title,
                transaction_date = excluded.transaction_date,
                transaction_code = excluded.transaction_code,
                transaction_shares = excluded.transaction_shares,
                transaction_price = excluded.transaction_price,
                acquired_disposed_code = excluded.acquired_disposed_code,
                shares_owned_after = excluded.shares_owned_after,
                ownership_nature = excluded.ownership_nature,
                ownership_direct_indirect = excluded.ownership_direct_indirect,
                conversion_or_exercise_price = excluded.conversion_or_exercise_price,
                exercise_date = excluded.exercise_date,
                expiration_date = excluded.expiration_date,
                underlying_security_title = excluded.underlying_security_title,
                underlying_security_shares = excluded.underlying_security_shares,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row["owner_index"],
                row["txn_index"],
                row.get("security_title"),
                row.get("transaction_date"),
                row.get("transaction_code"),
                row.get("transaction_shares"),
                row.get("transaction_price"),
                row.get("acquired_disposed_code"),
                row.get("shares_owned_after"),
                row.get("ownership_nature"),
                row.get("ownership_direct_indirect"),
                row.get("conversion_or_exercise_price"),
                row.get("exercise_date"),
                row.get("expiration_date"),
                row.get("underlying_security_title"),
                row.get("underlying_security_shares"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    def merge_adv_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_adv_filing
                (accession_number, cik, form, adviser_name, sec_file_number, crd_number,
                 effective_date, filing_status, source_format, parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number) DO UPDATE SET
                cik = excluded.cik,
                form = excluded.form,
                adviser_name = excluded.adviser_name,
                sec_file_number = excluded.sec_file_number,
                crd_number = excluded.crd_number,
                effective_date = excluded.effective_date,
                filing_status = excluded.filing_status,
                source_format = excluded.source_format,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row.get("cik"),
                row.get("form"),
                row.get("adviser_name"),
                row.get("sec_file_number"),
                row.get("crd_number"),
                row.get("effective_date"),
                row.get("filing_status"),
                row.get("source_format"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    def merge_adv_offices(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_adv_office
                (accession_number, office_index, office_name, city, state_or_country,
                 country, is_headquarters, parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, office_index) DO UPDATE SET
                office_name = excluded.office_name,
                city = excluded.city,
                state_or_country = excluded.state_or_country,
                country = excluded.country,
                is_headquarters = excluded.is_headquarters,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row["office_index"],
                row.get("office_name"),
                row.get("city"),
                row.get("state_or_country"),
                row.get("country"),
                row.get("is_headquarters"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    def merge_adv_disclosure_events(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_adv_disclosure_event
                (accession_number, event_index, disclosure_category, event_date,
                 is_reported, description, parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, event_index) DO UPDATE SET
                disclosure_category = excluded.disclosure_category,
                event_date = excluded.event_date,
                is_reported = excluded.is_reported,
                description = excluded.description,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row["event_index"],
                row.get("disclosure_category"),
                row.get("event_date"),
                row.get("is_reported"),
                row.get("description"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    def merge_adv_private_funds(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_adv_private_fund
                (accession_number, fund_index, fund_name, fund_type, jurisdiction,
                 aum_amount, parser_version, last_sync_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, fund_index) DO UPDATE SET
                fund_name = excluded.fund_name,
                fund_type = excluded.fund_type,
                jurisdiction = excluded.jurisdiction,
                aum_amount = excluded.aum_amount,
                parser_version = excluded.parser_version,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            rows,
            lambda row: [
                row["accession_number"],
                row["fund_index"],
                row.get("fund_name"),
                row.get("fund_type"),
                row.get("jurisdiction"),
                row.get("aum_amount"),
                row.get("parser_version"),
                sync_run_id,
            ],
        )

    # ------------------------------------------------------------------
    # stg_daily_index_filing
    # ------------------------------------------------------------------

    def merge_daily_index_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        """Upsert staged daily index filing rows. Returns row count."""
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO stg_daily_index_filing
                    (sync_run_id, raw_object_id, source_name, source_url,
                     business_date, source_year, source_quarter, row_ordinal,
                     form, company_name, cik, filing_date, file_name,
                     accession_number, filing_txt_url, record_hash, staged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (business_date, accession_number) DO UPDATE SET
                    sync_run_id = excluded.sync_run_id,
                    raw_object_id = excluded.raw_object_id,
                    source_name = excluded.source_name,
                    source_url = excluded.source_url,
                    source_year = excluded.source_year,
                    source_quarter = excluded.source_quarter,
                    row_ordinal = excluded.row_ordinal,
                    form = excluded.form,
                    company_name = excluded.company_name,
                    cik = excluded.cik,
                    filing_date = excluded.filing_date,
                    file_name = excluded.file_name,
                    filing_txt_url = excluded.filing_txt_url,
                    record_hash = excluded.record_hash,
                    staged_at = excluded.staged_at
                """,
                [
                    sync_run_id,
                    row.get("raw_object_id"),
                    row.get("source_name", "daily_form_index"),
                    row.get("source_url"),
                    row["business_date"],
                    row.get("source_year"),
                    row.get("source_quarter"),
                    row.get("row_ordinal"),
                    row.get("form"),
                    row.get("company_name"),
                    row.get("cik"),
                    row.get("filing_date"),
                    row.get("file_name"),
                    row.get("accession_number"),
                    row.get("filing_txt_url"),
                    row.get("record_hash"),
                    now,
                ],
            )
            count += 1
        return count

    def get_daily_index_filings(self, business_date: str) -> list[dict[str, Any]]:
        """Return all stg_daily_index_filing rows for a given business_date."""
        rows = self._conn.execute(
            "SELECT * FROM stg_daily_index_filing WHERE business_date = ? ORDER BY row_ordinal",
            [business_date],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_daily_index_checkpoint
    # ------------------------------------------------------------------

    def upsert_daily_index_checkpoint(self, row: dict[str, Any]) -> None:
        """Insert or update a daily index checkpoint row."""
        self._conn.execute(
            """
            INSERT INTO sec_daily_index_checkpoint
                (business_date, source_name, source_key, source_url,
                 expected_available_at, first_attempt_at, last_attempt_at,
                 attempt_count, raw_object_id, last_sha256, row_count,
                 distinct_cik_count, distinct_accession_count, status,
                 error_message, finalized_at, last_success_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (business_date) DO UPDATE SET
                first_attempt_at = COALESCE(
                    sec_daily_index_checkpoint.first_attempt_at,
                    excluded.first_attempt_at,
                    sec_daily_index_checkpoint.last_attempt_at,
                    excluded.last_attempt_at
                ),
                last_attempt_at = excluded.last_attempt_at,
                attempt_count = sec_daily_index_checkpoint.attempt_count + 1,
                raw_object_id = excluded.raw_object_id,
                last_sha256 = excluded.last_sha256,
                row_count = excluded.row_count,
                distinct_cik_count = excluded.distinct_cik_count,
                distinct_accession_count = excluded.distinct_accession_count,
                status = excluded.status,
                error_message = excluded.error_message,
                finalized_at = excluded.finalized_at,
                last_success_at = excluded.last_success_at
            """,
            [
                row["business_date"],
                row.get("source_name", "daily_form_index"),
                row["source_key"],
                row["source_url"],
                row["expected_available_at"],
                row.get("first_attempt_at"),
                row.get("last_attempt_at"),
                row.get("attempt_count", 1),
                row.get("raw_object_id"),
                row.get("last_sha256"),
                row.get("row_count"),
                row.get("distinct_cik_count"),
                row.get("distinct_accession_count"),
                row.get("status", "pending"),
                row.get("error_message"),
                row.get("finalized_at"),
                row.get("last_success_at"),
            ],
        )

    def get_daily_index_checkpoint(self, business_date: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_daily_index_checkpoint WHERE business_date = ?",
            [business_date],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    def get_last_successful_checkpoint_date(self) -> str | None:
        """Return the most recent business_date with status='succeeded', or None."""
        result = self._conn.execute(
            """
            SELECT business_date FROM sec_daily_index_checkpoint
            WHERE status = 'succeeded'
            ORDER BY business_date DESC
            LIMIT 1
            """
        ).fetchone()
        return str(result[0]) if result else None

    def get_pending_checkpoint_dates(self, up_to_date: str) -> list[str]:
        """Return business dates that are pending or missing up to up_to_date."""
        rows = self._conn.execute(
            """
            SELECT business_date FROM sec_daily_index_checkpoint
            WHERE status IN ('pending', 'failed_retryable')
              AND business_date <= ?
            ORDER BY business_date ASC
            """,
            [up_to_date],
        ).fetchall()
        return [str(row[0]) for row in rows]

    # ------------------------------------------------------------------
    # sec_raw_object
    # ------------------------------------------------------------------

    def upsert_raw_object(self, row: dict[str, Any]) -> None:
        """Insert or update a raw object row.

        fetched_at is set on first insert and never overwritten on conflict.
        All other mutable fields are updated on conflict.
        """
        for required in ("raw_object_id", "source_url", "storage_path", "sha256", "fetched_at", "http_status"):
            if row.get(required) is None:
                raise ValueError(f"upsert_raw_object: required field '{required}' is missing or None")
        self._conn.execute(
            """
            INSERT INTO sec_raw_object
                (raw_object_id, source_type, cik, accession_number, form,
                 source_url, storage_path, content_type, content_encoding,
                 byte_size, sha256, fetched_at, http_status,
                 source_last_modified, source_etag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (raw_object_id) DO UPDATE SET
                source_type = excluded.source_type,
                cik = excluded.cik,
                accession_number = excluded.accession_number,
                form = excluded.form,
                source_url = excluded.source_url,
                storage_path = excluded.storage_path,
                content_type = excluded.content_type,
                content_encoding = excluded.content_encoding,
                byte_size = excluded.byte_size,
                sha256 = excluded.sha256,
                http_status = excluded.http_status,
                source_last_modified = excluded.source_last_modified,
                source_etag = excluded.source_etag
            """,
            [
                row["raw_object_id"],
                row.get("source_type"),
                row.get("cik"),
                row.get("accession_number"),
                row.get("form"),
                row.get("source_url"),
                row.get("storage_path"),
                row.get("content_type"),
                row.get("content_encoding"),
                row.get("byte_size"),
                row.get("sha256"),
                row.get("fetched_at"),
                row.get("http_status"),
                row.get("source_last_modified"),
                row.get("source_etag"),
            ],
        )

    def get_raw_object(self, raw_object_id: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_raw_object WHERE raw_object_id = ?",
            [raw_object_id],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    def get_raw_objects_for_accession(self, accession_number: str, source_type: str | None = None) -> list[dict[str, Any]]:
        """Return raw objects for an accession, optionally filtered by source type."""
        if source_type is None:
            rows = self._conn.execute(
                """
                SELECT * FROM sec_raw_object
                WHERE accession_number = ?
                ORDER BY fetched_at DESC
                """,
                [accession_number],
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM sec_raw_object
                WHERE accession_number = ? AND source_type = ?
                ORDER BY fetched_at DESC
                """,
                [accession_number, source_type],
            ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_filing_attachment
    # ------------------------------------------------------------------

    def merge_filing_attachments(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        """Upsert filing attachment rows. Returns row count."""
        count = 0
        for row in rows:
            for required in ("accession_number", "document_name", "document_type", "document_url"):
                if not row.get(required):
                    raise ValueError(f"merge_filing_attachments: required field '{required}' is missing or None in row {row}")
            self._conn.execute(
                """
                INSERT INTO sec_filing_attachment
                    (accession_number, sequence_number, document_name,
                     document_type, document_description, document_url,
                     is_primary, raw_object_id, last_sync_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (accession_number, document_name) DO UPDATE SET
                    sequence_number = excluded.sequence_number,
                    document_type = excluded.document_type,
                    document_description = excluded.document_description,
                    document_url = excluded.document_url,
                    is_primary = excluded.is_primary,
                    raw_object_id = excluded.raw_object_id,
                    last_sync_run_id = excluded.last_sync_run_id
                """,
                [
                    row["accession_number"],
                    row.get("sequence_number"),
                    row["document_name"],
                    row.get("document_type"),
                    row.get("document_description"),
                    row.get("document_url"),
                    row.get("is_primary", False),
                    row.get("raw_object_id"),
                    sync_run_id,
                ],
            )
            count += 1
        return count

    def get_filing_attachments(self, accession_number: str) -> list[dict[str, Any]]:
        """Return all attachment rows for the given accession number."""
        rows = self._conn.execute(
            "SELECT * FROM sec_filing_attachment WHERE accession_number = ?",
            [accession_number],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_filing_text
    # ------------------------------------------------------------------

    def upsert_filing_text(self, row: dict[str, Any]) -> None:
        """Insert or update a filing text extraction row.

        Raises ValueError if any required field is missing or None.
        """
        for required in (
            "accession_number",
            "text_version",
            "source_document_name",
            "text_storage_path",
            "text_sha256",
            "char_count",
            "extracted_at",
        ):
            if row.get(required) is None:
                raise ValueError(
                    f"upsert_filing_text: required field '{required}' is missing or None"
                )
        self._conn.execute(
            """
            INSERT INTO sec_filing_text
                (accession_number, text_version, source_document_name,
                 text_storage_path, text_sha256, char_count, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, text_version) DO UPDATE SET
                source_document_name = excluded.source_document_name,
                text_storage_path = excluded.text_storage_path,
                text_sha256 = excluded.text_sha256,
                char_count = excluded.char_count,
                extracted_at = excluded.extracted_at
            """,
            [
                row["accession_number"],
                row["text_version"],
                row["source_document_name"],
                row["text_storage_path"],
                row["text_sha256"],
                row["char_count"],
                row["extracted_at"],
            ],
        )

    def get_filing_text(
        self, accession_number: str, text_version: str
    ) -> dict[str, Any] | None:
        """Return the filing text row for the given accession and version, or None."""
        result = self._conn.execute(
            "SELECT * FROM sec_filing_text WHERE accession_number = ? AND text_version = ?",
            [accession_number, text_version],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    def get_all_filing_texts(self, accession_number: str) -> list[dict[str, Any]]:
        """Return all text extraction rows for an accession, ordered by text_version."""
        rows = self._conn.execute(
            "SELECT * FROM sec_filing_text WHERE accession_number = ? ORDER BY text_version",
            [accession_number],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # sec_parse_run
    # ------------------------------------------------------------------

    def start_parse_run(self, row: dict[str, Any]) -> None:
        """Insert a new parse run with status='running'."""
        required = ["parse_run_id", "parser_name", "parser_version", "target_form_family"]
        for f in required:
            if row.get(f) is None:
                raise ValueError(f"start_parse_run: required field '{f}' is missing or None")
        started_at = row.get("started_at") or datetime.now(UTC)
        self._conn.execute(
            """
            INSERT INTO sec_parse_run
                (parse_run_id, accession_number, parser_name, parser_version,
                 target_form_family, status, started_at, rows_written)
            VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            [
                row["parse_run_id"],
                row.get("accession_number"),
                row["parser_name"],
                row["parser_version"],
                row["target_form_family"],
                started_at,
                row.get("rows_written"),
            ],
        )

    def complete_parse_run(
        self,
        parse_run_id: str,
        status: str = "succeeded",
        error_code: str | None = None,
        error_message: str | None = None,
        rows_written: int | None = None,
    ) -> None:
        """Update an existing parse run to a terminal status."""
        if not parse_run_id:
            raise ValueError("parse_run_id must not be empty")
        self._conn.execute(
            """
            UPDATE sec_parse_run
            SET status = ?, completed_at = ?, error_code = ?, error_message = ?, rows_written = COALESCE(?, rows_written)
            WHERE parse_run_id = ?
            """,
            [status, datetime.now(UTC), error_code, error_message, rows_written, parse_run_id],
        )

    def get_parse_run(self, parse_run_id: str) -> dict[str, Any] | None:
        """Return the parse run row as a dict, or None if not found."""
        result = self._conn.execute(
            "SELECT * FROM sec_parse_run WHERE parse_run_id = ?", [parse_run_id]
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    # ------------------------------------------------------------------
    # sec_sync_run
    # ------------------------------------------------------------------

    def start_sync_run(self, row: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO sec_sync_run
                (sync_run_id, sync_mode, scope_type, scope_key, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (sync_run_id) DO UPDATE SET
                sync_mode = excluded.sync_mode,
                scope_type = excluded.scope_type,
                scope_key = excluded.scope_key,
                started_at = excluded.started_at,
                status = excluded.status
            """,
            [
                row["sync_run_id"],
                row["sync_mode"],
                row["scope_type"],
                row.get("scope_key"),
                row.get("started_at", datetime.now(UTC)),
                row.get("status", "running"),
            ],
        )

    def complete_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str,
        rows_inserted: int | None = None,
        rows_updated: int | None = None,
        rows_deleted: int | None = None,
        rows_skipped: int | None = None,
        error_message: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE sec_sync_run
            SET completed_at = ?, status = ?, rows_inserted = ?, rows_updated = ?,
                rows_deleted = ?, rows_skipped = ?, error_message = ?
            WHERE sync_run_id = ?
            """,
            [
                datetime.now(UTC),
                status,
                rows_inserted,
                rows_updated,
                rows_deleted,
                rows_skipped,
                error_message,
                sync_run_id,
            ],
        )

    def get_sync_run(self, sync_run_id: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_sync_run WHERE sync_run_id = ?",
            [sync_run_id],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    # ------------------------------------------------------------------
    # pipeline_run
    # ------------------------------------------------------------------

    def start_pipeline_run(self, row: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO pipeline_run
                (pipeline_run_id, command_name, runtime_mode, environment_name,
                 started_at, status, arguments_json, scope_json, bronze_root,
                 storage_root, silver_root, serving_export_root)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (pipeline_run_id) DO UPDATE SET
                command_name = excluded.command_name,
                runtime_mode = excluded.runtime_mode,
                environment_name = excluded.environment_name,
                started_at = excluded.started_at,
                status = excluded.status,
                arguments_json = excluded.arguments_json,
                scope_json = excluded.scope_json,
                bronze_root = excluded.bronze_root,
                storage_root = excluded.storage_root,
                silver_root = excluded.silver_root,
                serving_export_root = excluded.serving_export_root,
                completed_at = NULL,
                writes_json = NULL,
                raw_writes_json = NULL,
                metrics_json = NULL,
                error_message = NULL,
                verification_status = NULL,
                last_verified_at = NULL,
                verification_report_json = NULL
            """,
            [
                row["pipeline_run_id"],
                row["command_name"],
                row["runtime_mode"],
                row.get("environment_name"),
                row.get("started_at", datetime.now(UTC)),
                row.get("status", "running"),
                self._json_text(row.get("arguments") or {}),
                self._json_text(row.get("scope") or {}),
                row.get("bronze_root"),
                row.get("storage_root"),
                row.get("silver_root"),
                row.get("serving_export_root"),
            ],
        )

    def complete_pipeline_run(
        self,
        pipeline_run_id: str,
        *,
        status: str,
        writes: list[dict[str, Any]],
        raw_writes: list[dict[str, Any]],
        metrics: dict[str, Any],
        error_message: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE pipeline_run
            SET completed_at = ?,
                status = ?,
                writes_json = ?,
                raw_writes_json = ?,
                metrics_json = ?,
                error_message = ?
            WHERE pipeline_run_id = ?
            """,
            [
                datetime.now(UTC),
                status,
                self._json_text(writes),
                self._json_text(raw_writes),
                self._json_text(metrics),
                error_message,
                pipeline_run_id,
            ],
        )

    def record_pipeline_verification(
        self,
        pipeline_run_id: str,
        *,
        verification_status: str,
        report: dict[str, Any],
    ) -> None:
        self._conn.execute(
            """
            UPDATE pipeline_run
            SET verification_status = ?,
                last_verified_at = ?,
                verification_report_json = ?
            WHERE pipeline_run_id = ?
            """,
            [
                verification_status,
                datetime.now(UTC),
                self._json_text(report),
                pipeline_run_id,
            ],
        )

    def get_pipeline_run(self, pipeline_run_id: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM pipeline_run WHERE pipeline_run_id = ?",
            [pipeline_run_id],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(value, default=str, sort_keys=True)

    # ------------------------------------------------------------------
    # sec_source_checkpoint
    # ------------------------------------------------------------------

    def upsert_source_checkpoint(self, row: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO sec_source_checkpoint
                (source_name, source_key, raw_object_id, last_success_at, last_sha256,
                 last_etag, last_modified_at, last_acceptance_datetime_seen,
                 last_accession_number_seen, bronze_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_name, source_key) DO UPDATE SET
                raw_object_id = excluded.raw_object_id,
                last_success_at = excluded.last_success_at,
                last_sha256 = excluded.last_sha256,
                last_etag = excluded.last_etag,
                last_modified_at = excluded.last_modified_at,
                last_acceptance_datetime_seen = excluded.last_acceptance_datetime_seen,
                last_accession_number_seen = excluded.last_accession_number_seen,
                bronze_path = excluded.bronze_path
            """,
            [
                row["source_name"],
                row["source_key"],
                row.get("raw_object_id"),
                row.get("last_success_at"),
                row.get("last_sha256"),
                row.get("last_etag"),
                row.get("last_modified_at"),
                row.get("last_acceptance_datetime_seen"),
                row.get("last_accession_number_seen"),
                row.get("bronze_path"),
            ],
        )

    def get_source_checkpoint(self, source_name: str, source_key: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            """
            SELECT * FROM sec_source_checkpoint
            WHERE source_name = ? AND source_key = ?
            """,
            [source_name, source_key],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    # ------------------------------------------------------------------
    # sec_company_sync_state
    # ------------------------------------------------------------------

    def upsert_company_sync_state(self, row: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO sec_company_sync_state
                (cik, tracking_status, bootstrap_completed_at, last_main_sync_at,
                 last_main_raw_object_id, last_main_sha256, latest_filing_date_seen,
                 latest_acceptance_datetime_seen, pagination_files_expected,
                 pagination_files_loaded, pagination_completed_at, next_sync_after,
                 last_error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (cik) DO UPDATE SET
                tracking_status = excluded.tracking_status,
                bootstrap_completed_at = COALESCE(excluded.bootstrap_completed_at, sec_company_sync_state.bootstrap_completed_at),
                last_main_sync_at = COALESCE(excluded.last_main_sync_at, sec_company_sync_state.last_main_sync_at),
                last_main_raw_object_id = COALESCE(excluded.last_main_raw_object_id, sec_company_sync_state.last_main_raw_object_id),
                last_main_sha256 = COALESCE(excluded.last_main_sha256, sec_company_sync_state.last_main_sha256),
                latest_filing_date_seen = COALESCE(excluded.latest_filing_date_seen, sec_company_sync_state.latest_filing_date_seen),
                latest_acceptance_datetime_seen = COALESCE(excluded.latest_acceptance_datetime_seen, sec_company_sync_state.latest_acceptance_datetime_seen),
                pagination_files_expected = COALESCE(excluded.pagination_files_expected, sec_company_sync_state.pagination_files_expected),
                pagination_files_loaded = COALESCE(excluded.pagination_files_loaded, sec_company_sync_state.pagination_files_loaded),
                pagination_completed_at = COALESCE(excluded.pagination_completed_at, sec_company_sync_state.pagination_completed_at),
                next_sync_after = COALESCE(excluded.next_sync_after, sec_company_sync_state.next_sync_after),
                last_error_message = excluded.last_error_message
            """,
            [
                row["cik"],
                row.get("tracking_status", "active"),
                row.get("bootstrap_completed_at"),
                row.get("last_main_sync_at"),
                row.get("last_main_raw_object_id"),
                row.get("last_main_sha256"),
                row.get("latest_filing_date_seen"),
                row.get("latest_acceptance_datetime_seen"),
                row.get("pagination_files_expected"),
                row.get("pagination_files_loaded"),
                row.get("pagination_completed_at"),
                row.get("next_sync_after"),
                row.get("last_error_message"),
            ],
        )

    def get_company_sync_state(self, cik: int) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_company_sync_state WHERE cik = ?",
            [cik],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    def get_active_ciks(self) -> list[dict[str, Any]]:
        """Return CIKs already marked active in silver — used by seed-universe to skip re-bootstrapping."""
        rows = self._conn.execute(
            "SELECT cik FROM sec_company_sync_state WHERE tracking_status = 'active'"
        ).fetchall()
        return [{"cik": row[0]} for row in rows]

    def get_ciks_with_bronze(self, tracking_status_filter: str = "all") -> list[dict[str, Any]]:
        """Return CIKs that have bronze submissions loaded (have a submissions_main checkpoint).

        Used by seed-silver-batches to build a batch file for reprocessing already-loaded bronze
        through silver, MDM, and gold without re-downloading from SEC.
        """
        if tracking_status_filter == "all":
            sql = """
                SELECT DISTINCT s.cik
                FROM sec_company_sync_state s
                WHERE EXISTS (
                    SELECT 1 FROM sec_source_checkpoint c
                    WHERE c.source_name = 'submissions_main'
                      AND c.source_key = 'cik:' || CAST(s.cik AS VARCHAR)
                )
                ORDER BY s.cik
            """
            rows = self._conn.execute(sql).fetchall()
        else:
            sql = """
                SELECT DISTINCT s.cik
                FROM sec_company_sync_state s
                WHERE s.tracking_status = ?
                  AND EXISTS (
                      SELECT 1 FROM sec_source_checkpoint c
                      WHERE c.source_name = 'submissions_main'
                        AND c.source_key = 'cik:' || CAST(s.cik AS VARCHAR)
                  )
                ORDER BY s.cik
            """
            rows = self._conn.execute(sql, [tracking_status_filter]).fetchall()
        return [{"cik": row[0]} for row in rows]

    # ------------------------------------------------------------------
    # sec_reconcile_finding
    # ------------------------------------------------------------------

    def insert_reconcile_findings(self, rows: list[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO sec_reconcile_finding
                    (reconcile_run_id, cik, scope_type, object_type, object_key, drift_type,
                     expected_value_hash, actual_value_hash, severity, recommended_action,
                     status, detected_at, resolved_at, resync_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (reconcile_run_id, cik, scope_type, object_type, object_key, drift_type)
                DO UPDATE SET
                    expected_value_hash = excluded.expected_value_hash,
                    actual_value_hash = excluded.actual_value_hash,
                    severity = excluded.severity,
                    recommended_action = excluded.recommended_action,
                    status = excluded.status,
                    detected_at = excluded.detected_at,
                    resolved_at = excluded.resolved_at,
                    resync_run_id = excluded.resync_run_id
                """,
                [
                    row["reconcile_run_id"],
                    row["cik"],
                    row["scope_type"],
                    row["object_type"],
                    row["object_key"],
                    row["drift_type"],
                    row.get("expected_value_hash"),
                    row.get("actual_value_hash"),
                    row.get("severity", "medium"),
                    row.get("recommended_action", "manual_review"),
                    row.get("status", "detected"),
                    row.get("detected_at", datetime.now(UTC)),
                    row.get("resolved_at"),
                    row.get("resync_run_id"),
                ],
            )
            count += 1
        return count

    def get_reconcile_findings(self, reconcile_run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM sec_reconcile_finding
            WHERE reconcile_run_id = ?
            ORDER BY cik, scope_type, object_type, object_key
            """,
            [reconcile_run_id],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    def get_table_counts(self) -> dict[str, int]:
        """Return current row count for every silver table, keyed by table name."""
        tables = [
            "sec_tracked_universe",
            "sec_company",
            "sec_company_ticker",
            "sec_company_address",
            "sec_company_former_name",
            "sec_company_submission_file",
            "sec_company_filing",
            "sec_current_filing_feed",
            "stg_daily_index_filing",
            "sec_daily_index_checkpoint",
            "sec_raw_object",
            "sec_filing_attachment",
            "sec_filing_text",
            "sec_parse_run",
            "sec_ownership_reporting_owner",
            "sec_ownership_non_derivative_txn",
            "sec_ownership_derivative_txn",
            "sec_adv_filing",
            "sec_adv_office",
            "sec_adv_disclosure_event",
            "sec_adv_private_fund",
            "sec_sync_run",
            "pipeline_run",
            "sec_source_checkpoint",
            "sec_company_sync_state",
            "sec_reconcile_finding",
        ]
        counts: dict[str, int] = {}
        for table in tables:
            exists = self._conn.execute(
                "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1",
                [table],
            ).fetchone()
            if exists is None:
                counts[table] = 0
                continue
            row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        return counts

    # ------------------------------------------------------------------
    # Fundamentals namespace — Branch B silver tables
    # ------------------------------------------------------------------

    def merge_financial_facts(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows_bulk(
            staging_table="stg_sec_financial_fact",
            staging_ddl="""
                CREATE TEMP TABLE IF NOT EXISTS stg_sec_financial_fact (
                    seq                 BIGINT,
                    cik                 BIGINT,
                    accession_number    TEXT,
                    fiscal_year         INTEGER,
                    fiscal_period       TEXT,
                    period_end          DATE,
                    period_start        DATE,
                    form_type           TEXT,
                    concept             TEXT,
                    value               DOUBLE,
                    unit                TEXT,
                    decimals            INTEGER,
                    segment             TEXT,
                    parser_version      TEXT
                )
            """,
            insert_first_sql="""
                INSERT INTO sec_financial_fact
                    (cik, accession_number, fiscal_year, fiscal_period, period_end, period_start,
                     form_type, concept, value, unit, decimals, segment, parser_version)
                SELECT cik, accession_number, fiscal_year, fiscal_period, period_end, period_start,
                       form_type, concept, value, unit, decimals, segment, parser_version
                FROM stg_sec_financial_fact
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY cik, accession_number, concept, fiscal_period, segment, period_end, period_start
                    ORDER BY seq ASC
                ) = 1
                ON CONFLICT (cik, accession_number, concept, fiscal_period, segment, period_end, period_start) DO NOTHING
            """,
            insert_last_sql="""
                INSERT INTO sec_financial_fact
                    (cik, accession_number, fiscal_year, fiscal_period, period_end, period_start,
                     form_type, concept, value, unit, decimals, segment, parser_version)
                SELECT cik, accession_number, fiscal_year, fiscal_period, period_end, period_start,
                       form_type, concept, value, unit, decimals, segment, parser_version
                FROM stg_sec_financial_fact
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY cik, accession_number, concept, fiscal_period, segment, period_end, period_start
                    ORDER BY seq DESC
                ) = 1
                ON CONFLICT (cik, accession_number, concept, fiscal_period, segment, period_end, period_start) DO UPDATE SET
                    value = excluded.value,
                    decimals = excluded.decimals,
                    parser_version = excluded.parser_version
            """,
            rows=rows,
            values_fn=lambda r: [
                r["cik"], r["accession_number"], r.get("fiscal_year"),
                r["fiscal_period"], r.get("period_end"),
                r.get("period_start", _INSTANT_FACT_PERIOD_START_SENTINEL),
                r.get("form_type", ""),
                r["concept"], r.get("value"), r.get("unit"),
                r.get("decimals"), r.get("segment", "consolidated"),
                r.get("parser_version"),
            ],
        )

    def merge_financial_derived(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows_bulk(
            staging_table="stg_sec_financial_derived",
            staging_ddl="""
                CREATE TEMP TABLE IF NOT EXISTS stg_sec_financial_derived (
                    seq                  BIGINT,
                    cik                  BIGINT,
                    accession_number     TEXT,
                    fiscal_year          INTEGER,
                    fiscal_period        TEXT,
                    period_end           DATE,
                    form_type            TEXT,
                    revenue              DOUBLE,
                    gross_profit         DOUBLE,
                    ebitda               DOUBLE,
                    ebit                 DOUBLE,
                    net_income           DOUBLE,
                    eps_diluted          DOUBLE,
                    total_assets         DOUBLE,
                    total_liabilities    DOUBLE,
                    total_equity         DOUBLE,
                    cash_and_equivalents DOUBLE,
                    total_debt           DOUBLE,
                    current_assets       DOUBLE,
                    current_liabilities  DOUBLE,
                    accounts_receivable  DOUBLE,
                    inventory            DOUBLE,
                    selling_general_admin_expense DOUBLE,
                    retained_earnings    DOUBLE,
                    depreciation_amortization DOUBLE,
                    property_plant_equipment_net DOUBLE,
                    shares_outstanding   DOUBLE,
                    operating_cash_flow  DOUBLE,
                    capex                DOUBLE,
                    free_cash_flow       DOUBLE,
                    gross_margin         DOUBLE,
                    ebitda_margin        DOUBLE,
                    net_margin           DOUBLE,
                    roic                 DOUBLE,
                    roe                  DOUBLE,
                    roa                  DOUBLE,
                    parser_version       TEXT
                )
            """,
            insert_first_sql="""
                INSERT INTO sec_financial_derived
                    (cik, accession_number, fiscal_year, fiscal_period, period_end, form_type,
                     revenue, gross_profit, ebitda, ebit, net_income, eps_diluted,
                     total_assets, total_liabilities, total_equity, cash_and_equivalents,
                     total_debt, current_assets, current_liabilities, accounts_receivable,
                     inventory, selling_general_admin_expense, retained_earnings,
                     depreciation_amortization, property_plant_equipment_net,
                     shares_outstanding, operating_cash_flow, capex, free_cash_flow,
                     gross_margin, ebitda_margin, net_margin, roic, roe, roa,
                     parser_version)
                SELECT cik, accession_number, fiscal_year, fiscal_period, period_end, form_type,
                       revenue, gross_profit, ebitda, ebit, net_income, eps_diluted,
                       total_assets, total_liabilities, total_equity, cash_and_equivalents,
                       total_debt, current_assets, current_liabilities, accounts_receivable,
                       inventory, selling_general_admin_expense, retained_earnings,
                       depreciation_amortization, property_plant_equipment_net,
                       shares_outstanding, operating_cash_flow, capex, free_cash_flow,
                       gross_margin, ebitda_margin, net_margin, roic, roe, roa,
                       parser_version
                FROM stg_sec_financial_derived
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY cik, accession_number, fiscal_period, period_end
                    ORDER BY seq ASC
                ) = 1
                ON CONFLICT (cik, accession_number, fiscal_period, period_end) DO NOTHING
            """,
            insert_last_sql="""
                INSERT INTO sec_financial_derived
                    (cik, accession_number, fiscal_year, fiscal_period, period_end, form_type,
                     revenue, gross_profit, ebitda, ebit, net_income, eps_diluted,
                     total_assets, total_liabilities, total_equity, cash_and_equivalents,
                     total_debt, current_assets, current_liabilities, accounts_receivable,
                     inventory, selling_general_admin_expense, retained_earnings,
                     depreciation_amortization, property_plant_equipment_net,
                     shares_outstanding, operating_cash_flow, capex, free_cash_flow,
                     gross_margin, ebitda_margin, net_margin, roic, roe, roa,
                     parser_version)
                SELECT cik, accession_number, fiscal_year, fiscal_period, period_end, form_type,
                       revenue, gross_profit, ebitda, ebit, net_income, eps_diluted,
                       total_assets, total_liabilities, total_equity, cash_and_equivalents,
                       total_debt, current_assets, current_liabilities, accounts_receivable,
                       inventory, selling_general_admin_expense, retained_earnings,
                       depreciation_amortization, property_plant_equipment_net,
                       shares_outstanding, operating_cash_flow, capex, free_cash_flow,
                       gross_margin, ebitda_margin, net_margin, roic, roe, roa,
                       parser_version
                FROM stg_sec_financial_derived
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY cik, accession_number, fiscal_period, period_end
                    ORDER BY seq DESC
                ) = 1
                ON CONFLICT (cik, accession_number, fiscal_period, period_end) DO UPDATE SET
                    revenue = excluded.revenue,
                    gross_profit = excluded.gross_profit,
                    ebitda = excluded.ebitda,
                    ebit = excluded.ebit,
                    net_income = excluded.net_income,
                    eps_diluted = excluded.eps_diluted,
                    total_assets = excluded.total_assets,
                    total_liabilities = excluded.total_liabilities,
                    total_equity = excluded.total_equity,
                    cash_and_equivalents = excluded.cash_and_equivalents,
                    total_debt = excluded.total_debt,
                    current_assets = excluded.current_assets,
                    current_liabilities = excluded.current_liabilities,
                    accounts_receivable = excluded.accounts_receivable,
                    inventory = excluded.inventory,
                    selling_general_admin_expense = excluded.selling_general_admin_expense,
                    retained_earnings = excluded.retained_earnings,
                    depreciation_amortization = excluded.depreciation_amortization,
                    property_plant_equipment_net = excluded.property_plant_equipment_net,
                    shares_outstanding = excluded.shares_outstanding,
                    operating_cash_flow = excluded.operating_cash_flow,
                    capex = excluded.capex,
                    free_cash_flow = excluded.free_cash_flow,
                    gross_margin = excluded.gross_margin,
                    ebitda_margin = excluded.ebitda_margin,
                    net_margin = excluded.net_margin,
                    roic = excluded.roic,
                    roe = excluded.roe,
                    roa = excluded.roa,
                    parser_version = excluded.parser_version
            """,
            rows=rows,
            values_fn=lambda r: [
                r["cik"], r["accession_number"], r.get("fiscal_year"),
                r["fiscal_period"], r.get("period_end"), r.get("form_type", ""),
                r.get("revenue"), r.get("gross_profit"), r.get("ebitda"),
                r.get("ebit"), r.get("net_income"), r.get("eps_diluted"),
                r.get("total_assets"), r.get("total_liabilities"), r.get("total_equity"),
                r.get("cash_and_equivalents"), r.get("total_debt"),
                r.get("current_assets"), r.get("current_liabilities"),
                r.get("accounts_receivable"), r.get("inventory"),
                r.get("selling_general_admin_expense"), r.get("retained_earnings"),
                r.get("depreciation_amortization"),
                r.get("property_plant_equipment_net"), r.get("shares_outstanding"),
                r.get("operating_cash_flow"), r.get("capex"), r.get("free_cash_flow"),
                r.get("gross_margin"), r.get("ebitda_margin"), r.get("net_margin"),
                r.get("roic"), r.get("roe"), r.get("roa"),
                r.get("parser_version"),
            ],
        )

    def merge_earnings_releases(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_earnings_release
                (cik, accession_number, filing_date, fiscal_year, fiscal_quarter,
                 period_end, revenue_gaap, net_income_gaap, eps_gaap_diluted,
                 has_non_gaap, has_guidance, parser_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (cik, accession_number) DO UPDATE SET
                fiscal_year = excluded.fiscal_year,
                fiscal_quarter = excluded.fiscal_quarter,
                period_end = excluded.period_end,
                revenue_gaap = excluded.revenue_gaap,
                net_income_gaap = excluded.net_income_gaap,
                eps_gaap_diluted = excluded.eps_gaap_diluted,
                has_non_gaap = excluded.has_non_gaap,
                has_guidance = excluded.has_guidance,
                parser_version = excluded.parser_version
            """,
            rows,
            lambda r: [
                r["cik"], r["accession_number"], r.get("filing_date"),
                r.get("fiscal_year"), r.get("fiscal_quarter"),
                r.get("period_end"), r.get("revenue_gaap"), r.get("net_income_gaap"),
                r.get("eps_gaap_diluted"),
                bool(r.get("has_non_gaap", False)),
                bool(r.get("has_guidance", False)),
                r.get("parser_version"),
            ],
        )

    def merge_accounting_flags(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_accounting_flag
                (cik, accession_number, fiscal_year, period_end, form_type,
                 auditor_name, auditor_pcaob_id, auditor_location, icfr_attestation,
                 auditor_changed, beneish_m_score, altman_z_score, piotroski_f_score,
                 parser_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (cik, accession_number) DO UPDATE SET
                auditor_name = excluded.auditor_name,
                auditor_pcaob_id = excluded.auditor_pcaob_id,
                auditor_location = excluded.auditor_location,
                icfr_attestation = excluded.icfr_attestation,
                auditor_changed = excluded.auditor_changed,
                beneish_m_score = COALESCE(excluded.beneish_m_score, sec_accounting_flag.beneish_m_score),
                altman_z_score = COALESCE(excluded.altman_z_score, sec_accounting_flag.altman_z_score),
                piotroski_f_score = COALESCE(excluded.piotroski_f_score, sec_accounting_flag.piotroski_f_score),
                parser_version = excluded.parser_version
            """,
            rows,
            lambda r: [
                r["cik"], r["accession_number"], r["fiscal_year"],
                r.get("period_end"), r.get("form_type", "10-K"),
                r.get("auditor_name"), r.get("auditor_pcaob_id"),
                r.get("auditor_location"), r.get("icfr_attestation"),
                r.get("auditor_changed"),
                r.get("beneish_m_score"), r.get("altman_z_score"),
                r.get("piotroski_f_score"),
                r.get("parser_version"),
            ],
        )

    def update_accounting_flag_scores(
        self,
        cik: int,
        accession_number: str,
        beneish_m_score: float | None,
        altman_z_score: float | None,
        piotroski_f_score: int | None,
    ) -> None:
        """Back-fill forensic scores into an existing sec_accounting_flag row."""
        self._conn.execute(
            """
            UPDATE sec_accounting_flag
            SET beneish_m_score   = COALESCE(?, beneish_m_score),
                altman_z_score    = COALESCE(?, altman_z_score),
                piotroski_f_score = COALESCE(?, piotroski_f_score)
            WHERE cik = ? AND accession_number = ?
            """,
            [beneish_m_score, altman_z_score, piotroski_f_score,
             int(cik), accession_number],
        )

    def merge_executive_records(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_executive_record
                (cik, accession_number, fiscal_year, exec_name, exec_role,
                 total_comp, base_salary, bonus, stock_awards, option_awards,
                 non_equity_incentive, parser_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (cik, accession_number, exec_name) DO UPDATE SET
                exec_role = excluded.exec_role,
                total_comp = excluded.total_comp,
                base_salary = excluded.base_salary,
                bonus = excluded.bonus,
                stock_awards = excluded.stock_awards,
                option_awards = excluded.option_awards,
                non_equity_incentive = excluded.non_equity_incentive,
                parser_version = excluded.parser_version
            """,
            rows,
            lambda r: [
                r["cik"], r["accession_number"], r.get("fiscal_year"),
                r["exec_name"], r.get("exec_role"),
                r.get("total_comp"), r.get("base_salary"), r.get("bonus"),
                r.get("stock_awards"), r.get("option_awards"),
                r.get("non_equity_incentive"),
                r.get("parser_version"),
            ],
        )

    def merge_thirteenf_holdings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._merge_rows(
            """
            INSERT INTO sec_thirteenf_holding
                (cik, accession_number, holding_index, period_of_report,
                 cusip, issuer_name, security_title, shares_held, market_value,
                 security_class, put_call, discretion_type,
                 voting_auth_sole, voting_auth_shared, voting_auth_none,
                 parser_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (cik, accession_number, holding_index) DO UPDATE SET
                shares_held = excluded.shares_held,
                market_value = excluded.market_value,
                security_class = excluded.security_class,
                parser_version = excluded.parser_version
            """,
            rows,
            lambda r: [
                r["cik"], r["accession_number"], r["holding_index"],
                r.get("period_of_report"), r.get("cusip"), r.get("issuer_name"),
                r.get("security_title"), r.get("shares_held"), r.get("market_value"),
                r.get("security_class"), r.get("put_call"), r.get("discretion_type"),
                r.get("voting_auth_sole"), r.get("voting_auth_shared"),
                r.get("voting_auth_none"), r.get("parser_version"),
            ],
        )

    def _merge_rows(
        self,
        sql: str,
        rows: list[dict[str, Any]],
        values_fn,
    ) -> int:
        count = 0
        for row in rows:
            self._conn.execute(sql, values_fn(row))
            count += 1
        return count

    def _merge_rows_bulk(
        self,
        staging_table: str,
        staging_ddl: str,
        insert_first_sql: str,
        insert_last_sql: str,
        rows: list[dict[str, Any]],
        values_fn,
    ) -> int:
        """Bulk UPSERT via a no-PK staging table, replicating row-by-row last-write-wins.

        `values_fn` must return values in the same column order as `staging_ddl`
        (excluding the leading `seq` column, which this method supplies via
        `enumerate`).

        The row-by-row loop in `_merge_rows` has per-column semantics on
        conflict: columns in the `ON CONFLICT DO UPDATE SET` clause take the
        *last* occurrence's value for a given primary key, while columns NOT
        in that clause (e.g. `period_end`, `fiscal_year`) are set only on the
        row's *first-ever* insert and never overwritten afterwards. A single
        QUALIFY-deduped INSERT cannot reproduce this per-column mix, so two
        passes are used:

        1. `insert_first_sql` — INSERT the *first* (lowest-seq) occurrence per
           PK, `ON CONFLICT DO NOTHING`. Establishes "first-insert-wins"
           columns for brand-new PKs; no-ops for PKs that already existed.
        2. `insert_last_sql` — INSERT the *last* (highest-seq) occurrence per
           PK, `ON CONFLICT DO UPDATE SET <mutable columns>`. Applies
           "last-write-wins" to the mutable columns for both new and
           pre-existing PKs.
        """
        if not rows:
            return 0
        self._conn.execute(staging_ddl)
        try:
            staged = [[i, *values_fn(row)] for i, row in enumerate(rows)]
            placeholders = ", ".join(["?"] * len(staged[0]))
            self._conn.executemany(
                f"INSERT INTO {staging_table} VALUES ({placeholders})", staged
            )
            self._conn.execute(insert_first_sql)
            self._conn.execute(insert_last_sql)
        finally:
            self._conn.execute(f"DELETE FROM {staging_table}")
        return len(rows)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_company_ticker_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse company_tickers_exchange/company_tickers style payloads into rows."""
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return rows

    fields = payload.get("fields")
    data = payload.get("data")
    if isinstance(fields, list) and isinstance(data, list):
        field_names = [str(field) for field in fields]
        for record in data:
            if not isinstance(record, list):
                continue
            item = dict(zip(field_names, record))
            cik = item.get("cik") or item.get("cik_str")
            ticker = item.get("ticker")
            if cik is None or not ticker:
                continue
            rows.append(
                {
                    "cik": int(cik),
                    "ticker": str(ticker),
                    "exchange": str(item.get("exchange")) if item.get("exchange") else None,
                }
            )
        return rows

    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        cik = entry.get("cik_str")
        ticker = entry.get("ticker", "")
        if cik is None:
            continue
        rows.append(
            {
                "cik": int(cik),
                "ticker": str(ticker),
                "exchange": str(entry.get("exchange")) if entry.get("exchange") else None,
            }
        )
    return rows
