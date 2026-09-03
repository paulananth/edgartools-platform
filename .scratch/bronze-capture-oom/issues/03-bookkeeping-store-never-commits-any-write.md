# 03 — BookkeepingStore Never Commits Any Write

Type: task
Status: resolved (fix implemented, tested, deployed, live-verified) — see
"Third finding" below for a sibling bug this fix exposed, itself now also
fixed, tested, deployed, and live-verified (2026-09-03)
Severity: critical — the real root cause behind Ticket 02's finding and behind
the "one-time reactivation" this file previously documented in CLAUDE.md,
which was itself wrong

## Question

Found while investigating why the live `daily-incremental-ticket15-postfix-1788270018`
execution kept re-processing the full 12,068-CIK universe on every retry
instead of resuming, and separately while investigating a 16-minute silent
stall in a `load-daily-form-index-for-date` diagnostic task. Both symptoms
traced back to the same, single, much larger bug than either ticket alone
described.

## Root cause (confirmed via direct code reading, not inference)

`edgar_warehouse/bookkeeping/store.py` (930+ lines, `BookkeepingStore`, 31
write methods — `upsert_daily_index_checkpoint`, `upsert_source_checkpoint`,
`upsert_company_sync_state`, `start_sync_run`/`complete_sync_run`,
`start_pipeline_run`/`complete_pipeline_run`, etc.) **never calls
`self._session.commit()` anywhere** — confirmed via `grep -n commit
edgar_warehouse/bookkeeping/store.py` returning zero matches, and a
repo-wide grep for any commit call near Bookkeeping's session also empty.
`edgar_warehouse/bookkeeping/database.py`'s `get_engine()` also does not use
`isolation_level="AUTOCOMMIT"` — a plain `create_engine(url,
pool_pre_ping=True)`.

SQLAlchemy's `Session` never auto-commits on its own. Every write made
through `BookkeepingStore` — every checkpoint, every sync-run/pipeline-run
record — is silently rolled back by Postgres when the owning process exits,
even though the call site logs the write as `"status": "succeeded"` with no
error of any kind.

**Confirmed live in prod, twice, independently:**
1. Ran `load-daily-form-index-for-date 2026-08-27` via a one-off ECS task.
   Logs showed `silver_publish_completed` / `status: "succeeded"`, row count
   6,615. A second ECS task, and a fresh rerun of the identical command
   minutes later, both failed to see the checkpoint —
   `_load_sealed_discovery_rows` raised `No sealed discovery observation for
   business_date=2026-08-27 (checkpoint status='missing')`.
2. Rediagnosed after stopping the interfering `daily_incremental` execution:
   reran the same sealing command a second time — same result. The write
   never became durable at any point.

**This means every `daily_incremental`/`bootstrap` run in prod has been
losing its own Bookkeeping state on every single run**, not just during
some one-time event. The "daily_incremental multi-hour runtime after
Bookkeeping Postgres cutover" 5-whys entry this session added to CLAUDE.md
earlier — which characterized the 12,068-CIK reactivation as a one-time,
expected consequence of Bookkeeping's empty-start design — is **wrong** and
needs correction: it is not one-time. Every run reprocesses the full
universe because no run has ever durably recorded that it processed
anything.

## Fix

Added `BookkeepingStore.commit()` (`edgar_warehouse/bookkeeping/store.py`),
a thin wrapper around `self._session.commit()`, documented with the finding
above. Called it at the two real conclusion points of
`edgar_warehouse/application/warehouse_orchestrator.py`'s
`_execute_warehouse_bronze_capture` — the function backing
`daily_incremental`/`bootstrap`/`load-daily-form-index-for-date` and every
other command dispatched through its shared `_capture_bronze_raw` fan-out
(confirmed via code reading that all ~30 command branches share the same
`bookkeeping` session instance, created once at the top of the function):
once after the success-path `complete_pipeline_run`/`complete_sync_run`
calls (before silver publish, so bookkeeping state is durable regardless of
what the rest of the command does), once in the `except` block's
failure-path `complete_sync_run`/`complete_pipeline_run` calls (same
existing `if not db_closed:` guard).

