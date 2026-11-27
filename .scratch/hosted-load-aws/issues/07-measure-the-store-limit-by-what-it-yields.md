# Measure the store limit by what it yields

Status: resolved
Type: task
Owner: claude (operator, 2026-11-27: "build the lean version on its own branch")

The operator asked why the load used 4 lanes when they read 8, and proposed bounding the load by the database's connections and
rows written, not only its CPU and memory; then "use 7 wastes and 5 whys".

## 5 whys

1. Only 4 lanes ran: the store's limit is 8 workers and the 4 running steps held 2 each (17:56 ET).
2. 8 workers: four a core on `STANDARD_L` (2 cores), a fixed rule.
3. Is 8 wrong? Not for this database: its CPU was 8% idle at 17:50 and 17:55 ET (92% before the load); lock waiters 0.4 to 0.6.
4. It looked like spare lanes: Grafana's "Lane budget" said 2 (8 workers over the widest first step's 4), and the state file speaks
   of lanes; the limit is workers.
5. The limit is a fixed rule never measured against the database, shown in lanes, not workers: nothing says whether it pays.

## The seven wastes on a feedback controller (raise while rows a minute rise)

- Over-production: at 92% database CPU it would find today's 8.
- Defects: rows a minute moves with the mix of steps running and counts a row only at its commit, so a controller acting on it
  raises and sheds on noise.
- Motion: a second set of database readings beside the exporter's and the status's.
- Transport: the database's CPU is readable only through Snowflake, a login the task does not hold.

So: measure first; the controller waits for a measurement that shows headroom at the limit.

## Checklist

- [x] The controller writes `store <name>: W of L workers in use; rows written a minute: ...; N waiting on locks` to the state file every ten minutes, one reading of the stores' counters a window: `test_the_store_line_gives_the_workers_in_use_the_rows_a_minute_and_the_lock_waiters_every_ten_minutes`, `test_a_load_that_names_no_store_writes_no_store_line` (2026-11-27 18:13 ET)
- [x] Grafana shows "Workers running" against "Worker limit" (its legend names store, memory or vcpu), not lanes; the exporter publishes `load_worker_budget{limit}` and `load_workers_running` only (2026-11-27 18:13 ET)
- [x] Tests: load jobs and load monitoring, 296 passed (2026-11-27 18:13 ET)
- [x] Live: the store line read twice ten minutes apart on the running load `aws-20261127` (workers in use given as 8): the first reading wrote no line, the second at 18:13 ET read `store hosted: 8 of 8 workers in use; rows written a minute: bookkeeping 6, change_journal 1,111, mdm 28,884, silver 101,451; 0 waiting on locks` (2026-11-27 18:13 ET)
- [ ] ~~A step that needs every worker lets shorter steps use the workers left while it waits~~ deferred to a follow-up ticket: `gleif` (8 workers, one document) waited about 2 minutes at 18:08 ET with 6 of 8 free behind `ownership-silver`'s 2; one step remained after it, so not worth changing in this run
- [x] `/code-review` (Standards, Spec, GoF; one `reviewer` agent on all three axes). GoF: leave it. Fixed: a store read that failed set an empty baseline, so the next line said "rows written a minute: none" (now the window stays open from the last reading: `test_a_store_that_could_not_be_read_writes_no_line_and_keeps_its_window_open_from_the_last_reading`, which on the old code failed with "rows written a minute: none" where `mdm 6,000` was due); an unreadable lock count was shown as 0 (now "lock waiters unknown": `test_a_lock_count_that_could_not_be_read_is_said_unknown_never_zero`, which on the old code failed its `endswith("; lock waiters unknown")`); the lanes figure no reader uses (`lanes_at_once`, `--lanes-at-once`, the budget's `lanes`) removed and `lane_budget` named `worker_budget`; HOSTED-LOADS and load-monitoring no longer speak of lanes against a budget. Cost noted, not changed: one parse of the load jobs file and one connection per store database every ten minutes (2026-11-27 18:13 ET)
- [x] Operator, 2026-11-27: "update skill load balanensing and data operations must work together": HOSTED-LOADS "Balancing a load: one worker limit, three skills" (data-operations sets, holds and changes the limit; load-monitoring shows it; database-monitoring reads the database's CPU, memory and log), and the handshakes of data-operations, load-monitoring, database-monitoring and OWNERSHIP point at it in the same words; skill lints pass (2026-11-27 18:13 ET)
- [x] Learning → skill: load-monitoring (the worker limit, judged by rows a minute and the database's CPU, never the compute's idle CPU) (2026-11-27 18:13 ET)
