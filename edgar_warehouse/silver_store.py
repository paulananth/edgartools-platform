"""Silver layer DuckDB management for the SEC EDGAR warehouse."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from edgar_warehouse.silver_landing_store import (
    _INSTANT_FACT_PERIOD_START_SENTINEL,
    SilverLandingStore,
)
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


class SilverDatabase(SilverLandingStore):
    """The DuckDB half of the silver store: DDL, migrations and local reads.

    Every writer lives on SilverLandingStore (silver-merge-engine-migration
    Ticket 14); this subclass exists until Ticket 17 deletes the engine."""

    def __init__(self, db_path: str, *, landing_export: LandingExportBuffer | None = None) -> None:
        super().__init__(landing_export=landing_export)
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

        Same shape as ``SnowflakeSilverReader.fetch`` so a reader-agnostic
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


    # ------------------------------------------------------------------
    # sec_company (silver merge)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # sec_company_address
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # sec_company_former_name
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # sec_company_submission_file
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # sec_company_filing
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Submission staging (composite operation)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # sec_current_filing_feed
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # ownership and ADV parser tables
    # ------------------------------------------------------------------


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


    # ------------------------------------------------------------------
    # sec_filing_attachment
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # sec_filing_text
    # ------------------------------------------------------------------


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

    # ------------------------------------------------------------------
    # Landing-only writers (silver-merge-engine-migration)
    # ------------------------------------------------------------------


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
