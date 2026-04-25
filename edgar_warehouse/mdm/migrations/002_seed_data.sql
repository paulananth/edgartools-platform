-- =============================================================================
-- MDM Seed / Reference Data
-- Migration: 002_seed_data.sql
-- Description: Inserts initial configuration and reference data for all
--              rule, graph-registry, and normalization tables.
--              All statements use ON CONFLICT DO NOTHING for idempotency.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- mdm_entity_type_definition (5 rows)
-- ---------------------------------------------------------------------------
INSERT INTO mdm_entity_type_definition (entity_type, neo4j_label, domain_table, api_path_prefix, primary_id_field, display_name) VALUES
    ('company',  'Company',  'mdm_company',  '/companies',  'cik',        'Company'),
    ('adviser',  'Adviser',  'mdm_adviser',  '/advisers',   'crd_number', 'Investment Adviser'),
    ('person',   'Person',   'mdm_person',   '/persons',    'entity_id',  'Person'),
    ('security', 'Security', 'mdm_security', '/securities', 'entity_id',  'Security'),
    ('fund',     'Fund',     'mdm_fund',     '/funds',      'entity_id',  'Private Fund')
ON CONFLICT (entity_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_source_priority (4 rows — entity_type = 'all')
-- ---------------------------------------------------------------------------
INSERT INTO mdm_source_priority (entity_type, source_system, priority, description) VALUES
    ('all', 'edgar_cik',        1, 'SEC CIK submission data — immutable source of truth'),
    ('all', 'adv_filing',       2, 'Form ADV filing data'),
    ('all', 'ownership_filing', 3, 'Form 3/4/5 derived data'),
    ('all', 'derived',          4, 'Computed or inferred values')
ON CONFLICT (entity_type, source_system) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_field_survivorship (9 rows)
-- ---------------------------------------------------------------------------
INSERT INTO mdm_field_survivorship (entity_type, field_name, rule_type, source_system, preferred_source_order, notes) VALUES
    ('company', 'canonical_name',  'source_priority',     NULL,         NULL,                           'Highest active priority source wins'),
    ('company', 'ein',             'immutable',           'edgar_cik',  NULL,                           'EIN set once from EDGAR, never overridden'),
    ('company', 'sic_code',        'immutable',           'edgar_cik',  NULL,                           'SIC authoritative from EDGAR only'),
    ('company', 'sic_description', 'immutable',           'edgar_cik',  NULL,                           'SIC description from EDGAR only'),
    ('company', 'primary_ticker',  'highest_source_rank', NULL,         NULL,                           'Ticker with source_rank=1 wins'),
    ('adviser', 'canonical_name',  'source_priority',     NULL,         '["adv_filing","edgar_cik"]',   'ADV has legal adviser name; preferred despite priority 2'),
    ('adviser', 'aum_total',       'most_recent',         'adv_filing', NULL,                           'Most recent ADV filing by effective_date'),
    ('person',  'canonical_name',  'source_priority',     NULL,         NULL,                           'Highest active priority source wins'),
    ('person',  'primary_role',    'most_recent',         NULL,         NULL,                           'Most recent non-null role from highest priority source')
ON CONFLICT (entity_type, field_name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_match_threshold (5 rows)
-- ---------------------------------------------------------------------------
INSERT INTO mdm_match_threshold (entity_type, match_method, auto_merge_min, review_min) VALUES
    ('person',  'cik_exact',  1.00, 1.00),
    ('person',  'fuzzy_name', 0.92, 0.80),
    ('person',  'ml_splink',  0.95, 0.75),
    ('company', 'fuzzy_name', 0.95, 0.85),
    ('adviser', 'fuzzy_name', 0.92, 0.80)
ON CONFLICT (entity_type, match_method) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_normalization_rule — legal suffixes (strip to empty string)
-- ---------------------------------------------------------------------------
INSERT INTO mdm_normalization_rule (rule_type, input_value, canonical_value) VALUES
    ('legal_suffix', 'inc',          ''),
    ('legal_suffix', 'incorporated', ''),
    ('legal_suffix', 'llc',          ''),
    ('legal_suffix', 'corp',         ''),
    ('legal_suffix', 'corporation',  ''),
    ('legal_suffix', 'lp',           ''),
    ('legal_suffix', 'ltd',          ''),
    ('legal_suffix', 'limited',      ''),
    ('legal_suffix', 'plc',          ''),
    ('legal_suffix', 'trust',        ''),
    ('legal_suffix', 'fund',         ''),
    ('legal_suffix', 'group',        ''),
    ('legal_suffix', 'partners',     ''),
    ('legal_suffix', 'associates',   ''),
    ('legal_suffix', 'co',           ''),
    ('legal_suffix', 'na',           ''),
    ('legal_suffix', 'holdings',     ''),
    ('legal_suffix', 'services',     '')
ON CONFLICT (rule_type, input_value) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_normalization_rule — title aliases
-- ---------------------------------------------------------------------------
INSERT INTO mdm_normalization_rule (rule_type, input_value, canonical_value) VALUES
    ('title_alias', 'CHIEF EXECUTIVE OFFICER',  'CEO'),
    ('title_alias', 'CEO',                       'CEO'),
    ('title_alias', 'C.E.O.',                    'CEO'),
    ('title_alias', 'CHIEF FINANCIAL OFFICER',  'CFO'),
    ('title_alias', 'CFO',                       'CFO'),
    ('title_alias', 'CHIEF OPERATING OFFICER',  'COO'),
    ('title_alias', 'COO',                       'COO'),
    ('title_alias', 'CHIEF TECHNOLOGY OFFICER', 'CTO'),
    ('title_alias', 'CTO',                       'CTO'),
    ('title_alias', 'CHIEF INVESTMENT OFFICER', 'CIO'),
    ('title_alias', 'CIO',                       'CIO'),
    ('title_alias', 'DIRECTOR',                 'Director'),
    ('title_alias', 'BOARD DIRECTOR',           'Director'),
    ('title_alias', 'BD. DIRECTOR',             'Director'),
    ('title_alias', 'EXECUTIVE VICE PRESIDENT', 'EVP'),
    ('title_alias', 'EVP',                       'EVP'),
    ('title_alias', 'EXEC VP',                   'EVP'),
    ('title_alias', 'SENIOR VICE PRESIDENT',    'SVP'),
    ('title_alias', 'SVP',                       'SVP'),
    ('title_alias', 'VICE PRESIDENT',           'VP'),
    ('title_alias', 'VP',                        'VP'),
    ('title_alias', 'PRESIDENT',                'President'),
    ('title_alias', 'SECRETARY',                'Secretary'),
    ('title_alias', 'CORP SECRETARY',           'Secretary'),
    ('title_alias', 'TREASURER',                'Treasurer'),
    ('title_alias', 'CHAIRMAN',                 'Chairman'),
    ('title_alias', 'CHAIRMAN OF THE BOARD',    'Chairman')
ON CONFLICT (rule_type, input_value) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_normalization_rule — address abbreviations
-- ---------------------------------------------------------------------------
INSERT INTO mdm_normalization_rule (rule_type, input_value, canonical_value) VALUES
    ('address_abbr', 'ST',   'Street'),
    ('address_abbr', 'AVE',  'Avenue'),
    ('address_abbr', 'BLVD', 'Boulevard'),
    ('address_abbr', 'DR',   'Drive'),
    ('address_abbr', 'STE',  'Suite'),
    ('address_abbr', 'RD',   'Road'),
    ('address_abbr', 'LN',   'Lane'),
    ('address_abbr', 'CT',   'Court'),
    ('address_abbr', 'PL',   'Place'),
    ('address_abbr', 'FL',   'Floor'),
    ('address_abbr', 'APT',  'Apartment'),
    ('address_abbr', 'BLDG', 'Building')
ON CONFLICT (rule_type, input_value) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_normalization_rule — US state codes
-- ---------------------------------------------------------------------------
INSERT INTO mdm_normalization_rule (rule_type, input_value, canonical_value) VALUES
    ('state_code', 'ALABAMA',              'AL'),
    ('state_code', 'ALASKA',               'AK'),
    ('state_code', 'ARIZONA',              'AZ'),
    ('state_code', 'ARKANSAS',             'AR'),
    ('state_code', 'CALIFORNIA',           'CA'),
    ('state_code', 'COLORADO',             'CO'),
    ('state_code', 'CONNECTICUT',          'CT'),
    ('state_code', 'DELAWARE',             'DE'),
    ('state_code', 'FLORIDA',              'FL'),
    ('state_code', 'GEORGIA',              'GA'),
    ('state_code', 'HAWAII',               'HI'),
    ('state_code', 'IDAHO',                'ID'),
    ('state_code', 'ILLINOIS',             'IL'),
    ('state_code', 'INDIANA',              'IN'),
    ('state_code', 'IOWA',                 'IA'),
    ('state_code', 'KANSAS',               'KS'),
    ('state_code', 'KENTUCKY',             'KY'),
    ('state_code', 'LOUISIANA',            'LA'),
    ('state_code', 'MAINE',                'ME'),
    ('state_code', 'MARYLAND',             'MD'),
    ('state_code', 'MASSACHUSETTS',        'MA'),
    ('state_code', 'MICHIGAN',             'MI'),
    ('state_code', 'MINNESOTA',            'MN'),
    ('state_code', 'MISSISSIPPI',          'MS'),
    ('state_code', 'MISSOURI',             'MO'),
    ('state_code', 'MONTANA',              'MT'),
    ('state_code', 'NEBRASKA',             'NE'),
    ('state_code', 'NEVADA',               'NV'),
    ('state_code', 'NEW HAMPSHIRE',        'NH'),
    ('state_code', 'NEW JERSEY',           'NJ'),
    ('state_code', 'NEW MEXICO',           'NM'),
    ('state_code', 'NEW YORK',             'NY'),
    ('state_code', 'NORTH CAROLINA',       'NC'),
    ('state_code', 'NORTH DAKOTA',         'ND'),
    ('state_code', 'OHIO',                 'OH'),
    ('state_code', 'OKLAHOMA',             'OK'),
    ('state_code', 'OREGON',               'OR'),
    ('state_code', 'PENNSYLVANIA',         'PA'),
    ('state_code', 'RHODE ISLAND',         'RI'),
    ('state_code', 'SOUTH CAROLINA',       'SC'),
    ('state_code', 'SOUTH DAKOTA',         'SD'),
    ('state_code', 'TENNESSEE',            'TN'),
    ('state_code', 'TEXAS',                'TX'),
    ('state_code', 'UTAH',                 'UT'),
    ('state_code', 'VERMONT',              'VT'),
    ('state_code', 'VIRGINIA',             'VA'),
    ('state_code', 'WASHINGTON',           'WA'),
    ('state_code', 'WEST VIRGINIA',        'WV'),
    ('state_code', 'WISCONSIN',            'WI'),
    ('state_code', 'WYOMING',              'WY'),
    ('state_code', 'DISTRICT OF COLUMBIA', 'DC')
ON CONFLICT (rule_type, input_value) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_normalization_rule — country codes
-- ---------------------------------------------------------------------------
INSERT INTO mdm_normalization_rule (rule_type, input_value, canonical_value) VALUES
    ('country_code', 'UNITED STATES',            'US'),
    ('country_code', 'UNITED STATES OF AMERICA', 'US'),
    ('country_code', 'USA',                      'US'),
    ('country_code', 'U.S.A.',                   'US'),
    ('country_code', 'U.S.',                     'US'),
    ('country_code', 'CANADA',                   'CA'),
    ('country_code', 'UNITED KINGDOM',           'GB'),
    ('country_code', 'GREAT BRITAIN',            'GB'),
    ('country_code', 'CAYMAN ISLANDS',           'KY'),
    ('country_code', 'BERMUDA',                  'BM'),
    ('country_code', 'IRELAND',                  'IE'),
    ('country_code', 'LUXEMBOURG',               'LU'),
    ('country_code', 'GERMANY',                  'DE'),
    ('country_code', 'FRANCE',                   'FR'),
    ('country_code', 'JAPAN',                    'JP'),
    ('country_code', 'AUSTRALIA',                'AU'),
    ('country_code', 'SINGAPORE',                'SG'),
    ('country_code', 'HONG KONG',                'HK'),
    ('country_code', 'SWITZERLAND',              'CH')
ON CONFLICT (rule_type, input_value) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_relationship_type (5 initial relationship types)
-- NOTE: mdm_entity_type_definition rows must exist before this block runs
-- (ensured by order within this migration file).
-- ---------------------------------------------------------------------------
INSERT INTO mdm_relationship_type (rel_type_name, source_node_type, target_node_type, direction, is_temporal, dedup_key_fields, merge_strategy, description) VALUES
    ('IS_INSIDER',
     'person',   'company',  'outbound', TRUE,
     '["source_entity_id","target_entity_id","title"]',
     'extend_temporal',
     'Person is officer/director/10pct owner of company'),
    ('HOLDS',
     'person',   'security', 'outbound', TRUE,
     '["source_entity_id","target_entity_id"]',
     'extend_temporal',
     'Person holds a security position'),
    ('ISSUED_BY',
     'security', 'company',  'outbound', TRUE,
     '["source_entity_id","target_entity_id"]',
     'extend_temporal',
     'Security is issued by company'),
    ('IS_ENTITY_OF',
     'adviser',  'company',  'outbound', TRUE,
     '["source_entity_id","target_entity_id"]',
     'replace',
     'Adviser is the same legal entity as a registered company'),
    ('MANAGES_FUND',
     'adviser',  'fund',     'outbound', TRUE,
     '["source_entity_id","target_entity_id"]',
     'extend_temporal',
     'Adviser manages a private fund')
ON CONFLICT (rel_type_name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- mdm_relationship_property_def
-- Uses subqueries to look up rel_type_id since UUIDs are generated at INSERT.
-- ---------------------------------------------------------------------------

-- IS_INSIDER properties
INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'role',             'text', TRUE,  'Officer/director role category'
FROM   mdm_relationship_type WHERE rel_type_name = 'IS_INSIDER'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'title',            'text', FALSE, 'Exact title string from filing'
FROM   mdm_relationship_type WHERE rel_type_name = 'IS_INSIDER'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'source_accession', 'text', FALSE, 'Source filing accession number'
FROM   mdm_relationship_type WHERE rel_type_name = 'IS_INSIDER'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

-- HOLDS properties
INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'shares_owned',     'float', FALSE, 'Number of shares held'
FROM   mdm_relationship_type WHERE rel_type_name = 'HOLDS'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'direct_indirect',  'text',  FALSE, 'D = direct ownership, I = indirect'
FROM   mdm_relationship_type WHERE rel_type_name = 'HOLDS'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'as_of_date',       'date',  FALSE, 'Date of the reported position'
FROM   mdm_relationship_type WHERE rel_type_name = 'HOLDS'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'source_accession', 'text',  FALSE, 'Source filing accession number'
FROM   mdm_relationship_type WHERE rel_type_name = 'HOLDS'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

-- MANAGES_FUND properties
INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'since_date',       'date',  FALSE, 'Date adviser began managing the fund'
FROM   mdm_relationship_type WHERE rel_type_name = 'MANAGES_FUND'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

INSERT INTO mdm_relationship_property_def (rel_type_id, property_name, data_type, is_required, description)
SELECT rel_type_id, 'source_accession', 'text',  FALSE, 'Source ADV filing accession number'
FROM   mdm_relationship_type WHERE rel_type_name = 'MANAGES_FUND'
ON CONFLICT (rel_type_id, property_name) DO NOTHING;

-- ISSUED_BY and IS_ENTITY_OF have no extra properties beyond temporal fields.

-- ---------------------------------------------------------------------------
-- mdm_relationship_source_mapping
-- Maps silver DuckDB/Parquet tables to relationship creation rules.
-- ---------------------------------------------------------------------------

-- IS_INSIDER from ownership_filing / sec_ownership_reporting_owner
-- Silver schema: accession_number, owner_index, owner_cik, owner_name,
--                is_director, is_officer, is_ten_percent_owner, is_other, officer_title.
-- Pipeline must derive: (a) issuer_cik via sec_filing join on accession_number,
--                       (b) role from the four boolean flags,
--                       (c) effective_from from sec_filing.filed_date / period_of_report.
INSERT INTO mdm_relationship_source_mapping (
    rel_type_id, source_system, source_table,
    source_entity_field, target_entity_field,
    source_entity_type, target_entity_type,
    property_mapping,
    effective_from_field, effective_to_field,
    description
)
SELECT
    rt.rel_type_id,
    'ownership_filing',
    'sec_ownership_reporting_owner',
    'owner_cik',
    'accession_number',
    'person',
    'company',
    '{"title": "officer_title", "source_accession": "accession_number", "role_derivation": {"is_director": "Director", "is_officer": "Officer", "is_ten_percent_owner": "10PctOwner", "is_other": "Other"}}'::JSONB,
    NULL,
    NULL,
    'IS_INSIDER from Form 3/4/5 reporting owner rows. Pipeline derives issuer_cik via sec_filing join on accession_number and role via boolean flags.'
FROM mdm_relationship_type rt
WHERE rt.rel_type_name = 'IS_INSIDER'
ON CONFLICT (rel_type_id, source_system, source_table) DO NOTHING;

-- MANAGES_FUND from adv_filing / sec_adv_private_fund
-- Silver schema: accession_number, fund_index, fund_name, fund_type, jurisdiction, aum_amount.
-- Pipeline must derive: (a) adviser CRD via sec_adv_filing.crd_number join on accession_number,
--                       (b) fund identity from (adviser_entity_id, fund_name) dedup key,
--                       (c) effective_from from sec_adv_filing.effective_date.
INSERT INTO mdm_relationship_source_mapping (
    rel_type_id, source_system, source_table,
    source_entity_field, target_entity_field,
    source_entity_type, target_entity_type,
    property_mapping,
    effective_from_field, effective_to_field,
    description
)
SELECT
    rt.rel_type_id,
    'adv_filing',
    'sec_adv_private_fund',
    'accession_number',
    'fund_name',
    'adviser',
    'fund',
    '{"source_accession": "accession_number", "fund_type": "fund_type", "jurisdiction": "jurisdiction", "aum_amount": "aum_amount"}'::JSONB,
    NULL,
    NULL,
    'MANAGES_FUND from Form ADV Schedule D private funds. Pipeline derives adviser via sec_adv_filing.crd_number and effective_from via sec_adv_filing.effective_date.'
FROM mdm_relationship_type rt
WHERE rt.rel_type_name = 'MANAGES_FUND'
ON CONFLICT (rel_type_id, source_system, source_table) DO NOTHING;

-- IS_ENTITY_OF derived from adviser CIK matching company CIK
INSERT INTO mdm_relationship_source_mapping (
    rel_type_id, source_system, source_table,
    source_entity_field, target_entity_field,
    source_entity_type, target_entity_type,
    property_mapping,
    effective_from_field, effective_to_field,
    filter_condition,
    description
)
SELECT
    rt.rel_type_id,
    'derived',
    'mdm_adviser',
    'cik',
    'cik',
    'adviser',
    'company',
    '{}'::JSONB,
    NULL,
    NULL,
    '{"cik_not_null": {"field": "cik", "op": "IS NOT NULL"}}'::JSONB,
    'IS_ENTITY_OF derived by matching adviser CIK to company CIK in mdm_company'
FROM mdm_relationship_type rt
WHERE rt.rel_type_name = 'IS_ENTITY_OF'
ON CONFLICT (rel_type_id, source_system, source_table) DO NOTHING;
