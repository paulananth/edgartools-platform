---
name: database-monitoring
description: Watches the performance and locks of the hosted PostgreSQL instance as a read-only login - connections, sessions waiting on locks and who blocks them, long transactions, the costliest statements, table churn. Use while a load runs, when a step looks stuck or slow, or before changing a worker count; never to change anything.
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
| Connect as the owner, the loader or a runtime login to look | The diagnostic login (`DIAGNOSE_DATABASE_URL`, in the stores folder's `reader.env`) |
| Print the address, a password or a login's URL | The script prints none; do not echo the environment |
| End a session, cancel a query, vacuum, or change a setting | Report the finding; the operator decides |
| Paste a statement's literals (they are values from the data) | The script replaces literals; keep it that way |
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
| All of it | `all` | The five readings in one pass |

## Reading a stuck or slow step

1. `summary`: pressed or not? If `connections` is near the limit, the workers or the scheduler's target is too high.
2. `locks`: if waiters exist, follow `blocker_pid`. Many waiters on one advisory lock are a queue behind one holder (the
   merge locks); a blocker idle in a transaction is a client that did not commit.
3. `sessions`: an `active` session on `IO` is the disk; on `Client` the worker is the bottleneck, not the database.
4. `statements`: the top total is the target to fix; compare two readings a few minutes apart, because the counters are
   cumulative since the last reset (a single reading shows history, not now).
5. Report the numbers with what they mean, as counts: the waiting sessions, the longest wait, the blocker's state. Then
   hand the finding to data-operations (worker count) or the owning ticket (a query or lock to change).

## Limits

- Statement text from `pg_stat_activity` is cut at 70 characters and has its literals replaced.
- `statements` needs the `pg_stat_statements` extension, present on the hosted instance; a store without it fails the
  reading, not the others.
- The login sees sessions of every store on the instance; `pg_monitor` shows no table rows.
- A reading is a moment: a lock held for a second does not show. Repeat before concluding anything.
