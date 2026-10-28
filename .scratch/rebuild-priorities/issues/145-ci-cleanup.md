# 145: Clean up the CI tests

Priority: 145. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 10:15 ET.

Type: task. Status: resolved (2026-10-28 11:53 ET).
Raised by the operator, 2026-10-28: "Can you clean up the CI tests"; then
"Merge #1197, then mine (Recommended)".

## Found (2026-10-28, the CI run of #1201, all green)

121 job-minutes per PR, about 20 on the clock. The slowest job, Skill adapter
(postgresql), took 19.6 of its 20 allowed minutes; Skill adapter (mysql) 15.9;
Integration 10.1; the eight installed-workflow jobs 4.5 to 7.6 each. Unit and
MDM ran as two jobs that installed the same thing (2.8 and 2.6 minutes). Two
jobs installed without `--frozen`; four installed PyMySQL and pymssql by hand,
unlocked; no job cached uv; every pytest printed each of about 4,000 tests.

## Parts

- [x] Codex's #1197 (retires 126 checkout cases the installed jobs already
  run, and one duplicate test): marked ready and updated onto `main`
  (2026-10-28, before 10:15 ET), merged on green: 10:24 ET, 21 checks
- [x] `ci.yml` (2026-10-28 10:15 ET): Unit, architecture and MDM tests in one
  job; every install `--frozen` with `--extra mdm` alone (it holds everything
  `mdm-runtime` and `s3` did); the database clients in the locked `dev` group,
  not `uv pip install`; uv's cache on in every job; `-q` in place of `-v`; two
  stale comments removed. Verified: the YAML loads (9 jobs), the tests that
  read `ci.yml` 6 passed, the clients import from the lock
- [x] PR, CI green, merge; job minutes and clock time measured against 121 and 20 (2026-10-28 11:53 ET): #1203 merged 10:51 ET, 20 checks; its run took 97 job-minutes and 10.3 minutes on the clock; the slowest jobs Integration 10.2, Skill adapter (postgresql) 9.9 (was 19.6), Skill adapter (mysql) 9.7 (was 15.9)
- [x] Learning → skill (2026-10-28 11:53 ET): CLAUDE.md test baseline: the database clients are in the `dev` group (no `--with pymysql`); none other
