# A read-only database monitoring skill

Status: open
Type: task

Operator: "create a database monitoring skill that can be used by data operation monitoring performance locks using read only accounts".
The hosted instance holds six stores; a load that looks stuck needs its connections, lock queues, long transactions, costliest
statements and table churn read without any login that can write.

Operator, later: "must check postgress logs for errors or memory errors". The log is in the account's event table, which the
Postgres login cannot read, so `logs` reads it through a SnowCLI connection whose role must be read-only.

## Parts

- [x] Skill `skills/database-monitoring/` with its hard stops, the readings and how to read a stuck step (portability and no-date lints pass, 2026-11-19 06:13 ET)
- [x] `scripts/db_monitor.py`: `summary`, `locks`, `sessions`, `statements`, `tables`, `all`, as the diagnostic login in a read-only session with a statement timeout; refuses a superuser; replaces literals in statements (tests/unit/test_db_monitor.py: 7 passed)
- [x] Run live on the hosted instance as the diagnostic login: every reading returned (78 of 500 connections, one advisory-lock waiter behind a merge, statements and tables listed) with no address printed (2026-11-19 06:13 ET)
- [x] data-operations points at it from its diagnosis paragraph, and the skills README lists it (the file stays under the 500-line cap)
- [x] Learning → skill: this ticket is the skill; data-operations' diagnosis paragraph names it
- [x] `logs`, `memory` and `databases` readings; `logs` refuses an administrator role, keeps level-marked and memory lines, drops DETAIL/STATEMENT/CONTEXT, and replaces addresses and literals (tests/unit/test_db_monitor.py; the log query run once on the hosted instance returned grouped errors and the out-of-memory lines, 2026-11-19 06:21 ET)
- [ ] Create the read-only log role (USAGE on a warehouse, SELECT on the event table only) and a SnowCLI connection for it: an account change, waits for the operator's word
- [ ] Run `logs` live as that role (today's connection is `ACCOUNTADMIN`, which the script refuses)
