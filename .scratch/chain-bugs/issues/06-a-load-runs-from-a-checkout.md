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
- [ ] ~~Failing test: the chain runs where `caffeinate`, `memory_pressure`, `footprint` and `sysctl` are missing~~ not needed: each call
  is already behind `sys.platform == "darwin"` (load_chain.py); `ps` and `pgrep` come from procps in the image
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
- [ ] `Dockerfile.loader` (procps, the whole `skills/` folder for the access audit, `edgar-warehouse` command, the commit)
- [ ] `loader-image.yml` pushes `loader-sha-<commit>` after green CI on `main`
- [ ] The state machine, the activity worker, the compose file and the start script
- [ ] Review (Standards, Spec, GoF), PR, merge on green
- [ ] Live check: the image is published for the merged commit, and an execution on the emulator passes readiness
- [ ] Rerun the 8 steps left after `company` through the pipeline: `nport-registrant`, `nport-fund`,
  `adv-mastering-03`, `adv-mastering-06`, `adv-silver-03`, `adv-silver-06`, `adv-custodians-03`, `adv-custodians-06`
- [ ] `gleif`: a read-only check of how many of its documents the Change Journal calls new; load it only at 0
- [ ] Skills: data-operations names the pipeline as the only way to start a load
- [ ] Learning → skill
