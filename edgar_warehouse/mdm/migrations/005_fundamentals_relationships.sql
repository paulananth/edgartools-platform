-- =============================================================================
-- Fundamentals Research Extension: New Entity Type, Relationship Types, and Seeds
-- Migration: 005_fundamentals_relationships.sql
-- Description: Adds audit_firm entity type, security_class attribute, three new
--              relationship types (EMPLOYED_BY, AUDITED_BY, INSTITUTIONAL_HOLDS),
--              their property definitions and source mappings, and seeds 10 audit
--              firms (Big 4 + Next 6) that cover ~99.5% of exchange-listed audits.
--
--              All INSERT statements use ON CONFLICT DO NOTHING for idempotency.
--              Safe to re-run; zero-op when already applied.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Extend mdm_entity.entity_type check constraint to include 'audit_firm'
--    PostgreSQL auto-names inline column CHECK constraints as {table}_{col}_check,
--    but we use a dynamic lookup in case the actual name differs.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_conname TEXT;
BEGIN
    -- Find the CHECK constraint on mdm_entity.entity_type (any name)
    SELECT conname INTO v_conname
    FROM pg_constraint
    WHERE conrelid = 'mdm_entity'::regclass
      AND contype = 'c'
      AND conname LIKE '%entity_type%';

    IF v_conname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE mdm_entity DROP CONSTRAINT %I', v_conname);
    END IF;
END $$;

ALTER TABLE mdm_entity ADD CONSTRAINT mdm_entity_entity_type_check
    CHECK (entity_type IN ('company', 'adviser', 'person', 'security', 'fund', 'audit_firm'));


