# Sequence the migration from the current live pipeline to the decoupled architecture

Type: grilling
Status: resolved
Blocked by: (none)

## Question

Every element of the target architecture is now locked: message substrate
(S3→SNS→SQS, [ticket 02](02-research-messaging-substrate-options.md)),
event granularity (per-accession, [ticket 04](04-decide-event-granularity.md)),
silver's write model (DuckDB, generalized reducer,
[ticket 09](09-decide-silver-write-storage-target.md)), gold compute
location (Python, unchanged, [ticket 08](08-decide-gold-compute-location.md)),
MDM's role (async, system of record,
[ticket 06](06-decide-mdm-role-in-new-architecture.md)), graph sync's role
([ticket 10](10-decide-graph-sync-role-in-new-architecture.md)), company
discovery ([ticket 11](11-finalize-company-discovery-event-flow.md)), and
the completeness watermark
([ticket 07](07-decide-completeness-watermark-signal.md)).

This map's Destination named migration sequencing as part of "done" but
deferred it as fog until the target shape existed. It exists now. Decide:

1. **Cutover shape**: big-bang (replace `load_history`'s synchronous chain
   in one deploy) vs. phased (e.g. bronze-capture decoupling first, then
   silver, then gold, each validated in production before the next) vs.
   parallel-run (new architecture shadows the old one, compared, before
   cutover)? This repo's own precedent — the stage0-stage1-consolidation
   and state-machine-consolidation maps both this session — used staged,
   validated rollouts with rollback snapshots; is that the model here too,
   or does the scale of this change (replacing the core pipeline shape,
   not consolidating within it) warrant something more conservative?
2. **In-flight executions**: this repo has a live, multi-day
   `load_history` execution pattern (this session watched one run for
   over 24 hours). Step Functions `UpdateStateMachine` doesn't affect
   already-running executions (confirmed this session, live). Does the
   new architecture need to coexist with in-flight old-shape executions
   during migration, or does cutover require draining/completing all
   in-flight runs first?
3. **Order among bronze/silver/gold/MDM/graph**: does decoupling have to
   proceed in dependency order (bronze first, since everything reads from
   it), or can pieces be decoupled independently and integrated
   incrementally (e.g. gold's delivery mechanism goes event-driven while
   silver is still produced synchronously)?
4. **Rollback**: what's the fallback if the new architecture underperforms
   or misbehaves in production — full revert to the synchronous chain, or
   a narrower per-component rollback?

## Answer

**Phase 0 (isolated testing) for the silver async reducer specifically,
then a live phased cutover in dependency order — reject both big-bang and
full parallel-run.** Decided 2026-08-11.

**Phase 0 — validate the silver async reducer in isolation before any
live cutover begins.** This is the highest-risk, most novel piece of new
engineering on this map — [ticket 01](01-research-silver-duckdb-concurrent-write-model.md)'s
own accepted-risk caveat (cost-at-scale vs. Snowflake `MERGE` at real
event frequency, never measured) lives here, and [ticket 09](09-decide-silver-write-storage-target.md)'s
generalization of a one-shot reducer to fire per-event is genuinely new
behavior, not a reuse of something already proven at this granularity.
Test against synthetic/replayed events, not live production data:
- Unit tests for the ETag-guard extraction (`stage_and_promote`, already
  scoped as Extract Function in ticket 09's Answer).
- Integration tests replaying synthetic per-event deltas against a test
  DuckDB/S3 setup, confirming the merge is correct and safe regardless of
  delivery order or duplicates — SQS gives neither ordering nor
  exactly-once delivery (per [ticket 04](04-decide-event-granularity.md)'s
  chosen substrate), so the reducer must be provably order-independent and
  idempotent before it ever sees live traffic, not merely assumed to be.
- This is categorically different from a parallel-run against shared
  production state (rejected below) — isolated testing touches no live
  data, so it carries none of the dual-writer hazard a shadow run would.

**Live cutover, once Phase 0 passes: phased, in dependency order — reject
big-bang and full parallel-run.**
1. **Bronze** first — everything else reads from it; decoupling it changes
   the least (bronze capture logic itself is unchanged, only the direct
   silver-write coupling is removed).
2. **Silver** next (now validated by Phase 0) — gold and MDM both depend
   on it.
3. **MDM and graph**, independently or in either order — [ticket 06](06-decide-mdm-role-in-new-architecture.md)
   and [ticket 10](10-decide-graph-sync-role-in-new-architecture.md)
   established they're no longer coupled to each other.
4. **Gold's delivery leg** last — already partially event-driven today
   (S3→SNS→`SNOWFLAKE_RUN_MANIFEST_TASK`), the smallest remaining change.

**Rejected: big-bang.** The map's own Rollout stance already implies this
("not assumed to be a big-bang cutover"); phased-and-validated is this
repo's own proven pattern from two prior maps this session
(state-machine-consolidation, stage0-stage1-consolidation).

**Rejected: full parallel-run (shadow the new architecture against live
data, compare).** Running old and new pipelines concurrently against the
*same* live silver/gold state reintroduces the exact class of hazard
tickets 01/09 spent real effort characterizing and fixing — two
independent writers against shared state. A shadow run isn't a safety net
here, it's the same risk with extra steps. Isolated Phase 0 testing gets
the pre-production confidence a shadow run would have provided, without
the hazard.

**In-flight executions: coexist, don't drain.** Confirmed empirically this
session — Step Functions `UpdateStateMachine` doesn't affect
already-running executions (retry5 kept running unaffected through two
live deploys this session). New async infrastructure deploys additively;
cut-over workflows pick up the new shape on their next invocation;
anything already running finishes on its original definition.

**Rollback: per-component, not whole-system revert.** The architecture is
decoupled by design; rollback should be too. If silver's async reducer
misbehaves post-cutover, revert just that piece back to synchronous while
bronze's decoupling stays live. An all-or-nothing rollback would force
unwinding stages that were working fine, contradicting the point of
decoupling them.

**Constraint carried from the map's locked cost stance:** no phase of this
migration — including Phase 0's test infrastructure — introduces
always-on compute. Phase 0's integration tests run on-demand (CI/local, or
a triggered task), not as a standing service.

