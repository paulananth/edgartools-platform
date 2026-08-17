# 05 — Route seed-universe's novelty detection through MDM, not silver

Type: grilling
Status: resolved
Blocked by: 01, 03 (both resolved)
Blocks: none (implementation-ready; not yet built)

## Question

Given ticket 04's streaming fix already resolves the acute OOM risk in
`_hydrate_silver_database_from_storage`, what concrete, measurable benefit
does a narrow-read mechanism still deliver for `seed-universe` specifically,
and what's the minimal design to ship it?

## Answer

The destination changed twice during this ticket's live discussion, away
from `httpfs` entirely:

**Round 1 (rejected by user):** `httpfs` remote `ATTACH (READ_ONLY)` against
canonical `silver.duckdb`, narrowed to `seed-universe`'s read. User: "not
interested in adding httpfs."

**Round 2 (superseded by round 3):** split a small "company-metadata"
cluster (`sec_company`, `sec_company_ticker`, `sec_company_sync_state`,
`sec_source_checkpoint`, legacy `sec_tracked_universe`) out of canonical
`silver.duckdb` into its own small companion file, since inspecting all
~10 existing call sites of `sec_company_sync_state`
(`mdm/coverage.py`, `mdm/pipeline.py`, `mdm/cli.py`,
`silver_support/sharded_reader.py`,
`application/commands/migrate_silver_shards.py`,
`scripts/build_relationship_release_manifest.py`) showed every one either
reads it standalone or joins it only with other company-scale tables --
never in the same query as a filing-scale content table (`sec_thirteenf_holding`,
`sec_financial_fact`, etc.). DuckDB natively supports attaching multiple
database files in one connection and querying across them, so this isn't
actually blocked by the blast-radius concern the map's "Out of scope"
section originally raised against full table isolation.

**Round 3 (the actual resolution):** the user's key correction --
**MDM is the system of record for company information, even though it is
mechanically downstream of silver** (`mdm/cli.py:1064-1068`'s own docstring:
"Warehouse `seed-universe` remains the single writer of ticker/sync state.
MDM imports that state from silver"). `MdmCompany`
(`edgar_warehouse/mdm/database.py:224-242`) already mirrors exactly what
`seed-universe`'s novelty check needs: a unique, indexed `cik` column plus
`tracking_status`, in Postgres -- small, fast, no duckdb file involved at
all.

**Design:** `seed-universe`'s "is this CIK already tracked" check moves from
a silver point-lookup (`db.get_company_sync_state(cik) is not None`) to a
query against MDM's `mdm_company.cik` (indexed, Postgres). CIKs MDM already
knows about skip straight past -- zero silver/duckdb touch. CIKs MDM
doesn't know about are the candidate-new set, and only that (normally
small) set drives the silver write.

**Correctness requirement, not optional:** MDM's copy is fed by a *prior*
run's silver write (`MdmSeedUniverse` imports right after `SeedUniverse` in
the same `load_history` execution, so within any single run MDM always
reflects the *previous* run's state, never the current one's own writes
yet). That means MDM's "not found" can be a false negative for a CIK that
silver already tracks but MDM hasn't re-imported yet. Today,
`_seed_silver_tracking_status`'s existing gate
(`if db.get_company_sync_state(cik) is not None: continue`) is safe only
because it checks the *same* store it's about to write to. Swapping that
gate to check MDM instead reopens a real clobber risk:
`upsert_company_sync_state`'s `ON CONFLICT (cik) DO UPDATE SET
tracking_status = excluded.tracking_status` (`silver_store.py:3437-3460`)
unconditionally overwrites `tracking_status` on conflict -- exactly the
hazard `_seed_silver_tracking_status`'s own comment warns about ("Existing
rows keep their current status so paused or completed companies are not
accidentally reactivated by discovery"). If MDM's stale view lets a
silver-tracked CIK through as "candidate new," the current upsert would
silently regress it back to `bootstrap_pending`.

**Correction made during implementation:** no new DB method was actually
needed. `_seed_silver_tracking_status` -- the function that runs on
`universe_rows` (the post-MDM-filter candidate set) -- already has its own
per-CIK guard, `if db.get_company_sync_state(cik) is not None: continue`,
which checks *silver directly*, not MDM. Left unchanged, this guard already
provides exactly the protection this ticket worried about: if MDM's stale
view lets an already-tracked CIK through the (new) MDM-based `active_ciks`
filter, this silver-level check still catches it before
`upsert_company_sync_state` would be called, so its unconditional
`tracking_status` overwrite is never reached for that CIK. MDM staleness
can at most cause a wasted existence check, never a clobbered status.

**Important scope correction:** this does *not* eliminate silver's hydrate
for `seed-universe` -- `_execute_warehouse_bronze_capture` unconditionally
hydrates canonical `silver.duckdb` before any command-specific logic runs
(ticket 04 made that hydrate cheap via streaming; it did not remove it), and
`seed-universe` still writes to silver via `seed_company_sync_state_bulk`
(inside `_sync_reference_data`) regardless of this change. What this ticket
actually achieves is routing the *active-CIK exclusion filter* specifically
to MDM (the system of record) instead of a silver query -- a more accurate,
system-of-record-driven `universe_rows` set, not a further memory/hydrate
reduction beyond what ticket 04 already delivered.

## Verdict

Implemented (PR #394, merged into `main`): `seed-universe`'s active-CIK
filter now calls `_get_mdm_tracked_ciks("active")` (an existing helper,
already required via `MDM_DATABASE_URL`) instead of `db.get_active_ciks()`.
`_seed_silver_tracking_status` is unchanged and remains the correctness
safety net. `seed_universe_filtered`'s `skipped_silver_active` field renamed
to `skipped_mdm_active`. New test:
`tests/unit/test_seed_universe_mdm_active_filter.py`, which uses a real
`SilverDatabase` disagreeing with the mocked MDM response to prove the
filter genuinely reads from MDM. Full suite green (1469 passed). This
supersedes both the `httpfs` and small-metadata-file directions explored
earlier in this same ticket -- neither is needed.

**Deployed and live-verified (2026-08-10):** built/pushed a fresh warehouse
image (digest `sha256:88096fefd28bcfa2fd6f7787787761d7eb2604a46afb97ffe48f4b434ad08585`)
and redeployed to prod in parallel with task #35's in-flight execution --
safe, since Step Functions snapshots a state machine's definition at
execution start, so a mid-flight redeploy never affects an already-running
execution. Verified via an isolated `seed-universe --limit 50` ECS task
(`edgartools-prod-large`, matching PR #391's established profile for this
command -- an initial attempt against `edgartools-prod-medium` OOM'd,
self-inflicted, not a regression). Live CloudWatch confirmed the real code
path: `mdm_sql_started`/`completed` shows a genuine
`SELECT mdm_company.cik FROM mdm_company WHERE tracking_status IN
('active')` against Postgres (62,362 rows, 558ms), followed by
`seed_universe_filtered` with the new `skipped_mdm_active` field
(`total_ciks=7998, new_ciks=963, skipped_mdm_active=62362`). Exit code 0.
