# 04: What the first hosted load with every lane at once found

Status: open
Type: bug
Blocked by: none
Blocks: none

Found on `hosted-lanes-20261125` (image `4bbeaefc`, OrbStack at 6 GB, 8 cores), the first full hosted reload with every lane
started at once, the memory gate and the lane controller (ticket 03). Clear and load: operator, 2026-11-25, "start the new
load", then "I'll apply Codex's plan"; OrbStack raised to 6 GB: "yes raise to 6 GB and restart".

The load finished: 30 of 30 steps, then the links build (417,640 links, 4,459,121 bindings). Start 21:08 ET (restarted 21:14 for
the OrbStack change), last step 05:06 ET, finish 07:47 ET. The run before it (`hosted-reset-20261125`, 2 lanes at once, image
`5ba5ad73`) took 317 min for the steps and 7.8 min for the finish. Every document count compared matched that run.

## Findings, each with what was measured

1. **A one-document step admitted at half its workers stays at half.** `gleif` waited for memory and started with 4 of its 8
   workers (22:34 ET); the controller may not move a step of one document (a move abandons it), so it ran its first attempt at 4
   and was stopped by its 240-minute bound in the source reading (02:34 ET). The run before took 110 min at 8 workers.
2. **The controller moved `openfigi-answers` six times** (21:12 to 00:37 ET), five sheds and one raise (00:21, 2.6 GB free) shed
   again 16 min later. Each move abandons the run in flight. `movable` passed it because its log names 3 runs, each one long read.
   It took 6 h 24 min against 37 min before; no document was lost (7,730, as before).
3. **One step was killed for memory**: `openfigi-answers`' source reading (`rules run --source openfigi`, status -9; the VM's
   global `oom-kill` about 22:10 ET by its kernel log, holding 0.86 GB `anon-rss`; the attempt reported it at 22:51, after its
   other bundles). It was admitted at 21:09 with 4 workers (2.0 GB at 0.5 GB a worker, more than it held when killed); the kill
   came after other steps were admitted into memory it was still growing into. The gate read free memory now, not what a running
   step had yet to reach.
