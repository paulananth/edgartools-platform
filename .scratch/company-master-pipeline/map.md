# Company Identity Pipeline

## Destination

A standalone data pipeline — decoupled from ownership (Form 3/4/5 + 13F) and
ADV — that captures SEC company master identity, 10-K filings, and
fundamental/financial data (XBRL) for every CIK, resolves them into MDM as
Company entities, and syncs them to the hosted graph, independent of
ownership/ADV relationship derivation. Runs in two modes mirroring the
platform's existing `load_history`/`daily_incremental` pairing: a
bulk/backfill mode for the full historical company universe, and a daily
incremental mode to keep company data current going forward. Ownership and
ADV processing proceed independently but should be sequenced to run *after*
company data for a given scope is available, since `IS_INSIDER` relationship
derivation already depends on resolved Company entities today
(`_derive_is_insider` skips unresolved issuers).

## Notes

- Domain: edgartools-platform, AWS-first SEC EDGAR data platform. Consult
  `CONTEXT.md` (root) for canonical vocabulary before introducing new terms;
  flag conflicts via `/domain-modeling` rather than silently overriding.
- Standing preference: reuse existing capabilities before building new ones.
  Confirmed already present: `mdm run --entity-type company`,
  `mdm sync-graph --entity-type company`, `bootstrap-fundamentals --mode
  entity-facts` (SEC companyfacts XBRL API — this already **is**
  "fundamentals"; treat it as reusable as-is unless a ticket finds otherwise).
- Every session should default to `/grilling` + `/domain-modeling` for design
  decisions; use `/research` for fact-finding that requires external
  documentation or third-party API behavior, not code already in this repo.
- Explicitly **separate concerns, deliberately deferred** (see Out of scope):
  Ownership (Form 3/4/5 + 13F) and ADV each get their own future decoupling
  effort. Ticket 21 (insider-scoped `EMPLOYED_BY` completeness) is a related
  but distinct effort the user has already flagged as handled separately.
- ~~Ticket 20 (the strict relationship-release production bulk load) is
  **on hold, gated on this map's progress**~~ — **hold lifted (confirmed
  2026-07-23):** six strict executions launched after the 2026-07-20 hold
  date, so it was informally lifted without this note being updated at the
  time. Ticket 20 proceeds independently of this map's progress; see
  `.scratch/release-readiness/issues/20-execute-required-relationship-production-bulk-load.md`
  for current status.

## Decisions so far

- [Master identity data scope](issues/01-master-identity-data-scope.md) —
  reuse existing `company_tickers`/`company_tickers_exchange` reference data +
  per-CIK `submissions.json` as-is; no new SEC ingestion needed.
- [10-K scope: metadata vs. structured document parse](issues/02-10k-scope.md)
  — filing metadata + XBRL companyfacts facts only; no dedicated 10-K
  document/text parse (no confirmed consumer for narrative sections).
- [Confirm `mdm run --entity-type company` / `sync-graph --entity-type company` behavior](issues/03-mdm-entity-type-scoping-behavior.md)
  — safe to use as-is; `run_companies()` never touches relationship
  derivation, `CompanyResolver` never joins ownership/ADV silver tables.
- [Bronze/Silver isolation mechanism](issues/04-bronze-silver-isolation-mechanism.md)
  — new `--mode company-identity` on the existing `bootstrap-fundamentals`
  command; reuses the unified silver DuckDB and existing idempotency, no new
  storage shape.
- [Bulk mode state machine shape](issues/05-bulk-mode-state-machine-shape.md)
  — woven into `load_history` as a new strict Stage 0 before Branch A
  ownership bootstrap, `MaxConcurrency=1`, no dedicated MDM/graph or
  gold-refresh step (feeds the existing single chains). Also surfaced and
  fixed a prerequisite: the windowed Branch B publish path shared the same
  full-copy-candidate OOM already fixed for company-identity's ad-hoc path
  (see TODOS.md, PR #215) — a live landmine, since `load_history` and
  `bootstrap` had zero prod executions ever.
- [Daily mode state machine shape](issues/06-daily-mode-state-machine-shape.md)
  — `daily_incremental` is restructured (not left untouched behind a
  separate schedule) into a Company phase reusing ticket 05's exact windowed
  capture, ahead of its existing pipeline; decisive because
  `daily_incremental` also has zero prod executions ever.

## Not yet specified

- ADV pipeline shape (own future map).
- Ownership pipeline shape beyond what Ticket 20 already does (own future map).

## Out of scope

- Redesigning Ticket 20's strict release state machine — ruled out by the
  "standalone, not woven in" destination decision this session.
- Ownership (Form 3/4/5 + 13F) pipeline redesign — separate future effort,
  named but not detailed here.
- ADV pipeline redesign — separate future effort, named but not detailed here.
- Insider-specific concerns (Ticket 21) — explicitly deferred by the user.
