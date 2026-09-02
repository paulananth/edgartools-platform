# 03 — BookkeepingStore Never Commits Any Write

Type: task
Status: resolved (fix implemented + tested; not yet deployed)
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

**This specific `commit()` fix's own line of code has not yet been
independently verified live** (deployed, but no fresh `daily_incremental`
run has completed since — the previous live execution,
`daily-incremental-ticket15-postfix-1788270018`, was stopped by explicit
operator instruction before this fix was built). Needs a fresh run to
confirm: a completed run's checkpoints/sync-state should now survive a
process restart and a subsequent run should show real skip-if-unchanged
behavior instead of reprocessing the full CIK universe.

## Correction needed elsewhere

CLAUDE.md's "daily_incremental multi-hour runtime after Bookkeeping
Postgres cutover 5-whys (expected, not a bug, 2026-09-01)" section
(written earlier in this same session, before this deeper root cause was
found) incorrectly characterizes the reactivation as one-time and
expected. It is neither — every run has been affected by this bug. That
CLAUDE.md section should be corrected or superseded by this ticket once
this fix is live-verified.
