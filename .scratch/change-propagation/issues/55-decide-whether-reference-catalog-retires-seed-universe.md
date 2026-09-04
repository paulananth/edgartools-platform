# 55 — Decide whether reference_catalog retires warehouse seed-universe

Type: grilling

Status: resolved

## Question

Now that the gated/ledger acquisition path exists (this map), why do we
still need warehouse `seed-universe`? Does `reference_catalog` (Ticket 23)
make it redundant, and if so, should this map decide to retire it?

## Live evidence (2026-09-02)

`seed-universe`'s real dispatch (`warehouse_orchestrator.py:2056-2125`) does
five distinct things, not one:

1. **Raw SEC fetch** — `_sync_reference_data` fetches `company_tickers`/
   `company_tickers_exchange` and writes `sec_company_ticker` silver rows.
2. **Bulk sync-state seed** — `_sync_reference_data` (when
   `seed_company_sync_state=True`) calls
   `bookkeeping.seed_company_sync_state_bulk([cik, ...])`
   (`warehouse_orchestrator.py:5480`) — bulk-inserting tracking rows into
   the **Bookkeeping** Postgres store's `sec_company_sync_state` table for
   every discovered CIK.
3. **MDM-active dedup** — filters the raw ticker universe down to CIKs not
   already `active` in MDM (`_get_mdm_tracked_ciks("active")`), so already-
   bootstrapped companies aren't re-seeded.
4. **Tracking-status assignment** — `_seed_silver_tracking_status(...,
   tracking_status="bootstrap_pending")` (line 2110), which also writes
   into the Bookkeeping store's `sec_company_sync_state` table (per its own
   docstring: "DuckDB Retirement Cutover Ticket 14: tracking state now
   comes from the bookkeeping store").
5. **CIK-batch manifest write** — `_write_cik_universe_batches(...)`
   writes this run's own CIK batch file, surfaced as `cik_universe_path` in
   the command's metrics/result.

`reference_catalog` (Ticket 23) covers **only #1**. Its own Answer section
says so explicitly, in its "Deliberately not reproduced" note:
`_sync_reference_data`'s `seed_company_sync_state_bulk` side effect is "Ticket
20's Acquisition Universe seeding concern, not a Silver domain producer this
family's `required_producers` model can express... whoever cuts a
universe-seeding command over to this new family must decide independently
how/where that seeding happens." Nobody has yet.

Separately confirmed: `reference_catalog` has **not passed Decision 2** (the
Ticket 10 per-family side-by-side parity proof, mirroring Tickets 51/53's
`filing_artifact` harness) — [Ticket 27](27-contract-legacy-acquisition-bypasses.md)
names it explicitly among the families not yet cut over. So even the one
piece `reference_catalog` *does* cover has no live-proven parity with
`seed-universe`'s legacy fetch yet.

## The bigger finding: #2 and #4 are not new fog — they're Ticket 54

[Ticket 54](54-bookkeeping-sits-outside-postgresql-authority-and-change-tracking.md)
(open, unclaimed) already asks whether Bookkeeping's change-detection
tables — explicitly naming `sec_company_sync_state` among them — should be
functionally consolidated onto this map's Change Ledger, with
`daily_incremental`'s legacy captures as its motivating (only known, until
now) caller. `seed-universe` turns out to be a **second, independent
caller** writing into that exact same table via two different code paths
(`seed_company_sync_state_bulk` and `_seed_silver_tracking_status`). This
doesn't change Ticket 54's recommendation, but it broadens its evidence
base and its blast radius: whatever Ticket 54 decides about
`sec_company_sync_state`'s home affects `seed-universe`'s design too, not
only `daily_incremental`'s.

`seed-universe`'s #3 (MDM-active dedup, reads MDM Postgres) and #5 (CIK
batch manifest, writes S3) are genuinely separate from Ticket 54's
Postgres-consolidation question — no gated-path equivalent exists for
either, and neither is sharp enough yet to ticket (see Not yet specified).

## Decision (user-confirmed via AskUserQuestion)

**Not justified yet.** `reference_catalog` is a partial building block for
one of `seed-universe`'s five responsibilities, not a replacement for the
command. Retiring `seed-universe` needs, at minimum: Ticket 54's
Bookkeeping/Change-Ledger consolidation question resolved (for #2/#4), a
Decision-2 parity proof for `reference_catalog` against #1 (new
[Ticket 56](56-build-reference-catalog-capture-parity-harness.md)), and a
design decision for #3/#5 that doesn't exist yet. `seed-universe` stays as
the current, correct command in the meantime — nothing here changes its
behavior or its callers (`load_history`'s `SeedUniverse` state, the
standalone `edgartools-prod-seed-universe` machine).

## Correction (2026-09-02, same session): "five responsibilities" overstated it

User pushback: the original need was just the CIK universe, not five
separate things. Checked against git history and this is right.
`seed_universe_loader`'s docstring, unchanged since this repo's first
commit (`d8a4a2e9`, April 2026): "Returns one row per (cik, ticker) pair
with enough metadata to seed `sec_tracked_universe`." Fetch (#1) and
registration (#2/#4 — sync-state seed + tracking-status assignment) were
**one fused original purpose from day one** — discovering a CIK and
registering it as tracked were never separate concerns. #3 (MDM-active
dedup) was added later, 2026-08-10, `#394` "source seed-universe's
active-CIK filter from MDM, not silver" — a reprocessing-avoidance
optimization layered on afterward, not original scope. #5 (CIK-batch
manifest write) is similarly a later addition tied to `load_history`'s
own batching needs, not intrinsic to universe-seeding.

Sharper framing: there is **one real core need** (discover CIKs, register
them into tracked/sync state — still not reproduced by `reference_catalog`,
still = Ticket 54's scope) and **two genuinely separable later add-ons**
(#3, #5) that consume the already-produced CIK list as output and don't
care how it was produced. Those two were never blockers to this decision
and shouldn't have been listed alongside #1/#2/#4 as if co-equal — they
can be preserved verbatim as a thin post-processing step regardless of
what fetches/registers the CIKs underneath. This doesn't change the
Decision below (the core fetch+register need is still only half-covered
by `reference_catalog`), but it narrows what actually needs resolving:
just Ticket 54 (registration) and Ticket 56 (fetch parity), not five
fronts.

## Answer

No code change. `seed-universe`'s five real responsibilities are now
documented (this ticket), and the question of whether/how to retire it is
resolved into two already-actionable pieces: Ticket 54 (already open, now
carries seed-universe as a second piece of evidence) for the
sync-state/tracking-status responsibilities, and new
[Ticket 56](56-build-reference-catalog-capture-parity-harness.md) for
proving `reference_catalog` an equal-or-superset replacement for the raw
fetch. The MDM-active-dedup and CIK-batch-manifest responsibilities have no
ledger-gated design yet and aren't sharp enough to ticket — moved to this
map's Not yet specified section.

## Deliverable

- [x] Live evidence gathered: enumerated seed-universe's five real
      responsibilities from its actual dispatch code, not assumption
- [x] Confirmed reference_catalog covers exactly one of the five
- [x] Traced the sync-state/tracking-status gap to the already-open
      Ticket 54, rather than filing a duplicate design question
- [x] User decision captured (not justified yet)
- [x] Follow-up ticket filed for the one genuinely new, sharp piece
      (Ticket 56, fetch-layer parity harness)
- [x] Remaining fog (MDM-dedup/CIK-batch homes) recorded in Not yet
      specified rather than force-ticketed
