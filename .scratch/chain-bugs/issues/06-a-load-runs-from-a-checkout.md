# 06: a load runs from a developer checkout, not from what CI built

Status: open
Type: task

Every load so far started by hand from a checkout on the Mac (a worktree, then a clone). The gate checks that the
checkout's commit is green on CI. The code that runs is still whatever that folder holds: its engine build, its
environment and its edits. Another session deleted the worktrees mid-work, which stopped one load.

Operator, 2026-11-23: "we must not be run the next load from a worktree we need a ci cd pipeline". Then on where it
runs, "can we run it on a aws emulator". For the emulator, "AWS Step Functions Local (Recommended)" (AWS's own image,
no account). For the image, "GitHub Container Registry (Recommended)".

## 5 whys

1. Why does a load run from a checkout? `load_chain.py` runs the `edgar-warehouse` of the folder it sits in.
2. Why that folder? No image of the loader is built: the existing images serve the retired AWS tasks and leave out the
   chain scripts.
3. Why does nothing build one? Loads moved to the local and hosted stores before any runtime for them existed (ticket
   255 holds the AWS one).
4. Why does readiness not catch it? Its CODE check proves that the commit is green. It does not prove that the running
   code is that commit.
5. Root cause: nothing ties the running code to the tested commit, and the load has no runtime of its own.

## 7 wastes

| Waste | Where | Fix |
|---|---|---|
| Defects | Code in a checkout can differ from its commit (an engine not rebuilt, an edit) | The image is built by CI from the green commit; the engine is compiled into it |
| Waiting | A load waited on a worktree that another session deleted | The load runs in its own container, from no folder |
| Motion | Each load meant finding a checkout, syncing its environment and rebuilding the engine | One command starts an execution of the newest green image |
| Over-processing | `readiness.py --build-engine` rebuilt the engine on the Mac per commit | Built once by CI |
| Others | None found | |

## Design

- `Dockerfile.loader` adds the chain scripts and an `edgar-warehouse` command to the existing warehouse dependency
  image, and records the commit it was built from.
- `.github/workflows/loader-image.yml` runs when CI passes on `main`. It builds the image for arm64 and pushes it
  to ghcr.io as `loader-sha-<commit>`.
- A Step Functions state machine (ASL in the repo) runs readiness, then each step in order, as activity tasks. A
  worker container from the pinned image takes each task and runs `readiness.py` or `load_chain.py --only <step>`.
- On the Mac, Step Functions Local runs in Docker. One script starts the emulator and the worker for the newest green
  image, then starts an execution.
- In the image, CODE reads the commit the image was built from. The image exists only for a commit that passed CI on
  `main`. ENGINE does not apply, because the image carries its own engine.

## Parts

- [x] GoF consult on the area: no pattern; one reader of the image's commit for the gate and CODE; `ps` needs procps in the image, 2026-11-23 19:57 ET
- [x] Failing test: in an image (no `.git`), the commit is the one the image records, for both the gate and CODE; CODE
  passes on it without `git` or `gh`; ENGINE does not apply. `test_an_image_names_the_commit_ci_built_it_from_for_the_gate_and_the_code_check`
  failed with `AttributeError: module 'readiness' has no attribute 'IMAGE_COMMIT'`, then passes; ENGINE is covered by
  `test_an_installed_bundle_has_no_engine_source_to_compare`, 2026-11-23 19:57 ET
- [ ] ~~Failing test: the chain runs where `caffeinate`, `memory_pressure`, `footprint` and `sysctl` are missing~~ deferred to
  none: each call is already behind `sys.platform == "darwin"` (load_chain.py), so there is nothing to fix; `ps` and `pgrep`
  come from procps in the image
- [x] The worker runs a readiness task and a step task, heartbeats, reports success and failure, refuses a bad input and
  stops a task the execution gave up on: `tests/unit/test_load_pipeline.py` (6 tests), 2026-11-23 19:57 ET