## Phase 0 executed (2026-08-11)

Built and tested in isolation, no live cutover, no new AWS infrastructure —
exactly the scope this Answer specified. Triggered by the user asking to
"introduce the decoupled architecture now" while a live `load_history`
backfill was mid-flight; scoped down to Phase 0 only (not the OOM fix, not
any cutover) via an explicit choice the user made from three options.

**1. Extract Function done (the concrete first item from
[ticket 09](09-decide-silver-write-storage-target.md)'s Answer):**
`StorageLocation.stage_and_promote()` (new method,
`edgar_warehouse/infrastructure/object_storage.py`) pulls the ETag-guarded
stage-then-promote sequence out of what were three independent hand-written
copies. `_publish_silver_database_if_remote` now calls it. More importantly,
this **closed ticket 01's identified gap for real**: `_publish_shard_if_remote`
previously called `upload_file` directly — a blind overwrite with *no*
version check at all — now uses the same guarded primitive, so a concurrent
writer to the same shard raises `PromotionConflictError` instead of silently
last-writer-wins. Deliberately no retry-on-conflict added there (unlike the
monolith path): each shard is single-writer-owned by design, so a conflict
signals a real invariant violation, not an expected race. 8 new tests
(`tests/unit/test_object_storage_stage_and_promote.py`,
`tests/unit/test_publish_shard_if_remote.py`).

**2. New module: `edgar_warehouse/application/silver_event_reducer.py`** —
generalizes `identity_refresh_publication.py`'s isolated-producer +
single-reducer pattern from one-shot-per-run to per-event, per this ticket's
Answer. `reduce_silver_events()` takes a list of already-verified
`AccessionDelta` (accession_number, storage-relative delta path, sha256) and
merges them into canonical in one call — no manifest-completeness
precondition, since there's no "run" concept anymore: every event is
independently mergeable. Reuses the exact same `merge_candidate_into_canonical`
+ `stage_and_promote` + bounded-retry-on-conflict machinery as the existing
reducer.

**3. The actual Phase 0 deliverable — proof, not assumption, that this is
order-independent and duplicate-safe:**
`tests/application/test_silver_event_reducer_idempotency.py` runs the
**real** `merge_candidate_into_canonical` against **real** DuckDB databases
(via `SilverDatabase`, not a mock) and proves, against `sec_company_filing`
(business key: `accession_number` — exactly ticket 04's chosen event
granularity):
- Two independent accessions merged in either order converge to the
  identical canonical state.
- The same accession redelivered across three separate reducer calls (SQS
  at-least-once) produces exactly one row, never three.
- A correction with a strictly newer `last_synced_at` authority value wins
  over an earlier one, regardless of which one arrives first — proving the
  declared authority-column conflict-resolution contract survives the new
  per-event path, not just disjoint-key merging.
- 12 more tests (`tests/unit/test_silver_event_reducer.py`) cover the
  reducer's own orchestration — checksum verification, within-call dedup,
  retry-on-conflict exhaustion, first-ever-publish seeding — against a faked
  merge function, isolating that logic from the real merge's own correctness
  (proven separately above).

**Total: 20 new tests, full repo suite green (2058 passed, 4 skipped).**
Not wired to any queue, not deployed, no cutover of anything currently
running — `ticket42-task35-fulluniverse-retry5` kept running unaffected on
the old synchronous architecture throughout. Not yet committed as of this
entry.

**What Phase 0 deliberately did not do**, per the user's own scoping
decision this session: fix the `bootstrap-fundamentals` OOM currently
stalling the live backfill (a separate, already root-caused, unrelated
prerequisite — same task-profile-sizing recipe as the documented gold-build
memory fix), or begin any part of the live phased cutover (bronze first,
per this ticket's Answer). Both remain open, unstarted follow-ups.

**Open design question surfaced, not resolved, while doing this work:**
whether a stage/consumer producing zero results should itself be a
fail-closed condition is not covered by [ticket 13](13-decide-failure-retry-dead-letter-semantics.md)
(which settled DLQ/retry semantics per queue, not this). Worth grilling
before any live cutover — the old architecture's Catch-and-continue
behavior (a Map exceeding its tolerated failure threshold silently advances
to the next stage) is exactly the failure mode the current live backfill is
demonstrating, and the new architecture should have an explicit answer
before it inherits the same gap.
