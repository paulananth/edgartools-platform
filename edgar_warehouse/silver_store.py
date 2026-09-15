"""Silver layer DuckDB management for the SEC EDGAR warehouse."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from edgar_warehouse import silver_schema
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer

if TYPE_CHECKING:
    from edgar_warehouse.bookkeeping.store import BookkeepingStore

try:
    import duckdb
except ImportError as exc:
    raise ImportError(
        "DuckDB is required for the silver layer. "
        "Install with: pip install 'edgartools[warehouse]'"
    ) from exc


logger = logging.getLogger(__name__)


_SCHEMA_MIGRATION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migration (
    migration_name             TEXT PRIMARY KEY,
    description                TEXT NOT NULL,
    applied_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


_DDL = f"""

{_SCHEMA_MIGRATION_TABLE_DDL}

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
    last_synced_at             TIMESTAMPTZ,
    -- MDM-ahead-of-silver (mdm-ahead-of-silver map, ticket 02): NULL at
    -- parse time, backfilled by an independent sweep -- never written
    -- synchronously by the ingestion write path itself.
    mdm_entity_id               TEXT
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
    -- MDM-ahead-of-silver (mdm-ahead-of-silver map, ticket 02): NULL at
    -- parse time, backfilled by an independent sweep -- never written
    -- synchronously by the ingestion write path itself.
    mdm_entity_id       TEXT,
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
    -- MDM-ahead-of-silver (mdm-ahead-of-silver map, ticket 02): NULL at
    -- parse time, backfilled by an independent sweep -- never written
    -- synchronously by the ingestion write path itself.
    mdm_entity_id       TEXT,
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
    -- MDM-ahead-of-silver (mdm-ahead-of-silver map, ticket 02): NULL at
    -- parse time, backfilled by an independent sweep -- never written
    -- synchronously by the ingestion write path itself.
    mdm_entity_id       TEXT,
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
    filing_action       TEXT,
    source_format       TEXT,
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    -- MDM-ahead-of-silver (mdm-ahead-of-silver map, ticket 02): NULL at
    -- parse time, backfilled by an independent sweep -- never written
    -- synchronously by the ingestion write path itself.
    mdm_entity_id       TEXT
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
    fund_index          BIGINT,
    filing_id           TEXT,
    adviser_crd_number  TEXT,
    private_fund_id     TEXT,
    reference_id        TEXT,
    schedule_section    TEXT,
    reporting_role      TEXT,
    filing_action       TEXT,
    fund_name           TEXT,
    fund_type           TEXT,
    jurisdiction        TEXT,
    aum_amount          DECIMAL(28,2),
    effective_date      DATE,
    source_dataset_period TEXT,
    source_sha256       TEXT,
    parser_version      TEXT,
    last_sync_run_id    TEXT,
    -- MDM-ahead-of-silver (mdm-ahead-of-silver map, ticket 02): NULL at
    -- parse time, backfilled by an independent sweep -- never written
    -- synchronously by the ingestion write path itself.
    mdm_entity_id       TEXT,
    PRIMARY KEY (accession_number, fund_index)
);

CREATE TABLE IF NOT EXISTS sec_adv_firm_roster (
    adviser_crd_number       TEXT,
    dataset_period           TEXT,
    private_funds_reported   BOOLEAN,
    private_fund_count_7b1   BIGINT,
    any_hedge_funds          BOOLEAN,
    hedge_fund_count         BIGINT,
    any_pe_funds             BOOLEAN,
    pe_fund_count            BIGINT,
    total_gross_assets_private_funds DECIMAL(28,2),
    private_fund_count_7b2   BIGINT,
    source_sha256            TEXT,
    parser_version           TEXT,
    last_sync_run_id         TEXT,
    PRIMARY KEY (adviser_crd_number, dataset_period)
);

CREATE TABLE IF NOT EXISTS sec_subsidiary_evidence (
    accession_number      TEXT,
    registrant_cik        BIGINT,
    document_name         TEXT,
    document_type         TEXT,
    row_ordinal           INTEGER,
    legal_name            TEXT,
    jurisdiction          TEXT,
    parent_scope          TEXT,
    immediate_parent_known BOOLEAN,
    effective_date        DATE,
    row_locator           TEXT,
    source_sha256         TEXT,
    parser_version        TEXT,
    last_sync_run_id      TEXT,
    PRIMARY KEY (accession_number, document_name, row_ordinal)
);

CREATE TABLE IF NOT EXISTS sec_auditor_report_evidence (
    accession_number            TEXT,
    registrant_cik              BIGINT,
    form_type                   TEXT,
    document_name               TEXT,
    audited_period_end          DATE,
    report_date                 DATE,
    principal_firm_name         TEXT,
    principal_firm_location     TEXT,
    pcaob_firm_id               TEXT,
    evidence_source             TEXT,
    raw_locator                 TEXT,
    source_sha256               TEXT,
    evidence_fingerprint        TEXT,
    form_ap_filing_id           TEXT,
    original_form_ap_filing_id  TEXT,
    latest_amendment            BOOLEAN,
    parser_version              TEXT,
    last_sync_run_id            TEXT,
    PRIMARY KEY (accession_number, evidence_fingerprint)
);

