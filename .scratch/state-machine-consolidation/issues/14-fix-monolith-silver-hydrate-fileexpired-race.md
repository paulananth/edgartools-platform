Type: task
Status: open, unclaimed

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

_(pending)_