Grepped every other `BookkeepingStore(...)` instantiation site in the repo
to check for other un-committed write paths: found exactly one more —
`edgar_warehouse/application/commands/verify_pipeline_run.py`'s
`record_pipeline_verification` call — fixed the same way. Every other
instantiation site (`cli.py`, `mdm/cli.py`,
`scripts/build_relationship_release_manifest.py`) is read-only
(`get_all_company_sync_states`, etc.) and needs no commit.

**Followed this codebase's existing convention, not a new one.** Checked
MDM's sibling Postgres store (`edgar_warehouse/mdm/database.py`): it also
does not use engine-level autocommit — it relies on 37 explicit
`session.commit()` calls scattered at logical completion points across
`mdm/adv_bulk.py`, `mdm/cli.py`, `mdm/export.py`, etc. `BookkeepingStore`'s
own module docstring says it is "ported 1:1" from MDM's equivalent methods,
so the explicit-commit-at-caller pattern was chosen over engine-level
`isolation_level="AUTOCOMMIT"` (a different, less safe mechanism used
nowhere else in this codebase) or rewriting `BookkeepingStore`'s
single-long-lived-session lifecycle into the Acquisition/Change Ledger
module's `with Session(engine) as session, session.begin():`
context-manager shape (a much larger, riskier change to a calling
convention every existing caller already depends on).

## Tests

- `tests/bookkeeping/test_store_commit.py` (new): two tests against a real
  second `Session` on the same underlying engine — proves (a) without an
  explicit `commit()`, closing the writing session rolls the write back
  (reproduces the live bug), and (b) `commit()` survives the writing
  session closing (proves the fix). Notes the SQLite+StaticPool fixture's
  own quirk (a still-open second session sees a still-open first session's
  *uncommitted* write, unlike real Postgres) and deliberately does not test
  that shape, since it doesn't discriminate the fix.
