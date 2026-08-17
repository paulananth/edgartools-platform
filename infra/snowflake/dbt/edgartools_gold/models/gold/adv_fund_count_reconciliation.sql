-- ADV_FUND_COUNT_RECONCILIATION: completeness cross-check between the
-- advFilingData-derived per-fund data already in silver (SEC_ADV_PRIVATE_FUND)
-- and SEC's independently-published, full-universe Firm Roster CSV aggregate
-- counts (SEC_ADV_FIRM_ROSTER). Purely additive visibility (ticket 04,
-- .scratch/adv-firm-roster-crosscheck/) -- never gates MDM entity resolution
-- or graph sync.
--
-- dbt-gold-silver-rewiring map, Ticket 02: both sources below now read dbt
-- silver (sec_adv_private_fund, sec_adv_firm_roster) via ref() instead of
-- the Python-builder-populated EDGARTOOLS_SOURCE mirrors.
--
-- Grain: one row per adviser_crd_number present in either source.
--
-- Join semantics (resolved 2026-07-28, see ticket 04's file for the full
-- history): the ticket's original "reconcile against each CRD's latest known
-- fund count, mirroring adv_bulk_ingest.py's reconstruct_effective_adv_set"
-- option is NOT faithfully implementable here -- SEC_ADV_PRIVATE_FUND only
-- carries rows for filings that reported at least one fund (there is no
-- CRD-keyed filing-level table exported to Snowflake), so a CRD's most
-- recent ADV filing that reports zero funds leaves no row here at all.
-- Picking "latest row present" would silently select an older, stale
-- nonzero-count filing for any firm that has since wound down its funds,
-- understating the true mismatch rate. This model instead uses the plain
-- reading of the ticket's own aggregation spec: COUNT(DISTINCT
-- private_fund_id) across ALL historical rows for the CRD, joined on
-- adviser_crd_number only -- no dataset_period filter, since
-- SEC_ADV_FIRM_ROSTER is a full-universe monthly snapshot while
-- SEC_ADV_PRIVATE_FUND is a rolling delta of filing activity (~17% of firms
-- per month); period-equality would show ~83% of firms as spurious
-- mismatches purely from that cadence gap. This deliberately over-counts
-- (never under-counts) firms whose funds have since been fully wound down --
-- an acceptable, documented blind spot for a purely-additive completeness
-- signal, not a launch-blocking gate.
{{ gold_model_config('ADV_FUND_COUNT_RECONCILIATION') }}

with filing_derived_counts as (

    -- private_fund_id is guaranteed non-null: adv_bulk_ingest.py's parser
    -- fails closed (WarehouseRuntimeError) on any row with an unresolved
    -- Fund ID before it ever reaches silver, so no coalesce/fallback key is
    -- needed here.
    select
        adviser_crd_number,
        count(distinct private_fund_id) as filing_derived_fund_count
    from {{ ref('sec_adv_private_fund') }}
    where adviser_crd_number is not null
    group by adviser_crd_number

),

-- SEC_ADV_FIRM_ROSTER accumulates one row per (adviser_crd_number,
-- dataset_period) as successive monthly snapshots are ingested -- keep only
-- each CRD's most recent snapshot for reconciliation.
latest_roster as (

    select
        adviser_crd_number,
        dataset_period,
        private_fund_count_7b1,
        private_fund_count_7b2,
        private_fund_count_7b1 + private_fund_count_7b2 as roster_fund_count
    from {{ ref('sec_adv_firm_roster') }}
    where adviser_crd_number is not null
    qualify row_number() over (
        partition by adviser_crd_number
        order by dataset_period desc
    ) = 1

)

select
    coalesce(f.adviser_crd_number, r.adviser_crd_number) as adviser_crd_number,
    r.dataset_period as roster_dataset_period,
    coalesce(f.filing_derived_fund_count, 0) as filing_derived_fund_count,
    coalesce(r.roster_fund_count, 0) as roster_fund_count,
    r.private_fund_count_7b1,
    r.private_fund_count_7b2,
    coalesce(r.roster_fund_count, 0) - coalesce(f.filing_derived_fund_count, 0) as fund_count_delta,
    coalesce(f.filing_derived_fund_count, 0) <> coalesce(r.roster_fund_count, 0) as mismatch
from filing_derived_counts f
full outer join latest_roster r
    on r.adviser_crd_number = f.adviser_crd_number
