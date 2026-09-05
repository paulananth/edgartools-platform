# 03 — Entity-facts incremental refresh trigger

Type: task
Status: open

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

- [ ] A manual `bootstrap-fundamentals --mode entity-facts` run against a
      real CIK window skips CIKs with no new qualifying filing, verified
      live — Phase 4 step 2's own verification requirement.
- [ ] A parser-version bump still forces a full refresh regardless of the
      new watermark (regression guard for the existing gate).
- [ ] `/gof-refactor-reviewer` consulted before editing
      `fundamentals_ingest.py`/`silver_once.py` (repo hard rule).
- [ ] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.
