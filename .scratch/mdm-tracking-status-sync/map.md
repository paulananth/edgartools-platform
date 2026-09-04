# MDM Tracking-Status Sync

Labels: wayfinder:map

## Destination

A decided design for keeping `mdm_company.tracking_status` continuously
synced from `sec_company_sync_state` (Bookkeeping Postgres — confirmed the
single system of record for company tracking status; `run_companies` and
`coverage.py` already read it directly rather than the MDM mirror).
Pulled by MDM itself during Mastering, diff-only (not a full resync every
run), via a new chunked bulk write. Done when someone can implement it
without hitting an undecided design question. This map does not
implement it.

## Notes

- Consult `/gof-refactor-reviewer` before touching
  `edgar_warehouse/mdm/pipeline.py` (Mastering/`run_companies`) or
  `edgar_warehouse/mdm/universe.py` — CLAUDE.md hard rule, no exceptions
  for small tickets.
- **Found while investigating (2026-09-04)** whether
  `sec_company_sync_state` and `mdm_company.tracking_status` actually stay
  in sync, prompted by the user's own conceptual framing
  ("sec_company_sync_state is the seed universe... must be in sync with
  mdm"): confirmed `mdm_company.tracking_status` is frozen at creation —
  `bulk_upsert_universe` (`edgar_warehouse/mdm/universe.py:90-95`)
  explicitly refuses to overwrite an existing row's value
  (`if company.tracking_status is None: ...`), and the one function built
  to refresh it later, `update_tracking_status`/`_sync_mdm_tracking_status`
  (`warehouse_orchestrator.py:6533`), has **zero live callers** anywhere in
  the pipeline. **No live consumer is currently harmed** by this —
  `run_companies`'s own docstring calls `sec_company_sync_state` "the sole
  source of tracking-status data" (DuckDB Retirement Cutover Ticket 13),
  and `coverage.py` reads it the same way, both deliberately bypassing the
  stale mirror. This is architectural debt (a column + a whole function
  implying a maintained invariant that was quietly abandoned at the
  Ticket 13 cutover), not a live bug — but the operator explicitly wants it
  fixed properly rather than left or merely documented.
- **Decided so far, via `/grilling` (2026-09-04):**
  - **Trigger**: pulled by MDM itself inside Mastering — not a separate
    scheduled push step, not inlined into `daily_incremental`'s own
    bookkeeping flow.
  - **Granularity**: diff-only — only CIKs whose `tracking_status` actually
    changed since MDM's last sync, not a full resync of the whole active
    set every run (this session already spent hours eliminating exactly
    this class of full-table-scan/N+1 cost elsewhere — see
    `claim_discovery_ciks`/`seed_company_sync_state_bulk_if_missing`).
  - **Write primitive**: a new chunked bulk method on the MDM side,
    mirroring tonight's `claim_discovery_ciks`/
    `seed_company_sync_state_bulk_if_missing` pattern — explicitly not a
    per-CIK loop through the existing single-CIK `update_tracking_status`.
- **Real, concrete gap found while charting, not yet resolved:**
  `sec_company_sync_state` (`edgar_warehouse/bookkeeping/models.py:284-315`)
  has **no dedicated "tracking_status changed at" column**. The closest
  candidate, `last_main_sync_at`, is a broader "this row was last touched
  by the main sync process" timestamp — it changes on events that don't
  necessarily mean `tracking_status` itself changed, and isn't set at all
  by `seed_company_sync_state_bulk_if_missing`'s insert-only path. The
  diff-only granularity decided above has no clean implementation path
  until this is resolved — see Ticket 01.
- Real files in scope: `edgar_warehouse/mdm/pipeline.py` (Mastering /
  `run_companies` entry point), `edgar_warehouse/mdm/universe.py`
  (`update_tracking_status`, `bulk_upsert_universe`),
  `edgar_warehouse/bookkeeping/store.py` (needs a new bulk "changed since
  X" read method), `edgar_warehouse/bookkeeping/models.py`
  (`SecCompanySyncState`).

## Decisions so far

(three axis-decisions below were settled while charting this map, recorded
here directly since they predate any child ticket)

- **Trigger**: pulled by MDM itself inside Mastering.
- **Granularity**: diff-only, keyed on last-changed.
- **Write primitive**: a new chunked bulk method, not the existing
  per-CIK `update_tracking_status`.
- [01 — Decide the "Changed Since" Watermark Mechanism](issues/01-decide-changed-since-watermark-mechanism.md)
  — new `tracking_status_changed_at` column on `sec_company_sync_state`,
  set only at real transitions (not on every touch, unlike
  `last_main_sync_at`); MDM's own "last synced up to" watermark lives in
  a small MDM Postgres table, mirroring the existing
  `MdmPublicationRequest.committed_watermark` / `MdmGraphGeneration.
  committed_watermark` precedent — bookkeeping stays consumer-agnostic.
- [02 — Decide Mastering's Integration Point and the Bulk Read/Write Method Signatures](issues/02-decide-mastering-integration-point-and-method-signatures.md)
  — diff-pull runs inside `run_companies` itself (every call, not just
  full `mdm mastering`), best-effort/non-blocking on failure, UPDATE-only
  write (never creates `mdm_company` rows), method signatures named
  (`get_company_sync_states_changed_since`, `sync_tracking_status_bulk`).
  Also found and fixed in the design: seed-universe's own "already
  onboarded" filter (`warehouse_orchestrator.py:2097`) would start
  wrongly re-seeding deregistered companies once the column goes live —
  fixed by a new status-agnostic `get_known_ciks` query.

## Not yet specified

(none — both tickets resolved; the route to the destination is fully
specified)

## Out of scope

<!-- none yet -->
