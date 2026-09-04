# 01 — Decide the "Changed Since" Watermark Mechanism

Type: grilling
Status: resolved

## Question

The map decided the sync is diff-only (only CIKs whose `tracking_status`
changed since MDM's last sync get re-pulled), but
`sec_company_sync_state` has no column that cleanly means "tracking_status
changed at this time" — only `last_main_sync_at`, a broader "this row was
last touched" timestamp that isn't a reliable proxy (it changes on events
that don't touch `tracking_status`, and `seed_company_sync_state_bulk_if_missing`'s
insert-only path doesn't set it at all).

Decide: does this sync need a new dedicated column (e.g.
`tracking_status_changed_at`) added to `sec_company_sync_state` via a
migration, explicitly set only by `demote_company_sync_state_bulk` and
`seed_company_sync_state_bulk_if_missing` when `tracking_status` itself is
set or changes — or is there an acceptable cheaper alternative (e.g.
`last_main_sync_at` widened to always fire alongside a
`tracking_status` write, or MDM tracking its own last-synced CIK-count/
digest and diffing against a full read each time despite the "diff-only"
framing)?

Whichever mechanism is chosen also needs to answer: where does MDM's own
"last synced up to" watermark live — a new column/table on the bookkeeping
side that MDM reads, or a small table in MDM Postgres itself that
bookkeeping has no knowledge of?

## Answer

Settled via `/grilling` (2026-09-04), two decisions:

1. **Bookkeeping-side changed signal:** add a new, dedicated
   `tracking_status_changed_at` column (nullable `TIMESTAMPTZ`) to
   `sec_company_sync_state`, via a migration on the Bookkeeping Postgres
   store. Set it explicitly — and only — at the real transition points:
   - `upsert_company_sync_state`'s caller in
     `edgar_warehouse/application/warehouse_orchestrator.py` (currently
     lines ~5354-5368): whenever the computed `tracking_status` differs
     from `existing_state.get("tracking_status")`, pass the new column
     alongside (not on every call — `last_main_sync_at` already proved
     that "stamp on every call" is the wrong shape, since it fires on
     ordinary re-syncs that don't move `tracking_status` at all).
   - `demote_company_sync_state_bulk`
     (`edgar_warehouse/bookkeeping/store.py:925`): set it to `demoted_at`
     unconditionally, since a Form 15 deregistration is by definition a
     real `active -> deregistered` transition every time this is called.
   - `seed_company_sync_state_bulk_if_missing` deliberately does **not**
     set it — it never changes `tracking_status` for an existing row
     (`ON CONFLICT DO NOTHING`), and a brand-new row's initial status
     isn't a "change" MDM needs to diff against; MDM's own bulk
     enrollment path (`mdm seed-universe`) already reads new rows
     directly, not through this diff.
   Rejected: widening `last_main_sync_at` (already shown imprecise — it's
   a general "touched" timestamp, not a "status changed" signal, and
   isn't set at all by the insert-only seed path); abandoning diff-only
   for a full count/digest comparison (reintroduces exactly the
   full-table-scan cost this same session's `claim_discovery_ciks` /
   `seed_company_sync_state_bulk_if_missing` fixes were built to
   eliminate, and directly contradicts the map's own diff-only
   granularity decision).

2. **MDM's own watermark location:** a small table in **MDM Postgres**
   itself (e.g. a single-row `mdm_sync_watermark`, or a column on an
   existing MDM-side state table), holding the last
   `tracking_status_changed_at` value MDM has consumed from bookkeeping.
   Bookkeeping stays a pure source of truth with zero knowledge of, or
   responsibility for, tracking any consumer's read progress — matching
   the existing precedent already live in
   `edgar_warehouse/mdm/database.py`: `MdmPublicationRequest.
   committed_watermark` (line 1012) and `MdmGraphGeneration.
   committed_watermark` / `MdmGraphPartition.mdm_watermark` (lines 1073,
   1132) both already have MDM tracking its own sync progress against
   external input entirely within its own schema. Rejected: a
   bookkeeping-side column/table tracking what MDM has consumed — no
   other bookkeeping consumer today gets this treatment, and it would
   couple bookkeeping's schema to one consumer's read cadence.

This closes both open questions Ticket 01 was scoped to — Ticket 02
(Mastering integration point + method signatures) is now unblocked.