4. **The hosted store dropped connections five times** (`adv-funds`, `person` and `gleif`'s attempt 2 were the store
   ending a session idle in its transaction for over 10 minutes; the links build's was logged by the store only as the client
   gone: see the store's monitoring below): `adv-funds` (23:08), `person` (23:13) and the links build (05:07) with
   `SSL connection has been closed unexpectedly` / `SSL SYSCALL error: EOF detected`; once silently: `gleif`'s attempt 2 had
   finished its document and then waited on a socket the store no longer held (no session in `pg_stat_activity`, the kernel's
   socket established with empty queues, keepalive timer about 40 min away). It was ended by hand at 04:54 ET (the same stop its
   bound would have made at 06:34); attempt 3 found the document loaded. The engine's connections kept the operating system's
   keepalive: libpq turns it on, and the kernel first probes after 2 hours idle, then every 75 s, 8 times.
5. **A failed links build reports success**: `links rc=1` was followed by `chain done`, and `load.sh` exited 0 (05:07 ET).
6. **The writes were held by this machine's upload, not by the store**: MDM writes fell from about 100,000 rows a minute to about
   10,000, the long steps' processes waited at 0 to 10% CPU, and the links build took 146 min against 7.8 before. The store's own
   monitoring (below) shows it was not the limit; one connection's upload from this machine was, and that rate varies.
7. **Exited workers are not reaped**: about 100 zombie `python` processes in the worker container, children of moves and stops,
   whose parent is the activity worker as PID 1.
8. **The links differ slightly from the run before**: 417,640 links (+797) and 4,459,121 bindings (−1,119) from the same captures.
9. **The loader's login was refused six times** (`Snowflake authentication failed`, user `edgar_loader`): once on `control` at
   21:41 ET and five times on `data` (22:44, twice at 22:54, twice at 23:05 ET), minutes before the `adv-funds` and `person` drops;
   the same env file's logins worked before and after. At 21:41:54, the second of the `control` refusal, the store logged
   `Connection reset by peer` on dozens of loader sessions on `data`, `control` and `config` at once: the same second the
   controller shed `openfigi-answers` (its move ends the step's load and its workers), as at 21:12:41, its first shed.

## What the store's own monitoring shows (finding 6, read 2026-11-26)

Read with the diagnostic login (`pg_stat_*`, `pg_stat_statements`, `pg_db_role_setting`) and the read-only log login (the
account's event table: the instance's metrics by minute and its server log), the exporter's Prometheus history, timed uploads and
downloads, and a live rerun of the links build alone (08:55 ET, stopped at 09:25 once read).

- **The store was not pressed.** The instance is an AWS `m8g.medium` in us-east-2: 1 vCPU, 4.2 GB, a fixed-performance type
  (no burst credits). Hour by hour from 21:00 to 08:00 ET it was 46 to 83% idle (25% at 03:00, its busiest hour), steal 0,
  disk wait at most 21%, swap flat at about 260 MB. Transactions waiting on a lock averaged 0 to 1.4 an hour (none after 02:00).
  Its sessions mostly waited on the client: 1 to 10 `data` sessions idle against 0 to 4 active.
- **This machine was idle too**: load 0.00 to 0.14 a core from 23:30 ET (the exporter's `load_machine_load_per_core`). Packet loss
  on its path is not measured: macOS shows its TCP counters only to an administrator.
- **The links build read in 4 minutes and wrote for 140.** The store sent it 1.8 to 7.5 MB/s from 05:22 to 05:25 ET (the scan of
  the records table, 11.4 GB), then received 695 MB at 5 to 100 KB/s until 07:46 ET while the build landed its rows on one
  connection. The rerun did the same: the scan ended in about 5.5 min, and landing ran at 50 to 380 KB/s with the client blocked
  sending a batch (about 2.2 MB in its socket's send queue, the store waiting in `ClientRead`, the client's stack in `do_execute`
  of the landing merge, `relational.py:183`).
- **One connection's upload from this machine varies, and is low now.** The 7.8-min build of the run before landed on one
  connection at 1.6 to 2.4 MB/s (19:11 to 19:13 ET, 11-25), against 5 to 100 KB/s overnight. This morning, one connection to the
  store sent its first 4 MB at 2.2 to 2.9 MB/s and 32 MB at 0.36 MB/s; one 32 MB upload to Apple's speed-test server ran at
  0.34 MB/s, three at once at 0.48, 0.58 and 0.68 MB/s each, and many at once (macOS `networkQuality`) at 88 Mbps up and 289 down,
  with a 100 ms base round trip. Downloads from the store ran at 23 to 33 MB/s on one connection. So a write's rate follows its
  connections: one lane's 8 or so `data` sessions (`load_lanes_running` 1 from 02:30 ET) gave the store 1.5 to 2.5 MB/s from 02:41
  to 04:05, about 0.25 MB/s each; it fell to near 0 by 04:20 when that lane's writes ended (`gleif` attempt 2 finished its document).
- **Production runs in AWS, not over this machine's connection**, so this upload rate is a figure of this machine's loads only:
  no engine change follows from it.
- **Three of finding 4's drops are the store's own kills.** The loader login's `idle_in_transaction_session_timeout` is 10 min
  (`infra/scripts/harden-hosted-roles.py`). The server log ended six `edgar_loader` sessions on `data` for it: 23:08:24
  (`adv-funds` failed 23:08:27), 23:13:14 (`person`, 23:13:17), 00:52:20, 02:33:19 and 02:34:42 (`gleif` attempt 1, 02:34:16),
  and 04:29:44 (`gleif` attempt 2, the silent one: the client never saw the close; its writes had ended about 10 minutes before).
  The links build's drop is no kill: the store logged only `connection to client lost` at 05:07:12, after the build's `rc=1` at
  05:07. What each client did inside the open transaction is below.

## What each killed session was doing (finding 4, read 2026-11-26)

Read from each session's lines in the store's server log (process id, session start, the transaction id, statements over
2 s), the failed steps' error files, and the instance's network metric by minute. The store's own keepalive is 2 s idle, then
every 2 s, 4 times (`tcp_keepalives_*`), so a client host that vanished is noticed in seconds and logged as a reset, not as an
idle transaction.

- **`adv-funds` (23:08:24), `person` (23:13:14) and `gleif` attempt 2 (04:29:44): an insert in flight.** Each client's error
  file shows it inside `cursor.execute` of a multi-row insert when the close came: `write_masters`' insert into the golden
  records (`adv-funds`, `gleif`) and `add_deferred`'s insert (`person`), each up to 2,000 rows a statement (`BLOCK`). The store
  meanwhile waited 10 minutes for that client's next message. So no client work sat inside the transaction: the statement
  stopped arriving on that one connection while the store's other connections still received 1.2 to 2.4 MB/s (median of each
  minute's total, the 10 minutes before the first two kills) and about 140 KB/s (before `gleif`'s). `person`'s session had no
  transaction id: its first write never landed, 10 minutes after it connected. `adv-funds` and `person` saw the close 3 s after
  the kill; `gleif`'s client did not until it was stopped by hand at 04:54, when its error file was written.
- **00:52:20, 02:33:19 and 02:34:42: three sessions opened together at 23:07:17**, alive 1 h 45 min to 3 h 27 min, each with
  a transaction id (it had written), last logged statement a 2.2 to 2.3 s read of `mastering_record`. Their client wrote no
  error: `gleif` attempt 1 ended at its bound (02:34:16), so the client of the 00:52 kill never noticed it for 1 h 42 min, and
  the store logged the 02:34:42 kill 26 s after that stop, so the stopped client's close never reached it either. Which step
  opened them, and what each was sending, is not read: the store was emptied at 10:18 ET today, and its log keeps no statement
  under 2 s.
- **The links build (05:07:12) is a different failure.** The session opened at 05:06:16, ran a 32 s `FETCH FORWARD 50000` of
  its records scan, and then the store's send to the client timed out (`could not send data to client: Connection timed
  out`): the path stopped acknowledging the store's data within a minute.

These point at the path between this machine and the store rather than at the store or the engine's transactions (a
connection's traffic stops while its neighbours flow, and a close is lost in either direction); the cause is an open part.
The client's keepalive bounds a connection whose path no longer answers to about two minutes; it does not bound a
connection whose path still answers probes while its data stalls.

## Parts

- [x] A step whose work is one document starts with its declared workers or waits for them (finding 1): a step marked `one_document: true` in `rules/load-jobs.yaml` (`gleif` and `gleif-pairs`, each the one publisher file, `1 documents in 1 bundles` in last night's logs) is admitted only with all its workers, with no other load running starts with all of them, and is never moved by the controller (`test_the_controller_never_moves_a_step_declared_one_document`, on the old code `{'long'} <= set()`); while it waits it holds the admission lock, so steps of other lanes wait behind it, as they did behind its half; `test_a_step_of_one_document_waits_for_all_its_workers_since_it_can_never_be_raised_later` (on the old code `TypeError: admit() got an unexpected keyword argument 'one_document'`) and `test_a_step_declared_one_document_is_admitted_as_one` (`[False, False] == [True, False]`); the count is declared because the load knows it only after its source extract is prepared (2026-11-26 12:57 ET)
- [x] The controller moves a step only between runs, never one it shed earlier in the same attempt (finding 2): a shed, like a raise, comes only within a minute of a bundle completing (`worth_moving`), and a step a move took workers from in its current attempt (`shed_this_attempt`, read from the state file, and the `--auto` scheduler's own record) is never moved again in it; `test_a_step_shed_in_this_attempt_is_read_from_the_state_file_and_a_new_attempt_clears_it` (on the old code `AttributeError`), `test_the_controller_never_moves_a_step_it_shed_earlier_in_the_same_attempt` (`['long'] == ['short']`), `test_a_pressed_machine_sheds_the_step_with_the_shortest_chain_and_the_next_shed_lands_on_another_step` (`('short', 2) != ('long', 4)`) and the in-flight shed case of `test_a_move_that_would_not_repay_its_restart_names_why`; a pressed machine with no step at a bundle boundary sheds nothing until one is (2026-11-26 13:25 ET)
- [x] A step's memory at admission is its measured peak where one is known, not `worker_gb` alone, and neither an admission nor a raise takes what a running step has yet to reach of its peak (finding 3): `peak_gb` in `rules/load-jobs.yaml`; `admit` waits for at least a step's own `peak_gb`, and `admit` and the controller read free memory less `unreached_peaks` (each running step's `peak_gb` less the resident memory its processes hold), which also sets the workers an admission gets; `test_a_step_waits_for_the_peak_a_running_step_has_yet_to_reach`, `test_a_step_with_a_measured_peak_waits_for_it_though_its_workers_need_less`, `test_the_unreached_peak_of_the_running_steps_is_their_declared_peak_less_what_they_hold`, `test_the_controller_raises_nothing_into_a_running_steps_unreached_peak` and `test_a_peak_is_a_positive_number_of_gigabytes` (on the old code `TypeError`, `AttributeError`, a raise, `DID NOT RAISE`). For `openfigi-answers` this protects little yet: its `peak_gb` 0.9 is only a lower bound (0.86 GB when killed, still growing), its own admission is unchanged (4 workers already ask 1.0 GB), and the reserve against it is the 0.9 GB less what it holds (2026-11-26 14:03 ET)
- [x] Each step's sampled peak written on its `done` and `stopped` lines, so the next reload declares measured peaks (finding 3): `attempt_loop` samples the resident memory of the step's load (`held_gb`, its driver and workers) every 10 s through each load of the attempt, moves included, and ends the line with `; sampled peak N.NN GB`; `test_a_step_writes_the_peak_memory_its_load_was_sampled_at` for a done and a stopped attempt (on the old code `AttributeError`); a peak between two readings is missed (2026-11-26 14:44 ET)
- [ ] `openfigi-answers`' source extract peak measured (the next load's `sampled peak` on its line, or one run of it sampled to its end) and declared as its `peak_gb` (finding 3)
- [x] The engine's database connections carry client keepalives and a timeout, so a dropped connection fails within minutes (finding 4): every store's engine (`database_connections.connect`, Bookkeeping's and the Change Journal's own; `bundle.py`'s 5 s readiness probe aside) sets `control_contract.keep_alive` on each connection's socket, which probes after 60 s idle, every 10 s, 6 times, and on Linux give up on unacknowledged data after 120 s (macOS has no such option); `tests/storage_adapters/test_connection_keepalives.py` read the socket's options on PostgreSQL and MySQL, and on SQL Server found pymssql gives no socket, so it keeps the operating system's keepalive (before the change: 7,200 s idle, 75 s, 8 probes); two Linux containers on the loader image (OrbStack) against a disposable PostgreSQL 16 whose network was cut under `select pg_sleep(600)` failed the new engine's query after 125 s, while the old engine's was still waiting at 4 min (2026-11-26 11:48 ET)
- [x] A failed links build fails the load: no `chain done`, `load.sh` exits non-zero (finding 5): `finish` writes `finish stopped: links rc=<n>` (or `lookups`) and no `chain done`, and `load_jobs.py --finish` exits 1, which the activity worker reports as the task's failure, so the execution fails and `load.sh` exits 1; `test_a_failed_finish_build_fails_the_finish_and_the_load_is_not_complete` and `test_a_failed_links_build_makes_the_finish_command_exit_non_zero` (on the old code `assert None is False` and `assert 0 == 1`); `skills/data-operations/HOSTED-LOADS.md` says how to read and restart it (2026-11-26 12:20 ET)
- [x] The store's slowdown read from its own monitoring (throughput limits, connection drops) before any engine change (finding 6): the store was not the limit, one connection's upload from this machine was (a rate that varies: about 2 MB/s on 11-25, 5 to 100 KB/s overnight), and three of finding 4's drops are the store's idle-in-transaction kills; read from the instance's event-table metrics and server log, `pg_stat_*`, and a live rerun of the links build (2026-11-26 09:25 ET)
- [x] The `adv-funds`, `person` and `gleif` attempt 2 kills traced to what their client did inside the open transaction (finding 4): each was inside the execute of a multi-row insert the store never finished receiving, while the store's other connections still received data; read from the server log by session and the steps' error files (2026-11-26 11:48 ET)
- [ ] The kills at 00:52, 02:33 and 02:34 (three sessions opened together at 23:07:17) traced to their step and to what each was sending: the store's log keeps no statement under 2 s, and its tables were emptied on 2026-11-26 (finding 4)
- [ ] Why one connection's statement stops arriving at the store while its neighbours flow, and why a close is lost in either direction, read on the path between this machine and the store (finding 4)
- [ ] The links build's drop at 05:07 explained: no store kill was logged before it (finding 4)
- [ ] The six refused loader logins explained (finding 9)
- [x] `db_monitor.py` reads the instance's own telemetry (CPU by state, network by minute, waiting transactions, machine type) and times one connection's upload, so this reading is one command (finding 6): `telemetry --minutes N --every M` (the event table through the read-only log connection: machine type and region, then per interval CPU by state, eth0 KB/s received and sent, mean transactions waiting on locks, most connections; a partly read interval is measured by the CPU seconds it covers) and `upload` (round trip, a download, up to eight sends of 4 MB, none started after 60 s; the statement timeout starts once a statement has arrived, so it bounds no send); run on the hosted store at 15:48 ET: `m8g.medium`, 84% idle, one connection's upload 0.40 MB/s overall (0.17 to 0.79 a send), round trip 104 ms; `logs` and `telemetry` compare the event table's UTC times with `sysdate()`, since `current_timestamp()` read 8 hours of a 30-minute window; tests in `tests/unit/test_db_monitor.py` (on the old code `AttributeError` and the window assertion) (2026-11-26 15:51 ET)
- [x] The worker container reaps exited children (`init: true` or a reaper) (finding 7): the worker service runs with `init: true`, so Docker's init is PID 1; on the loader image, 20 orphaned children that exited stayed as 20 zombies under the activity worker as PID 1 and none under `--init`; `test_the_worker_runs_under_an_init_that_reaps_its_exited_children` (on the old file `KeyError: 'init'`); the catalog status command `load_jobs.py` kills at its timeout is waited on too, since an init reaps only orphans (`test_a_catalog_command_cut_off_at_its_timeout_is_reaped`, on the old code `assert None is not None`); it applies when `load.sh` next brings the worker up (2026-11-26 12:40 ET)
- [x] A step waiting for memory does not hold the admission lock (found in the reload of 2026-11-26: `gleif`, waiting for the 3.2 GB of its 8 workers from 17:02 ET, held it, and no other step started while lanes were ready): the lock is held for a reading and an admission only, and a waiter holds `<gate>.wait` shared so the controller raises nothing meanwhile; `test_a_step_waiting_for_memory_lets_a_step_that_fits_be_admitted_meanwhile` (on the old code `[] == [('small', 1)]`); the running reload keeps its image, so `gleif` there starts once the running steps end (2026-11-26 17:26 ET)
- [ ] The links differences explained from the two runs' rows, or shown to be expected (finding 8)
- [ ] A hosted reload with no step killed for memory (status -9), more than 2 lanes at once and each step's workers named in its log (from ticket 03)
- [ ] Learning → skill
