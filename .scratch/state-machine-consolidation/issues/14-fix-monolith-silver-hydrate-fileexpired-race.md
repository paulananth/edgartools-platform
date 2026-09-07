Type: task
Status: resolved (2026-09-06) — no code change needed; see Answer below

**Spawned by:** [Ticket 11 — Decide bronze-seed-silver-gold default-path fate](11-decide-bronze-seed-silver-gold-default-path-fate.md)'s fresh evidence (2026-09-06): a live `one_click_data_refresh` execution (`one-click-data-refresh-verify-1788697757`, 08:29–10:41 ET) crashed with `States.ExceedToleratedFailureThreshold` after `s3fs.utils.FileExpired` errors recurred across ~38 distinct ECS tasks within that single run — a stale S3 read handle on the canonical `silver.duckdb` object, raised from `_publish_silver_database_if_remote`'s `context.storage_root.download_file(...)` call (`edgar_warehouse/application/warehouse_orchestrator.py:1199`), whenever the object gets replaced by a concurrent writer mid-download.

**Deliberately not decided/blocked on Ticket 11's retire/keep/redesign question** — this ticket tracks characterizing and (if the machine survives) fixing the underlying race, independent of what Ticket 11 decides. If Ticket 11 retires the default path outright, this ticket becomes moot and should be closed as out-of-scope rather than resolved.

## Question

Characterize the monolith `silver.duckdb` hydrate path's `FileExpired` race, and fix it if worth fixing:

