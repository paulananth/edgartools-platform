# 6 empty gold tables blocking gold-verify-live (Stage 15 follow-up)

Status: resolved (2026-08-09)

## Resolution

Disposition settled per-table via a short wayfinder grilling session
(2026-08-09), no fog found for the go-live-triage question itself (per
wayfinder's own no-fog rule, decided directly rather than charted):

| Table | Disposition |
|---|---|
| `ACCOUNTING_FLAGS` | Already tracked — task #35 (full-universe `bootstrap-fundamentals` via `load_history`). No new action. |
| `GUIDANCE_FACTS` / `EARNINGS_CALENDAR` | Same producer/fix as `ACCOUNTING_FLAGS` — populated by the same `bootstrap-fundamentals` full-universe run once task #35 executes. Closes automatically, no separate action. |
| `CONSENSUS_ESTIMATES` / `TRANSCRIPT_EVENTS` | Intentionally pilot-scoped by design (ERDP-01/ERDP-04). **Action needed:** exclude both from `gold-verify-live`'s required-table list (`edgar_warehouse/serving/gold_verify.py`'s `GOLD_LIVE_TABLES`) — not yet implemented, small follow-up. |
| `ADVISER_DISCLOSURES` | Real gap, confirmed **not** "no producer code" (that earlier claim in this file was wrong) — a real gold builder (`_build_fact_adv_disclosure`) and dbt model already exist; the actual gap is one layer upstream: nothing in production writes to the silver table `sec_adv_disclosure_event` it reads from. This is the *same* gap the `adv-pipeline` map's ticket 07 had already researched (parser-extension problem, not missing-data — confirmed real DRP disclosure data exists in the bulk archive) but never spec'd for implementation. Turned into an implementation-ready spec: [adv-pipeline ticket 09 — Office/Disclosure Bulk-Parser Extension Spec](../../adv-pipeline/issues/09-office-disclosure-parser-extension-spec.md). |

Two small follow-ups remain before this table set is fully closed:
excluding the 2 pilot tables from `gold-verify-live` (mechanical, not yet
done), and implementing adv-pipeline ticket 09 (spec'd, ready for
`/to-spec` + build, not yet done). Both are tracked at their respective
locations, not re-tracked here.

## Context

Stage 15 (`gold-verify-live`) requires all 21 `EDGARTOOLS_GOLD` dynamic
tables to be non-empty. After fixing the 5 `EDGARTOOLS_PROD_LOADER` grant
gaps that blocked `SNOWFLAKE_RUN_MANIFEST_TASK` (see the "Manifest-pipeline
ownership" and this session's live grant fixes to
`infra/snowflake/sql/bootstrap/08_loader_role.sql`), the task now succeeds
and 15 of 21 tables are populated with real data. 6 remain at 0 rows, and
this is **not** another grants bug -- confirmed live via
`EDGARTOOLS_PROD.EDGARTOOLS_SOURCE` row counts: all 6 underlying source
tables are genuinely at 0 rows, so gold is correctly empty.

Decided 2026-08-09: proceed to Stage 16/17/18 with Stage 15 left
in-progress/partial; resolve this ticket as a follow-up rather than
blocking the rest of go-live on it.

## Root causes (3 distinct groups, verified against code + live row counts)

1. **`ACCOUNTING_FLAGS`** -- already-tracked. Ticket 42's full-universe
   backfill (task #35, still pending) is exactly what populates this via
   `run_bootstrap_fundamentals_per_filing`. Not yet run in this rebuilt
   account.

2. **`GUIDANCE_FACTS` / `EARNINGS_CALENDAR`** -- same producer as #1
   (`sec_guidance_fact` silver table, written only by
   `run_bootstrap_fundamentals_per_filing` -- the standalone
   `bootstrap-fundamentals` CLI command / `load_history`'s
   `Stage1BPerFiling`). Stage 14's `bronze_seed_silver_gold` one-click
   refresh chains `SeedFromBronze -> BatchSilver -> MdmRun -> MdmBackfill
   -> MdmSync -> MdmVerify -> GoldRefresh` -- it has **no fundamentals-per-
   filing step at all**, so these were never going to populate from the
   stage that actually ran. `EARNINGS_RELEASE` (a different, upstream
   silver table) already has 918 real rows -- confirms filing-level data
   exists, just not yet passed through the fundamentals-extraction pass.

3. **`CONSENSUS_ESTIMATES` / `TRANSCRIPT_EVENTS`** -- by design, pilot-
   scope "Explore" products (ERDP-01 / ERDP-04,
   `edgar_warehouse/explore/consensus_estimates.py` /
   `transcript_events.py`). `transcript_events.py` locks its pilot universe
   to a single CIK (Apple), requiring a manual IR-website pointer or file
   upload; `consensus_estimates.py` requires an explicit pilot loader run
   (yahoo/firm_manual sources). Neither is wired into any automated
   pipeline -- empty is the expected state until someone runs the pilot
   loader by hand.

4. **`ADVISER_DISCLOSURES`** -- the outlier: no producer exists anywhere in
   the codebase. The dbt gold model
   (`infra/snowflake/dbt/edgartools_gold/models/gold/adviser_disclosures.sql`)
   and the `EDGARTOOLS_SOURCE.ADVISER_DISCLOSURES` table both exist, but
   `edgar_warehouse/serving/gold_models.py` has zero references to it --
   no builder function, no silver table, nothing writes rows. This is a
   genuine, real implementation gap, not a sequencing/scope issue like the
   other 5 tables. Needs its own scoping ticket (what is an "adviser
   disclosure" supposed to be sourced from -- likely ADV Part 2 brochure
   items, not yet parsed anywhere in this codebase).

## Options for closing this ticket

- Narrow `gold-verify-live`'s `GOLD_LIVE_TABLES` check
  (`edgar_warehouse/serving/gold_verify.py`) to exclude the 2 pilot-scoped
  tables permanently (they may never be broadly populated), and/or split
  the check into "must be populated at go-live" vs "known future/pilot
  work" tiers.
- Run `bootstrap-fundamentals` at full-universe scale (closes ticket 42's
  task #35 and, as a side effect, `GUIDANCE_FACTS`/`EARNINGS_CALENDAR` too).
- Scope and implement an `ADVISER_DISCLOSURES` producer (separate piece of
  work -- likely needs an ADV Part 2 brochure parser that doesn't exist
  yet).

None of these were started as part of this ticket -- this is a pure
root-cause record for whoever picks it up next.