-- ---------------------------------------------------------------------------
-- 2. Create mdm_audit_firm domain table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mdm_audit_firm (
    entity_id       UUID PRIMARY KEY REFERENCES mdm_entity(entity_id),
    firm_name       TEXT NOT NULL,
    pcaob_firm_id   TEXT UNIQUE,
    big4            BOOLEAN NOT NULL DEFAULT FALSE,
    canonical_name  TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mdm_audit_firm_pcaob_id ON mdm_audit_firm(pcaob_firm_id);
CREATE INDEX IF NOT EXISTS idx_mdm_audit_firm_canonical ON mdm_audit_firm(canonical_name);


-- ---------------------------------------------------------------------------
-- 3. Register audit_firm in mdm_entity_type_definition
-- ---------------------------------------------------------------------------
INSERT INTO mdm_entity_type_definition
    (entity_type, neo4j_label, domain_table, api_path_prefix, primary_id_field, display_name)
VALUES
    ('audit_firm', 'AuditFirm', 'mdm_audit_firm', '/audit-firms', 'entity_id', 'Audit Firm')
ON CONFLICT (entity_type) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 4. Add security_class to mdm_security
--    Hybrid enum: equity | etf_fund | fixed_income | warrant | unknown_security
--    Populated by: cusip_ticker_mapping() → equity; titleOfClass parsing → others
-- ---------------------------------------------------------------------------
ALTER TABLE mdm_security ADD COLUMN IF NOT EXISTS security_class TEXT;


-- ---------------------------------------------------------------------------
-- 5. Insert new relationship types
--    EMPLOYED_BY   — Person → Company    (DEF 14A proxy executive compensation)
--    AUDITED_BY    — Company → AuditFirm (10-K XBRL dei_AuditorFirmId)
--    INSTITUTIONAL_HOLDS — Adviser → Security (13F institutional holdings)
-- ---------------------------------------------------------------------------
INSERT INTO mdm_relationship_type
    (rel_type_name, source_node_type, target_node_type, direction,
     is_temporal, merge_strategy, dedup_key_fields, description)
VALUES
    (
        'EMPLOYED_BY',
        'person', 'company', 'outbound',
        TRUE, 'extend_temporal',
        '["source_entity_id","target_entity_id","fiscal_year"]'::jsonb,
        'Executive employment relationship derived from DEF 14A proxy compensation tables'
    ),
    (
        'AUDITED_BY',
        'company', 'audit_firm', 'outbound',
        TRUE, 'extend_temporal',
        '["source_entity_id","target_entity_id","fiscal_year"]'::jsonb,
        'External auditor relationship derived from 10-K XBRL DEI dei_AuditorFirmId fact'
    ),
    (
        'INSTITUTIONAL_HOLDS',
        'adviser', 'security', 'outbound',
        TRUE, 'extend_temporal',
        '["source_entity_id","target_entity_id","quarter_end"]'::jsonb,
        'Institutional equity holdings derived from 13F-HR filings (full SEC 13F filer list)'
    )
ON CONFLICT (rel_type_name) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 6. Property definitions — EMPLOYED_BY
-- ---------------------------------------------------------------------------
INSERT INTO mdm_relationship_property_def
    (rel_type_id, property_name, data_type, is_required, description)
SELECT
    rt.rel_type_id,
    v.property_name,
    v.data_type,
    v.is_required,
    v.description
FROM mdm_relationship_type rt
CROSS JOIN (VALUES
    ('role',                'text',    TRUE,  'Standardized role code: CEO, CFO, COO, etc.'),
    ('title',               'text',    FALSE, 'Exact proxy title string as filed'),
    ('fiscal_year',         'integer', TRUE,  'Fiscal year of the proxy filing'),
    ('total_compensation',  'float',   FALSE, 'Total compensation in USD'),
    ('stock_awards',        'float',   FALSE, 'Stock award value in USD'),
    ('option_awards',       'float',   FALSE, 'Option award value in USD'),
    ('non_equity_incentive','float',   FALSE, 'Non-equity incentive plan compensation in USD'),
    ('tenure_start_year',   'integer', FALSE, 'First year person appears in proxy for this company'),
    ('source_accession',    'text',    FALSE, 'Source DEF 14A accession number')
) AS v(property_name, data_type, is_required, description)
WHERE rt.rel_type_name = 'EMPLOYED_BY'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 7. Property definitions — AUDITED_BY
-- ---------------------------------------------------------------------------
INSERT INTO mdm_relationship_property_def
    (rel_type_id, property_name, data_type, is_required, description)
SELECT
    rt.rel_type_id,
    v.property_name,
    v.data_type,
    v.is_required,
    v.description
FROM mdm_relationship_type rt
CROSS JOIN (VALUES
    ('fiscal_year',      'integer', TRUE,  'Fiscal year end of the 10-K filing'),
    ('pcaob_firm_id',    'text',    FALSE, 'PCAOB registration number from dei_AuditorFirmId'),
    ('icfr_attestation', 'boolean', FALSE, 'Whether auditor attested to ICFR effectiveness'),
    ('auditor_changed',  'boolean', FALSE, 'TRUE if auditor differs from the prior fiscal year'),
    ('source_accession', 'text',    FALSE, 'Source 10-K accession number')
) AS v(property_name, data_type, is_required, description)
WHERE rt.rel_type_name = 'AUDITED_BY'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 8. Property definitions — INSTITUTIONAL_HOLDS
-- ---------------------------------------------------------------------------
INSERT INTO mdm_relationship_property_def
    (rel_type_id, property_name, data_type, is_required, description)
SELECT
    rt.rel_type_id,
    v.property_name,
    v.data_type,
    v.is_required,
    v.description
FROM mdm_relationship_type rt
CROSS JOIN (VALUES
    ('quarter_end',      'date',    TRUE,  'Period of report quarter-end date (from 13F header)'),
    ('shares_held',      'float',   TRUE,  'Number of shares held at quarter end'),
    ('market_value',     'float',   FALSE, 'Market value in USD (multiplied from 13F units)'),
    ('ownership_pct',    'float',   FALSE, 'Computed: shares_held / total_shares_outstanding'),
    ('put_call',         'text',    FALSE, 'Put/Call indicator for option holdings'),
    ('discretion_type',  'text',    FALSE, 'Investment discretion: Sole | Shared | None'),
    ('source_accession', 'text',    FALSE, 'Source 13F-HR accession number')
) AS v(property_name, data_type, is_required, description)
WHERE rt.rel_type_name = 'INSTITUTIONAL_HOLDS'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 9. Source mappings
-- ---------------------------------------------------------------------------

-- EMPLOYED_BY: DEF 14A proxy → sec_executive_record
INSERT INTO mdm_relationship_source_mapping
    (rel_type_id, source_system, source_table,
     source_entity_field, target_entity_field,
     source_entity_type, target_entity_type,
     property_mapping, effective_from_field, description)
SELECT
    rt.rel_type_id,
    'proxy_filing',
    'sec_executive_record',
    'exec_name',
    'cik',
    'person',
    'company',
    '{
        "role":                 "exec_role",
        "title":                "exec_role",
        "fiscal_year":          "fiscal_year",
        "total_compensation":   "total_comp",
        "stock_awards":         "stock_awards",
        "option_awards":        "option_awards",
        "non_equity_incentive": "non_equity_incentive",
        "tenure_start_year":    "tenure_start_year",
        "source_accession":     "accession_number"
    }'::jsonb,
    'fiscal_year',
    'Person employment from DEF 14A compensation tables; person resolved via hybrid CIK crosswalk + UUID5'
