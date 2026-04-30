"""Silver layer DuckDB management for the SEC EDGAR warehouse."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError as exc:
    raise ImportError(
        "DuckDB is required for the silver layer. "
        "Install with: pip install 'edgartools[warehouse]'"
    ) from exc


_DDL = """
CREATE TABLE IF NOT EXISTS sec_tracked_universe (
    cik                BIGINT PRIMARY KEY,
    input_ticker       TEXT,
    current_ticker     TEXT,
    universe_source    TEXT    NOT NULL,
    tracking_status    TEXT    NOT NULL DEFAULT 'active',
    history_mode       TEXT    NOT NULL DEFAULT 'recent_only',
    effective_from     TIMESTAMPTZ NOT NULL,
    effective_to       TIMESTAMPTZ,
    load_priority      INTEGER,
    scope_reason       TEXT,
    added_at           TIMESTAMPTZ NOT NULL,
    removed_at         TIMESTAMPTZ
);

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
"""


class SilverDatabase:
    """Manages the silver-layer DuckDB instance for a warehouse root."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._conn.execute(_DDL)
        self._ensure_schema_evolution()

    def _ensure_schema_evolution(self) -> None:
        migration_statements = [
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS input_ticker TEXT",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS current_ticker TEXT",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS universe_source TEXT",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS tracking_status TEXT",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS history_mode TEXT",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS effective_from TIMESTAMPTZ",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS effective_to TIMESTAMPTZ",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS load_priority INTEGER",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS scope_reason TEXT",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ",
            "ALTER TABLE sec_tracked_universe ADD COLUMN IF NOT EXISTS removed_at TIMESTAMPTZ",
            "ALTER TABLE sec_parse_run ADD COLUMN IF NOT EXISTS rows_written INTEGER",
            "ALTER TABLE sec_source_checkpoint ADD COLUMN IF NOT EXISTS bronze_path TEXT",
        ]
        for statement in migration_statements:
            self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # sec_tracked_universe
    # ------------------------------------------------------------------

    def seed_tracked_universe(self, company_tickers_exchange: dict[str, Any]) -> int:
        """Upsert rows from company_tickers_exchange.json into sec_tracked_universe.

        Returns the number of rows inserted or updated.
        """
        rows = _parse_company_ticker_rows(company_tickers_exchange)
        return self.seed_tracked_universe_rows(rows)

    def seed_tracked_universe_rows(self, rows: list[dict[str, Any]]) -> int:
        """Upsert tracked-universe rows that were already parsed from SEC reference data."""
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            cik = row.get("cik")
            ticker = row.get("ticker")
            if cik is None or not ticker:
                continue
            self._conn.execute(
                """
                INSERT INTO sec_tracked_universe
                    (cik, input_ticker, current_ticker, universe_source,
                     tracking_status, history_mode, effective_from, added_at)
                VALUES (?, ?, ?, 'seeded_from_sec_reference', 'active', 'recent_only', ?, ?)
                ON CONFLICT (cik) DO UPDATE SET
                    input_ticker = excluded.input_ticker,
                    current_ticker = excluded.current_ticker,
                    universe_source = excluded.universe_source,
                    tracking_status = excluded.tracking_status,
                    history_mode = excluded.history_mode,
                    effective_from = COALESCE(sec_tracked_universe.effective_from, excluded.effective_from),
                    added_at = COALESCE(sec_tracked_universe.added_at, excluded.added_at)
                """,
                [int(cik), str(ticker), str(ticker), now, now],
            )
            count += 1
        return count

    def auto_enroll_tracked_universe(
        self,
        ciks: list[int],
        *,
        universe_source: str = "auto_discovered",
        scope_reason: str = "daily_index",
    ) -> int:
        now = datetime.now(UTC)
        count = 0
        for cik in sorted(set(ciks)):
            existed = self.get_tracked_universe_entry(cik) is not None
            self._conn.execute(
                """
                INSERT INTO sec_tracked_universe
                    (cik, universe_source, tracking_status, history_mode,
                     effective_from, added_at, scope_reason)
                VALUES (?, ?, 'active', 'recent_only', ?, ?, ?)
                ON CONFLICT (cik) DO NOTHING
                """,
                [cik, universe_source, now, now, scope_reason],
            )
            if not existed:
                count += 1
        return count

    def get_tracked_universe_entry(self, cik: int) -> dict[str, Any] | None:
        result = self._conn.execute(
            "SELECT * FROM sec_tracked_universe WHERE cik = ?", [cik]
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, result))

    def get_tracked_universe_count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM sec_tracked_universe"
        ).fetchone()[0]

    def get_tracked_universe_ciks(self, status_filter: str = "active") -> list[int]:
        rows = self._conn.execute(
            "SELECT cik FROM sec_tracked_universe WHERE tracking_status = ?",
            [status_filter],
        ).fetchall()
        return [row[0] for row in rows]

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
        now = datetime.now(UTC)
        count = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT INTO sec_company_filing
                    (accession_number, cik, form, filing_date, report_date,
                     acceptance_datetime, act, file_number, film_number, items,
                     size, is_xbrl, is_inline_xbrl, primary_document,
                     primary_doc_desc, last_sync_run_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                [
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
            count += 1
        return count

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
            "sec_source_checkpoint",
            "sec_company_sync_state",
            "sec_reconcile_finding",
        ]
        counts: dict[str, int] = {}
        for table in tables:
            row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        return counts

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
