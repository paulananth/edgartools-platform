# Hosted loads: what stops them, and how to resume

Read before starting or resuming a load on the hosted instance. Each item is a cause met on a real load and its rule.

## Before a load starts
- **Role guards first.** `infra/scripts/harden-hosted-roles.py --confirm` (owner login) gives every login a connection limit,
  statement and idle-transaction timeouts, a `work_mem` ceiling for the loader and the audit classes. A load with the
  instance's default `work_mem` (hundreds of MB per sort or hash step and session) ran the server out of memory with ten
  merge workers. The access-audit skill tests these guards.
- **The engine must match the code.** A Rust change reaches a load only after the engine is rebuilt into the environment that
  runs it (`uv pip install --reinstall ./crates/source-contract` for a venv used with `PYTHONPATH`). A step that fails with a
  missing method or an unknown normalizer on today's `main` is a stale engine, not a data fault: rebuild, then resume.
- **`EDGAR_WAREHOUSE` names the executable** (`.venv/bin/edgar-warehouse`), never its folder: a folder fails with
  "Permission denied" on every step.

## While a load runs
- **One scheduler per run label.** A second `load_chain.py --auto` on the same label doubles every step. Look for a running
  scheduler (`ps`) before starting one, and stop the scheduler before its steps.
- **Read the database with the database-monitoring skill**: `summary` and `locks` every check,
  `logs` after any step that stops with a database error.
- **A scheduler that "stopped" has usually finished everything it could**: it names the failed steps and what waits on them.
  Fix the cause (engine, memory, a login), then start it again; done steps cost one call each.

## Stopping loads
- Stop the scheduler first (it would start the next step), then its step processes. The state file keeps every done step.
- A reset of the stores (`reset-hosted-databases.py --confirm`) refuses while any session is connected: confirm none runs
  (`summary`) before it, and expect the previous run's done steps to be set aside as another store's state.