CREATE TABLE IF NOT EXISTS sec_pcaob_firm_identity (
    pcaob_firm_id    TEXT,
    canonical_name   TEXT,
    city             TEXT,
    state            TEXT,
    country          TEXT,
    status           TEXT,
    snapshot_uri     TEXT,
    snapshot_sha256  TEXT,
    last_sync_run_id TEXT,
    PRIMARY KEY (pcaob_firm_id, snapshot_sha256)
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

CREATE TABLE IF NOT EXISTS discovery_checkpoint (
    scope_type                 TEXT NOT NULL,
    scope_key                  TEXT NOT NULL,
    discovery_source           TEXT NOT NULL,
    status                     TEXT NOT NULL,
    run_id                     TEXT,
    claimed_at                 TIMESTAMPTZ,
    finished_at                TIMESTAMPTZ,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json              TEXT,
    PRIMARY KEY (scope_type, scope_key)
);

-- Run-level lease shared by the Daily Identity Refresh and the Identity
-- Backstop Sweep (release-readiness ticket 45/49) so only one of the two
-- ever runs at a time. Deliberately separate from discovery_checkpoint,
-- which leases individual CIKs within a run, not a whole run against its
-- siblings.
CREATE TABLE IF NOT EXISTS pipeline_run_lease (
    lease_name                 TEXT PRIMARY KEY,
    status                     TEXT NOT NULL DEFAULT 'idle',
    run_id                     TEXT,
    mode                       TEXT,
    acquired_at                TIMESTAMPTZ,
    released_at                TIMESTAMPTZ,
    -- Set when a 'backstop'-mode acquire attempt is deferred (lease busy);
    -- cleared only when a 'backstop'-mode run subsequently releases the
    -- lease successfully. Carries the miss forward across runs/days so the
    -- next available slot resolves to backstop instead of whatever its own
    -- regular schedule would have requested (release-readiness ticket 45's
    -- "prioritize the next available slot" requirement).
    backstop_overdue           BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

CREATE TABLE IF NOT EXISTS gold_manifest (
    run_id                  TEXT NOT NULL,
    command_name            TEXT NOT NULL,
    table_name              TEXT NOT NULL,
    storage_layer           TEXT NOT NULL,
    relative_path           TEXT NOT NULL,
    storage_path            TEXT,
    row_count               BIGINT NOT NULL,
    parquet_sha256          TEXT NOT NULL,
    byte_size               BIGINT,
    previous_run_id         TEXT,
    previous_row_count      BIGINT,
    previous_parquet_sha256 TEXT,
    row_count_delta         BIGINT,
    parquet_changed         BOOLEAN NOT NULL,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, storage_layer, table_name)
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
    -- Ticket 33 (change-propagation map): validity-interval retirement. A
    -- fact absent from a fresher, COMPLETE company-facts snapshot for its
    -- CIK is retired by closing its interval (is_current=FALSE,
    -- valid_to=<retirement time>) rather than being deleted, per
    -- spec.md's "RETIRE ... never physically deletes history" rule.
    -- valid_from marks first capture. Retirement/reinstatement no longer
    -- happen locally (silver-merge-engine-migration Ticket 02: this table
    -- is landing-only); the columns stay for schema-migration history and
    -- merge_candidate_into_canonical's remaining live caller.
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
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
    -- NOTE: Non-GAAP EPS value and beat/miss flags are NOT stored here --
    -- they require cross-period comparison and will land via forward
    -- migration when built. Guidance ranges (revenue/EPS low/mid/high) are
    -- NOT stored here either, but for a different reason: they landed as
    -- ERDP-02's separate sec_guidance_fact table (below), keyed by
    -- accession_number for the join, not as new columns on this table.
    parser_version          TEXT,
    ingested_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number)
);

-- ERDP-02: structured guidance values (low/mid/high) extracted from the
-- earnings-release guidance table, plus firm_manual override/supplement
-- rows. accession_number is NOT NULL DEFAULT '' (not nullable) because
-- DuckDB PRIMARY KEY columns reject NULL; firm_manual rows (no SEC
-- accession) use '' as the "no accession" sentinel instead.
CREATE TABLE IF NOT EXISTS sec_guidance_fact (
    fact_key                BIGINT NOT NULL,
    cik                     BIGINT NOT NULL,
    ticker                  TEXT,
    company_key             BIGINT,
    accession_number        TEXT NOT NULL DEFAULT '',
    metric                  TEXT NOT NULL,   -- controlled vocab: revenue, eps_diluted, ...
    period_type             TEXT NOT NULL,   -- annual | quarterly | range_fy | other
    fiscal_year             INTEGER NOT NULL,
    fiscal_quarter          INTEGER NOT NULL, -- 0 = annual (D4)
    period_end              DATE,
    value_low               DOUBLE,
    value_mid               DOUBLE,
    value_high              DOUBLE,
    unit                    TEXT,
    currency                TEXT,
    is_non_gaap             BOOLEAN NOT NULL DEFAULT FALSE,
    as_of                   DATE NOT NULL,
    source_system           TEXT NOT NULL,   -- sec_8k | sec_10q | sec_10k | firm_manual | other
    source_ref              TEXT,
    excerpt                 TEXT,            -- <=500 chars, raw table cell context
    confidence               TEXT NOT NULL DEFAULT 'medium', -- high | medium | low
    parser_version           TEXT,
    ingested_at              TIMESTAMPTZ DEFAULT NOW(),
    -- Natural key includes source_system so SEC-derived and firm_manual
    -- rows coexist without overwrite (ERDP-02-05).
    PRIMARY KEY (cik, metric, fiscal_year, fiscal_quarter, as_of,
                 accession_number, is_non_gaap, source_system)
);

