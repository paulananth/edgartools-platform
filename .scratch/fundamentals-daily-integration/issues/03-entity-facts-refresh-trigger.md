# 03 — Entity-facts incremental refresh trigger

Type: task
Status: done

**Blocked by:** 01 — Fix the `sec_financial_fact`/`sec_accounting_flag`
retirement publish-conflict bug (user's explicit decision: fix the
retirement bug first, as a prerequisite, since entity-facts writes into
those exact two tables).

## What to build

A per-CIK watermark — check `sec_company_sync_state` first (if it already
exists and is queried per-CIK elsewhere, extend it there; otherwise a
small new table mirroring Ticket 02's shape), e.g. a new column
`entity_facts_refreshed_at`.

On each `daily_incremental` run, select CIKs where the most recent
10-K/10-K-A/10-Q/10-Q-A `filing_date` in `sec_company_filing` is newer than
`entity_facts_refreshed_at` (or the watermark is null/absent — first
touch). This **composes with, not replaces**, the existing
`has_companyfacts_at_version` parser-version gate
(`silver_once.py:61-76`): a parser-version bump must still force a refresh
of every CIK regardless of watermark — that existing gate already gets
this right. The new trigger only narrows *which* CIKs are attempted on an
ordinary (non-version-bump) day.

## Tests

- Unit test proving a CIK with no new 10-K/10-Q since its last refresh is
  skipped (zero SEC calls).
- A companion test proving a CIK with a new qualifying filing is
  refreshed.

## Acceptance

- [x] A manual `bootstrap-fundamentals --mode entity-facts` run against a
      real CIK window skips CIKs with no new qualifying filing, verified
      live — Phase 4 step 2's own verification requirement.
- [x] A parser-version bump still forces a full refresh regardless of the
      new watermark (regression guard for the existing gate) — unit-tested
      via `EntityFactsRefreshTriggerTests` (composition with
      `has_companyfacts_at_version`, not a replacement of it).
- [x] `/gof-refactor-reviewer` consulted before editing
      `fundamentals_ingest.py`/`silver_once.py` (repo hard rule).
- [x] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.

## Answer

Implemented as specified: `sec_entity_facts_refresh_watermark(cik,
entity_facts_refreshed_at)`, composed with (not replacing) the existing
`has_companyfacts_at_version` parser-version gate via
`get_ciks_with_new_qualifying_filing` (`silver_once.py`). Landed on PR
[#603](https://github.com/paulananth/edgartools-platform/pull/603),
merged into `main` (commit `6813190c`).

Same two prerequisite fixes as [Ticket 02](02-accession-level-incremental-scoping.md)
were required before live verification could actually pass (Tickets 17/18
in `duckdb-retirement-cutover`). Once deployed to prod, live verification
against CIK 908311 confirmed the full loop: run 1 fetched
(`network_fetches: 1`) and wrote a watermark row; run 2 skipped
(`silver_skips: 1, network_fetches: 0`) — re-confirmed a second time after
the real prod deploy (`edgartools-prod-large:299`).
