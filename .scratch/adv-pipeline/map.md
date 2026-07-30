# ADV Pipeline

## Destination

A decided, buildable plan for the full Form ADV data pipeline: reconcile the
existing adviser-fund source contract with the real current SEC/IAPD bulk
format (confirmed changed as of 2026-07-24 — see Notes), decide the
private-fund-detail strategy, and specify automated fetch wired into
`load_history` (baseline) and `daily_incremental` (ongoing refresh), all the
way through silver → MDM entity resolution → derived relationships →
Neo4j/Snowflake graph. Hands off to `/to-spec` + `/to-tickets` +
`/implement` once the map is clear — this map decides, it does not build
(with the narrow exception of the manual end-to-end validation task, which
is execution needed to unblock a later decision, not the destination itself).

## Notes

- Domain: edgartools-platform, AWS-first SEC EDGAR data platform. Consult
  root `CONTEXT.md` for canonical vocabulary; flag conflicts via
  `/domain-modeling` rather than silently overriding.
- **This is the "own future map" that `company-master-pipeline`'s map
  explicitly deferred** ("ADV pipeline shape (own future map)" in its Not
  yet specified section) — that map's Company Identity Pipeline work is a
  separate, already-decided effort and is not touched here.
- Standing preference: reuse existing capabilities before building new
  ones. Confirmed already working (validated live against Ticket 20's graph
  work, 2026-07-23/24): `mdm run --entity-type adviser --entity-type fund`,
  `mdm derive-relationships`, `mdm sync-graph`, `mdm verify-graph`,
  `mdm graph-activate`, and `ingest-relationship-sources --kind
  iapd_adv_bulk` (needs a source manifest with `storage_path` + `sha256`,
  already implemented). The only genuinely missing/broken pieces are: (1)
  the parser's assumed archive format, (2) automated fetch, (3) pipeline
  wiring.
- Primary context artifact for this whole map:
  [`docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md`](../../docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md)
  — documents the live-format discovery and a candidate ordered next-steps
  list this map formalizes into tickets.
