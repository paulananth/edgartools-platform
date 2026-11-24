# Handoff to Codex: run the load jobs

Operator, 2026-11-24: "can you hand off to codex to run the force publish" (after "once done load all again with force
publish flag so it ignores change journal"). Claude does not start it; Codex owns the run from here.

## State when handed off
- `load.sh --force` is merged (the loader image of `main`'s commit has it). Nothing is running that you start or stop: a
  plan execution (read-only) may still be ending; wait until `load.sh` of the plan has exited.
- The catalog was published and reads `confirmed` for the rules of the current `main`. If `main` moved under `rules/`
  since, publish again (`edgar-warehouse rules catalog --root rules publish`, then `check`) or readiness stops at CATALOG.
- The pipeline's exporter serves the monitor (`load_monitor_up 1`); the old host exporter is stopped.
- The run label `force-1124` is unused: its state file starts fresh.

## Operator's latest word (2026-11-24)
"fix all skills and load with the default load time linit of 2 h max": run the **default load** (no `--force`): every lane,
then the finish, the Change Journal skipping what is loaded, 2 hours at most. The force publish below stays available only
if the operator says so again. Claude ran the default load for one minute by mistake and stopped it (nothing loaded):
use a fresh run label, not `load-1124`.

## Run it
1. `git worktree add ../edgartools-platform-force-run -b codex/force-run origin/main`, source nothing by hand: `load.sh`
   reads the stores, captures and logs from its defaults.
2. Smoke first, read-only: `RUN=load-1124b infra/load-pipeline/load.sh --plan` must exit 0 (readiness passes, 43 jobs).
3. Then, in the background: `RUN=load-1124b infra/load-pipeline/load.sh --force`.
   The window is 2 hours (operator, 2026-11-24: "do not stop at 2 hours but report the miss"): `load.sh` prints
   `DEADLINE MISSED` once and the load goes on; report the miss with each job's time. It refuses while another execution runs, pulls the image of `main`'s newest commit, and exits 0 only when the
   execution succeeded. Every load job of the run ignores the Change Journal and processes its documents again.
4. Estimate to say before starting: about 8 to 16 hours (the longest dependency path of the jobs' per-attempt bounds is
   16 hours; measured pieces: the GLEIF merge about 1.4 hours, N-PORT security about 1.7 hours).

## Watch it (every 30 minutes, nothing between)
- Grafana: `http://127.0.0.1:3001/d/load-monitor`; `skills/load-monitoring` (`monitoring.py status`).
- In the container: `docker exec edgartools-load-worker-1 ps`, and `/proc/<pid>/io` before and after a minute for a step
  whose log is still empty. The state file is `chain-force-1124.log` in the load logs folder.
- A failed lane stops only what depends on it; the execution ends FAILED with the lane named. Read the step's
  `.errors` file, find the root cause by five whys, fix it on its own branch and PR, then run the same command again: a
  step that finished in this run is not run twice, and a stopped attempt carries on in the same forced run.

## Not decided here
- A forced load that exceeds a job's `minutes` bound stops its attempt (attempts left carry on). Raise a bound only
  with a measured time.
- The 2-hour window is the operator's; the estimate above says it will be missed, so say so before starting.
- Never print a secret, a password, a token or a database address; no provider request.

## Addendum 2026-11-24 08:00 ET: the forced load `load-1124c` cannot finish; fix, then run the default load

Operator: "Just tell codex to fix it". What Claude measured in execution `49827879` (forced, run label `load-1124c`, started
07:19 ET). The operator's last instruction was the **default load** (no `--force`), so first **stop this execution**
(`stop-execution` on the emulator, then stop the worker container so its load processes end; a stopped load resumes), and
use a fresh run label for the rerun.

Failures, each with its root cause (all read from `chain-load-1124c.log` and the jobs' `.errors` files):
1. **`gleif-pairs`: FileNotFoundError on the capture files.** The files in `captures/gleif/20260911-1600/` are symlinks
   into `~/.local/share/edgartools/mdm/research/gleif-20260911-1600/`, and `infra/load-pipeline/compose.yml` mounts
   `CAPTURES` but not that folder, so in the worker the links point to nothing. Fix: mount what the links point to
   read-only, or (better, one place for it) have `load.sh` resolve each input's symlinks and mount their target folders;
   add a test that every file of every input resolves inside the worker's mounts. `gleif` waits on `gleif-pairs`, so it
   stops with it.
2. **`ncen-registrant-2025q4`, `ncen-fund-2025q4`, `ownership` (and the lanes after them): "Source native revision has
   contradictory publications".** A forced load makes every document again as `<run>+force-<time>` with the same revision, and
   the engine refuses the same revision with other content. Decide with the operator: either a forced load passes a revision
   above the last load's for each step (the engine's own message says so), or force publish is not used on a store that
   holds those revisions. A default load does not hit this (it reads the Change Journal and skips).
3. **`nport-security`, `nport-security-silver`: killed (status -9), `OOMKilled=true` on the worker.** The worker container is
   limited to about 3.9 GiB for every lane together, and the pipeline starts every lane at once, so nothing holds the heavy
   merges back (the local scheduler `--auto` does). Fix: size the worker's memory limit from the jobs' measured `worker_gb`,
   or hold heavy jobs back by memory; check the machine first: it has 8 GiB, swap was about 60 percent used, and the load average
   was 12 to 14 on 8 cores.

Then: run the default load (`RUN=<fresh label> infra/load-pipeline/load.sh`), 2 hours at most, report the miss (a default
load should take minutes: the Change Journal skips what is loaded). Each fix is its own branch, PR and test that fails first.

## Addendum 2 (Claude, 2026-11-24 ~08:30 ET): what changed since the first addendum

Read this after the first addendum. The forced load `49827879` (`load-1124c`) was aborted at 08:20 ET; do not rerun it as it was.

Merged to `main`:
- **#2098: a forced load is a new publication.** `load_jobs.arguments()` gives a forced job `--revision <forced time as digits,
  YYYYMMDDHHMMSS>`, replacing the file's revision. This was failure 2 of the first addendum (`ownership`, `ncen-*`,
  "contradictory publications"). Side effect not tested: a default load after a forced one carries the delivery revision,
  lower than the forced one; the engine may refuse it. Check before mixing the two on one store.

In PR #2099 (open when written; merge on green, then wait for the Loader image on its commit):
- **Lanes and workers are one budget.** `load_jobs.py --lanes-at-once [--capacity local|<profile>]` = the capacity's vCPUs over the
  widest first job's workers (8 cores and 4 workers: 2). `load.sh` sets it as the lanes step's `MaxConcurrency` (it runs that
  command in the loader image; `CAPACITY=<profile>` for another compute); the other lanes queue. This was failure 3 (the N-PORT
  jobs killed with status -9, 26 workers on 8 cores, load average 20). Measured, do not retry: the emulator refuses
  `MaxConcurrencyPath`, and a lane queued in the worker times out on its heartbeat. The first start with this code is the live
  check: `load.sh` prints `<n> lanes at once`; expect 2 on this machine.
- The number is platform-neutral (a capacity of `rules/load-jobs.yaml`); only `load.sh` and the state machine apply it.

Still open, yours:
- **The mount gap (failure 1):** `gleif-pairs` reads capture files that are symlinks into
  `~/.local/share/edgartools/mdm/research/gleif-20260911-1600/`, not mounted in the worker. Fix and test that every file of
  every input resolves inside the worker's mounts.
- **Then the default load** (operator, 2026-11-24: "load with the default load time limit of 2 h max", and "do not stop at 2
  hours but report the miss"): no `--force`, a fresh run label, `load.sh` from `main` with the new image. A default load should
  take minutes: the Change Journal skips what is loaded.
