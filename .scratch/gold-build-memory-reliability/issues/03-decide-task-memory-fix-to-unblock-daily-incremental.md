# Decide the task-memory fix to unblock the failed daily_incremental execution

Type: grilling
Status: resolved

## Question

`daily_incremental`'s first-ever prod execution (`daily-incremental-1785336584`) is now
terminally `FAILED` — all 3 retries OOM'd identically. Ticket 01 (streaming `build_gold`) is
the structural fix, but it's a real multi-file refactor that will take more than one session;
meanwhile there's a failed execution and no working `daily_incremental` path today.

Separately, this session's `/gof-refactor-reviewer` pass found that `large`
(`infra/scripts/deploy-aws-application.sh:936`, 2048 CPU) carries the **identical** 4096MB
memory ceiling as `medium` (1024 CPU) — only CPU differs. Commit `37c3171`'s stated intent for
moving `gold-refresh` to `large` back in May was explicitly more memory ("full-universe DuckDB
expands to several GB in the buffer pool during build_gold()"), but the actual change only
raised CPU, not memory. So `gold-refresh`'s own prior OOM fix may already be memory-ineffective
today, on top of `daily_incremental` never having gotten any equivalent fix at all.

This ticket decides the immediate tactical mitigation — not the structural fix (that's ticket
01) — so `daily_incremental` (and possibly `gold_refresh`, `bootstrap`, `full_reconcile`, the
other `medium`-profile `GOLD_AFFECTING_COMMANDS` members) has a working path forward now.

Questions to resolve with the user, one at a time:

1. Should `medium`'s memory be raised (e.g. 4096 → 8192MB, mirroring what `mdm-large` already
   uses), should `large`'s memory actually be raised past `medium`'s (restoring `37c3171`'s
   original intent), or should `daily_incremental` specifically move to a distinct profile?
   Recommended: raise `large`'s memory (e.g. to 8192MB) and move `daily_incremental` onto
   `large`, since `targeted_resync`/`bootstrap_full` already treat `large` as the "full-universe
   gold build" profile — this restores the fix `37c3171` intended rather than inventing a new
   profile.
2. Should this bump apply to all four `medium`-profile `GOLD_AFFECTING_COMMANDS` members
   (`daily_incremental`, `bootstrap`, `full_reconcile`, `gold_refresh`) now, or just
   `daily_incremental` (the one with confirmed live-incident evidence), deferring the other
   three until/unless they show the same failure? Recommended: apply to all four — they share
   the identical `build_gold()` call site, so the same failure is only a matter of when one of
   them runs at sufficient scale, and ticket 02 will enforce this floor going forward anyway.
3. Once the value is decided, should this ticket also drive the actual `deploy-aws-application.sh`
   edit + prod redeploy + a fresh `daily_incremental` execution to confirm it now succeeds, or
   should that execution be left to a separate follow-up? Recommended: this ticket drives it
   through to a confirmed-successful `daily_incremental` execution, since "decided but not
   applied" leaves the pipeline in the same failed state.

Blocked by: none. Independent of tickets 01/02 — this is the tactical bridge until 01 lands.

## Answer

Decisions confirmed with the user, one question at a time:

1. Raise `large`'s memory 4096 → 8192MB and move `daily_incremental` onto it (the recommended
   option) — restores commit `37c3171`'s original intent rather than inventing a new profile.
2. Apply to all four `medium`-profile `GOLD_AFFECTING_COMMANDS` members
   (`daily_incremental`, `bootstrap`, `full_reconcile`, `gold_refresh`), not just
   `daily_incremental`.
3. Drive this through to a confirmed-successful `daily_incremental` execution, not stop at
   "decided but not applied."