- Existing contract:
  [`docs/release-readiness/adviser-fund-source-contract.md`](../../docs/release-readiness/adviser-fund-source-contract.md),
  approved via `.scratch/release-readiness/issues/13-define-adviser-fund-source-contract.md`
  (resolved) and implemented per
  `.scratch/release-readiness/issues/21-implement-authoritative-form-adv-private-fund-ingestion.md`
  (marked resolved, commits `ddc24d3`/`846d648`/`4f4e1a9`). **Ticket 01
  found the contract and parser were never actually broken** — last
  session's "zero rows" finding came from staging the wrong SEC product
  (the sec.gov Firm Roster CSV) instead of the correct one
  (`adviserinfo.sec.gov`'s monthly `advFilingData` relational feed, which
  the parser's existing regexes match exactly). This map still owns Ticket
  21 (explicit user decision, 2026-07-24), but the reconciliation is now
  much lighter: confirm the operational fetch target, not rewrite the
  parser. See ticket 01's Answer/research file for full detail.
- Every session should default to `/grilling` + `/domain-modeling` for
  design decisions; use `/research` (background subagent) for fact-finding
  that needs primary-source SEC/IAPD documentation, not code already in
  this repo.
- **Corrected by ticket 01 (2026-07-24):** the authoritative per-fund source
  (`advFilingData`) is a **monthly delta of filing activity**, not a
  full-universe snapshot — verified by row count (June 2026: 2,938 firm
  rows vs. ~17,073 registered firms total, ~17% coverage). This is actually
  closer in shape to 13F/proxy's windowed relationship types than
  originally assumed — it needs a rolling multi-month union (deduped by
  CRD/FilingID, latest per firm), not a single current-snapshot fetch. The
  separate Firm Roster CSV (`sec.gov`) *is* a true full-universe
  point-in-time snapshot, but only carries aggregate private-fund counts,
  not per-fund identity. Ticket 03's Q1/Q2 answers need to be revisited
  under this corrected model.
- **Hard requirement, restated explicitly by the user (2026-07-24): ADV data
  must reach the Neo4j/Snowflake graph, end to end — not stop at silver.**
  This binds every ticket's resolution, especially ticket 02: if bulk data
  truly only supports firm-level aggregate private-fund counts (no PFID),
  that may force `MANAGES_FUND` itself to degrade or drop — but it must
  **not** become a reason to drop Adviser/Fund entity resolution or graph
  sync altogether. At minimum, resolved Adviser and Fund entities (from
  whatever the Firm Roster format actually supports) must resolve into MDM
  and sync to the hosted graph; `MANAGES_FUND` edge fidelity is the part
  that's genuinely at risk pending ticket 01/02, not the graph destination
  itself. Ticket 04's manual validation is the checkpoint that proves this
  actually happened (real nodes/edges, not the placeholder 112/1 counts).

## Decisions so far

- [01 — Confirm Scope of IAPD Bulk Format Change](issues/01-confirm-scope-of-iapd-format-change.md)
  — the old relational per-fund format was never discontinued; it moved to
  `adviserinfo.sec.gov`'s monthly `advFilingData` feed. `adv_bulk_ingest.py`'s
  existing parser already matches this feed's real files — last session's
  "zero rows" blocker was caused by fetching the wrong SEC product, not a
  format change the parser needs rewriting for. New finding: the feed is a
  monthly filing-activity delta (~17% of firms/month), not a full snapshot,
  so full coverage needs a rolling multi-month window.
- [03 — ADV Time-Scope and Cadence Semantics](issues/03-adv-time-scope-and-cadence-semantics.md)
  — `load_history` fetches a rolling ~13-month window of monthly deltas
  only (no 2000-2024 historical backfill, mirroring the 13F/proxy
  narrow-to-current-state precedent); `daily_incremental` runs daily gated
  by a local `dataset_period`-already-ingested check (unchanged by the
  delta-vs-snapshot correction); each `dataset_period` is fully immutable
  once ingested; ERA and RIA get identical handling.
- [02 — Fetch Target and Rolling-Window Strategy](issues/02-parser-and-private-fund-detail-strategy.md)
  — 13-month rolling window locked (already tested in production; dedup-latest-per-CRD
  logic was already live in `mdm/adv_bulk.py`, not actually open); Firm Roster CSV
  ingested as a parallel completeness cross-check (design spun off to ticket 08); no
  2000-2024 historical backfill, confirming ticket 03's conclusion under corrected
  premises; found a genuine gap — bulk feed never populates `sec_adv_office`/
  `sec_adv_disclosure_event` — spun off to ticket 07 (research).
- [07 — Office and Disclosure-Event Coverage in the Bulk advFilingData Feed](issues/07-office-disclosure-bulk-coverage.md)
  — the gap is a parser-extension problem, not a missing-data problem: the monthly
  archive already contains real per-office data (`IA/ERA_Schedule_D_1F`, 13K+ rows) and
  real per-event DRP disclosure data (4 file families × IA/ERA), all keyed by the same
  `FilingID` the existing parser already joins on — `adv_bulk_ingest.py` just doesn't read
  these 6 file families yet. No implementation done (research-only ticket).
- [05 — Reconcile Ticket 21 and the Adviser-Fund Source Contract](issues/05-reconcile-ticket-21-and-contract.md)
  — updated `adviser-fund-source-contract.md` with the rolling-window and Firm Roster
  cross-check addendum (real gaps, not a no-op); annotated ticket 21 (implementation was
  correct, only the 2026-07-24 blocker doc's diagnosis was wrong); appended a correction
  to the blocker doc rather than rewriting it.
- [04 — Manual End-to-End Validation](issues/04-manual-end-to-end-validation.md) — ran
  against prod (dev reported not viable); the real finding was that this session's ingest
  was a byte-identical no-op (proven via matching source/staged/canonical checksums in the
  task's own log) — the 13-month `advFilingData` window was already loaded by a prior
  session (matching this map's own Notes citing 2026-07-23/24 graph work), not freshly
  loaded today. Read-only Snowflake query confirmed 138,585 real `MANAGES_FUND` edges live
  in the graph (exact match to MDM), decisively not the placeholder 112/1 counts. Did NOT
  run `backfill-relationships`/`sync-graph`/`graph-activate` — would have swept in other
  relationship types' un-attested pending work (ticket 20's in-flight `INSTITUTIONAL_HOLDS`
  backfill, etc.) into a new activated generation. Ticket 02's decision is validated.

- [06 — Automated Fetch and Pipeline Wiring Shape](issues/06-automated-fetch-and-pipeline-wiring.md)
  — new `fetch-adv-bulk` CLI subcommand (manifest as its own artifact, mirroring
  `mdm build-relationship-release-manifest`); wired into `load_history` as a new
  sequential Stage between bronze/silver and MDM (not a parallel Map — ADV fetch isn't
  CIK-windowed); `daily_incremental` invokes it daily with a cheap local-check-first
  no-op path, no fixed day-of-month gate; optional `dataset_period`/`force` SM-input
  fields for manual repair, mirroring `artifact_policy`'s Check→Default pattern.
- [08 — Design the Firm Roster CSV Completeness Cross-Check](issues/08-firm-roster-crosscheck-design.md)
  — new narrow `sec_adv_firm_roster` silver table (CRD + ~8 aggregate private-fund
  columns only, not the full 448/171-column row) plus a dbt gold reconciliation view
  (`adv_fund_count_reconciliation`) joining it against `advFilingData`-derived fund
  counts; mismatches surface as a queryable gold view and a dashboard panel, never
  gating MDM/graph sync; fetch mirrors `daily_incremental`'s monthly local-check-first
  pattern, reconciliation recomputes on the gold table's normal refresh schedule.

## Not yet specified

- Longer-term: whether ADV data should ever get its own Stage-0-style phase
  woven into `load_history`/`daily_incremental` the way Company Identity did
  (company-master-pipeline tickets 05/06), or stays a separate
  `ingest-relationship-sources` invocation alongside them — ticket 06
  resolves the immediate wiring shape; whether it later gets promoted to a
  first-class phase is out of view until that ships and is observed running.
- `sec_adv_filing` has no `source_dataset_period` column, unlike
  `sec_adv_private_fund` — `ingest_adv_bulk_archive`'s `filing_rows` never
  carries it (found while implementing ticket 06's `fetch-adv-bulk` command,
  which had to query `sec_adv_private_fund` instead for its idempotency
  check). Whether this is worth its own backfill/schema ticket, or is
  harmless as-is, hasn't been decided.
## Out of scope

(none yet)

## Handoff

The frontier is empty — all 8 tickets are resolved and the way to this map's destination
is clear. Per the Destination's stated handoff, `/to-spec` has produced two
`ready-for-agent` specs covering the remaining build work (ticket 06 decisions 2–4 and
ticket 08's full design):

- [Wire `fetch-adv-bulk` into `load_history` and `daily_incremental`](../adv-fetch-pipeline-wiring/spec.md)
  — **done.** Both tickets (`01-wire-stage-into-load-history`,
  `02-wire-stage-into-daily-incremental`) implemented via TDD against the existing
  `test_load_history_state_machine.py`/`test_daily_incremental_state_machine.py`
  structural test harness, code-reviewed (two real bugs found and fixed: a Catch bypassing
  the new stage, a missing `ResultPath: null` reintroducing this file's own documented
  D-15 bug class), and committed on `claude/adv-pipeline-t04-t05` (commit `28a343e`). Not
  yet pushed/merged.
- [Firm Roster CSV completeness cross-check](../adv-firm-roster-crosscheck/spec.md) —
  broken into 4 published tickets under `../adv-firm-roster-crosscheck/issues/`, approved
  by the user 2026-07-28: `01-firm-roster-parser-silver-table` (unblocked, frontier) →
  `{02-fetch-ingest-stage-wiring, 03-snowflake-passthrough-exports}` (both blocked only by
  01, parallelizable) → `04-reconciliation-model-dashboard` (blocked by 03). Ticket 02 can
  now wire directly into the `AdvBulkFetch` Stage the first spec shipped, rather than
  waiting on it. Scope grew by one table (`SEC_ADV_PRIVATE_FUND`) beyond ticket 08's
  Answer once the existing gold `PRIVATE_FUNDS` table was confirmed CIK-keyed, not
  CRD-keyed — see that spec's Further Notes. **Tickets 01-03 shipped** (PR #296,
  `9f09def`). **Ticket 04 implemented 2026-07-28** (`adv_fund_count_reconciliation` dbt
  model + dashboard panel, `claude/adv-fund-count-reconciliation`) — see that ticket's file
  for the join-semantics resolution and the live-Snowflake-credentials gap (`dbt
  compile`/`dbt run --full-refresh`/browser smoke test not run this session).
