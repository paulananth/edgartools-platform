# Investigate silver DuckDB's current concurrent-write model

Type: research
Status: resolved
Blocked by: (none)

## Question

The whole premise of this map — independent, message-driven silver
consumers reacting to bronze-write events — implies multiple concurrent
silver-ingestion workers, potentially processing different bronze events in
parallel. But this repo's CLAUDE.md repeatedly documents concurrent writes
to `silver.duckdb` as a solved-with-difficulty problem, not a free capability:
`load_history`'s `WindowedBootstrap` runs at `MaxConcurrency=1` *by design*,
specifically because a prior architecture (`bootstrap_batched`'s
`DISTRIBUTED` Map) hit a real `silver.duckdb` consistency race from
concurrent writers (see `bootstrap_batched`'s deletion rationale,
state-machine-consolidation wayfinder map ticket 03). Ticket-20's own
residual-holds incident describes an "N-way silver-promotion race."

But `docs/data-architecture.md`'s Storage Layout table also lists
`silver/sec/shards/shard-{shard_index}.duckdb` as an existing canonical
path, and CLAUDE.md's INSTITUTIONAL_HOLDS/EMPLOYED_BY incident mentions a
`ShardedSilverReader` (`edgar_warehouse/silver_support/sharded_reader.py`)
that exposes shards as a cross-shard `UNION ALL` **read** view.

Establish, from the actual code (not assumption):

1. Do silver DuckDB shards already support independent, safe **concurrent
   writes** (each consumer owns one shard file, writes to it without
   contending with any other writer), or is sharding today a read-only
   abstraction over data that was still written sequentially?
2. If shards are write-safe today, what determines shard assignment (per
   CIK? per batch? per consumer identity?) — and would that assignment
   scheme naturally fit "whichever consumer received this bronze-write
   event," or would it need redesigning?
3. What exactly was the `bootstrap_batched`/ticket-20 concurrent-writer
   race — was it a single-file DuckDB locking/corruption issue, a
   logical-consistency issue (partial merges visible to readers), or both?
   This determines whether sharding (per (1)) actually solves the *same*
   class of problem, or a different one.
4. Is there a canonical-silver "promotion"/merge step today (the reducer
   pattern seen in `identity_refresh_publication.py`) that any
   sharded-write design would still need, just re-triggered per-event
   instead of per-run?

This is the single most foundational technical constraint for this map —
if concurrent silver writes aren't safely possible without new machinery,
that reshapes the event-granularity (ticket 02) and consumer-boundary
(downstream) decisions materially.