- [x] The state machine runs readiness, then the execution's `steps` in order, and holds no step names. Measured on Step
  Functions Local with the real worker and stub commands: a Map of one at a time still started step `c` after `b` failed
  (`FAILED`, 4 tasks run), so the steps became a loop; then `b` failing ends it with `c` never started (3 tasks run), and
  all passing runs all 4 (`SUCCEEDED`). The unit test holds that shape, 2026-11-23 19:57 ET
- [ ] One worker container takes tasks one at a time. QUIET's process count sees only that container; its database
  side (the loader's sessions) still covers the host
- [ ] Mounts: stores and logs writable (readiness record, chain state), captures and proving read-only, at the paths
  `STORES`, `LOGS`, `CAPTURES`, `PROVING` name
- [ ] `Dockerfile.loader` (procps, the whole `skills/` folder for the access audit, `edgar-warehouse` command, the commit): proved by the PR's image build
- [ ] `loader-image.yml` pushes `loader-sha-<commit>` after green CI on `main`
- [ ] The state machine, the activity worker, the compose file and the start script
- [x] Failing test: a load started from a checkout is refused before the gate, and a `COMMIT` file in a checkout is no
  image. `test_a_load_started_from_a_checkout_is_refused_before_the_gate` failed with `Failed: a checkout is refused before
  the gate` (3 cases) and `test_a_checkout_holding_a_commit_file_is_still_a_checkout` with `assert 'abc123' == ''`; both
  pass, 2026-11-23 20:05 ET
- [x] The finish (links and lookups) runs after the steps when asked; probed on Step Functions Local: finish runs after the
  last step, never after a failed one, and is skipped when not asked, 2026-11-23 20:05 ET
- [x] Review: GoF none; Standards and Spec fixed (refuse a checkout, `.git` beats a `COMMIT` file, one execution at a time,
  a deadline that stops the execution, every failed outcome named, logins mounted read-only, paths and run label passed
  through, the image check runs the chain's scripts, the init runbook points at the pipeline); rejected: the trailer (the
  session's attribution), the token on pull requests (a fork's token is read-only), typed times (stamped by the script),
  a pinned digest (a rebuild of one commit is that commit's code), 2026-11-23 20:05 ET
- [ ] PR, merge on green
- [x] Live check: the image for main's commit pulled with no login (the package is public); the first execution found two
  faults only a live run shows, each fixed with a test that failed first. `load.sh` set the worker's activity only after the
  emulator's `compose up`, which reads every service's variables
  (`test_every_variable_the_compose_file_requires_is_set_before_load_sh_first_runs_compose` failed with
  `AssertionError: ['ACTIVITY_ARN']`). The worker's endpoint variable was named for "stepfunctions", but boto3 reads
  `AWS_ENDPOINT_URL_SFN`, so the worker called real AWS with the placeholder login and was refused
  (`test_the_worker_s_client_points_at_the_emulator_the_compose_file_names` failed with
  `assert 'https://stat...amazonaws.com' == 'http://localhost:8083'`). With both fixed, an execution in the image passed all
  13 readiness checks and planned `nport-registrant` (1 document, 1 bundle, no open runs): `SUCCEEDED` in about a minute, 2026-11-23 20:42 ET
- [x] The leftover state machines of the old pipeline are deleted from the AWS account (operator, 2026-11-23: "need to
  cleanup aws step functions"): 27 (12 `edgartools-prod-*`, 15 cost-sizing canaries), none run since 2026-09-21, no
  running execution, schedule or event-rule target; each definition and its tags saved outside the repository first;
  `list-state-machines` then listed none, 2026-11-23 21:05 ET
- [x] Lanes, several workers and waits (operator, 2026-11-23: "must be able to run lanes and multiple workers and
  dependency"; "what runs on the lane is never fixed for the step function"). Without named steps the state machine asks
  the loader for the chain file's lanes and runs them all at once, each lane's steps with their own workers. A failed lane
  is caught, so the others go on, and the execution fails at the end. A step whose needed step failed waited forever: it
  now stops at once (`test_a_step_whose_needed_step_failed_in_another_lane_stops_at_once_and_never_waits` failed with
  `Failed: a step blocked by a failed step never waits` on the old `wait_for`; its two neighbours with `AttributeError`). Probed on Step
  Functions Local: the 3 lanes started in the same second; with `B` failing, `A` and `C` ran to their end and the
  execution failed with no finish, 2026-11-23 21:05 ET
- [x] A load's tasks were lost to an older worker's poll: the 8-step execution failed with `States.Timeout` before any
  step, its readiness task taken 3 ms after it was scheduled by a long poll of the worker compose had just replaced. Each
  load now gets a new activity, the older ones deleted after the check that nothing runs
  (`test_each_load_gets_its_own_activity_so_no_poller_of_an_older_worker_takes_its_tasks` failed with
  `assert '$' in 'edgartools-load'`, then passes), 2026-11-23 21:05 ET
- [x] Review (Standards, Spec, GoF): GoF none. Fixed: a failure counts only after its load's start (`--begin`), a step
  named alone never waits, a lane that breaks records its steps, no cap on the lanes at once (a capped lane could wait on a
  queued one), `--plan --finish` refused, `load.sh` holds a lock, a failed poll keeps its poller, tighter tests. Each new
  case failed first (`AttributeError: ... 'begin_load'`, `TypeError: ... 'others_run'`, `assert set() == {'a1', 'a2'}`).
  Rejected: typed times (stamped by the script); a lock for two lanes of one source and target (none in the chain file), 2026-11-23 21:12 ET
- [x] Six of the 8 steps ran through the pipeline, each skipped in about 20 s (0 documents loaded); `adv-custodians-03`
  then waited on `gleif`, which was not in the run, and the execution was stopped after 12 min, 2026-11-23 21:24 ET
- [x] A load never waits on what cannot come (operator, 2026-11-23: "load must never confuse itself on waiting for
  others"): before the first step, the loader refuses a load when a step needs a step that does not exist, lanes that
  cannot finish, or, for named steps, a step neither done nor earlier in the run.
  `test_a_load_whose_step_would_wait_on_what_cannot_come_is_refused_before_any_step_runs` failed with
  `AttributeError: module 'load_chain' has no attribute 'wait_problems'`, then passes. The real 8-step run is refused
  ("adv-custodians-03 needs gleif: not done, and not before it in this run"); with `gleif` first it passes; the chain file
  has no problem. On Step Functions Local a refused begin ends the execution before any step, 2026-11-23 21:24 ET
- [x] Review of the wait check (Standards, Spec, GoF): fixed a killed lane leaving its waiters (the worker records its
  steps not done: `test_a_lane_that_ends_without_success_has_its_unfinished_steps_recorded` failed with
  `assert [['--lane', 'A']] == [...]`), a step done by an earlier load satisfying a step while this load runs it again
  (`test_a_step_this_load_runs_is_done_only_once_this_load_finishes_it` failed with `TypeError: begin_load() takes 1
  positional argument`), the whole chain in file order checked like named steps; the lanes check derived from the one
  rule of what a step follows (`needs`), and the test that copied the scheduler now calls the check. Rejected: lane runs
  outside the pipeline (a checkout refuses them, the pipeline runs every lane); a store lease for two loads of one source
  and target (no such pair in the chain file); another store's state file (set aside by design, a rerun skips), 2026-11-23 21:28 ET
- [ ] Run `adv-custodians-03` and `adv-custodians-06` after `gleif`: `nport-registrant`, `nport-fund`,
  `adv-mastering-03`, `adv-mastering-06`, `adv-silver-03`, `adv-silver-06`, `adv-custodians-03`, `adv-custodians-06`
- [ ] `gleif`: a read-only check of how many of its documents the Change Journal calls new; load it only at 0
- [x] Skills: data-operations names the pipeline as the only way to start a load, with lanes, waits and failure
  (`HOSTED-LOADS.md`, "Where a load runs"); pipeline-orchestration's AWS page holds what the old state machines and Step
  Functions Local taught; aws-snowflake-operations says the account holds no old state machine and how one is deleted, 2026-11-23 21:05 ET
- [x] Learning → skill: the three skill changes above, 2026-11-23 21:05 ET
