# Clear the hosted stores around the mirror without hand-written scripts

Status: resolved
Type: task
Owner: claude (operator, 2026-11-27: "fix the skills and scripts")

Found while clearing the stores for ticket 01:

- The gate said only `MIRRORED unreadable (the mirror operator could not list the mirror)` when Snowflake refused the warehouse
  because resource monitor `EDGARTOOLS_PROD_MONITOR` was over quota. The cause took a separate script to find. Detaching the
  monitor from `COMPUTE_WH` did not lift it: the monitor still held the account.
- No committed command suspends, resumes or lists the mirror as the mirror operator. The skill names the procedures only.
- After `SUSPEND_MIRROR` the mirror's walsender and logical slot stayed active on the data database for minutes. The table reset
  refuses with a walsender connected, and its refusal says only "inspect the manifest and store configuration".

## Checklist

- [x] The gate's refusal keeps the Snowflake error number (never its text), and the skill says what 090073 means and how to find
  where the monitor is set: `test_a_refused_listing_names_snowflakes_error_number_and_nothing_of_its_text` (an invented account in the driver's text; the gate says `unreadable (Snowflake error 090073)`) (2026-11-27 15:09 ET)
- [x] `mirror_sql.py suspend|resume|status`, and a runner that runs a statement as the mirror operator and prints its rows as JSON: unit test of the three calls; live, `status | mirror_run.py` read `edgartools_mirror` SUSPENDED (2026-11-27 15:09 ET)
- [x] `reset-hosted-tables.py --wait-minutes`: waits for blocking sessions to leave; a refusal names what blocks it: unit tests (waits, refuses naming `walsender 1`, `main` exits 2 with it); live, read only, the query named `pg base extension worker 1, walsender 1` on the data database and nothing on the control database (2026-11-27 15:09 ET)
- [x] HOSTED-LOADS and HOSTED-MIRRORING name the commands of the clear in order: skill lints pass (2026-11-27 15:09 ET)
- [x] Tests: the affected unit tests pass: 89 passed (readiness, mirror SQL, table reset, five skill lints) (2026-11-27 15:09 ET)
- [x] `/code-review` (Standards, Spec, GoF), each on `risky-reviewer`: no hard violation; applied a negative error number shown as none, a missing login reported as not tried, 090073 named as any resource monitor, the QUIET check named in step 1, the runner renamed `run_as_mirror_operator`; left: a lock held by a session is refused by the database (55P03) without naming it (2026-11-27 15:09 ET)
- [x] Learning → skill: HOSTED-LOADS (090073 and an account-level monitor; the clear's five steps) and HOSTED-MIRRORING (suspend, status and resume commands; the wait for the walsender) (2026-11-27 15:09 ET)
