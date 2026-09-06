Type: grilling
Status: claimed

**Spawned by:** [Ticket 09 — Retire superseded document-loading machines](09-retire-superseded-document-loading-machines.md)'s deferral (2026-09-05): `bronze_seed_silver_gold`'s default path was confirmed to still be install.sh's live, documented "canonical one-click path for cold-starting or recovering an environment's silver/MDM/gold from a bronze snapshot" (`{"batch_size": 100, "release_mode": false}`), directly contradicting the ticket's original confirmed-unused premise for that one machine. The user chose to defer rather than retire-and-break or redesign `install.sh` in the same pass.

## Question

What is `bronze_seed_silver_gold`'s default path's actual fate — retire it (and redesign `install.sh`'s cold-start/recovery path onto something else), keep it as-is permanently, or fold it into a different consolidated shape?

Context to bring into the conversation:

- `install.sh` triggers this machine directly by name for cold-start/recovery — any retirement decision has to say what replaces that call, not just delete it.
- [Ticket 07](07-collapse-mdm-tail-to-a-single-deployed-machine.md)'s original design for this machine (rewiring its tail onto the new single deployed MDM machine) was paused and is now considered moot, per Ticket 08's resolution: `mdm reconcile-backstop` already independently serves the one capability (unbounded full-universe mastering) that design existed to preserve. Confirm this is still true before assuming it settles the question.
- The machine's separate "strict release mode" branch (`{"release_mode": true}`) is explicitly out of scope here — Ticket 07 already decided it stays untouched, not reopened by this ticket.
- Live execution history for the default path (last checked as part of Ticket 09) should be re-verified before deciding — confirm via `aws stepfunctions list-executions` whether `install.sh`'s cold-start path has actually been exercised recently, not just documented as callable.

Use `/grilling` and `/domain-modeling` per this map's convention — this is a real product decision (whether to keep, retire, or redesign a documented operational recovery path), not mechanical.

## Answer

_(pending)_

## Fresh evidence (2026-09-06)

The machine was renamed `bronze_seed_silver_gold` → `one_click_data_refresh`
in the interim (naming-only, `edgartools-prod-one-click-data-refresh`; the
old ARN was deleted, not aliased — AWS Step Functions has no in-place
rename). Its default path (`{"batch_size": 100, "release_mode": false}`)
was run live this morning (`one-click-data-refresh-verify-1788697757`,
08:29:19–10:41:34 ET) — the first execution under the new name, and it
failed the same way its predecessor chronically did:
`States.ExceedToleratedFailureThreshold` on the "Clean and Merge Filings"
Map (`toleratedFailurePercentage: 0.0`, so any single item failure aborts
the whole run — 2 failed / 19 aborted / 33 succeeded out of 739 items
before the threshold tripped).

**This time the root cause is concrete, not just statistical.** Both
failed `bootstrap-batch` items crashed identically:
`s3fs.utils.FileExpired: [Errno 16] The remote file corresponding to
filename .../silver/sec/silver.duckdb and Etag "..." no longer exists`,
raised from `_publish_silver_database_if_remote`'s
`context.storage_root.download_file(...)` call
(`warehouse_orchestrator.py:1199`) — an ECS task's cached S3 read handle
went stale mid-download because the canonical `silver.duckdb` object was
replaced by a concurrent writer between the handle's open and its read.

**Confirmed via live execution timestamps: `daily_incremental`'s own
scheduled run (`edgartools-prod-daily-incremental-refresh`, `cron(0 12 ? *
MON-SAT *)` = 8am ET) was running concurrently the entire time** —
08:00:36–10:44:07 ET, almost exactly overlapping this
`one_click_data_refresh` attempt (08:29:19–10:41:34 ET). Two independent
pipelines were hydrating/publishing the same canonical `silver.duckdb`
monolith at the same time — the same *family* of bug as this map's own
documented "Shard-publish promotion-race" fix (CLAUDE.md), but that fix
covers the **shard** publish path's write-side conflict
(`PromotionConflictError`, already retried); this is the **monolith**
path's **read**-side race (`FileExpired` on download), previously
unfixed and, as far as this investigation found, never even
characterized before today.

**This changes the shape of the decision, not necessarily the answer:**
the historical ~3.3% success rate (61 executions, 2 SUCCEEDED) was
previously unexplained noise; today's evidence suggests at least one real,
fixable, non-hypothetical cause. Worth asking, before finalizing
retire/keep/redesign: how many of the historical failures would this one
fix (avoid same-time overlap, or make the monolith hydrate read
retry-on-`FileExpired` the way the shard path already retries its own
conflict) actually resolve, versus how many were something else entirely?

**Q2 follow-up (2026-09-06): historical failure-cause distribution is
mostly unrecoverable, but the one data point that IS recoverable is
stronger than first framed.** The old machine's Step Functions execution
records are gone (deleted on rename, `StateMachineDoesNotExist` confirmed
live), and `/aws/ecs/edgartools-prod-warehouse`'s CloudWatch log retention
is only **7 days** — so no log-level reconstruction of the historical
~44-FAILED-execution pattern is possible either. What IS recoverable: a
`filter-log-events` sweep of the full 7-day retention window for
`FileExpired` returned **76 log lines across ~38 distinct ECS task
streams — all of them inside this one morning's single execution**, none
in the days before it (there were no other `one_click_data_refresh`/
`bronze_seed_silver_gold` executions in that window to compare against).

That reframes the earlier "concurrent-with-daily_incremental" hypothesis:
this isn't a rare collision that happened to strike once — it recurred
roughly every ~2 minutes throughout the first ~77 minutes of this one run
(consistent with the Map's `aborted: 19` count, and possibly with more of
the `succeeded: 33` also having hit-and-recovered from it, not just the 2
that finally exhausted retries). At `MaxConcurrency: 20`, this rate is at
least as consistent with the 20 concurrent `bootstrap-batch` workers
racing **each other's own** periodic hydrate/merge/republish cycles
against the same canonical `silver.duckdb` as it is with
`daily_incremental`'s overlap — the two candidate causes are not
distinguished by this evidence (both were active the whole time), and
telling them apart would need CloudTrail S3 data-event correlation this
investigation didn't attempt. Either way, the practical conclusion is the
same: this is a frequent, systemic failure mode of the monolith hydrate
path under concurrent writers, not an unexplained rarity — see
[Ticket 14](14-fix-monolith-silver-hydrate-fileexpired-race.md) for the
follow-up characterization/fix work this spawned.
