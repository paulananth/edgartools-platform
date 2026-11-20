---
name: database-monitoring
description: Watches the performance, locks and server log of the hosted PostgreSQL instance as read-only logins - connections, sessions waiting on locks and who blocks them, long transactions, the costliest statements, table churn, memory settings and the log's errors and out-of-memory lines. Use while a load runs, when a step looks stuck or slow, or before changing a worker count; never to change anything.
---

# Database monitoring

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

Reads the one hosted instance (six stores: `mdm`, `rdm`, `rules`, `bookkeeping`, `change_journal`, `silver`) through its
**diagnostic login**: a member of `pg_monitor` that cannot write, never the owner, the loader or a runtime login. It tells
[data-operations](../data-operations/SKILL.md) why a load is slow or stopped. It never fixes: a kill, a vacuum, a setting
or a worker change is the operator's call, made in data-operations.

## Hard stops

| Never | Instead |
|---|---|
| Connect as the owner, the loader or a runtime login to look | The diagnostic login (`DATA_URL` and `CONTROL_URL`, in the stores folder's `reader.env`) |
| Print the address, a password or a login's URL | The script prints none; do not echo the environment |
| End a session, cancel a query, vacuum, or change a setting | Report the finding; the operator decides |
| Paste a statement's literals, or a log's DETAIL, STATEMENT or CONTEXT lines (they quote values from the data) | The script replaces literals and drops those lines; keep it that way |
| Read the server log as an administrator role | The read-only log role (see Postgres logs) |
| Loop faster than the run changes | One reading every 30 minutes for a run already going |

## Setup

```bash
set -a; . ~/.config/edgartools/hosted/reader.env; set +a   # the stores folder; never print it
python scripts/db_monitor.py summary   # from this skill's folder
```

The script uses a read-only session with a 15 s statement timeout and refuses a superuser. `--database NAME` reads another
store (statements and table churn are per database; sessions and locks cover the whole instance). `--json` prints one
object per reading.

## What to read, in order

| Question | Command | What a number means |
|---|---|---|
| Is the instance pressed? | `summary` | `connections` against `max_connections`; `waiting_on_locks` of 3 or more is pressure (one waiter is normal); `idle_in_transaction` that stays high holds locks and blocks vacuum |
| Who waits on whom? | `locks` | One row per waiting session and its blocker: the lock kind (`advisory` is a merge's value or kind claim; `relation` and `transactionid` are row or table locks), `waited_s`, and the blocker's state and transaction age. A blocker `idle in transaction` is a stuck client; an `active` one is working |
| What is long? | `sessions --min-seconds 60` | Statements and transactions running at least that long, with the wait kind and event (`Lock`, `IO`, `Client`) |
| What costs most? | `statements --by total` (also `mean`, `calls`) | `total_s` is where the time went; `mean_ms` with few calls is one slow statement; many calls at 1-2 ms is a chatty client. `blocks_read` against `blocks_hit` says cold reads against cache |
| Which table churns? | `tables` | `dead` rows high with an old `last_autovacuum` means bloat; a large `seq_scan` against `idx_scan` on a big table means a missing index |
| Can the memory settings overrun the machine? | `memory` | `work_mem` is per sort or hash step, per session: `work_mem_if_each_active_sorts_once_mb` is a floor, since one query can hold several steps; compare it with the instance size, `shared_buffers` included |
| Which store spills or rolls back? | `databases` | `temp_mb` and `temp_files` are sorts and hashes that did not fit `work_mem`; `deadlocks` and a high `rollbacks` against `commits` name the store to look at |
| What did the server log? | `logs --minutes 60` | See Postgres logs |
| Is it costing more than it should? | `budget` | See Cost watch |
| All of it | `all` | Every reading above (the log only when its connection is set) |

## Postgres logs

The hosted server writes its log to the account's event table (read through `SNOWFLAKE.TELEMETRY.EVENTS_VIEW`, log type
`postgres-otelcol-vm-agent`, one row per log line, keyed by the instance id, a few minutes late). The diagnostic Postgres
login cannot read it; `logs` reads it through a SnowCLI connection:

```bash
export MONITOR_SNOWFLAKE_CONNECTION=<a connection whose role reads only the event table>
python scripts/db_monitor.py logs --minutes 120
```

- **A read-only role.** The connection's role holds `USAGE` on a warehouse and `SELECT` on the event table, nothing else
  (the role holds Snowflake's `EVENTS_VIEWER` application role, which grants `SELECT` on that view and not on the table itself; its user is a key-pair service user, so no password exists). The script reads `current_role()`
  first and refuses `ACCOUNTADMIN`, `SECURITYADMIN`, `SYSADMIN`, `USERADMIN` and `ORGADMIN`. Creating that role is an
  account change: the operator says so first (aws-snowflake-operations).
- **What it keeps.** Lines that carry a level (`PANIC`, `FATAL`, `ERROR`, `WARNING`) and the memory and kill lines, grouped by
  message with a count and the first and last time: `memory` first, then `fatal`, `error`, `warning`.
- **Memory lines.** `out of memory`, `could not resize shared memory`, `terminated by signal 9` (the system's kill),
  `invalid memory alloc request`, `cannot allocate memory`, `could not fork new process`, and the connection-exhaustion lines
  (`remaining connection slots are reserved`, `too many clients`). One of these within a step's run window is that step's
  cause until shown otherwise: read `memory` and `databases` beside it, and lower the step's workers before retrying.
- **What the common ones mean.** `canceling autovacuum task` is vacuum yielding to a lock: harmless alone. `duplicate key
  value violates unique constraint` is a writer racing another (expected for claims, a defect for anything else).
  `Snowflake authentication failed` for a runtime login is a wrong or rotated password in a run's env file; for `postgres`,
  `admin`, `root` or `test` from an address that is not ours it is a probe, and `pg_hba.conf` refusing it is the right outcome:
  report the count and the times to the operator, never the address.
- The log can hold what a failed statement quoted; the script drops those lines, so never read the table by hand to
  "see more".

## Cost watch (no Snowflake resource monitor)

A resource monitor needs an account role this skill never holds, and it does not govern a hosted Postgres instance. `budget`
is the cheap stand-in, using only the diagnostic login: one reading of pressure and size, one line appended to a local
history file (`--history`, mode 0600), and each limit given that the reading has reached.

```bash
python scripts/db_monitor.py budget --rate <cost per hour of the instance> --limit-budget <spend to stop at> \
  --limit-connections-pct 80 --limit-longest-transaction-s 3600 --limit-size-mb <cap> --limit-temp-mb <cap>
```

- Run it at the run's 30-minute check (or from a `/loop`); it exits 1 and prints `OVER: ...` when a limit is reached, and
  prints nothing else of note when all is well, so a quiet check sends no message.
- Spend is estimated: hours since the history's first line times `--rate`. Delete the history to start a new clock.
  A reading never stops or changes anything; the operator decides (a stopped instance is their call).
- A limit left out is not checked. Sensible first limits: connections 80%, a transaction over an hour, the stores' size at
  the disk you are willing to pay for, and spilled MB growing run over run.

## Reading a stuck or slow step

1. `summary`: pressed or not? If `connections` is near the limit, the workers or the scheduler's target is too high.
2. `locks`: if waiters exist, follow `blocker_pid`. Many waiters on one advisory lock are a queue behind one holder (the
   merge locks); a blocker idle in a transaction is a client that did not commit.
3. `sessions`: an `active` session on `IO` is the disk; on `Client` the worker is the bottleneck, not the database.
   `logs`: a memory line in the window means memory, whatever the step's own message says.
   A step that dies with `out of memory` is `work_mem` times its sort and hash steps times its sessions against the
   instance's memory: `memory` shows the setting, and the fix is a role-level `work_mem` ceiling for the loader and fewer
   workers, never a retry at the same size.
4. `statements`: the top total is the target to fix; compare two readings a few minutes apart, because the counters are
   cumulative since the last reset (a single reading shows history, not now).
5. Report the numbers with what they mean, as counts: the waiting sessions, the longest wait, the blocker's state. Then
   hand the finding to data-operations (worker count) or the owning ticket (a query or lock to change).

## Limits

- Statement text from `pg_stat_activity` is cut at 70 characters and has its literals replaced.
- `statements` needs the `pg_stat_statements` extension, present on the hosted instance; a store without it fails the
  reading, not the others.
- The login sees sessions of every store on the instance; `pg_monitor` shows no table rows.
- `logs` lags a few minutes and needs the read-only role; without it every other reading still works.
- A reading is a moment: a lock held for a second does not show. Repeat before concluding anything.
