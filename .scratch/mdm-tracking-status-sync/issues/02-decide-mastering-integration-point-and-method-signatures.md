# 02 — Decide Mastering's Integration Point and the Bulk Read/Write Method Signatures

Type: grilling
Status: resolved
Blocked by: 01

## Question

Once Ticket 01 settles the watermark mechanism, decide the concrete
implementation shape:

- Where inside `mdm mastering` / `run_companies`
  (`edgar_warehouse/mdm/pipeline.py`) does the pull-and-sync step run —
  before entity resolution starts for this run, as its own first phase?
  Does it block Mastering's own work on completion, or can it run
  best-effort (matching `BackpropagateIdsToSilver`'s own
  `Catch: States.ALL` — a failure here shouldn't fail an otherwise-
  successful Mastering run)?
- What's the new `BookkeepingStore` method's signature for reading
  "CIKs whose tracking_status changed since watermark W" — one bulk
  query, chunked how, returning what shape?
- What's the new MDM-side bulk write method's signature (mirroring
  `seed_company_sync_state_bulk_if_missing`/`demote_company_sync_state_bulk`'s
  chunked-upsert pattern) — does it live in `edgar_warehouse/mdm/universe.py`
  next to `update_tracking_status`, or somewhere else?
- Does this change anything about `seed-universe`'s own
  `_get_mdm_tracked_ciks("active")` "already onboarded" filter (map's own
  "Not yet specified" note) — confirm it still behaves correctly once the
  column is actually live instead of frozen.

Resolving this ticket should leave the map ready to hand off for
implementation — no further undecided design question standing in the way.

## Answer

Settled via `/grilling` (2026-09-04), four decisions:

1. **Integration point:** inside `run_companies` itself
   (`edgar_warehouse/mdm/pipeline.py:304`), immediately after the existing
   `bookkeeping.get_all_company_sync_states()` read (currently line 450).
   Fires on every call — full `mdm mastering` runs, `--limit`-scoped runs,
   and the Ticket 21 insider-path `issuer_ciks` call alike — since the
   diff-only design already makes a no-change call cheap regardless of
   caller, and `bookkeeping` is already a required parameter here with no
   new plumbing needed. `run_all` (pipeline.py:1933) needs no separate
   integration of its own — it already calls `run_companies` as one of its
   5 concurrent steps.
2. **Failure handling:** best-effort. Wrap only the new sync step in
   try/except, log a warning event (e.g. `mdm_tracking_status_sync_failed`)
   with the exception, and let `run_companies` finish normally. The
   existing bookkeeping read (`tracking_by_cik`, used to freeze new rows'
   status at creation) stays blocking, unchanged — DuckDB Retirement
   Cutover Ticket 13's decision holds for that read. This new write-back
   step is a separate concern with its own, looser policy, mirroring
   `BackpropagateIdsToSilver`'s own `Catch: States.ALL` precedent
   (CLAUDE.md) — a denormalized mirror write shouldn't fail an otherwise-
   successful Mastering run.
3. **Method signatures:**
   - New `BookkeepingStore` read method,
     `get_company_sync_states_changed_since(self, watermark: datetime |
     None) -> list[dict]` — one bulk query,
     `WHERE tracking_status_changed_at > :watermark` (or unconditional when
     `watermark is None`, first-ever sync), ordered by `cik`, returning
     `cik`/`tracking_status`/`tracking_status_changed_at` per row. No
     chunking needed on the read side — the diff-only design already
     bounds the result set.
   - New MDM-side bulk write method, `sync_tracking_status_bulk(engine,
     rows: list[dict]) -> int`, in `edgar_warehouse/mdm/universe.py` next
     to `update_tracking_status`, chunked the same way
     `demote_company_sync_state_bulk`/`seed_company_sync_state_bulk_if_missing`
     already are (mirroring `_COMPANY_SYNC_STATE_BULK_CHUNK_SIZE = 1000`).
     **UPDATE-only, never INSERT/upsert** — a bare `mdm_company` row can't
     be created without also creating its parent `mdm_entity` row
     (`bulk_upsert_universe`, `universe.py:74-92`, is the only place that
     does the 2-step entity-then-company creation correctly; a bulk sync
     method has no business doing that). A changed-since CIK with no
     existing `mdm_company` row is silently skipped — not MDM's job to
     create here; it'll be enrolled later by seed-universe or
     `CompanyResolver` with an already-correct status at that point.
4. **Seed-universe filter fix (confirmed real regression, not
   hypothetical):** `warehouse_orchestrator.py:2097`'s
   `_get_mdm_tracked_ciks("active")` — used to exclude "already onboarded"
   companies from re-seeding — was silently correct only because the
   column was frozen (so a row created "active" stayed "active" forever,
   over-including rather than ever dropping out). Once tracking_status is
   genuinely live, a deregistered company correctly drops out of
   `"active"`, which would make seed-universe treat it as new and attempt
   to re-seed it. Fix: add a new status-agnostic method,
   `get_known_ciks(engine) -> list[int]` (`SELECT cik FROM mdm_company`, no
   `WHERE` at all) to `universe.py`, and swap this one call site from
   `_get_mdm_tracked_ciks("active")` to it — matches the real semantic
   intent ("already onboarded" means "a row exists," not "currently
   active") without requiring this call site to enumerate or maintain the
   `tracking_status` enum.

This closes the map's last open design question. The route from here to
the [MDM Tracking-Status Sync](../map.md) destination is now fully
specified — implementation can proceed without further architecture
debate.
