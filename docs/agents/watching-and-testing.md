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

## Writing a test

A test earns its place by failing when behaviour breaks and by passing when only the internals change
(operator, 2026-11-16, after an audit of the suite). Before writing one, say what a user of the code would
see go wrong; if nothing, write no test.

1. **Assert behaviour, never a file's text.** Do not read a script, Terraform or YAML file and assert that
   a string is in it, or is gone from it ("no longer contains X" is a changelog, not a test). Run the script
   with fakes on `PATH`, or call the function. A security or cost invariant that is only readable from
   config (an IAM scope, a log retention) may be pinned, once, with a reason in the test's name.
2. **Never assert what a fake returns.** A fake that answers `"sentinel"` and a test that asserts the
   sentinel came back tests the fake. Assert what the code did with the answer. A fake never re-implements the
   logic it stands in for (a diff of "already applied" pairs): it records what it was handed, and the real
   logic gets its own test on the real store.
3. **No copied counts.** `len(x) == 34` over repo content fails on every legitimate addition. Assert the
   property (`x` is not empty, each item has its field), or the one item the rule is about. A closed external
   code set (309 place codes) may keep its count.
4. **A mock matches the real interface.** Patch a function with `tests.support.patching.checked(monkeypatch, owner, "name", replacement)`
   (never a bare `lambda *a`), or subclass the real class or protocol, so a changed signature fails the test.
   `checked` holds the arguments to the real function's, not the result: a replacement returns what the real function returns
   (one value, not a tuple the caller once took), and at least one test calls the real function unpatched. A fake that kept an
   old return shape kept CI green while the code that unpacked it failed on the first live load. A hand-written fake of an outside service
   (OpenMetadata, Docker) names the version it was probed against and has one contract test against the
   real service or a recorded response.
5. **Not tied to call order.** Assert the outcome (rows, state, refusal), not the exact sequence of internal
   calls or the role string that made each one. A `pytest.fail` guard on a call that must never happen
   ("plan must not connect") is a behaviour and is fine.
6. **No clocks.** A test waits on an event or a counter its own fake sets, never on `time.sleep` and a
   tolerance: a slow machine must change how long a test takes, not whether it passes.
7. **Every test has an assertion that can fail.** A test whose only check is `is not None`, or that has no
   assert and no raising helper, proves nothing. Change the code under test once and see the test fail.
8. **Use real data shapes.** Start a body from the real rules file and change it (as `test_target_manifest`
   does), never a hand-built dict that can drift from the real one.

