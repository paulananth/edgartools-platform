# Make the Clean MDM database tests fast

Type: task
Status: in progress (Claude, branch `claude/company-mastering-23-fast-database-tests`)
Blocked by: nothing
Blocks: nothing; it shortens every later ticket's test run (ticket 17 first)

## Why

Operator, 2026-09-29: "Why tests are taking over 10 min". Measured the same
day (`tests/integration/test_clean_*.py` at ticket 13's head):

- Every PostgreSQL 16 test rebuilt the Clean MDM schema from nothing: drop
  it, run all 19 migrations, run them again to check a rerun installs
  nothing. About **3.4 seconds per test**, before the test's own work.
- About 150 such tests: **8 to 9 minutes of setup**, about half of a full
  run (13 to 17 minutes, all tests one at a time).
- Each of the 10 test files starts its own PostgreSQL container: 15 to 25
  seconds each.

## Change

Each module's first test migrates a **template database** once, with the
same double-migration check. Every test then gets its own copy
(`CREATE DATABASE … TEMPLATE`), dropped after it. The `database` fixture
keeps its shape, so no test changes. Tests that start from an older
migration on purpose (`initialize_database` under a patched migration list)
keep their own path on the container's base database.

## Checklist

- [x] The template and per-test copy in `tests/integration/test_clean_mdm_postgres.py`.
- [x] Time the Clean PostgreSQL tests before and after, on the same machine
  (2026-09-29): **6:09 before, 3:40 after**, 142 passed and 1 xfailed each
  time. The machine was busy for both runs; a quiet re-run was stopped by
  Claude Code for low memory. A second run of the same code took 4:36, so
  runs vary by a minute or more.
  - What remains: each test file's own container start (10 to 15 seconds,
    10 files) and the tests' own work. Sharing one container across files
    needs the fixture in a `conftest.py`; a session scope inside a test
    module is registered once per importing module, so it gained nothing
    and was reverted.
  - The idle OpenMetadata stack (Elasticsearch and two services, about a
    third of the Colima VM's CPU and 2.6 GB) was stopped;
    `docker compose -p edgartools-catalog -f infra/openmetadata/docker-compose.yml start`
    brings it back.
- [ ] Full suite green; PR; CI; merge on the operator's word.

## Not in scope

- Running tests in parallel (`pytest-xdist`): a later step if still needed.
