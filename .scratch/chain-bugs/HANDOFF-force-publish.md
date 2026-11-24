# Handoff to Codex: run the force publish of every load job

Operator, 2026-11-24: "can you hand off to codex to run the force publish" (after "once done load all again with force
publish flag so it ignores change journal"). Claude does not start it; Codex owns the run from here.

## State when handed off
- `load.sh --force` is merged (the loader image of `main`'s commit has it). Nothing is running that you start or stop: a
  plan execution (read-only) may still be ending; wait until `load.sh` of the plan has exited.
- The catalog was published and reads `confirmed` for the rules of the current `main`. If `main` moved under `rules/`
  since, publish again (`edgar-warehouse rules catalog --root rules publish`, then `check`) or readiness stops at CATALOG.
- The pipeline's exporter serves the monitor (`load_monitor_up 1`); the old host exporter is stopped.
- The run label `force-1124` is unused: its state file starts fresh.

## Run it
1. `git worktree add ../edgartools-platform-force-run -b codex/force-run origin/main`, source nothing by hand: `load.sh`
   reads the stores, captures and logs from its defaults.
2. Smoke first, read-only: `RUN=force-1124 infra/load-pipeline/load.sh --plan` must exit 0 (readiness passes, 43 jobs).
3. Then, in the background with a deadline: `RUN=force-1124 LOAD_DEADLINE_HOURS=48 infra/load-pipeline/load.sh --force`.
   It refuses while another execution runs, pulls the image of `main`'s newest commit, and exits 0 only when the
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
- Never print a secret, a password, a token or a database address; no provider request.
