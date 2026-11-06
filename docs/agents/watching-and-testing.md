# Watching runs and testing locally

Detail moved out of `CLAUDE.md`, which keeps the rule and a pointer here.

## Watchers

Every background watcher (CI, a long test, a proof) has a deadline and an
  exit for every outcome, including the PR merging or closing. Stop test
  containers when a run ends, however it ends. macOS has no `timeout`
  command (a watcher wrapped in it exits at once and does nothing); give the
  deadline with a background `sleep N; pkill -P <pid>; kill <pid>` instead.
  Stop the job's children first: `kill <pid>` alone leaves a process pool's
  workers running (27 were left, idle up to 34 hours, 2026-10-30). Name each
  process by its id, never by a name pattern (`pkill -f`) or with job control
  (`set -m`): a test using both stopped two other runs and the Docker engine
  (2026-10-30).
  Start `merge_on_green.sh` itself as the background command, with no trailing `&`
  and no redirect: the harness reports its real exit; a detached copy reported
  "completed" at once and its merge result went unseen (2026-11-01).

`merge_on_green.sh` reads the PR's head every round, so a push needs no restart. Restart it only
after it has exited.

## Which tests to run

- No test is expected to fail: CI is green on `main`.
- **Locally, run the tests a change can affect; CI runs everything** (operator, 2026-09-29, after a
  16-minute integration run). `pytest-testmon` records which code each test executes and re-runs only
  the tests touching changed Python: `TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run pytest
  --testmon <folders>` (one shared record for every worktree; a test never recorded always runs; it needs pytest's cache,
  so never add `-p no:cacheprovider`).
  It cannot see non-Python inputs: after a change to a migration `.sql`, a rules `.yaml` or another
  data file, also run that area's test files by name. The full suite runs in CI on every PR, and
  nothing merges until it is green.
- **A change to skills, tickets or docs only** needs no project environment, so never
  `uv sync` a new worktree for it (several minutes, Rust engine included; operator,
  2026-10-28: "If the skills test is building the whole environment it is a waste").
  The genericity lint reads files only: `uv run --no-project --with pytest -- pytest -q
  -p no:cacheprovider tests/unit/test_profiling_genericity.py` (under 1 s), and after an edit to
  CLAUDE.md or AGENTS.md, `tests/unit/test_guides_name_existing_paths.py` the same way. CI runs the rest.
- **A change to the Rust engine** (`crates/source-contract/`) reaches Python only after
  `uv sync --all-extras --group dev --reinstall-package source-contract`; until then Python tests run
  the old engine. testmon then reruns nearly every test (10 minutes, ticket 138), so name the area's
  test files instead. The storage-adapter scenarios run locally on MySQL with
  `CI=true SKILL_ADAPTER_TEST_ENGINE=mysql uv run --no-sync pytest tests/storage_adapters/...` (the database clients are in the `dev` group);
  remove the `skill-adapter-proof-*` containers after.
