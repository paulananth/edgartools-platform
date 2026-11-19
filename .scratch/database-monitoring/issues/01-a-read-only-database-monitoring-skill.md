# A read-only database monitoring skill

Status: resolved
Type: task

Operator: "create a database monitoring skill that can be used by data operation monitoring performance locks using read only accounts".
The hosted instance holds six stores; a load that looks stuck needs its connections, lock queues, long transactions, costliest
statements and table churn read without any login that can write.

## Parts

- [x] Skill `skills/database-monitoring/` with its hard stops, the readings and how to read a stuck step (portability and no-date lints pass, 2026-11-19 06:13 ET)
- [x] `scripts/db_monitor.py`: `summary`, `locks`, `sessions`, `statements`, `tables`, `all`, as the diagnostic login in a read-only session with a statement timeout; refuses a superuser; replaces literals in statements (tests/unit/test_db_monitor.py: 7 passed)
- [x] Run live on the hosted instance as the diagnostic login: every reading returned (78 of 500 connections, one advisory-lock waiter behind a merge, statements and tables listed) with no address printed (2026-11-19 06:13 ET)
- [x] data-operations points at it from its diagnosis paragraph, and the skills README lists it (the file stays under the 500-line cap)
- [x] Learning → skill: this ticket is the skill; data-operations' diagnosis paragraph names it