**Scope note (2026-08-11):** confirmed live that today's `MaxConcurrency=1`
on `WindowedBootstrap` is a silver-write-safety constraint, not an SEC
rate-limit constraint — intra-window artifact fetch already runs at real
concurrency (`ThreadPoolExecutor`, default 5 workers), independently
rate-limited via `sec_client.py`'s bucket. Parsing (bronze bytes -> typed
records, CPU-bound, no correctness constraint) has no inherent reason to be
serialized either — only the final commit-to-`silver.duckdb` step does, per
the race this ticket investigates. Whether the fix is (a) making DuckDB
writes safely concurrent (this ticket's questions 1-2) or (b) moving the
write target off DuckDB entirely is [Decide silver's write/storage
target](09-decide-silver-write-storage-target.md), blocked on this
ticket's findings.

## Answer

Method: read `SilverDatabase` (`edgar_warehouse/silver_store.py`, 4360
lines) end to end for every shard/write/lock code path; traced the actual
shard-write call graph in `edgar_warehouse/application/warehouse_orchestrator.py`;
read `edgar_warehouse/application/identity_refresh_publication.py` and
`edgar_warehouse/infrastructure/object_storage.py` in full; read
`edgar_warehouse/application/sharding/shard_manifest.py` in full; and
walked the git history (`git log -S`, `git show`) of the commits that
introduced sharding (`921e011d`, PR #27), the `bootstrap_batched` ->
`load_history` redesign, the ticket-20 promotion-race fix (`a1f5d37b`,
PR #222), the Stage-14 cutover fixes (`995856c7`, PR #368), and the
shard-aware-scheduling decision (`b64f1de5`/`071db87b`, PR #372), plus the
matching `.scratch/` tickets those commits reference
(`state-machine-consolidation/issues/01`, `/03`;
`pipeline-throughput-architecture/issues/12`;
`release-readiness/issues/03`, `/20`, `/66`).

### 1. Is silver DuckDB sharding write-safe today, or read-only over sequentially-written data?

**Neither cleanly — it's a third thing: shard writes exist and are used in
production, but with materially weaker safety than the non-sharded path,
and are wired into only one of the pipelines that matter for this map.**

- `ShardedSilverReader` (`edgar_warehouse/silver_support/sharded_reader.py:32`,
  `:101-124`) is explicitly read-only: it ATTACHes every shard with
  `(READ_ONLY)` specifically "to prevent accidental writes to shard files"
  (`:32`) and its own module docstring requires "all listed shard files
  must be closed by their writers before this reader ATTACHes them"
  (`:53`) — i.e. it assumes writing and reading are temporally separate,
  not concurrent.
- The actual shard **write** path is `_execute_warehouse_bronze_capture`
  in `warehouse_orchestrator.py:448-518`. It is gated to exactly one
  command: `_using_shard_path` is only `True` when
  `command_name == "bootstrap-batch"` **and** `context.storage_root.is_remote`
  **and** a `cik_list` was passed (`:457-461`). `bootstrap-next` (the
  command `load_history`'s `WindowedBootstrap` actually calls, per
  `deploy-aws-application.sh:2430`) never takes this branch — it always
  falls through to `_hydrate_silver_database_from_storage` /
  `_open_silver_database` (`:515-518`), i.e. the single monolithic
  `silver/sec/silver.duckdb` object, exactly as CLAUDE.md's Phased
  Pipeline section already documents. **Sharding, as implemented today,
  has never been wired into the pipeline this map's motivation
  (`load_history`'s multi-day runtime) is actually about.** It is used
  by `bootstrap-batch`, which backs the separate, already-parallel
  `silver_mdm_gold`/`bronze_seed_silver_gold` reprocessing pipelines
  (`--artifact-policy skip`, no new SEC calls — see CLAUDE.md's own
  "Key invariants" section).
- Where it is used, the actual write mechanism (`_publish_shard_if_remote`,
  `warehouse_orchestrator.py:1212-1254`) is a **plain, unconditional
  `context.storage_root.upload_file(...)` stream-copy**
  (`object_storage.py:151-166`) — no ETag/version check, no read-modify-
  merge against the prior shard content, no conflict detection of any
  kind. Contrast this with the monolith publish path
  (`_publish_silver_database_if_remote`, `warehouse_orchestrator.py:980-1063`),
  whose own docstring states the *design intent* explicitly: "the merged
  result is uploaded to an immutable staging key and promoted onto the
  canonical key only if canonical's version/ETag has not changed since it
  was read... A concurrent writer... raises `PromotionConflictError`...
  instead of silently last-writer-wins." Shard writes get none of that —
  a second writer to the same shard file, if it ever raced the first,
  would silently clobber it with no error and no merge, a genuine
  last-writer-wins hazard.
- `SilverDatabase._shard_advisory_lock` (`silver_store.py:1154-1170`,
  `flock`-based, used by `stage_submission` at `:1727`) does **not**
  close this gap for the cross-task case that matters here: it locks a
  local file path (`f"{self._path}.lock"`) on the filesystem the process
  is running on. Each `bootstrap-batch` ECS task hydrates its shard into
  its own container's local `/tmp` (`open_silver_shard`,
  `silver_support/session.py:19-41`, "accepts an already-resolved local
  filesystem path") — separate containers have separate filesystems, so
  this lock can only serialize writers *within one process/container*
  (e.g. concurrent threads), never across the concurrent ECS tasks that
  `BatchSilver`'s `MaxConcurrency` actually spins up. There is no
  distributed lock, and no ETag guard, on the shard-upload step.
- What keeps this from causing observed data loss today is **scheduling
  avoidance, not a concurrency-control mechanism**: CIK-range shard
  assignment (see Q2) plus round-robin batch interleaving
  (`_interleave_round_robin`, `warehouse_orchestrator.py:5078-5089`,
  landed via ticket 12/PR #372) keeps concurrent Map slots pointed at
  *different* shard files most of the time. This was empirically
  stress-tested, not just designed: at `MaxConcurrency=16` against 4
  shards (guaranteeing ~4 tasks per shard by pigeonhole), a live prod run
  completed 216 batches with **zero** `PromotionConflictError`s and no
  reported data loss (`pipeline-throughput-architecture/issues/12.md`,
  "Addendum" section) — but that's an absence-of-observed-collision
  result from real task-launch jitter staggering same-shard writes in
  practice, not a proof that concurrent same-shard writes are safe by
  construction. (Also note: `PromotionConflictError` couldn't have fired
  on the shard path even if two tasks *had* collided — that error type
  only exists on the ETag-guarded monolith path; a real shard collision
  would show up as silently missing rows, not a raised, loggable
  exception, so "zero conflicts observed" is weaker evidence here than
  the ticket-12 write-up's phrasing implies for the monolith case.)

**Verdict for Q1: sharding is not a write-safe primitive today.** It is a
read-side abstraction (`ShardedSilverReader`) plus one narrow,
scheduling-dependent write path (`bootstrap-batch` only) that lacks the
conflict-detection the monolith path already has. Concurrent writes to
*different* shards are safe today only because collisions are avoided by
convention (CIK-range partitioning + round-robin scheduling), not because
each shard enforces single-writer-at-a-time or detects a lost update.

### 2. Shard assignment scheme — CIK-range, run-scoped or event-scoped?

Shard assignment is a **static, fixed-at-migration-time CIK-range
partition**, not per-batch or per-consumer-identity. `shard_manifest.py`'s
module docstring (`:6-19`) and `migrate_silver_shards.py:123-126` show 4
fixed bands (e.g. `shard_index=0` for `cik_min=0, cik_max=1_053_917`),
computed once via `approx_quantile` over `sec_company.cik`
(`pipeline-throughput-architecture/issues/12.md`) at `migrate-silver-shards`
run time (a one-time historical migration, run live in prod 2026-08-08)
and stored in a `shard-manifest.json` that both the reader
(`_hydrate_shard_for_window`, `warehouse_orchestrator.py:1147-1192`) and
writer (`_shard_partition_ciks`, `:5046-5075`) sides consult via
`band_for_cik(manifest, cik)` (`shard_manifest.py:119-155`, a pure
deterministic CIK -> shard_index lookup).

This **does not naturally fit** "whichever async consumer received this
particular bronze-write event": the mapping is a property of the CIK
itself (a fixed, pre-computed range table), not of which consumer, batch,
or event happened to process it. That's actually a reasonable property
for a message-driven redesign to *reuse* (a CIK-keyed router — "which
shard does this event's CIK belong to" — is exactly the kind of stable,
content-addressed routing key an event-driven consumer needs), but three
things would need to change, not just be adopted as-is:
1. The manifest is currently static and 4-way (chosen based on total CIK
   count at one point in time — see the "Not yet specified" fog note in
   `pipeline-throughput-architecture/issues/12.md`: "re-sharding to more
   shards... left as fog"). A message-driven design scaling consumers up
   and down would need shard count to be a live, re-partitionable
   parameter, not a one-time migration artifact.
2. Today's shard-count-vs-`MaxConcurrency` relationship is tuned by hand
   per pipeline (4, then 16, then 20 were each separately measured/decided
   — `pipeline-throughput-architecture/issues/12.md`) precisely *because*
   there's no real conflict-safety mechanism per Q1 — an event-driven
   design with elastic concurrency can't rely on "keep concurrency close
   to shard count and hope task-launch jitter saves you."
3. As found in Q1, the write step itself (`upload_file`, no ETag) would
   need the same conflict-detection the monolith path already has
   (`promote_staged`/`expected_etag`, or table/row-level locking) before
   "one consumer owns one shard, writes independently" is actually true
   rather than assumed.

### 3. What was the `bootstrap_batched`/ticket-20 race — corruption, logical-consistency, or both?

**Logical-consistency / lost-update, not filesystem corruption — and it
is explicitly designed to fail closed (a raised, retryable error) rather
than corrupt data**, confirmed from two related but distinct historical
incidents:

- **The `bootstrap_batched` -> `load_history` redesign** (root motivation
  for `WindowedBootstrap`'s `MaxConcurrency=1`): commit `921e011d` (PR #27,
  2026-05-22) introduced the exact code comment
  `state-machine-consolidation/issues/01` quotes: *"Replaces the original
  DISTRIBUTED Map over `cik_batches.jsonl` with an INLINE Map
  (MaxConcurrency=1) over `cik_windows.jsonl`... Sequential windows ensure
  silver.duckdb is consistent at each step"* (`deploy-aws-application.sh:1969-1971`,
  unchanged wording still live today). This same commit is also the one
  that introduced `ShardedSilverReader` and shard writing (Phase 09 of the
  same PR) — i.e. sequential-windowed bootstrap and sharding were designed
  *together*, but sharding was only wired into `bootstrap-batch`, not into
  the windowed path being fixed. Nothing in this commit, `state-machine-
  consolidation/issues/01` or `/03`, or CLAUDE.md's own account describes
  file-level DuckDB corruption or lock contention — the described failure
  mode throughout is "consistency," i.e. concurrent writers racing to
  read-merge-publish the same canonical object.
- **The concrete, reproduced mechanism** is documented directly in commit
  `a1f5d37b` (PR #222, 2026-07-22, "retry canonical publish on a lost
  promotion race") and `995856c7` (PR #368, "Stage 14 cutover fixes"):
  every concurrent Distributed Map batch (ticket 20's strict release Map,
  later also `bronze_seed_silver_gold`'s `BatchSilver`) independently
  reads canonical `silver.duckdb`, merges its own candidate into a local
  copy, and attempts to publish via an **ETag-guarded conditional
  promote** (`object_storage.py:15-37`, `PromotionConflictError`). When a
  second batch's canonical baseline had gone stale (another batch
  published first), the promote call raised `PromotionConflictError` and
  — before the `a1f5d37b` fix — nothing retried it, so "the first batch to
  publish always won and every other concurrently-finishing batch failed
  outright." This is a **lost-update / optimistic-concurrency conflict**,
  not corruption: the mechanism is explicitly built so a losing writer's
  work is *never silently dropped* — the staged candidate is preserved
  and the conflict is a loud, typed, retryable exception. The actual
  production cost was **operational** (retry-storm expense, not data
  loss): `995856c7`'s commit body records one batch needing "72
  `PromotionConflictError` retries in an 8-minute window... against a
  ~1.6GB canonical file," each retry re-downloading/re-merging/re-uploading
  the whole file — this cost, not any corruption, is what drove
  `MaxConcurrency` down (4->2 for ticket 20's strict Map, same fix later
  applied to `BatchSilver`) before sharding existed to shrink the
  per-conflict cost.
- **Whether sharding (Q1) fixes the same class of problem, a different one, or neither:**
  it addresses a *different* part of the same problem. The ticket-20 race
  was cost driven by canonical **file size** (O(canonical size) per
  conflict, regardless of how much content actually changed) — sharding
  directly shrinks that (`pipeline-throughput-architecture/issues/12.md`:
  "`silver_publish` dropped from 2-6+ minutes... to ~8.5s per batch"). But
  sharding, as wired today, does **not** carry over the ETag-guarded
  conflict-detection that made the *original* race safe-but-expensive
  rather than silently lossy (Q1) — so today's shards are cheaper to write
  but, unlike the monolith path, have no mechanism to detect a genuine
  collision if scheduling avoidance ever fails (MaxConcurrency exceeding
  shard count combined with unlucky timing, a re-sharding event mid-run,
  etc.). In other words: sharding solved the *cost* half of the original
  finding and inherited none of the *safety* half.

### 4. Is there a canonical-silver promotion/merge "reducer" step that a redesign would still need?

**Yes, and it already exists as live production infrastructure — just not
generalized to the main silver ingestion path.**
`edgar_warehouse/application/identity_refresh_publication.py`'s own module
docstring states its scope precisely: *"The Step Functions Map owns
execution of the individual CIK batches. This module deliberately owns
only the durable contract between those batches and the single reducer:
it never selects CIKs, fetches SEC data, or publishes the canonical
database"* (`:1-7`). Traced what it actually does:

- **Writes (N producers, fully parallel-safe):** each Map batch task calls
  `persist_batch_outcome` (`:129-156`), which writes two **immutable,
  batch-unique** objects — a delta DuckDB file at
  `identity_refresh/runs/{run_id}/batches/{batch_id}/delta.duckdb` and a
  matching `outcome.json` — via `storage_root.write_immutable_bytes`.
  Batch IDs are content-addressed (`batch_id_for_ciks`, sha256 of the
  sorted CIK list, `:78-85`), so there is **zero write contention between
  batches by construction**: every writer owns a unique path, not a
  shared one. This is a genuinely different (and stronger) safety property
  than either the monolith-direct-write or shard-write paths in Q1/Q3.
- **Reduce (exactly one process, sequential merge, ETag-guarded promote):**
  `reduce_identity_refresh` (`:186-356`) runs once, reads the one
  reference snapshot plus every batch delta (checksum-verified against
  the manifest, `load_complete_run_manifest`/`validate_complete_run_manifest`,
  `:159-183`, `:359-403`), merges them **sequentially** into canonical
  `silver/sec/silver.duckdb` (`:232`, same monolith path as the direct
  write case — the reducer does not target shards) via the identical
  `merge_candidate_into_canonical` + `promote_staged`/`expected_etag`
  mechanism as `_publish_silver_database_if_remote`, and retries on
  `PromotionConflictError` up to `max_attempts` (`:326-337`).
- **Is this live today?** Yes, but scoped narrowly: it backs
  `daily_incremental`'s bounded "Company Identity Refresh"
  (`Stage0CompanyIdentityBounded` -> N parallel batches ->
  `ReduceIdentityRefresh`, `deploy-aws-application.sh:3355-3423`,
  `:3596-3599`). It was **removed from `load_history`** in the
  stage0-stage1-consolidation map (ticket 02/04, comment at
  `deploy-aws-application.sh:2359-2386`) — not because the pattern was
  wrong, but because `load_history`'s `WindowedBootstrap` already writes
  the identical `sec_company*` rows as a byproduct of its own capture, so
  a second reducer pass over the same data was redundant work, not a
  safety requirement there.

So: **any sharded/concurrent silver-write redesign still needs a
promotion/merge step** — the open design question this raises for the
map is not "do we need a reducer," it's "does the reducer run once per
message/event (this ticket's premise) or is it still a periodic/batched
merge over a window of events." The existing reducer is architected as
one-shot-per-run (one manifest, one full set of expected batches, exactly
one final canonical promotion attempt sequence) — re-triggering it
per-event would need either a much higher promotion frequency against the
same ETag-guarded canonical object (reintroducing the Q3 cost problem at
higher frequency, unless paired with real per-shard writers) or a
rethink of "reduce" as an incremental/streaming operation rather than a
batch-closing one. Left as exactly the kind of decision ticket 09 (and
this map's granularity ticket 02) exists to make — not resolved here.

### 5. Scope-note re-verification: is `MaxConcurrency=1` about SEC rate-limiting or silver-write safety?

**Confirmed, independently, from primary sources — the scope note holds.**

- `deploy-aws-application.sh:2404-2413` (comment directly above the
  `WindowedBootstrap` Map definition): *"Mode is DISTRIBUTED, not INLINE...
  MaxConcurrency=1 still enforces one window at a time under DISTRIBUTED
  mode."* The Map's own `Comment` field, live in the generated ASL:
  *"Branch A ownership bootstrap (MaxConcurrency=1): one window at a time
  so silver/ownership/ is consistent"* (`:2435`), with `"MaxConcurrency": 1`
  at `:2436`. No SEC-rate-limit language anywhere in this state's
  definition or its surrounding comments (`:2388-2436`) — the stated
  reason is silver consistency, full stop.
- A second, independent piece of evidence for *why* it isn't a rate-limit
  concern: `deploy-aws-application.sh:2390-2392` notes that even Branch A
  and Branch B (fundamentals) of the *same* window are deliberately
  sequenced against each other, not run as two concurrent ECS tasks,
  because "Running two ECS tasks against the same S3-backed DuckDB
  artifact would race the hydrate/publish round trip and could drop
  whichever task published second" — a pure silver-object-contention
  concern, unrelated to SEC request volume (Branch B's fundamentals fetch
  and Branch A's ownership fetch are different SEC endpoints entirely).
- Intra-window artifact concurrency is real and already independently
  throttled, confirmed at the code level: `bronze_filing_artifacts.py:39-49`
  defines `_DEFAULT_ARTIFACT_FETCH_CONCURRENCY = 5`
  (`WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY`-overridable), and its own comment
  states *"pyrate_limiter's thread-safe Limiter... remains the real
  throughput ceiling regardless of pool size"* — the `ThreadPoolExecutor`
  dispatch is at `bronze_filing_artifacts.py:400`, explicitly scoped to
  "Real fetches run concurrently... no DuckDB access, since a single
  `SilverDatabase` connection is not safe for concurrent use (ticket 03)"
  (`:387-390`) — i.e. the concurrency is deliberately confined to the
  network-I/O phase and kept away from the DB-write phase entirely, inside
  a single window/task. The independent rate limiter is
  `edgar_warehouse/infrastructure/sec_client.py:26-37`: a `pyrate_limiter`
  `Limiter` over an `InMemoryBucket` sized "9 req/sec... matches
  `EDGAR_RATE_LIMIT_PER_SEC`" (`:27`) — a per-task in-process throttle,
  not something `MaxConcurrency` at the window level touches at all.
  This matches CLAUDE.md's own "Key invariants" caveat that this limiter
  "enforces per-task throttling but does not coordinate across ECS tasks"
  — i.e. raising window-level `MaxConcurrency` would need *its own*
  cross-task SEC-budget reasoning if it were ever raised, but that is a
  separate, not-yet-hit concern from the silver-consistency one that
  actually set it to 1 today.

## Verdict

1. **Sharding is not a write-safe primitive today.** It's a real,
   production-live optimization for one narrow pipeline
   (`bootstrap-batch`/`BatchSilver`), built on a plain unconditional file
   overwrite with no conflict detection, kept safe in practice only by
   CIK-range partitioning + round-robin scheduling that avoids same-shard
   collisions most of the time — not by any per-shard locking, versioning,
   or merge step. It has never been wired into `load_history`'s
   `WindowedBootstrap`/`bootstrap-next`, the actual pipeline whose
   `MaxConcurrency=1` this map's motivation is about.
2. **Shard assignment is a static CIK-range partition**, not per-event or
   per-consumer-identity. It's a reasonable routing key to reuse (CIK is a
   stable content-addressable property of every event this map would
   emit), but the manifest is a one-time migration artifact today, not a
   live/elastic partitioning scheme, and would need re-partitioning
   support plus the Q1 write-safety gap closed before "whichever consumer
   got this event, for this CIK's shard" is a safe design, not just a
   convenient one.
3. **The race was logical-consistency (lost-update/optimistic-concurrency
   conflict on the shared canonical object), not filesystem corruption —
   and the system is explicitly designed to fail closed, not corrupt,
   when it happens.** The `PromotionConflictError`/ETag mechanism
   (`object_storage.py`) guarantees a losing concurrent writer's work is
   preserved and retryable, never silently dropped, on the monolith path.
   The real production pain was retry-storm *cost* (O(canonical file
   size) per conflict), which is what motivated lowering `MaxConcurrency`
   historically and is exactly what sharding fixes — but sharding fixes
   only the cost dimension, not the safety dimension, and (per Q1) the
   shard-write path currently has *weaker* safety than the very
   monolith path this whole line of fixes was protecting.
4. **Yes — a canonical-silver promotion/merge reducer is required in any
   design, and one already exists and runs in prod today**
   (`identity_refresh_publication.py`, backing `daily_incremental`'s
   Company Identity Refresh): N producers write fully independent,
   content-addressed, immutable deltas (zero write contention by
   construction), and exactly one reducer process performs one sequential
   merge + ETag-guarded promote. This is architecturally the strongest
   existing precedent in this codebase for safe concurrent producers
   against DuckDB-backed silver. It is currently one-shot-per-run, not
   per-event — extending it (or an equivalent) to fire per-message is the
   real design gap for this map, not whether the pattern exists at all.
5. **Confirmed independently, not just re-asserted:** `MaxConcurrency=1`
   on `WindowedBootstrap` is a silver-consistency choice, explicit in the
   live ASL comment and code, unrelated to SEC rate limiting — which is
   already independently enforced per-task via `sec_client.py`'s
   `pyrate_limiter` bucket and already runs at real concurrency
   (`ThreadPoolExecutor`, default 5) for the artifact-fetch phase, kept
   deliberately isolated from the single, non-thread-safe DuckDB
   connection.

**For ticket 09 (and by extension 04/06/07): the evidence favors "fix
DuckDB concurrency," not "move the write target off DuckDB" — with one
important caveat.** This codebase already has two independently-proven,
safe patterns for concurrent writers against DuckDB-backed silver: (a) the
ETag-guarded merge-then-promote-with-retry mechanism, safe by construction
for any N concurrent direct writers to a shared object (used today at
`MaxConcurrency` values of 2, 4, and 20 in different pipelines without
data loss — only cost scales with N and file size); and (b) the
isolated-producer-plus-single-reducer pattern, which is a closer
architectural match for "many async message-driven consumers" than
anything else in the codebase and is already running in production. Both
are DuckDB-native solutions, not replacements for it. The one real gap
found in this investigation — shard writes lacking the ETag/merge
protection the monolith path already has — is a **fixable
implementation gap in the existing sharding code**, not evidence that
DuckDB itself can't support the concurrency this map needs; closing it
means giving `_publish_shard_if_remote` the same `promote_staged`/
`expected_etag` treatment `_publish_silver_database_if_remote` already
has, which is a bounded, scoped fix, not an architecture change.
**Caveat, stated plainly rather than papered over:** this verdict is about
technical feasibility, not about whether the *cost* profile of "always
merge/reduce sequentially against a growing DuckDB file" ultimately scales
better than Snowflake's native concurrent `MERGE` at whatever event
frequency ticket 02 lands on — that's a genuinely separate question (per
ticket 09's own framing, "(b)... would eliminate the DuckDB
write-serialization constraint entirely rather than needing to solve it")
that this ticket's evidence does not settle either way, since nothing
found here measured or modeled per-event reduce frequency against a
Snowflake-native alternative. What this ticket does settle is narrower but
load-bearing for ticket 09: the "DuckDB concurrent writes are fundamentally
unsafe / require exotic new machinery" premise in this ticket's own
question is not supported by the evidence — safe patterns already exist
and run in prod; what's missing is generalizing them, not replacing the
storage engine.