-- D6: quarantine for candidate guidance facts that fail §5.3 constraints
-- (e.g. all of low/mid/high null, low > high). Not gold-published.
CREATE TABLE IF NOT EXISTS sec_guidance_fact_reject (
    cik                     BIGINT NOT NULL,
    accession_number        TEXT NOT NULL DEFAULT '',
    metric                  TEXT,
    reject_reason           TEXT NOT NULL,
    raw_payload             TEXT,            -- JSON-encoded candidate row
    parser_version          TEXT,
    ingested_at             TIMESTAMPTZ DEFAULT NOW()
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
    -- Forensic scores (computed cross-period by accounting_flags.score_accounting_flags;
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
    -- Ticket 33: same validity-interval retirement as sec_financial_fact
    -- above -- an accession's flag row absent from a fresher, COMPLETE
    -- company-facts snapshot is retired rather than deleted, keeping both
    -- required producers of the company_facts family symmetric instead of
    -- only one of them tracking retirement.
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
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

CREATE TABLE IF NOT EXISTS sec_employment_event (
    accession_number    TEXT NOT NULL,
    event_index         BIGINT NOT NULL,
    cik                 BIGINT NOT NULL,
    event_type          TEXT NOT NULL,
    person_name         TEXT NOT NULL,
    exec_role           TEXT,
    previous_role       TEXT,
    compensation_amount DOUBLE,
    effective_date      DATE NOT NULL,
    parser_version      TEXT NOT NULL,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (accession_number, event_index)
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

CREATE TABLE IF NOT EXISTS sec_thirteenf_filing (
    accession_number         TEXT PRIMARY KEY,
    cik                      BIGINT NOT NULL,
    period_of_report         DATE NOT NULL,
    filing_date              DATE NOT NULL,
    form                     TEXT NOT NULL,
    amendment_type           TEXT,
    confidential_omission    BOOLEAN NOT NULL DEFAULT FALSE,
    effective_status         TEXT NOT NULL DEFAULT 'effective',
    superseded_by_accession  TEXT,
    parser_version           TEXT NOT NULL,
    ingested_at              TIMESTAMPTZ DEFAULT NOW()
);

-- fundamentals-daily-integration map, Ticket 02: accession-level dedup
-- marker for the per-filing/thirteenf bootstrap-fundamentals modes. A
-- brand-new table needs no ALTER-based schema migration on its own --
-- IF NOT EXISTS already covers both fresh and already-existing stores
-- (unlike migrations 010/011, which added columns to tables that already
-- existed). Deliberately not keyed off the content tables themselves
-- (e.g. "does a sec_thirteenf_holding row exist for this accession") --
-- one 13F filing can produce many holding rows, so a partially-written
-- filing would otherwise look "done" after only its first few rows landed.
CREATE TABLE IF NOT EXISTS sec_fundamentals_processed_accession (
    mode                TEXT NOT NULL,       -- 'per-filing' | 'thirteenf'
    accession_number    TEXT NOT NULL,
    processed_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (mode, accession_number)
);

-- fundamentals-daily-integration map, Ticket 03: per-CIK watermark for the
-- entity-facts refresh trigger. Composes with (does not replace)
-- has_companyfacts_at_version's existing one-time-per-parser-version gate
-- -- see run_bootstrap_entity_facts / get_ciks_with_new_qualifying_filing.
CREATE TABLE IF NOT EXISTS sec_entity_facts_refresh_watermark (
    cik                        BIGINT PRIMARY KEY,
    entity_facts_refreshed_at TIMESTAMPTZ
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


# Same-run reads of three landing-only tables (silver-merge-engine-migration
# Ticket 06d, ADR 0011): the writer call that records a row also indexes it,
# and get_filing/get_filing_attachments/get_raw_object answer from that. Per
# table: its key columns, and the columns the old upsert's DO UPDATE SET never
# touched, which keep their first value in the run.
_IN_RUN_LOOKUP_TABLES: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "sec_company_filing": (
        ("accession_number",),
        frozenset({"cik", "act", "file_number", "film_number", "items"}),
    ),
    "sec_filing_attachment": (("accession_number", "document_name"), frozenset()),
    "sec_raw_object": (("raw_object_id",), frozenset({"fetched_at"})),
}


class SilverDatabase:
    """Manages the silver-layer DuckDB instance for a warehouse root."""

    def __init__(self, db_path: str, *, landing_export: LandingExportBuffer | None = None) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._conn.execute(_DDL)
        self._ensure_schema_evolution()
        # Guards .fetch() only (see its docstring): a single DuckDB
        # Connection is not safe for concurrent execute()+description reads
        # from multiple threads. MDMPipeline.derive_relationships() (make-
        # mdm-path-multi-threaded fix) now calls .fetch() from several
        # relationship-type worker threads sharing this same instance --
        # every other method here is still only ever called from the
        # single-threaded bronze/silver capture path, so this lock doesn't
        # add contention there.
        self._fetch_lock = threading.Lock()
        # Rows of _IN_RUN_LOOKUP_TABLES recorded this run: table -> first key
        # value -> remaining key values -> row.
        self._in_run_rows: dict[str, dict[Any, dict[tuple[Any, ...], dict[str, Any]]]] = {
            table_name: {} for table_name in _IN_RUN_LOOKUP_TABLES
        }
        # Opt-in, silver-snowflake-migration map Ticket 01: when set, every
        # merge_*/upsert_* method below also records its rows here via the
        # @track_landing_* decorators, for a later flush to the Snowflake
        # landing zone. None (the default) makes every decorator a no-op --
        # existing callers are unaffected.
        self.landing_export = landing_export

    def _ensure_schema_evolution(self) -> None:
        self._conn.execute(_SCHEMA_MIGRATION_TABLE_DDL)
        for migration_name, description, migrate, requires_transaction in self._schema_migrations():
            if self._schema_migration_applied(migration_name):
                continue
            self._apply_schema_migration(migration_name, description, migrate, requires_transaction)

    def _schema_migrations(self) -> tuple[tuple[str, str, Any, bool], ...]:
        return (
            (
                "001_financial_period_end_pk",
                "Recreate financial tables whose primary keys predate period_end.",
                self._migrate_financial_period_end_pk,
                True,
            ),
            (
                "002_financial_fact_period_start_pk",
                "Recreate sec_financial_fact whose primary key predates period_start.",
                self._migrate_financial_fact_period_start_pk,
                True,
            ),
            (
                "003_parse_run_rows_written",
                "Add rows_written to sec_parse_run.",
                self._add_parse_run_rows_written,
                True,
            ),
            (
                "004_source_checkpoint_bronze_path",
                "Add bronze_path to sec_source_checkpoint.",
                self._add_source_checkpoint_bronze_path,
                True,
            ),
            (
                "005_financial_derived_factor_columns",
                "Add accounting factor input columns to sec_financial_derived.",
                self._add_financial_derived_factor_columns,
                True,
            ),
            (
                "006_adv_pfid_lineage",
                "Add IAPD FilingID, CRD, PFID, section, effective-date and source lineage.",
                self._add_adv_pfid_lineage,
                True,
            ),
            (
                "007_adv_private_fund_fund_index_bigint",
                "Widen sec_adv_private_fund.fund_index SMALLINT -> BIGINT (a real single "
                "March-2026 filing hit 22,277 of the 32,767 SMALLINT ceiling).",
                self._widen_adv_fund_index_to_bigint,
                True,
            ),
            (
                "008_pipeline_run_lease_backstop_overdue",
                "Add backstop_overdue to pipeline_run_lease.",
                self._add_pipeline_run_lease_backstop_overdue,
                True,
            ),
            (
                "009_mdm_entity_id_columns",
                "Add mdm_entity_id to the 5 MDM-ahead-of-silver source tables "
                "(company, adviser, person, fund, security).",
                self._add_mdm_entity_id_columns,
                True,
            ),
            (
                "010_company_facts_retirement_columns",
                "Add valid_from/valid_to/is_current to sec_financial_fact and "
                "sec_accounting_flag (change-propagation map Ticket 33).",
                self._add_company_facts_retirement_columns,
                # False: DuckDB 1.5.2's ALTER TABLE ADD COLUMN ... DEFAULT <expr>
                # against a non-empty table triggers an internal row-backfill
                # rewrite that bumps the table's version; a second ALTER TABLE
                # statement against that same table inside the same explicit
                # transaction then hits
                # "TransactionException: ... another transaction has altered
                # this table" at COMMIT -- reproduced live against real prod
                # data (a 1-row sec_financial_fact table is enough; an empty
                # one never triggers it, which is why no prior test caught
                # this). This migration issues exactly that shape (3 ADD
                # COLUMN statements per table, two of them DEFAULT-bearing) on
                # two tables. Every statement uses IF NOT EXISTS, so it is
                # already safe to run outside the shared transactional
                # envelope (interrupt-and-retry just re-runs any not-yet-added
                # column as a no-op) -- unlike _backup_and_recreate_table-based
                # migrations (001/002/007), which genuinely need that envelope
                # for atomicity across their RENAME+CREATE+INSERT sequence.
                False,
            ),
            (
                "011_financial_fact_retirement_state_observed_at",
                "Add retirement_state_observed_at to sec_financial_fact and "
                "sec_accounting_flag, giving a genuine retirement's own "
                "authority-column tie (ingested_at never advances on retire, "
                "by design) a second, narrower tiebreak column instead of "
                "permanently aborting the publish (fundamentals-daily-"
                "integration map, Ticket 01; closes CLAUDE.md's "
                "'sec_financial_fact retirement publish-conflict' 5-whys "
                "Part B).",
                self._add_financial_fact_retirement_state_observed_at,
                # False: same DuckDB ADD-COLUMN-with-DEFAULT-on-populated-table
                # commit-conflict risk documented for migration 010 above --
                # this migration issues its own DEFAULT-bearing ADD COLUMN per
                # table. Every statement is IF NOT EXISTS, so it's already
                # safe to run outside the shared transactional envelope.
                False,
            ),
        )

    def _schema_migration_applied(self, migration_name: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM schema_migration
            WHERE migration_name = ?
            """,
            [migration_name],
        ).fetchone()
        return row is not None

    def _apply_schema_migration(
        self, migration_name: str, description: str, migrate: Any, requires_transaction: bool = True
    ) -> None:
        if not requires_transaction:
            # No explicit BEGIN/COMMIT: each statement migrate() issues
            # autocommits on its own. Only safe for a migration whose
            # statements are independently idempotent (e.g. all
            # ADD COLUMN IF NOT EXISTS) -- see the "010_company_facts_
            # retirement_columns" entry above for why this exists.
            migrate()
            self._record_schema_migration(migration_name, description)
            return
        self._conn.execute("BEGIN TRANSACTION")
        try:
            migrate()
            self._record_schema_migration(migration_name, description)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def _record_schema_migration(self, migration_name: str, description: str) -> None:
        self._conn.execute(
            """
            INSERT INTO schema_migration (migration_name, description, applied_at)
            VALUES (?, ?, ?)
            """,
            [migration_name, description, datetime.now(UTC)],
        )

    def _add_parse_run_rows_written(self) -> None:
        self._conn.execute("ALTER TABLE sec_parse_run ADD COLUMN IF NOT EXISTS rows_written INTEGER")

    def _add_source_checkpoint_bronze_path(self) -> None:
        self._conn.execute("ALTER TABLE sec_source_checkpoint ADD COLUMN IF NOT EXISTS bronze_path TEXT")

    def _add_financial_derived_factor_columns(self) -> None:
        for column, column_type in _SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS.items():
            self._conn.execute(
                f"ALTER TABLE sec_financial_derived ADD COLUMN IF NOT EXISTS {column} {column_type}"
            )

    def _add_adv_pfid_lineage(self) -> None:
        self._conn.execute(
            "ALTER TABLE sec_adv_filing ADD COLUMN IF NOT EXISTS filing_action TEXT"
        )
        columns = {
            "filing_id": "TEXT",
            "adviser_crd_number": "TEXT",
            "private_fund_id": "TEXT",
            "reference_id": "TEXT",
            "schedule_section": "TEXT",
            "reporting_role": "TEXT",
            "effective_date": "DATE",
            "source_dataset_period": "TEXT",
            "source_sha256": "TEXT",
            "filing_action": "TEXT",
        }
        for column, column_type in columns.items():
            self._conn.execute(
                f"ALTER TABLE sec_adv_private_fund ADD COLUMN IF NOT EXISTS {column} {column_type}"
            )

    def _add_pipeline_run_lease_backstop_overdue(self) -> None:
        # DuckDB's ALTER TABLE ADD COLUMN rejects a NOT NULL constraint
        # ("Adding columns with constraints not yet supported"); DEFAULT
        # alone is sufficient here since every write path (mark/clear) sets
        # an explicit TRUE/FALSE and never NULL.
        self._conn.execute(
            "ALTER TABLE pipeline_run_lease ADD COLUMN IF NOT EXISTS "
            "backstop_overdue BOOLEAN DEFAULT FALSE"
        )

    def _add_mdm_entity_id_columns(self) -> None:
        # mdm-ahead-of-silver map, ticket 02/05: no DEFAULT -- NULL is the
        # deliberate "pending resolution" marker the backfill sweep queries
        # against (WHERE mdm_entity_id IS NULL), mirroring the existing
        # mdm_change_log.exported_at / mdm_relationship_instance.graph_synced_at
        # nullable-column-plus-sweep pattern.
        for table in (
            "sec_company",
            "sec_adv_filing",
            "sec_ownership_reporting_owner",
            "sec_adv_private_fund",
            "sec_ownership_non_derivative_txn",
            "sec_ownership_derivative_txn",
        ):
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT"
            )

    def _add_company_facts_retirement_columns(self) -> None:
        # DuckDB ALTER TABLE ADD COLUMN rejects a NOT NULL constraint (see
        # _add_pipeline_run_lease_backstop_overdue above) -- DEFAULT alone is
        # sufficient: valid_from's DEFAULT NOW() backfills every pre-existing
        # row to "became valid at migration time" (retirement wasn't tracked
        # before, so that's the earliest honest value), and is_current's
        # DEFAULT TRUE backfills every pre-existing row to "current", which
        # is correct since nothing could have retired it before this
        # migration existed.
        for table in ("sec_financial_fact", "sec_accounting_flag"):
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ DEFAULT NOW()"
            )
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ"
            )
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT TRUE"
            )

    def _add_financial_fact_retirement_state_observed_at(self) -> None:
        """Ticket 01 (fundamentals-daily-integration map). DEFAULT NOW()
        backfills every pre-existing row to "as of migration time, this row's
        current retirement state was last observed now" -- the earliest
        honest value, since retirement-state timestamps weren't tracked
        before this column existed (same rationale as
        _add_company_facts_retirement_columns above).
        """
        for table in ("sec_financial_fact", "sec_accounting_flag"):
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                "retirement_state_observed_at TIMESTAMPTZ DEFAULT NOW()"
            )

    def mark_fundamentals_accession_processed(self, mode: str, accession_number: str) -> None:
        """Record that ``mode`` (per-filing | thirteenf) fully wrote this accession.

        Ticket 02 (fundamentals-daily-integration map). Callers must issue
        this only after every real output row for the accession has already
        been written and returned -- this table's whole purpose is letting a
        crash-and-retry never see an accession marked processed without its
        real rows having landed, and this method has no way to enforce that
        ordering itself.

        Landing-only (silver-merge-engine-migration Ticket 12): the readers
        query Snowflake silver, whose dbt model keeps one row per
        (mode, accession_number) by landing `parse_sequence` -- the row from
        the latest load, as the old ON CONFLICT update kept the latest write.
        """
        self._record_landing_passthrough(
            "sec_fundamentals_processed_accession",
            [{"mode": mode, "accession_number": accession_number}],
            defaults={},
            stamp={"processed_at": datetime.now(UTC)},
        )

    def mark_entity_facts_refreshed(self, cik: int) -> None:
        """Record that entity-facts successfully refreshed this CIK just now.

        Ticket 03 (fundamentals-daily-integration map). Callers must issue
        this only after every real output row for the CIK has already been
        written and returned, same ordering contract as
        mark_fundamentals_accession_processed above.

        Landing-only, same as mark_fundamentals_accession_processed above;
        the dbt model keeps one row per cik.
        """
        self._record_landing_passthrough(
            "sec_entity_facts_refresh_watermark",
            [{"cik": int(cik)}],
            defaults={},
            stamp={"entity_facts_refreshed_at": datetime.now(UTC)},
        )

    def _widen_adv_fund_index_to_bigint(self) -> None:
        """``CREATE TABLE IF NOT EXISTS`` never widens an existing store's column type.

        A store created before this migration would keep fund_index SMALLINT
        forever -- and one real filing already used 68% of that ceiling in a
        single month. See "Schema conventions" in CLAUDE.md. DuckDB refuses a
        plain ALTER COLUMN TYPE on a column that is part of a PRIMARY KEY
        (accession_number, fund_index here), so this reuses the same
        backup-and-recreate approach as the period_end PK migrations above.
        """
        row = self._conn.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'sec_adv_private_fund' AND column_name = 'fund_index'
            """
        ).fetchone()
        if row is not None and row[0] == "SMALLINT":
            logger.warning(
                "Migrating sec_adv_private_fund.fund_index SMALLINT -> BIGINT: "
                "backing up the legacy table and copying rows into the current schema."
            )
            self._backup_and_recreate_table(
                "sec_adv_private_fund",
                reason="fund_index_bigint",
                missing_values={},
            )

    def _migrate_financial_period_end_pk(self) -> None:
        """Recreate financial tables whose PK predates PR #57 without data loss.

        ``CREATE TABLE IF NOT EXISTS`` does not alter an existing table's
        constraints, so a store created before the period_end PK fix
        retains the old PK and the ``ON CONFLICT (..., period_end)``
        targets in ``merge_financial_facts``/``merge_financial_derived``
        raise a binder error. The legacy table is retained as ``backup_*`` and
        rows are copied into a current-schema replacement table.
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
                "backing up the legacy table and copying rows into the current schema.",
                table,
            )
            self._backup_and_recreate_table(
                table,
                reason="pre_period_end_pk",
                missing_values={
                    "period_start": f"DATE '{_INSTANT_FACT_PERIOD_START_SENTINEL}'",
                    # Ticket 33's valid_from/is_current are NOT NULL on
                    # sec_financial_fact -- a backed-up pre-Ticket-33 store's
                    # rows have no source value for these, so the recreate's
                    # copy-select must supply one explicitly (the same
                    # reasoning as _add_company_facts_retirement_columns'
                    # ALTER-path migration: treat pre-existing rows as
                    # "became valid, and is current, as of migration time").
                    # Harmless no-op for sec_financial_derived, the other
                    # table this migration also recreates -- it has neither
                    # column, so _table_columns() never selects these keys.
                    "valid_from": "NOW()",
                    "is_current": "TRUE",
                },
            )

    def _migrate_financial_fact_period_start_pk(self) -> None:
        """Recreate sec_financial_fact if its PK predates Stage 2
        of the period_end PK fix (period_start added to the PK).

        Same rationale and backup+copy pattern as
        ``_migrate_financial_period_end_pk``: a store whose sec_financial_fact
        PK already includes period_end (Stage 1) but not period_start (Stage 2)
        would otherwise raise a binder error on the first
        ``merge_financial_facts`` call, since its
        ``ON CONFLICT (..., period_start)`` target has no backing constraint.
        A store still on the pre-Stage-1 PK is handled by the period_end
        migration above, which recreates it via the current Stage-2 schema.
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
                "(Stage 2 of the period_end PK fix): backing up the legacy table "
                "and copying rows into the current schema."
            )
            self._backup_and_recreate_table(
                "sec_financial_fact",
                reason="pre_period_start_pk",
                missing_values={
                    "period_start": f"DATE '{_INSTANT_FACT_PERIOD_START_SENTINEL}'",
                    # Same NOT NULL backfill reasoning as
                    # _migrate_financial_period_end_pk above -- a store on
                    # this pre-Stage-2 PK also predates Ticket 33's
                    # valid_from/is_current columns.
                    "valid_from": "NOW()",
                    "is_current": "TRUE",
                },
            )

    def _backup_and_recreate_table(
        self,
        table: str,
        *,
        reason: str,
        missing_values: dict[str, str],
    ) -> str:
        suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        backup_table = f"backup_{table}_{reason}_{suffix}"
        quoted_table = self._quote_identifier(table)
        quoted_backup = self._quote_identifier(backup_table)

        self._conn.execute(f"ALTER TABLE {quoted_table} RENAME TO {quoted_backup}")
        self._conn.execute(_DDL)

        target_columns = self._table_columns(table)
        backup_columns = set(self._table_columns(backup_table))
        insert_columns = ", ".join(self._quote_identifier(column) for column in target_columns)
        select_exprs = []
        for column in target_columns:
            if column in backup_columns:
                select_exprs.append(self._quote_identifier(column))
            else:
                select_exprs.append(missing_values.get(column, "NULL"))
        self._conn.execute(
            f"""
            INSERT INTO {quoted_table} ({insert_columns})
            SELECT {", ".join(select_exprs)}
            FROM {quoted_backup}
            """
        )
        return backup_table

    def _table_columns(self, table: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'main'
              AND table_name = ?
            ORDER BY ordinal_position
            """,
            [table],
        ).fetchall()
        return [row[0] for row in rows]

    def close(self) -> None:
        self._conn.close()

    def fetch(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dicts.

        API-compatible with ``ShardedSilverReader.fetch`` so a reader-agnostic
        caller can read from either a single writable shard or a multi-shard
        reader.

        Parameters
        ----------
        sql:
            SQL query string.
        params:
            Optional list of positional query parameters.

        Thread-safe: serializes concurrent callers on ``_fetch_lock`` (see
        ``__init__``) since a single DuckDB Connection cannot safely run
        ``execute()`` and read back ``.description`` from more than one
        thread at a time -- MDMPipeline.derive_relationships() calls this
        from multiple relationship-type worker threads.
        """
        with self._fetch_lock:
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
        cause_reference: str | None = None,
    ) -> int:
        """Landing-only (silver-merge-engine-migration Ticket 06e). Callers pass
        bare {cik, ticker, exchange} dicts from the SEC catalogs; each landed
        row adds source_name, source_rank (its position in the whole input,
        skipped rows included), cause_reference when given, and the sync
        stamp. Recording only those bare dicts once landed rows without the
        NOT NULL source_name and suspended LOAD_SILVER_LANDING_TASK
        (silver-snowflake-migration issue 08). A row with no cik or an empty
        ticker is skipped, not raised. The old local DELETE of this
        source_name's earlier snapshot never reached landing: a ticker that
        drops out of a snapshot is a Silver Landing Retirement Record's job."""
        landed_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(rows, start=1):
            if row.get("cik") is None or not row.get("ticker"):
                continue
            landed = {
                "cik": row["cik"],
                "ticker": row["ticker"],
                "exchange": row.get("exchange"),
                "source_name": source_name,
                "source_rank": ordinal,
            }
            if cause_reference is not None:
                landed["cause_reference"] = cause_reference
            landed_rows.append(landed)
        return self._record_landing_passthrough(
            "sec_company_ticker", landed_rows, defaults={}, stamp=self._synced_now_stamp(sync_run_id)
        )

    # ------------------------------------------------------------------
    # sec_company (silver merge)
    # ------------------------------------------------------------------

    def merge_company(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        """Record staged company rows for landing. Returns row count."""
        return self._record_landing_passthrough(
            "sec_company",
            rows,
            defaults={"first_sync_run_id": sync_run_id},
            stamp=self._synced_now_stamp(sync_run_id),
        )

    # ------------------------------------------------------------------
    # sec_company_address
    # ------------------------------------------------------------------

    def merge_addresses(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_company_address", rows, defaults={}, stamp=self._synced_now_stamp(sync_run_id)
        )

    # ------------------------------------------------------------------
    # sec_company_former_name
    # ------------------------------------------------------------------

    def merge_former_names(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_company_former_name", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    # ------------------------------------------------------------------
    # sec_company_submission_file
    # ------------------------------------------------------------------

    def merge_submission_files(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_company_submission_file",
            rows,
            defaults={},
            stamp=self._synced_now_stamp(sync_run_id),
        )

    # ------------------------------------------------------------------
    # sec_company_filing
    # ------------------------------------------------------------------

    def merge_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        # cik is nullable in the DDL, so the NOT NULL check would not catch a
        # missing key that the old values_fn's row["cik"] rejected.
        for row in rows:
            if "cik" not in row:
                raise ValueError(f"sec_company_filing row is missing the 'cik' key: {row!r}")
        return self._record_landing_passthrough(
            "sec_company_filing", rows, defaults={}, stamp=self._synced_now_stamp(sync_run_id)
        )

    def get_filing(self, accession_number: str) -> dict[str, Any] | None:
        rows = self._in_run_lookup("sec_company_filing", accession_number)
        return rows[0] if rows else None

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
        filing_min_date: Any = None,
    ) -> dict[str, Any]:
        """Stage one company's full submission: run loaders, record the company
        tables for landing, merge the filing rows locally."""
        with self._shard_advisory_lock():
            return self._stage_submission_locked(
                cik=cik,
                main_payload=main_payload,
                pagination_payloads=pagination_payloads,
                sync_run_id=sync_run_id,
                raw_object_id=raw_object_id,
                load_mode=load_mode,
                recent_limit=recent_limit,
                filing_min_date=filing_min_date,
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
        filing_min_date: Any = None,
    ) -> dict[str, Any]:
        from edgar_warehouse.loaders.bronze_submission_extractors import (
            filter_rows_by_min_filing_date,
            is_reporting_company_entity_type,
            stage_address_loader,
            stage_company_loader,
            stage_former_name_loader,
            stage_manifest_loader,
            stage_pagination_filing_loader,
            stage_recent_filing_loader,
        )

        # individual-filer-company-misclassification map, Ticket 03/04: SEC's
        # own entityType is only knowable once main_payload is fetched (here),
        # so this is the sole place to gate the sec_company/address/former_name
        # writes -- an individual/insider filer (entityType='other') is not a
        # reporting company and must not be written into the company universe.
        is_reporting_company = is_reporting_company_entity_type(main_payload.get("entityType"))
        if is_reporting_company:
            company_rows = stage_company_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
            address_rows = stage_address_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
            former_name_rows = stage_former_name_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        else:
            company_rows = []
            address_rows = []
            former_name_rows = []
        manifest_rows = stage_manifest_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        recent_rows = filter_rows_by_min_filing_date(
            stage_recent_filing_loader(
                main_payload, cik, sync_run_id, raw_object_id, load_mode, recent_limit=recent_limit
            ),
            filing_min_date,
        )

        rows_written = 0
        company_rows_written = self.merge_company(company_rows, sync_run_id)
        rows_written += company_rows_written
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
            pagination_rows = filter_rows_by_min_filing_date(
                stage_pagination_filing_loader(
                    pagination_payload, cik, sync_run_id, raw_object_id, load_mode
                ),
                filing_min_date,
            )
            all_filing_rows.extend(pagination_rows)
            pagination_accessions.extend(
                row["accession_number"] for row in pagination_rows if row.get("accession_number")
            )
        rows_written += self.merge_filings(all_filing_rows, sync_run_id)

        return {
            "rows_written": rows_written,
            "company_rows_written": company_rows_written,
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
        # The old loop skipped (never raised on) a falsy accession_number.
        return self._record_landing_passthrough(
            "sec_current_filing_feed",
            [r for r in rows if r.get("accession_number")],
            defaults={},
            stamp=self._synced_now_stamp(sync_run_id),
        )

    # ------------------------------------------------------------------
    # ownership and ADV parser tables
    # ------------------------------------------------------------------

    def merge_ownership_reporting_owners(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_ownership_reporting_owner", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_ownership_non_derivative_txns(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_ownership_non_derivative_txn", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_ownership_derivative_txns(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_ownership_derivative_txn", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_filing", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_offices(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_office", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_disclosure_events(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_disclosure_event", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_private_funds(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_private_fund", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_firm_roster(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_firm_roster", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_subsidiary_evidence(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_subsidiary_evidence",
            rows,
            defaults={"immediate_parent_known": False, "parser_version": "subsidiary_exhibit_v1"},
            stamp=self._sync_run_stamp(sync_run_id),
        )

    def merge_auditor_report_evidence(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_auditor_report_evidence",
            rows,
            defaults={"parser_version": "auditor_evidence_v1"},
            stamp=self._sync_run_stamp(sync_run_id),
        )

    def merge_pcaob_firm_identities(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_pcaob_firm_identity", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    # ------------------------------------------------------------------
    # sec_daily_index_checkpoint
    # ------------------------------------------------------------------

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
        for required in ("raw_object_id", "source_url", "storage_path", "sha256", "fetched_at", "http_status"):
            if row.get(required) is None:
                raise ValueError(f"upsert_raw_object: required field '{required}' is missing or None")
        self._record_landing_passthrough("sec_raw_object", [row], defaults={}, stamp={})

    def get_raw_object(self, raw_object_id: str) -> dict[str, Any] | None:
        rows = self._in_run_lookup("sec_raw_object", raw_object_id)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # sec_filing_attachment
    # ------------------------------------------------------------------

    def merge_filing_attachments(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        for row in rows:
            for required in ("accession_number", "document_name", "document_type", "document_url"):
                if not row.get(required):
                    raise ValueError(f"merge_filing_attachments: required field '{required}' is missing or None in row {row}")
        return self._record_landing_passthrough(
            "sec_filing_attachment",
            rows,
            defaults={"is_primary": False},
            stamp=self._sync_run_stamp(sync_run_id),
        )

    def get_filing_attachments(self, accession_number: str) -> list[dict[str, Any]]:
        """Return all attachment rows this run recorded for the given accession number."""
        return self._in_run_lookup("sec_filing_attachment", accession_number)

    # ------------------------------------------------------------------
    # sec_filing_text
    # ------------------------------------------------------------------

    def upsert_filing_text(self, row: dict[str, Any]) -> None:
        """Record a filing text extraction row, landing-only
        (silver-merge-engine-migration Ticket 06e); the dbt model collapses
        rows on (accession_number, text_version).

        Raises ValueError if any required field is missing or None, before
        anything is recorded.
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
        self._record_landing_passthrough("sec_filing_text", [row], defaults={}, stamp={})

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
        """Return current row count for every silver table, keyed by table name.

        DuckDB Retirement Cutover Ticket 14: the 10 ``BOOKKEEPING_TABLES``
        names are excluded here on purpose, from both the baseline set and
        the live ``duckdb_tables()`` result -- these tables moved to the
        Postgres-backed ``BookkeepingStore`` and are no longer written via
        this connection, so this method always reports DuckDB-side truth
        going forward rather than stale/frozen zeros. Callers that want a
        combined view merge this with ``BookkeepingStore.get_table_counts()``
        (see ``warehouse_orchestrator.py``'s ``_execute_warehouse_bronze_capture``).
        """
        from edgar_warehouse.bookkeeping.models import BOOKKEEPING_TABLES

        baseline_tables = {
            "schema_migration",
            "sec_tracked_universe",
            "sec_company",
            "sec_company_ticker",
            "sec_company_address",
            "sec_company_former_name",
            "sec_company_submission_file",
            "sec_company_filing",
            "sec_current_filing_feed",
            "sec_raw_object",
            "sec_filing_attachment",
            "sec_filing_text",
            "sec_ownership_reporting_owner",
            "sec_ownership_non_derivative_txn",
            "sec_ownership_derivative_txn",
            "sec_adv_filing",
            "sec_adv_office",
            "sec_adv_disclosure_event",
            "sec_adv_private_fund",
            "sec_subsidiary_evidence",
            "sec_auditor_report_evidence",
            "sec_pcaob_firm_identity",
            "sec_financial_fact",
            "sec_financial_derived",
            "sec_earnings_release",
            "sec_accounting_flag",
            "sec_executive_record",
            "sec_thirteenf_holding",
        }
        rows = self._conn.execute(
            """
            SELECT table_name
            FROM duckdb_tables()
            WHERE table_name NOT LIKE 'backup_%'
            ORDER BY table_name
            """
        ).fetchall()
        counts: dict[str, int] = {}
        tables = sorted(
            (baseline_tables | {table for (table,) in rows}) - set(BOOKKEEPING_TABLES)
        )
        for table in tables:
            exists = self._conn.execute(
                "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1",
                [table],
            ).fetchone()
            if exists is None:
                counts[table] = 0
                continue
            quoted_table = self._quote_identifier(table)
            row = self._conn.execute(f"SELECT COUNT(*) FROM {quoted_table}").fetchone()
            counts[table] = row[0] if row else 0
        return counts

    # ------------------------------------------------------------------
    # Landing-only writers (silver-merge-engine-migration)
    # ------------------------------------------------------------------

    def _record_landing_passthrough(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        *,
        defaults: dict[str, Any],
        stamp: dict[str, Any],
    ) -> int:
        """Landing-only write for a table whose local DuckDB copy is dead
        (silver-merge-engine-migration Tickets 02-06): DuckDB Retirement
        Cutover Ticket 10 made the local store ephemeral, so the QUALIFY/ON
        CONFLICT merge these tables used to run computed a result no later run
        consumed. The dbt silver models collapse the raw landing rows on the
        old ON CONFLICT keys. Rows of the `_IN_RUN_LOOKUP_TABLES` are also
        indexed for this run's own `get_*` reads (Ticket 06d), with or without
        a landing buffer attached; raw SQL on local DuckDB finds none of them.

        `defaults` mirrors the old values_fn's `r.get(col, default)` fills
        exactly -- applied only when the key is absent, never over an
        explicit None. `stamp` adds write-time columns the landing schema
        carries but the caller doesn't supply (facts/flags: `ingested_at` +
        the Ticket 33 validity trio; per-filing and 13F tables:
        `ingested_at`; company submission, filing, attachment, ownership, ADV
        and relationship-source evidence tables and the current filing feed:
        `last_sync_run_id`, plus `last_synced_at` where the table has it
        (company tickers too, Ticket 06e); the two fundamentals markers:
        `processed_at` / `entity_facts_refreshed_at` (Ticket 12); derived,
        raw objects and filing text: nothing, their landing rows are recorded
        as given). A `values_fn` coercion that replaced a present value --
        `bool(...)`, `or ""` -- is applied by the caller before this call,
        since `defaults` only fills absent keys.

        A row that would have violated this table's NOT NULL DDL raises here
        instead of failing the Snowflake load of its whole Parquet file
        later -- the same fail-loud behaviour the DuckDB INSERT had.
        """
        if not rows:
            return 0
        required = self._required_columns(table_name)
        recorded = []
        for row in rows:
            full = {**defaults, **row, **stamp}
            missing = [c for c in required if full.get(c) is None]
            if missing:
                raise ValueError(
                    f"{table_name} row is missing NOT NULL column(s) {missing}: {row!r}"
                )
            recorded.append(full)
        landing_export = getattr(self, "landing_export", None)
        if landing_export is not None:
            landing_export.record(table_name, recorded)
        if table_name in _IN_RUN_LOOKUP_TABLES:
            self._remember_in_run(table_name, recorded)
        return len(recorded)

    @staticmethod
    def _required_columns(table_name: str) -> tuple[str, ...]:
        """NOT NULL columns from the silver schema snapshot
        (edgar_warehouse/silver_schema.py, silver-merge-engine-migration
        Ticket 13; generated from the live DDL while DuckDB exists). Defaulted
        ones count too -- DuckDB rejected an explicit NULL there as well, and
        `defaults`/`stamp` are what supply them now. Fails closed on a table
        the snapshot does not know: every landing-only table has at least
        cik/accession_number NOT NULL, so a misspelled or unsnapshotted table
        must not pass as "nothing required"."""
        try:
            return silver_schema.REQUIRED[table_name]
        except KeyError:
            raise ValueError(f"{table_name}: not in the silver schema snapshot") from None

    def _remember_in_run(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        """Index recorded rows for this run's own reads. A key that recurs keeps
        the old upsert's rule: first-value columns from its earliest write, every
        other column from its latest. Stores copies, so a landing row is never
        mutated."""
        key_columns, first_value_columns = _IN_RUN_LOOKUP_TABLES[table_name]
        by_first_key = self._in_run_rows[table_name]
        for row in rows:
            group = by_first_key.setdefault(row[key_columns[0]], {})
            rest_key = tuple(row[column] for column in key_columns[1:])
            merged = dict(row)
            earlier = group.get(rest_key)
            if earlier is not None:
                merged.update({column: earlier.get(column) for column in first_value_columns})
            group[rest_key] = merged

    def _in_run_lookup(self, table_name: str, first_key: Any) -> list[dict[str, Any]]:
        """Rows this run recorded under `first_key`, as copies carrying every
        column of the schema snapshot in order (None where the write had
        none): the row shape `SELECT *` returned before the table went
        landing-only."""
        columns = silver_schema.COLUMNS[table_name]
        return [
            {column: row.get(column) for column in columns}
            for row in self._in_run_rows[table_name].get(first_key, {}).values()
        ]

    @staticmethod
    def _ingested_at_stamp() -> dict[str, Any]:
        """ingested_at was DuckDB's DEFAULT NOW() and every ON CONFLICT
        branch's `ingested_at = now()`; landing rows now carry it per write.
        Gold models output it and MDM's EMPLOYED_BY derivation filters
        sec_executive_record/sec_employment_event on it as a watermark."""
        return {"ingested_at": datetime.now(UTC)}

    @staticmethod
    def _sync_run_stamp(sync_run_id: str) -> dict[str, Any]:
        """`last_sync_run_id` for tables that record which sync run last
        wrote a row (company submission, ticker, filing, attachment,
        ownership, ADV and relationship-source evidence tables, the current
        filing feed). The old `values_fn`s always wrote the call's
        `sync_run_id`, whatever the row said, so this overrides a row-supplied
        value."""
        return {"last_sync_run_id": sync_run_id}

    @classmethod
    def _synced_now_stamp(cls, sync_run_id: str) -> dict[str, Any]:
        """`last_sync_run_id` plus `last_synced_at` (now), for tables that
        also record when a sync last wrote the row."""
        return {**cls._sync_run_stamp(sync_run_id), "last_synced_at": datetime.now(UTC)}

    @classmethod
    def _current_row_stamp(cls) -> dict[str, Any]:
        """Write-time columns for sec_financial_fact/sec_accounting_flag
        landing rows: `ingested_at` plus the Ticket 33 validity trio. Any row
        present in a write is current as of that write (is_current=True/
        valid_to=None need no read-back); valid_from is this write's time, a
        deliberate last-write-wins simplification for the landing/dbt
        collapse."""
        stamp = cls._ingested_at_stamp()
        return {**stamp, "valid_from": stamp["ingested_at"], "valid_to": None, "is_current": True}

    def merge_financial_facts(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_financial_fact",
            rows,
            defaults={
                "period_start": _INSTANT_FACT_PERIOD_START_SENTINEL,
                "form_type": "",
                "segment": "consolidated",
            },
            stamp=self._current_row_stamp(),
        )

    def merge_financial_derived(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_financial_derived",
            rows,
            defaults={"form_type": ""},
            stamp={},
        )

    def merge_earnings_releases(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_earnings_release",
            [
                {
                    **r,
                    "has_non_gaap": bool(r.get("has_non_gaap", False)),
                    "has_guidance": bool(r.get("has_guidance", False)),
                }
                for r in rows
            ],
            defaults={},
            stamp=self._ingested_at_stamp(),
        )

    def merge_guidance_facts(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_guidance_fact",
            [
                {
                    **r,
                    "accession_number": r.get("accession_number") or "",
                    "is_non_gaap": bool(r.get("is_non_gaap", False)),
                }
                for r in rows
            ],
            defaults={"confidence": "medium"},
            stamp=self._ingested_at_stamp(),
        )

    def merge_guidance_fact_rejects(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_guidance_fact_reject",
            [{**r, "accession_number": r.get("accession_number") or ""} for r in rows],
            defaults={},
            stamp=self._ingested_at_stamp(),
        )

    def merge_accounting_flags(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_accounting_flag",
            rows,
            defaults={"form_type": "10-K"},
            stamp=self._current_row_stamp(),
        )

    def merge_executive_records(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_executive_record", rows, defaults={}, stamp=self._ingested_at_stamp()
        )

    def merge_employment_events(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_employment_event", rows, defaults={}, stamp=self._ingested_at_stamp()
        )

    def merge_thirteenf_holdings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_thirteenf_holding", rows, defaults={}, stamp=self._ingested_at_stamp()
        )

    def merge_thirteenf_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_thirteenf_filing",
            [{**r, "confidential_omission": bool(r.get("confidential_omission", False))} for r in rows],
            defaults={"effective_status": "effective", "parser_version": "1"},
            stamp=self._ingested_at_stamp(),
        )



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
