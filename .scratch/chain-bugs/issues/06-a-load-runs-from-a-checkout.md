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
- [x] Rerun the 8 steps left after `company` through the pipeline: `nport-registrant`, `nport-fund`, `adv-mastering-03`,
  `adv-mastering-06`, `adv-silver-03` and `adv-silver-06` ran in about 20 s each with 0 documents loaded; `gleif`,
  `adv-custodians-03` and `adv-custodians-06` ran in that order in one execution (SUCCEEDED, the custodians started 9 s
  after `gleif` ended): each ended "0 documents loaded, 1 already loaded before", so the Change Journal skipped all
  eight; `gleif` read its source for 11 min 36 s before it skipped, 2026-11-23 22:07 ET
- [x] `gleif`: the read-only check found 1 bundle, 1 document, 0 fresh, so it was safe to load, 2026-11-23 22:03 ET
- [ ] The exporter runs in the pipeline (PR 2090): it served from a deleted checkout and reported `load_monitor_up 0`, and a
  host `ps` cannot see a container's load. Live check after the merge: stop the old host exporter, `load_monitor_up 1`,
  and the running step shows in Grafana
- [x] A source holds its own input files. Operator, 2026-11-23: "list every delivery by name in source.yaml, update the skill
  data onboarding and data operation should use it" (after "this cannot be on load-chain they are attached to the source
  and the input files for the source"). The file is `sources/<source>/inputs.yaml`, beside `source.yaml`; the review found that the processing
  identity (`source_rules`) and the catalog's rules digest hold every yaml file of a source folder, so both now skip it by
  name (`rules.files.INPUTS`): a new delivery changes no rules version. Moving it into `source.yaml` is open for the operator.
  Tests failed first: `chain_steps() takes 1 positional argument` (the resolution), the chain file held `capture:` lines, and
  `test_a_new_delivery_changes_neither_the_processing_identity_nor_the_rules_digest` (`inputs.yaml` was in the identity);
  all 43 steps resolve to the folders they had before, 2026-11-23 22:03 ET
- [x] Skills: data-operations names the pipeline as the only way to start a load, with lanes, waits and failure
  (`HOSTED-LOADS.md`, "Where a load runs"); pipeline-orchestration's AWS page holds what the old state machines and Step
  Functions Local taught; aws-snowflake-operations says the account holds no old state machine and how one is deleted, 2026-11-23 21:05 ET
- [x] No application lock (operator, 2026-11-24: "There should be no application triggered lock"): `load.sh` kept a lock folder that a dead run left
  behind and that refused the next start twice; the execution check against Step Functions already enforces one load at a time, so the
  lock is gone. `test_one_load_at_a_time_is_the_state_machines_own_record_and_load_sh_keeps_no_lock_file` failed first (`.lock` found in
  the script), 2026-11-24 14:15 ET