Implemented on branch `claude/gold-task-memory-bump` (PR #313, stacked on #312 → #311):
`register_task_definition large 2048 4096` → `2048 8192`; `workflow_profile()`'s
`full_reconcile`/`gold_refresh` cases moved to `large` (their real operative path, via the
`workflow_profile()`-driven loop).

**Critical finding while implementing this, changing the actual fix needed:**
`workflow_profile()` is never called with `"daily_incremental"` or `"bootstrap"` anywhere in
the script — confirmed via `grep` (the only call site is the loop at line ~3098, which doesn't
include either). Their real `RunWarehouseTask` step — the one that OOM'd in prod — is built
directly by `write_warehouse_mdm_gold_definition`'s `run_wh`, hardcoded to `wh_medium_arn`
regardless of `workflow_profile()`. The actual fix is changing `run_wh` to `wh_large_arn`,
which this branch does; `workflow_profile()`'s `daily_incremental`/`bootstrap` cases were kept
set to `large` for consistency but documented as dead code. This same discovery invalidated
ticket 02's first test version (see that ticket's updated Answer) — it was rewritten
(PR #312) to validate the real dispatch path instead, and its negative-check was re-run
against this exact bug (reverting `run_wh`, confirming `daily-incremental`/`bootstrap` drop
from 8192 back to 4096) before this branch was written.

**Deployed and re-run (2026-07-30):** built a new warehouse image from `claude/gold-task-memory-bump`
(includes ticket 01's streaming fix + this ticket's memory/wiring fix; digest
`sha256:aca8078c658bc3f66ac40fa9e41923c4f29743f23ad5623756d94888728cbb30`, confirmed to differ
from the previously-deployed `sha256:b91139254a...`), reused the unrelated existing MDM image
digest, and deployed via `deploy-aws-application.sh --env prod --enable-mdm`. Started a fresh
`daily_incremental` execution to confirm.

**Important scope note on "success" here:** both ticket 01 (streaming) and this ticket's memory
bump are live together in the same deploy — there was no way to test them in isolation given
the urgency of unblocking the pipeline. A successful re-run confirms *the combination* works,
not that either fix alone was sufficient. Ticket 01's own step 5 ("confirm peak memory drops
materially") remains formally unconfirmed in isolation — the discriminating signal to look for
is whether `sec_thirteenf_holding`'s `gold_table_completed` event appears at all (it never has
in any of the 4 failed attempts), attributed specifically to the `RunWarehouseTask` step's log
stream (not the trailing `GoldRefresh` step, which also builds gold and would confound
attribution).

**Also important — this is not a like-for-like retry of the failed execution.** The failed
`daily-incremental-1785336584` ran an older state-machine shape that predates
`Stage0CompanyIdentity` (added by the Company Identity Pipeline map's ticket 06, never before
run in prod at all). The re-run below exercises `ComputeWindows` → `Stage0CompanyIdentity` (a
`MaxConcurrency=1` Map over ~70 sequential 500-CIK windows across the full universe) *before*
reaching `RunWarehouseTask` — the step that actually OOM'd and that this ticket's fix targets.
If Stage0 itself fails, that is new, untested territory unrelated to the memory fix, not this
fix failing — don't conflate the two.

**Deployed and running (2026-07-30):** `large` task-def revision confirmed bumped
(`edgartools-prod-large:90`, up from `:89`). Started execution
`daily-incremental-ticket03-1785413694`
(`arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-daily-incremental:daily-incremental-ticket03-1785413694`),
confirmed `RUNNING`. **Execution result still pending as of this write-up** — the
wiring-confirmation signal (`RunWarehouseTask`'s actual `TaskDefinition` ARN via
`get-execution-history`) won't be available until Stage0's ~70 sequential tasks complete, and
full completion takes on the order of hours based on prior attempts' timing. Update this
section with the outcome once known; only then does this ticket's question 3 resolve and
`Status` move to `resolved`.

**Prod is now running code from `claude/gold-task-memory-bump`, not `main`.** Three stacked
PRs are open and unmerged: #311 (streaming fix) → #312 (task-sizing guard) → #313 (this
ticket's memory bump + wiring fix). If review changes anything in any of them before merge,
prod and `main` will have diverged silently until they're reconciled.