- `tests/unit/test_pipeline_run_tracking.py`: extended the existing
  `test_bronze_capture_records_pipeline_run` with a `commit()` call-order
  assertion (must fire after `complete_pipeline_run`); added
  `test_bronze_capture_commits_bookkeeping_on_failure` (failure path) and
  `test_verify_pipeline_run_commits_the_verification_record` (a real second
  Session/engine, same discriminating shape as the store-level tests, for
  `verify-pipeline-run`'s own write path).
- Full repo suite green: 2961 passed, 6 skipped (one more than baseline —
  the race-condition test below).
- mypy: 26 pre-existing errors, none introduced by this fix (confirmed via
  `git stash` line-number comparison on `bookkeeping/store.py`).

## Second finding, from 3-axis review (Standards axis), fixed before commit

The initial version of this fix introduced a real regression, caught by
the mandatory Standards review pass: the success-path `bookkeeping.commit()`
fires (and closes the local silver db, setting `db_closed = True`) *before*
`_publish_silver_database_with_retry` and `write_landing_export` run, both
still inside the same `try` block. If either of those then raised, the
`except` block's failure-recording was gated on `if not db_closed:` — since
`db_closed` was already `True`, the failure record was skipped entirely,
leaving a **durably committed, factually wrong `status="succeeded"`
pipeline_run row for a run that had actually failed**. Before this fix
existed, that same window produced no durable record at all (silently
rolled back either way) — a false "we don't know" rather than a false
"succeeded." The fix made this specific failure mode *worse*, not better.

**Fix:** removed the `db_closed` gate from the `except` block's bookkeeping
calls — `complete_sync_run`/`complete_pipeline_run` are plain idempotent
`UPDATE ... WHERE run_id = ...` statements (confirmed by reading
`store.py`), safe to call again even after the success path already wrote
and committed `"succeeded"`; the except block now unconditionally
overwrites the row to `"failed"` and commits that correction. The
`db_closed` flag's other, correct use (`finally: if not db_closed:
db.close()`, guarding the local silver-db file handle) is untouched.

**Test:** `test_bronze_capture_corrects_a_committed_success_when_silver_publish_fails`
(`tests/unit/test_pipeline_run_tracking.py`) forces
`_publish_silver_database_with_retry` to raise after the success commit has
already fired, and asserts `complete_pipeline_run` is called twice
(`"succeeded"` then `"failed"`, in that order) with two matching commits.
Verified to fail without the fix (reverted the except-block change locally,
confirmed the test catches exactly 1 call instead of 2, restored the fix) —
same fail-before/pass-after discipline as every other test in this ticket.

Also trimmed near-duplicated explanatory comments across the three call
sites (Standards' minor "Duplicated Code" finding) down to one-liners
pointing at `BookkeepingStore.commit`'s own docstring, keeping only the
genuinely unique content at each site (the success path's INVARIANT note;
the except path's explanation of why the `db_closed` gate was removed).

Full suite re-run green after this second fix: 2961 passed, 6 skipped.

## Deployed

Built and pushed a new prod warehouse image
(`sha256:5099a185dd1f20edb8ce42ef068130c7cc087b16d241749189b831d1ba05b42a`,
tag `warehouse-sha-5706d2f39e15`/`warehouse-prod`) containing this fix
**bundled with bronze-capture-oom Ticket 01's chunking fix** (commit
`5706d2f3` — both landed in the same image build since Ticket 01 was
already committed when this bug was found). Deployed via
`deploy-aws-application.sh --env prod --enable-mdm`; confirmed
`RunWarehouseTask` in `edgartools-prod-daily-incremental`'s state machine
now points at `edgartools-prod-large:239`, which resolves to this image
digest.

**Live-verified 2026-09-02**: sealed a `load-daily-form-index-for-date`
checkpoint via one ECS task on the new image, reran the identical command,
confirmed it took the cache-hit path (`rows_skipped: 1`, zero
`sec_call_started` events) instead of re-fetching from SEC. The commit fix
itself works exactly as designed.

## Third finding: live daily_incremental run exposed a second, sibling bug

Started a fresh `daily_incremental` execution
(`daily-incremental-verify-bookkeeping-fix-1788343855`) to verify both
fixes end-to-end. It progressed past `ResolveCompanyIdentityBounded`/
`ReduceIdentityRefresh`, entered `RunWarehouseTask`, and its first attempt
**actually worked** — sealed real, durable checkpoints for 2026-08-27
through 2026-09-01 (`status: succeeded`) and correctly marked 2026-09-02 as
`waiting_for_publish` (confirmed by querying the live Bookkeeping Postgres
checkpoint table directly). That is the commit fix working exactly as
intended, for the first time ever in prod.

But the *next* three attempts all failed fast (~1 minute each, exit code
2, not the multi-hour OOM pattern) with
`WarehouseRuntimeError: start_date must be on or before end_date`, raised
from `_resolve_scope`'s `"daily-incremental"` branch
(`edgar_warehouse/application/warehouse_orchestrator.py:6902`).

**Root cause:** `start_date = next_business_day(date.fromisoformat(last_success))`
— with `last_success = "2026-09-01"` (the checkpoint the prior attempt had
just durably sealed), this computes `start_date = 2026-09-02`. But
`end_date = latest_eligible_business_date(now)` also resolves to
`2026-09-01`, since SEC's 2026-09-02 daily index isn't published until
06:00 ET the following day. `start_date (09-02) > end_date (09-01)` → the
existing hard-error check fires. This is a genuine, previously-dormant
bug: **it could never trigger before this fix**, because checkpoints never
survived a process exit, so `last_success` was always `None` and
`start_date` always fell back to `end_date` trivially. My own commit fix
is what finally let a real `daily_incremental` run catch up to steady
state and expose it — this specific case ("caught up, nothing new
published yet") is the *correct*, expected condition for a recurring job,
not an error.

**Fix:** when `start_date` is auto-derived (not an explicit operator
`--start-date`) and lands after `end_date`, clamp it back to `end_date`
instead of raising — mirrors the existing sibling branch immediately below
it (`else: start_date = end_date`, the no-prior-success case). Traced the
downstream caller (`_capture_bronze_raw`'s daily-incremental dispatch,
`warehouse_orchestrator.py:~1605-1620`): in the common recurring-mode case
(`--recurring-index-lookback-days`, which every real invocation passes),
`business_date_start` gets unconditionally overwritten from `business_date_end`
anyway, so the clamped value's only real job in that path is to stop the
scope-resolution step itself from raising — for a non-recurring invocation,
the clamped value drives one iteration of `_load_daily_index_for_date` for
`end_date`, which correctly takes its own existing cache-hit fast path.

**Corrected by Standards review before commit:** the first version of this
fix clamped whenever `start_date > end_date`, regardless of whether
`end_date` came from an explicit `--end-date` or was auto-resolved. Live-
reproduced the gap: a real `last_success` (e.g. `2026-09-01`) racing
against an explicitly-passed, stale `--end-date` (e.g. `2026-08-15`) would
silently clamp to a misleadingly narrow single-day window instead of
raising — even though the operator explicitly asked for a specific end
date. This contradicts the repo's fail-closed posture elsewhere (see the
daily-accession-expansion 5-whys: "fails closed on expansion"). **Fixed**
by scoping the clamp to a fully-automatic invocation only (`end_date_was_
explicit` tracked before the auto-resolve default is applied) — any
explicit `--start-date` or `--end-date` now still raises on a mismatch,
matching the pre-fix behavior for that case exactly. The final
`if start_date > end_date: raise` check is reachable for both the
fully-explicit case and this explicit-end-date-vs-real-last-success case.

**Test:** `tests/unit/test_daily_incremental_scope_resolution.py` (new, 5
cases) — no-prior-success, normal-advance, the exact caught-up scenario
(verified to fail before the fix with the identical live error message,
pass after), explicit-args-still-raises, and
`test_explicit_stale_end_date_still_raises_even_with_a_real_last_success`
(the Standards-review finding above — verified to fail with the narrower
clamp, pass with the `end_date_was_explicit` guard). Full suite re-run
green: 2966 passed, 6 skipped.

**Live-verified 2026-09-03** (via `/diagnose`, root-causing what looked
live like an unexplained "self-resolved" failure before this git history
was found): confirmed via `git merge-base --is-ancestor fecd88f1 HEAD` that
this exact commit landed on `main` through PR #529
(`claude/daily-incremental-caught-up-clamp`) at 2026-09-02 07:03:59 -0400 —
19 minutes after the last of the 4 failed attempts
(`daily-incremental-verify-bookkeeping-fix-1788343855`, last failure
06:44:54 -0400) and 11 minutes before the next execution
(`daily-incremental-bothfixes-1788347684`, started 07:14:48 -0400)
succeeded. Confirmed via `aws stepfunctions list-executions` that every
`daily-incremental` execution since has reached `SUCCEEDED`
(`bothfixes-1788347684`, `bothfixes-take2-1788349393`,
`stresstest-zero-updates-1788383101` — the last of which also confirmed
the commit fix itself is holding: `catalog_network_fetches: 0` across
9,457 CIKs, i.e. zero re-fetches from SEC, while still landing 42,604 real
backlog rows into silver). This is the fresh run this note was waiting on
— reached a real terminal `SUCCEEDED` state, not the date-range check.

**Pre-existing wrinkle, found by `/gof-refactor-reviewer` review, not
introduced by this fix and not blocking it:** `sync_scope_key_for_command`
(`edgar_warehouse/domain/policy/command_scope.py:100`) builds the persisted
`sync_run.scope_key` as `f"{business_date_start}:{business_date_end}"` from
`_resolve_scope`'s value — *before* `_capture_bronze_raw`'s recurring-mode
override (`business_date_start = business_date_end - timedelta(days=
recurring_lookback_days - 1)`) ever runs. So for a caught-up recurring run,
the logged `scope_key` (e.g. `"2026-09-01:2026-09-01"`) understates the
actual lookback window that got revalidated. This mismatch already existed
for the normal-advancing case before this fix — it was just never visible,
because the caught-up case always raised before `start_sync_run` recorded
anything. Now that the caught-up case succeeds, the misleading log record
becomes visible for the first time. Worth a follow-up if bookkeeping audit
trails matter here; not a correctness bug in the fix itself.

## Correction needed elsewhere

CLAUDE.md's "daily_incremental multi-hour runtime after Bookkeeping
Postgres cutover 5-whys (expected, not a bug, 2026-09-01)" section
(written earlier in this same session, before this deeper root cause was
found) incorrectly characterizes the reactivation as one-time and
expected. It is neither — every run has been affected by this bug. That
CLAUDE.md section should be corrected or superseded by this ticket once
this fix is live-verified.