- [x] Lanes and the monitor agree (operator, 2026-11-24: "Why are we not using all the lanes fix the skill load monitor and data operations they must
  work together"): measured, two lanes already held 2.45 of the container runtime's 3.9 GiB (about 0.4 GiB a worker) with CPU at 1.7 of 8 cores, so
  memory limits the lanes. The lane budget now uses the workers a compute carries (the range a step's workers follow, not vCPUs alone), and
  `lane_budget` names the limit; the exporter shows lanes and workers running against it and the dashboard has Lanes running and Lane budget.
  `test_the_exporter_shows_the_lane_budget_beside_the_lanes_and_workers_running` failed first, 2026-11-24 14:36 ET
- [ ] More lanes at once on this machine need more container-runtime memory or narrower first steps (the widest, 4 workers, sets 2 lanes): decide
  with the next measured load
- [x] Learning → skill (operator, 2026-11-24: "Update skills from learning"): HOSTED-LOADS names how to restart the runtime (`orbctl stop`, `orbctl start`) and what a forced load costs; load-monitoring says a watcher reads its own run label's log and an execution lost to a restart is not a failure, 2026-11-24 14:26 ET
- [x] Learning → skill: the three skill changes above, 2026-11-23 21:05 ET
- [x] The load chain is named load jobs. Operator, 2026-11-23: "no load chain its load jobs"; scope chosen: "Everything live".
  `rules/load-jobs.yaml`, `load_jobs.py`, `test_load_jobs.py`, `chain_steps` → `load_jobs()`, and the text of skills, runbooks,
  the workflow and compose. Kept as they are, because a store's state is named by them: the `chain-<RUN>.log` state files, the
  `chain store` and `chain done` lines in them, and the `chain-<job>` session tag. `test_the_load_jobs_are_named_load_jobs_everywhere_a_reader_looks`
  fails on main (it names the files holding the old name), 2026-11-23 22:18 ET
- [ ] ~~Rename `step` to `job` in the file keys, flags and worker input~~ deferred: `steps`, `--only` and the task input are the
  worker's and state machine's contract; changing them is its own change
- [x] Force publish through the pipeline. Operator, 2026-11-23: "once done load all again with force publish flag so it ignores
  change journal". `load.sh --force` puts `force` in the execution's input, the machine hands it to every lane and step task,
  the worker adds `--force`, and `load_jobs.py` gives it to every load (a plan never has it; `--finish`, `--list`, `--status`
  and `--begin` refuse it). Tests failed first: 8 (the worker's commands, the machine's tasks, the arguments, the refusals), 2026-11-23 22:32 ET
- [ ] Load all 43 load jobs again with force publish: `RUN=<new label> LOAD_DEADLINE_HOURS=<hours> load.sh --force`; the time
  is said before it starts, then checked every 30 minutes
- [x] A forced load is a new publication. The first forced load (execution 49827879) stopped `ownership`, `ncen-registrant-2025q4` and
  `ncen-fund-2025q4` with "Source native revision has contradictory publications" (the run name changed under the revision).
  Operator, 2026-11-24: "Fix item 3 build a new image". A forced load now gives each job one revision of its own, the forced time as
  digits (YYYYMMDDHHMMSS: above every delivery date and every earlier forced run). Tests failed first
  (`--revision` was the file's `1`, not the forced time), 2026-11-24 08:09 ET
- [x] Lanes and workers are one budget. Operator, 2026-11-24: "Make the skills and scripts understand MaxConcurrency and workers" (after
  "They are doing the same thing"). The 7-wastes analysis: 11 lanes at once asked for 26 workers on 8 cores, load average 20, two
  N-PORT jobs killed (status -9, OOMKilled). `load.sh` now sets the lanes step's `MaxConcurrency` to the machine's cores over the widest
  first job's workers (`load_jobs.py --lanes-at-once`); measured: the emulator refuses `MaxConcurrencyPath`, and a lane queued in
  the worker times out on its heartbeat (task 2 and 3 of 3 `TaskTimedOut`). Tests failed first (`lanes_at_once` and the flag
  did not exist), 2026-11-24 08:19 ET
- [ ] ~~The worker's memory limit~~ covered by the lanes budget above; remeasure on the next load
- [x] The mount gap: `gleif-pairs` read capture files that are symlinks into a folder the worker does not mount. Codex's change reads the
  publisher input, whose three payload files are regular files (PR 2100); Claude took the branch over on the operator's word ("Take
  over codex/gleif-worker-input-20261124") and updated the one expectation, `test_each_step_resolves_to_the_folder_its_source_names`
  (it still named the symlinked input; failed first on the new config), 2026-11-24 09:51 ET
- [x] The second mount gap: the default load's `company`, `person` and `openfigi-answers` stopped with "Corrupt control document". The
  forced load had left runs unfinished, the default load drives them again, and the worker reads each run's frozen rules from the
  folder `BOOKKEEPING_MANIFEST_ROOT` names, which it does not mount (in the container the file did not exist; the engine reports a
  missing file as a corrupt control document, a misleading message). `load.sh` reads the folder from `worker.env` and the compose
  file mounts it writable. `test_the_worker_mounts_the_folder_of_the_run_documents_that_worker_env_names` failed first with
  `assert (0 == 1)` (no such mount), 2026-11-24 11:28 ET
- [ ] The engine's message: a missing artifact is reported as a corrupt control document (`Artifacts.json` wraps the missing-file
  error); name it a missing artifact
- [x] OpenMetadata decoupled from loads (operator, 2026-11-24: "Decouple open metadata from loads"): the CATALOG readiness check is gone
  (a stopped or drifted catalog twice held a load for an hour, and the stack's memory starved the Docker engine), and a finished step no
  longer publishes its status (`--catalog-status` does it after a load). `test_a_state_file_that_will_be_set_aside_is_shown_and_a_catalog_that_drifted_or_is_down_never_closes_the_gate`
  failed first with `KeyError: 'catalog'` on the old gate, 2026-11-24 13:07 ET
- [x] Learning → skill (operator, 2026-11-24: "Add learning to skills goal is to load all data in the shortest possible time"): HOSTED-LOADS has "The shortest time to load everything" (lanes, no catalog or plan in a load, a runtime watch and restart, the mounts, leftover runs, one start script) and load-monitoring names the runtime test first, 2026-11-24 13:44 ET
- [x] No standing plan: the loader never ran one (only `--plan` does); the plan before a load was a step of the run script, which repeated
  readiness and cost a whole execution. HOSTED-LOADS and data-operations now say a routine load needs no plan, 2026-11-24 11:29 ET
- [x] Learning → skill: data-operations and data-onboarding point at `sources/<source>/inputs.yaml` for a source's deliveries, 2026-11-23 22:03 ET
