# Run only the affected tests locally; CI runs everything

Type: task
Status: done (Claude, branch `claude/company-mastering-24-parallel-tests`, 2026-09-29)
Blocked by: nothing
Blocks: nothing; it shortens every later ticket's local test run

## Why

Operator, 2026-09-29: "why full run is 12 mins not acceptable", then, after
the breakdown, "stop and try a diffrant approach", and "yes" to running
only the affected tests locally with the full suite in CI.

## Measured (2026-09-29 20:09 ET, rules ticket 14's head)

`tests/integration`: 313 tests, 24 files, 16.5 min, run one file at a time.

- About 21 files each start their own PostgreSQL 16 container and migrate
  it before their first test: 10 to 25 s each, at least 5.2 min.
- The 19 heaviest tests (end-to-end Bookkeeping runs, the Clean MDM full
  replay): 3.0 min.
- The other ~275 tests, about 1.8 s each: ~8.3 min.

Tried and dropped: running 4 files at a time (pytest-xdist). This Mac has 4
cores and Colima 4 CPUs and 8 GB; 4 workers plus 4 databases share the
same cores, and the two largest files still run whole on one worker. The run
was stopped at 8 minutes, about 80% done.

## Done

- `pytest-testmon` in the dev group. It records which code each test
  executes and, with `--testmon`, re-runs only the tests that touch changed
  Python. One shared record for every worktree:
  `TESTMON_DATAFILE=~/.cache/edgartools/testmondata`. It needs pytest's
  cache: `-p no:cacheprovider` stops it (`KeyError: 'lf'`).
- Checked: `tests/unit/test_rules_files.py` ran 76 tests in 4.1 s, then
  deselected all 76 in 0.7 s with nothing changed.
- It cannot see non-Python inputs (migration `.sql`, rules `.yaml`, data
  files): after such a change, run that area's test files by name too.
- CI is unchanged: it runs every folder on every PR, and nothing merges
  until it is green.
- CLAUDE.md's test section and Claude's memory say the same.

## Later, if the full run must be shorter

One PostgreSQL container per run instead of one per file, migrated once
into template databases (saves most of the 5.2 min), for CI and anyone who
runs everything.
