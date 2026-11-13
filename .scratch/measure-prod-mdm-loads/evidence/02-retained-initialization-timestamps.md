# Evidence — retained initialization timestamps

Date checked: 2026-11-13. Read-only inspection of local retained evidence. No production
connection, no credential read, no write. All times given in UTC and ET (ET = UTC-5 on these
dates).

## Summary table

| Item | Found? | Value | Evidence |
|---|---|---|---|
| `CREATE POSTGRES INSTANCE` request start | **Yes** | 2026-11-10 18:31:51.570 PT / 2026-11-10 21:31:51.570 ET (2026-11-11 02:31:51.570 UTC) | `~/.local/share/edgartools/load-logs/measure-prod-readonly-20261112T180117Z/query-history-postgres.json` |
| `CREATE POSTGRES INSTANCE` request end | Yes | 2026-11-10 18:32:06.340 PT = 21:32:06.340 ET (02:32:06.340 UTC), `EXECUTION_STATUS = SUCCESS` | same file |
| Instance `created_on` | Yes | 2026-11-10 18:32:04.947 PT = 21:32:04.947 ET | `~/.local/share/edgartools/load-logs/measure-prod-fresh-report-20261112/show-postgres-instances.json` |
| Exact `READY` transition observation | **No** | — | searched below |
| Per-store migration durations | **No** | — | searched below |
| Migration command events (`mdm_command_started` / `_completed`) for MDM/Bookkeeping/Silver/Change Journal | **No** | only `build-lookups` events exist | searched below |

## 1. Instance request start and end — found

`query-history-postgres.json` (retained Snowflake query-history export, directory
`measure-prod-readonly-20261112T180117Z`) holds the exact statement:

```
START_TIME 2026-11-10T18:31:51.570000-08:00
END_TIME   2026-11-10T18:32:06.340000-08:00
QUERY_TEXT CREATE POSTGRES INSTANCE EDGARTOOLS_PROD_MDM ...
EXECUTION_STATUS SUCCESS
```

The query text is reproduced here in shape only (compute family, storage size, auth authority,
PostgreSQL version, network policy and comment are instance metadata already public in the
checked-in report; no credential or host value is included).

`query-history-postgres2.json` holds the same request under a second query id and the preceding
network-rule and network-policy statements at 18:31:37 and 18:31:38 PT.

**These timestamps are already carried in the retained snapshot**: the 2026-11-12 report's
`initialization.request_start_at_et` is `2026-11-10T21:31:51.570000-05:00` and
`request_end_at_et` is `2026-11-10T21:32:06.340000-05:00`. The fresh evidence confirms them.

The instance's own `created_on` (21:32:04.947 ET) sits inside the request window, two seconds
before the statement ended — the instance existed before the `CREATE` returned.

## 2. Exact READY transition — not found

Searched for a retained observation of the instance reaching `READY`:

- `SHOW POSTGRES INSTANCES` runs are present at 2026-11-10 18:30:24 PT (before creation),
  2026-11-11 19:07:15 PT and 2026-11-12 09:53:53 PT. Only the **latest** (2026-11-12 11:53:53 ET)
  has a captured result, and it reads `state = READY`.
- `DESCRIBE POSTGRES INSTANCE` runs are present at 18:32:06, 18:32:41, 18:34:17, 18:34:34,
  18:35:42, then 2026-11-11 18:46:51, 18:55:32, 18:55:59, 18:56:30, 19:24:41, 19:29:28 PT. **No
  result body was retained for any of them**, so no `state` value at any of those moments is known.
- No load-log file contains a `READY` line for `EDGARTOOLS_PROD_MDM`
  (`grep -h -o "EDGARTOOLS_PROD_MDM.\{0,120\}" *.log | grep -i ready` returns nothing).
- The only retained `state` value is the 2026-11-12 11:53:53 ET observation.

**Conclusion:** the earliest provable observation of `READY` is the 2026-11-12 11:53:53 ET
`SHOW POSTGRES INSTANCES`; the *transition* time is unavailable. The report field
`ready_transition_at_et` stays `null` with `unavailable_reason = "Exact READY transition
observation absent."` — the same wording the 2026-11-12 snapshot used. A
`ready_observed_at_et` field may carry 2026-11-12 11:53:53 ET **labelled as an observation, not a
transition**.

## 3. Per-store migration durations — not found

- The retained `create-instance.json` is credential-bearing and was **not** read raw; only its size
  (3695 bytes) and modification time were taken.
- `create-instance.err` is **0 bytes** — no error output, and no migration event trail.
- The Snowflake query history contains no `mdm migrate` statement; migrations ran against the
  Postgres endpoint, not through Snowflake SQL.
- The retained 2026-11-12 snapshot records `migration_durations = null` with
  `migration_unavailable_reason = "Migration records lack per-migration timestamps."` — a prior
  verified finding, unchanged by this check.

**Conclusion:** `migration_durations` stays `null` with that reason. No migration may be re-run to
manufacture timings.

## 4. MDM command events — only `build-lookups` exists

A scan of every private load log for `mdm_command_started` / `mdm_command_completed` finds **5
events in 3 files**, all of them `build-lookups`:

| File | Event | UTC |
|---|---|---|
| `hosted-lookups-attempt-1.log` | `mdm_command_started` (`build-lookups`) | 2026-11-12 18:06:07.216571Z |
| `hosted-lookups-attempt-1.log` | `mdm_command_completed` (`build-lookups`, `duration_ms` 856899, exit 0) | 2026-11-12 18:20:24.142347Z |
| `hosted-lookups-loop.log` | `mdm_command_completed` (duplicate of the above) | 2026-11-12 18:20:24.142347Z |
| `reload-20261112-lookups-b.log` | `mdm_command_started` (`build-lookups`) | 2026-11-13 15:07:12.126551Z |
| `reload-20261112-lookups-b.log` | `mdm_command_completed` (`build-lookups`, `duration_ms` 947669, exit 0) | 2026-11-13 15:22:59.778524Z |

No `mdm migrate` event exists for MDM, Bookkeeping, Silver or Change Journal. Those command
events belong to a lookup build, which is **not** part of initialization.

## Consequence for the report

The `initialization` section can hold:

- `request_start_at_et` — 2026-11-10 21:31:51.570 ET (exact, from the Snowflake operation log);
- `request_end_at_et` — 2026-11-10 21:32:06.340 ET (exact);
- `instance_created_on_at_et` — 2026-11-10 21:32:04.947 ET (exact);
- `ready_transition_at_et` — `null`, reason: exact READY transition observation absent;
- `ready_observed_at_et` — 2026-11-12 11:53:53 ET, labelled as the earliest retained observation;
- `migration_durations` — `null`, reason: migration records lack per-migration timestamps.

`end_to_end_from_init_seconds` therefore stays `null`: the initialization *duration* cannot be
computed (no READY transition), even though the request start is now exact. The report keeps the
verified-baseline interval (`baseline_at_et` → `end_at_et`) as its elapsed measure, exactly as the
plan requires.