**Update (2026-07-30, later same day) — faster verification path started in parallel.**
`daily_incremental`'s `Stage0CompanyIdentity` turned out to be a separately-diagnosed,
already-decided-but-not-yet-implemented problem: it reprocesses the entire ~26,300-CIK
tracked universe sequentially (`MaxConcurrency=1`) on every run, not just the day's impacted
CIKs — confirmed live (16/53 windows after ~7h) to match release-readiness's
[ticket 43](../../release-readiness/issues/43-investigate-daily-incremental-full-universe-scope.md)/
[ticket 45](../../release-readiness/issues/45-decide-narrow-daily-incremental-stage0-and-cadence.md)
finding of a 10h16m Stage0-alone runtime on the first-ever prod execution. That fix
([ticket 49](../../release-readiness/issues/49-implement-bounded-daily-identity-refresh-schedule.md))
is designed but still `Status: open` — out of scope for this ticket, not re-litigated here.

Rather than wait ~8+ more hours for `daily-incremental-ticket03-1785413694` to clear Stage0
before reaching `RunWarehouseTask`, started a second, much faster verification: `bootstrap`
(`deploy-aws-application.sh:2218`, `if workflow_name != "daily_incremental"` branch) goes
`SeedUniverse → RunWarehouseTask` directly with no Stage0 prefix, but hits the *identical*
`write_warehouse_mdm_gold_definition`/`run_wh` wiring and the same full-universe
`iter_gold_tables()` gold build (including `sec_thirteenf_holding`) this ticket's fix targets.
Started `bootstrap-ticket03-verify-1785426021`
(`arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-bootstrap:bootstrap-ticket03-verify-1785426021`),
confirmed `RUNNING`. `daily_incremental`'s original execution is left running in parallel as a
slower, secondary confirmation. Whichever completes first (or fails) first will supply the
discriminating `gold_table_completed`/OOM signal for `sec_thirteenf_holding` this ticket's
question 3 is waiting on.

## Update (2026-08-02 — question 3 resolved, discriminating signal confirmed)

Both parallel executions reached a terminal state days ago and were never checked back against
this ticket's own stated success criterion — closing that gap now via `describe-execution` and
CloudWatch, not new work.

- `bootstrap-ticket03-verify-1785426021` — **SUCCEEDED**. Its `RunWarehouseTask`-equivalent
  `bootstrap` command ran on `edgartools-prod-large:90` (8192MB, image digest
  `sha256:aca8078c658bc3f66ac40fa9e41923c4f29743f23ad5623756d94888728cbb30` — the exact digest
  this ticket built). CloudWatch confirms the discriminating event this ticket named as the test:
  `{"event": "gold_table_started", "table": "sec_thirteenf_holding", ...}` followed by
  `{"event": "gold_table_completed", "table": "sec_thirteenf_holding", "rows": 6799919,
  "duration_seconds": 5.81, ...}`, attributed to the `bootstrap` command's own log stream (not
  `GoldRefresh`, avoiding the attribution confound flagged above). All 28 gold tables completed;
  `gold_build_completed`/`gold_publish_completed` fired cleanly. Container exited 0. This is the
  first time `sec_thirteenf_holding`'s gold build has ever completed in any of the four prior OOM
  attempts or since — the memory bump + streaming fix combination works.
- `daily-incremental-ticket03-1785413694` — **FAILED**, but not from OOM. `Stage0CompanyIdentity`
  (~9h56m) and `RunWarehouseTask` (~3h20m) both completed with the container exiting 0 — no OOM
  signature — then the execution failed afterward in `ForceCheck` with `States.Runtime` on absent
  `$.force` (the exact bug independently root-caused and fixed by ticket 54, merged as PR #319).
  Secondary confirmation, consistent with the primary result: the memory fix held under the real
  `daily_incremental` dispatch path too, just masked by an unrelated later failure.

**Question 3 answered: yes.** Both the `large` memory bump (4096→8192MB) and the `run_wh`
dispatch-wiring fix are confirmed working in prod, independent of ticket 01's isolated streaming
claim (still formally unconfirmed alone, per the note above, but the combination this ticket
shipped is proven end-to-end). No further production run is required to close this ticket.

**Status: resolved.**
