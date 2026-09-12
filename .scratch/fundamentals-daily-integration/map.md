# Bring Missing Fundamentals Artifacts Into daily_incremental

Label: `wayfinder:map`

## Destination

A shipped, deployed change that brings `load_history`'s Stage 1B
fundamentals-extraction modes — per-filing (earnings/executive records),
13F holdings, and XBRL entity-facts — into `daily_incremental`'s own Step
Functions pipeline, with real accession-level incremental scoping (not just
a narrower CIK window) and a prerequisite fix to the standing
`sec_financial_fact`/`sec_accounting_flag` retirement publish-conflict bug,
so MDM/gold see fresh earnings releases, executive records, 13F holdings,
and financial facts on a daily cadence instead of only whenever
`load_history` is re-run against the whole universe.

## Notes

- Repo: `edgartools-platform`. This map carries decisions **and** their
  implementation (Phases 0-4 below), following the convention the
  `change-propagation` map already established: plan-only tickets would be
  a poor fit here because the destination is a shipped, deployed change,
  not a spec handoff.
- **Origin:** this map's tickets convert an already-approved implementation
  plan (`/Users/aneenaananth/.claude/plans/mossy-meandering-dream.md`,
  approved via `ExitPlanMode` 2026-09-05) into wayfinder tickets. The three
  scope decisions below were already made by the user via `AskUserQuestion`
  during that plan-mode session, so tickets 01-03 are mostly execution, not
  open decisions:
  1. Integrate **all three** fundamentals modes (per-filing, thirteenf,
     entity-facts), not a subset.
  2. Build **real accession-level incremental scoping**, not just a
     narrower CIK window.
  3. **Fix the standing `sec_financial_fact` retirement bug first**, as a
     prerequisite, before entity-facts writes go live.