1. **Distinguish the two candidate concurrent writers.** Today's evidence doesn't separate them: `daily_incremental`'s scheduled run (`cron(0 12 ? * MON-SAT *)`, 8am ET) was active the entire window, AND `one_click_data_refresh`'s own `MaxConcurrency: 20` Map means up to 20 `bootstrap-batch` workers are each independently hydrating/merging/republishing the same canonical file, so they could just as easily be racing each other. Use CloudTrail S3 data events (`PutObject`/`CompleteMultipartUpload` on the `silver/sec/silver.duckdb` key) correlated against the ~38 `FileExpired` timestamps to attribute each crash to a specific writer (`daily_incremental`'s task vs. a sibling `bootstrap-batch` task).
2. **If self-collision among the 20 concurrent workers is a real contributor:** this is the same *family* of bug as the already-fixed "Shard-publish promotion-race" (CLAUDE.md) and this map's own consolidation work, but on the **monolith** path's **read** side rather than the shard path's **write** side. Decide whether the fix is (a) retry-on-`FileExpired` at the download call site (mirroring `_publish_silver_database_with_retry`'s existing retry-on-conflict pattern, just for the read instead of the write), (b) serializing the hydrate step so only one worker downloads at a time (defeats the point of `MaxConcurrency: 20`), or (c) something else.
3. **If `daily_incremental` overlap is a real contributor:** decide whether a scheduling/operator-rule mitigation (documented in CLAUDE.md, added 2026-09-06 per this ticket's own spawning evidence) is sufficient, or whether an active guard (a cross-command lease, mirroring the existing `sec_fetch_active` lease) is warranted — this second question is explicitly what [Ticket 11](11-decide-bronze-seed-silver-gold-default-path-fate.md)'s own Q3 already deferred; don't duplicate that decision here, just note whether this investigation's findings should feed back into it.
4. **Log retention caveat:** `/aws/ecs/edgartools-prod-warehouse`'s CloudWatch retention is only 7 days — any live re-investigation needs to happen against a fresh reproduction (or CloudTrail, which retains longer), not by searching further back than 7 days.

**Done when:** the dominant cause (self-collision, `daily_incremental` overlap, or both) is identified with real evidence (not assumed), and either a fix is implemented + tested + deployed, or a documented decision to not fix it (e.g. because Ticket 11 retired the machine) is recorded here.

## Answer

**Dominant cause, with real evidence (not assumed): self-collision among
the monolith's own concurrent writers, not primarily `daily_incremental`
overlap — and the whole race is now moot regardless, structurally
eliminated as a side effect of [Ticket 10](
../duckdb-retirement-cutover/issues/10-atomic-write-path-cutover.md), which
landed live in prod *after* the crash this ticket investigates.**

**Step 1 (attribution) — CloudTrail was not viable, used equivalent
evidence instead.** `aws cloudtrail describe-trails` returns zero trails
account-wide (`trailList: []`) — no S3 data events (`PutObject`/
`CompleteMultipartUpload`) have ever been recorded for this bucket, at any
retention length; the ticket's proposed Step 1 method doesn't apply here,
not even in principle. Substituted with two things that were still fresh
within the 7-day CloudWatch retention window (today's date was still
2026-09-06 in ET when this was pulled):

1. **Clustering analysis of the 76 `FileExpired` log lines** (across 38
   distinct `warehouse-medium` ECS task streams, filtered from
   `/aws/ecs/edgartools-prod-warehouse` for the crashing execution's exact
   08:29–10:41 ET window): 39 unique failure timestamps group into **20
   clusters** spread roughly every 2–4 minutes across the 77-minute run,
   **12 of which have 2–4 tasks failing within a sub-second window of each
   other** (e.g. 4 tasks within 437ms at one point). A single external
   writer (`daily_incremental`, which publishes at most a handful of times
   over its own run) cannot produce 20 evenly-spaced clustered events with
   multiple simultaneous victims each — this pattern is the signature of
   many concurrent workers (`MaxConcurrency: 20`) each independently
   publishing on their own cadence throughout the run, each publish capable
   of invalidating several *other* in-flight readers at once.
2. **`daily_incremental`'s own execution window that same day**: it ran
   08:00:36–10:44:07 ET (`SUCCEEDED`) — essentially the *entire* crashing
   `one_click_data_refresh` execution's lifetime (08:29–10:41 ET) falls
   inside it, confirming the overlap was real and total, not partial. This
   doesn't rule daily_incremental out as *a* contributor, but the
   clustering shape above (20 evenly-spaced multi-task clusters) is not
   what a single external writer produces — it's better explained by the
   20-worker self-collision, with daily_incremental's overlap as, at most,
   a secondary/undistinguished contributor.

**Step 4 was moot before it needed answering.** By the time this
investigation ran, [Ticket 10](
../duckdb-retirement-cutover/issues/10-atomic-write-path-cutover.md) had
already been deployed to prod (warehouse task-def revision 272, registered
**2026-09-06T19:41:42-04:00** — confirmed via `describe-task-definition`,
several hours *after* the 08:29–10:41 ET crash this ticket investigates).
Reading the current code directly (not assuming from the ticket name)
confirms Ticket 10 retired canonical `silver/sec/silver.duckdb` as a write
target **entirely**, for both writers that used to touch it:

- `_publish_silver_database_if_remote` (`warehouse_orchestrator.py`) is now
  a permanent no-op — its own docstring: "canonical `silver/sec/
  silver.duckdb` [is] no longer a write target for any command."
  `bootstrap-batch`'s own comment at `warehouse_orchestrator.py:540` says
  it explicitly: "That contention no longer applies -- bootstrap-batch's
  real write target is the Snowflake landing zone (append-only, one
  Parquet file per run, no shared mutable object)."
- `reduce_identity_refresh` (`identity_refresh_publication.py`) — a
  *second*, independent writer to the same canonical object this
  investigation hadn't previously distinguished from the first — is
  likewise retired: "This reducer used to be a second, independent write
  path to that same canonical object... That race can no longer happen
  once nothing promotes, so the merge/stage/promote body... is retired
  with it."
- The shard-file write path (`_publish_shard_if_remote_with_retry`) has
  zero real callers anywhere in the codebase (confirmed via grep) — it was
  already dead before this investigation, per the same docstring.

Every remaining consumer of `_hydrate_silver_database_from_storage`
(the reconciliation tooling this session used directly for Ticket 11,
`silver_landing_historical_backfill.py`, `mdm/cli.py`'s fallback path) is
now read-only. `s3fs.utils.FileExpired` requires the underlying S3 object
to change mid-download — with no writer left anywhere, that precondition
cannot occur, so this specific race is structurally impossible under the
currently-deployed code, not just less likely.

**Decision, per this ticket's own "Done when" criteria: no fix
implemented, and none needed** — not because Ticket 11 retired the
machine (Ticket 11 remains `claimed`, undecided, as of this writing), but
because a separately-completed ticket (Ticket 10) already eliminated the
precondition as an intentional side effect of its own, unrelated scope.
Deliberately did **not** add defensive retry-on-`FileExpired` at the
`_hydrate_silver_database_from_storage` call site (the ticket's own
candidate fix (a)) — there is no live writer today for it to guard
against, and adding speculative protection against a scenario the current
code cannot produce is exactly the kind of premature protection this
repo's own conventions warn against. If a future ticket ever
re-introduces a writer to this object (e.g. resurrecting the shard-publish
path), that future change is the right place to add the read-side retry,
mirroring `_publish_silver_database_with_retry`'s existing pattern.

**Feeds back into [Ticket 11](
11-decide-bronze-seed-silver-gold-default-path-fate.md)'s open decision**:
the specific `FileExpired` failure mode that motivated this ticket is now
resolved regardless of what Ticket 11 decides about the machine's overall
fate — but this does not mean the machine's historical ~3.3% success rate
is now safe to assume fixed. Nothing in this investigation characterized
the *other* ~42 historical failures/aborts, which may have entirely
different causes unrelated to this specific race. Not re-run live to
confirm empirically (the user separately declined to run `one_click_data_
refresh` again in this same session, given its poor historical odds) —
whoever next runs it, as part of Ticket 11's resolution or otherwise,
should watch specifically for whether `FileExpired` still appears at all
(it shouldn't) versus what other failure modes remain.
