-- TRANSCRIPT_EVENTS: transcript event pointers (ERDP-04).
--
-- Gold Explore only — not pure-SEC Agent-Grade Decision Features (ADR 0001).
-- Isolated DAG branch — no ref() into ownership or fundamentals chains.
--
-- Source shape:
--   EDGARTOOLS_SOURCE.TRANSCRIPT_EVENTS loaded from serving Parquet export
--   built by edgar_warehouse.explore.transcript_events /
--   write_transcript_events_to_serving_export.
--
-- Grain: one row per (cik, event_id, source_system) -- EVENT_KEY is a
-- deterministic hash of that natural key. Unlike EARNINGS_CALENDAR /
-- GUIDANCE_FACTS / CONSENSUS_ESTIMATES, as_of is NOT part of the natural
-- key: a pointer is revalidated in place (as_of bumped on the same row via
-- MERGE on EVENT_KEY at the source-load layer), not versioned. No
-- ranked/is_current projection is needed here as a result.
{{ gold_model_config('TRANSCRIPT_EVENTS') }}

select
    event_key,
    cik,
    ticker,
    company_key,
    event_id,
    event_type,
    fiscal_year,
    fiscal_quarter,
    event_date,
    accession_number,
    storage_uri,
    content_sha256,
    char_count,
    language,
    source_system,
    source_url,
    as_of,
    ingested_at
from {{ source("edgartools_source", "TRANSCRIPT_EVENTS") }}