- **Key facts established before charting** (full detail in the plan file
  above; condensed per-ticket below):
  - per-filing/thirteenf modes (`edgar_warehouse/application/workflows/fundamentals_ingest.py`)
    make **zero new SEC calls** — pure local reads of `sec_filing_attachment`/
    `sec_raw_object` bytes `daily_incremental` already captures. Idempotent
    on write (`ON CONFLICT ... DO UPDATE`) but **no read-side skip** — every
    run re-scans a CIK's entire historical matching-form set.
  - entity-facts makes one real SEC call per CIK, gated only by
    `has_companyfacts_at_version` (a one-time parser-version gate, no "new
    filing since last fetch" awareness).
  - `sec_company_filing` already captures 10-K/10-Q filing metadata
    regardless of whether that form's artifact content was ever fetched —
    the foundation for an entity-facts refresh trigger, no new bronze
    capture needed.
  - Retirement bug: `retire_financial_facts_not_in_snapshot`'s own `UPDATE`
    never bumps `sec_financial_fact`'s `authority_column` (`ingested_at`),
    so a genuine retirement always ties on conflict resolution and aborts
    the whole silver publish with `SemanticMergeConflictError` (confirmed
    live: 434,805 ambiguous conflicts on one run). Reinstatement (the
    merge's own `ON CONFLICT DO UPDATE` branch) already bumps `ingested_at`
    correctly — only the retire path is broken.
  - `bootstrap-fundamentals` is deliberately excluded today from
    `SOURCE_EXPORT_COMMANDS` and the `sec_fetch_active` cross-command
    lease — wiring it into `daily_incremental` means entity-facts' SEC
    calls inherit the already-held lease for free, as long as the new
    states run before `ReleaseSecFetchLease`.
  - `load_history`'s Stage 1B runs these three modes on `wh_large_arn`
    (not medium) due to confirmed, mode-specific OOM history in the shared
    `merge_candidate_into_canonical` publish step. `MaxConcurrency: 1`,
    `ToleratedFailurePercentage: 15` (AD-13 catch-and-continue).
- **ADV, raised when this map was charted, resolved via grilling — see
  Decisions so far and Out of scope.** ADV bulk fetch
  (`FetchAdvBulk`/`IngestAdvBulkSources`) and Firm Roster fetch are
  **already** wired into `daily_incremental`'s Step Functions definition
  ([adv-fetch-pipeline-wiring](../adv-fetch-pipeline-wiring/spec.md) tickets
  01/02, both fully implemented). That's a different shape of gap than
  Phases 0-3 below, which need brand-new Step Functions states because
  `bootstrap-fundamentals` isn't wired into `daily_incremental` at all
  today.
- Per CLAUDE.md hard rule: consult `/gof-refactor-reviewer` before editing
  any production code file in any ticket below. Per CLAUDE.md hard rule:
  `/code-review` runs all three axes (Standards, Spec, GoF) before any
  ticket's PR is ready. Only commit/push/open a PR when the user
  explicitly asks — not yet asked for this map's work.
- Use `/grilling` + `/domain-modeling` if any ticket below needs to reopen
  a design question the plan didn't already settle.

## Decisions so far

- **ADV scope, resolved via this session's grilling round (2026-09-05):**
  ADV bulk fetch and Firm Roster fetch are already fully wired into
  `daily_incremental` (confirmed live in `deploy-aws-application.sh`) —
  no gap there. But the MDM-resolution layer is not diff-processed:
  `resolve_advisers_bulk`/`resolve_funds_bulk` use a bare, unordered
  `SELECT ... LIMIT 100` with no exclusion of already-resolved rows,
  and `daily_incremental`'s daily `mdm mastering --entity-type all
  --limit 100` call feeds that exact limit into both — confirmed live,
  not just theoretical (this is the same plateau bug Ticket 94 already
  fixed for `run_companies`, filed separately as release-readiness
  Ticket 100 and left unresolved there). User decided: fix it here, as
  [Ticket 06](issues/06-fix-adv-bulk-select-limit-plateau.md), alongside
  this map's other `daily_incremental` incremental-scoping work.
- [Fix the sec_financial_fact/sec_accounting_flag retirement publish-conflict bug](issues/01-fix-financial-fact-retirement-conflict.md)
  — closed CLAUDE.md's open "Part B" gap: a new `retirement_state_observed_at`
  column (migration 011) gives a genuine retirement its own tiebreak column
  instead of permanently tying on `ingested_at` and aborting the whole
  silver publish. Prerequisite for Ticket 03, now unblocked. 3-axis code
  review clean (0 blocking findings); CLAUDE.md's own 5-whys entry updated
  to reflect the resolution.
- [Fix `resolve_advisers_bulk`/`resolve_funds_bulk`'s unordered `LIMIT` plateau](issues/06-fix-adv-bulk-select-limit-plateau.md)
  — ported `run_companies`' growing-window fix (release-readiness Ticket
  94), extracting the shared helper into a new `bounded_fetch.py` module so
  `adv_bulk.py`'s free functions can reuse it without a circular import.
  `/code-review`'s Spec and GoF axes each surfaced one real, evidenced
  gap (a missing fund-side test; near-duplicated logic across the two
  sibling functions, matching this file's own history of fixing one and
  not the other) — both fixed before closing. 8 new tests, confirmed
  red-before/green-after via `git stash`; full `tests/mdm/` suite and full
  repo suite green, no new failures. Not yet committed.

- **Tickets 02/03 implemented** (accession-level dedup for per-filing/
  thirteenf, per-CIK refresh-trigger watermark for entity-facts) — logically
  correct, real-DuckDB-backed unit tests green, 3-axis `/code-review` clean,
  PR [#603](https://github.com/paulananth/edgartools-platform/pull/603)
  open. **Live verification blocked**, not by this work but by a separate,
  bigger pre-existing bug found while attempting it — see
  [duckdb-retirement-cutover Ticket 17](../duckdb-retirement-cutover/issues/17-repoint-bootstrap-fundamentals-reads-to-snowflake.md):
  `bootstrap-fundamentals` reads per-filing/thirteenf filing metadata and
  entity-facts' existing skip check from a local DuckDB that nothing has
  hydrated since 2026-09-07 (duckdb-retirement-cutover Ticket 10's own
  cutover). Confirmed live: per-filing sees zero filings for a CIK with
  1,006 real ones in Snowflake; entity-facts re-fetches every CIK's
  companyfacts on every run regardless of whether it already has current
  data. Tickets 02/03's own skip logic composes correctly with the
  *existing* gates, but neither can be meaningfully verified live until
  Ticket 17 repoints those reads to Snowflake `EDGARTOOLS_SILVER`.
- **Ticket 17's own live verification surfaced a second, independent gap on
  the write side** — see
  [duckdb-retirement-cutover Ticket 18](../duckdb-retirement-cutover/issues/18-bootstrap-fundamentals-never-wires-landing-export-buffer.md):
  `bootstrap-fundamentals` never wired a `LandingExportBuffer` into its
  `SilverDatabase` at all, so every write it makes (not just Tickets 02/03's
  two new tables — every existing fundamentals table) never reached the
  Snowflake landing zone, confirmed via a stale `MAX(ingested_at)` query
  against `SEC_EXECUTIVE_RECORD` after a run that logged 20 new rows for
  that same table. Fixed by resolving `SILVER_LANDING_EXPORT_ROOT` in
  `bootstrap_fundamentals.py`'s own context builder (it never had, unlike
  the shared `command_context_factory`) and porting the same
  construct-then-flush pattern `_execute_warehouse_bronze_capture` already
  uses. Tickets 02/03's own live verification depends on this landing too,
  not just Ticket 17's read-side fix.
- **Tickets 02/03 now fully live-verified end-to-end (2026-09-11/12)** —
  after Ticket 17 (read), Ticket 18 (write), and a third mechanical fix
  (`LOAD_SILVER_LANDING()`'s hardcoded table list, noted in Ticket 17's
  closing evidence) all landed together. Per-filing: run 1 against CIK
  908311 processed 15 filings; run 2 showed `filings_already_processed: 15,
  filings_parsed: 0`. Entity-facts: run 1 fetched (`network_fetches: 1`) and
  wrote a refresh watermark; run 2 skipped (`silver_skips: 1,
  network_fetches: 0`). Every step confirmed via a direct Snowflake query,
  not just task logs. PR #603 ready to merge pending CI.

<!-- tickets 01-05 below convert the approved plan; none has been worked through this map yet -->

## Not yet specified

- Whether Phase 4's live `daily_incremental` verification run surfaces any
  further gap in the three modes' interaction with the existing
  `RunMdmChain`/`FactPublishtoGold` states — not specifiable until Phase 3
  ships and a real execution is observed.

## Out of scope

- [ADV Pipeline Ticket 09 — Office/Disclosure Bulk-Parser Extension Spec](../adv-pipeline/issues/09-office-disclosure-parser-extension-spec.md)
  — raised when this map was charted; the user's grilling answer addressed
  only the ADV `LIMIT`-plateau question (now Ticket 06 here), not this one.
  Stays on the ADV Pipeline map, unimplemented, ready-for-agent whenever
  picked up — needs no Step Functions wiring since ADV bulk fetch already
  rides `daily_incremental`'s existing stage.