FROM mdm_relationship_type rt
WHERE rt.rel_type_name = 'EMPLOYED_BY'
ON CONFLICT (rel_type_id, source_system, source_table) DO NOTHING;

-- AUDITED_BY: 10-K XBRL DEI → sec_accounting_flag
INSERT INTO mdm_relationship_source_mapping
    (rel_type_id, source_system, source_table,
     source_entity_field, target_entity_field,
     source_entity_type, target_entity_type,
     property_mapping, effective_from_field, description)
SELECT
    rt.rel_type_id,
    'tenk_filing',
    'sec_accounting_flag',
    'cik',
    'auditor_pcaob_id',
    'company',
    'audit_firm',
    '{
        "fiscal_year":      "fiscal_year",
        "pcaob_firm_id":    "auditor_pcaob_id",
        "icfr_attestation": "icfr_attestation",
        "auditor_changed":  "auditor_changed",
        "source_accession": "accession_number"
    }'::jsonb,
    'fiscal_year',
    'Company auditor from 10-K XBRL dei_AuditorFirmId; PCAOB ID primary match, firm_name fuzzy fallback for FY2020'
FROM mdm_relationship_type rt
WHERE rt.rel_type_name = 'AUDITED_BY'
ON CONFLICT (rel_type_id, source_system, source_table) DO NOTHING;

-- INSTITUTIONAL_HOLDS: 13F-HR → sec_thirteenf_holding
INSERT INTO mdm_relationship_source_mapping
    (rel_type_id, source_system, source_table,
     source_entity_field, target_entity_field,
     source_entity_type, target_entity_type,
     property_mapping, effective_from_field, description)
SELECT
    rt.rel_type_id,
    'thirteenf_filing',
    'sec_thirteenf_holding',
    'cik',
    'cusip',
    'adviser',
    'security',
    '{
        "quarter_end":     "period_of_report",
        "shares_held":     "shares_held",
        "market_value":    "market_value",
        "put_call":        "put_call",
        "discretion_type": "discretion_type",
        "source_accession":"accession_number"
    }'::jsonb,
    'period_of_report',
    '13F institutional holdings; security auto-created if CUSIP unknown; security_class set via cusip_ticker_mapping + titleOfClass'
FROM mdm_relationship_type rt
WHERE rt.rel_type_name = 'INSTITUTIONAL_HOLDS'
ON CONFLICT (rel_type_id, source_system, source_table) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 10. Seed 10 audit firms: Big 4 + Next 6
--     PCAOB IDs sourced from https://pcaobus.org/Registration/Firms/Details/
--     Covers ~99.5% of all exchange-listed company audits
--
--     Idempotent: DO $$ block checks pcaob_firm_id before inserting.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_entity_id UUID;
BEGIN
    -- ── Big 4 ──────────────────────────────────────────────────────────────

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '238') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'PricewaterhouseCoopers LLP', '238', TRUE, 'pricewaterhousecoopers');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '34') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'Deloitte & Touche LLP', '34', TRUE, 'deloitte');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '42') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'Ernst & Young LLP', '42', TRUE, 'ernst young');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '185') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'KPMG LLP', '185', TRUE, 'kpmg');
    END IF;

    -- ── Next 6 ─────────────────────────────────────────────────────────────

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '248') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'Grant Thornton LLP', '248', FALSE, 'grant thornton');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '243') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'BDO USA LLP', '243', FALSE, 'bdo usa');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '49') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'RSM US LLP', '49', FALSE, 'rsm us');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '686') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'Forvis Mazars LLP', '686', FALSE, 'forvis mazars');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '71') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'CBIZ CPAs PC', '71', FALSE, 'cbiz cpas');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM mdm_audit_firm WHERE pcaob_firm_id = '659') THEN
        v_entity_id := gen_random_uuid();
        INSERT INTO mdm_entity (entity_id, entity_type) VALUES (v_entity_id, 'audit_firm');
        INSERT INTO mdm_audit_firm (entity_id, firm_name, pcaob_firm_id, big4, canonical_name)
        VALUES (v_entity_id, 'Moss Adams LLP', '659', FALSE, 'moss adams');
    END IF;

END $$;
