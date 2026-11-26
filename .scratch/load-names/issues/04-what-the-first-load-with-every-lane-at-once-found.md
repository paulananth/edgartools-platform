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
   `oom-kill`, global, 22:51 ET). The gate sizes a step by `worker_gb` a worker; that reading's peak is larger.
4. **The hosted store dropped connections five times** (`adv-funds`, `person` and `gleif`'s attempt 2 were the store
   ending a session idle in its transaction for over 10 minutes; the links build's was logged by the store only as the client
   gone: see the store's monitoring below): `adv-funds` (23:08), `person` (23:13) and the links build (05:07) with
   `SSL connection has been closed unexpectedly` / `SSL SYSCALL error: EOF detected`; once silently: `gleif`'s attempt 2 had
   finished its document and then waited on a socket the store no longer held (no session in `pg_stat_activity`, the kernel's
   socket established with empty queues, keepalive timer about 40 min away). It was ended by hand at 04:54 ET (the same stop its
   bound would have made at 06:34); attempt 3 found the document loaded. The engine's connections have no client keepalive or
   timeout of their own.
5. **A failed links build reports success**: `links rc=1` was followed by `chain done`, and `load.sh` exited 0 (05:07 ET).
6. **The writes were held by this machine's upload, not by the store**: MDM writes fell from about 100,000 rows a minute to about
   10,000, the long steps' processes waited at 0 to 10% CPU, and the links build took 146 min against 7.8 before. The store's own
   monitoring (below) shows it was not the limit; one connection's upload from this machine was.
9. **The loader's login was refused twelve times** (`Snowflake authentication failed`, user `edgar_loader`, database `data`) at
   21:41, 22:44, 22:54 and 23:05 ET, minutes before the `adv-funds` and `person` drops; the same env file's logins worked before and
   after.

## What the store's own monitoring shows (finding 6, read 2026-11-26)

Read with the diagnostic login (`pg_stat_*`, `pg_stat_statements`) and the read-only log login (the account's event table:
the instance's metrics and server log), then a live rerun of the links build alone (08:55 ET, stopped once read).

- **The store was not pressed.** The instance is an AWS `m8g.medium` in us-east-2: 1 vCPU, 4.2 GB, a fixed-performance type
  (no burst credits). Hour by hour from 21:00 to 08:00 ET it was 46 to 83% idle (25% at 03:00, its busiest hour), steal 0,
  disk wait at most 21%, swap flat at about 260 MB. Transactions waiting on a lock averaged 0 to 1.4 an hour (none after 02:00).
  Its sessions mostly waited on the client: 1 to 10 `data` sessions idle against 0 to 4 active.
- **This machine was idle too**: load 0.00 to 0.14 a core from 23:30 (the exporter's `load_machine_load_per_core`), and no packet
  loss: the worker container's TCP counters over the whole links build retransmitted 4,674 of 38.8 million segments (0.01%).
- **The links build read in 4 minutes and wrote for 140.** The store sent it 1.8 to 7.5 MB/s from 05:22 to 05:25 ET (the scan of
  the records table, 11.4 GB), then received 5 to 100 KB/s until 07:46 ET while the build landed its rows on one connection. The
  rerun did the same: the scan ended in about 5.5 min, and landing ran at 50 to 380 KB/s with the client blocked sending a batch
  (about 2.2 MB in its socket's send queue, the store waiting in `ClientRead`, the client's stack in `do_execute` of the landing
  merge, `relational.py:183`).
- **One connection's upload from this machine is capped at about 0.3 to 0.7 MB/s**, to the store and to Apple's speed-test server
  alike: one 32 MB upload ran at 0.34 MB/s; three at once at 0.48, 0.58 and 0.68 MB/s each; many at once (macOS `networkQuality`)
  at 88 Mbps up and 289 down, with a 100 ms base round trip. Downloads from the store ran at 23 to 33 MB/s on one connection. So
  the load's writes go as fast as the number of connections uploading at once: the store received 1.5 to 2.5 MB/s while several
  lanes wrote (02:41 to 04:05 ET) and under 0.2 MB/s once one lane was left (from 04:06).
- **Production runs in the store's region** (AWS Step Functions), so this cap is a figure of this machine's loads only: no engine
  change follows from it.
- **The drops of finding 4 are the store's own kills.** The loader login's `idle_in_transaction_session_timeout` is 10 min
  (`infra/scripts/harden-hosted-roles.py`). The server log ended six `edgar_loader` sessions on `data` for it: 23:08:24
  (`adv-funds` failed 23:08:27), 23:13:14 (`person`, 23:13:17), 00:52:20, 02:33:19 and 02:34:42 (`gleif` attempt 1, 02:34:16),
  04:29:44 (`gleif` attempt 2, the silent one: the client never saw the close). The links build's drop is no kill: the store
  logged only `connection to client lost` at 05:07:12, after the build's `rc=1` at 05:07. A session is idle in its transaction while a statement is still arriving, so a batch sent
  slower than the limit is killed as one idle.
7. **Exited workers are not reaped**: about 100 zombie `python` processes in the worker container, children of moves and stops,
   whose parent is the activity worker as PID 1.
8. **The links differ slightly from the run before**: 417,640 links (+797) and 4,459,121 bindings (−1,119) from the same captures.

## Parts

- [ ] A step whose work is one document starts with its declared workers or waits for them (finding 1)
- [ ] The controller moves a step only between runs, never one it shed earlier in the same attempt (finding 2)
- [ ] A step's memory at admission is its measured peak where one is known, not `worker_gb` alone (finding 3)
- [ ] The engine's database connections carry client keepalives and a timeout, so a dropped connection fails within minutes (finding 4)
- [ ] A failed links build fails the load: no `chain done`, `load.sh` exits non-zero (finding 5)
- [x] The store's slowdown read from its own monitoring (throughput limits, connection drops) before any engine change (finding 6): the store was not the limit, one connection's upload from this machine was, and finding 4's drops are the store's idle-in-transaction kills; read from the instance's event-table metrics and server log, `pg_stat_*`, and a live rerun of the links build (2026-11-26 09:25 ET)
- [ ] Each of the six idle-in-transaction kills traced to what its client did inside the open transaction: a statement sent slower than the 10-minute limit, or client work with the transaction open (finding 4)
- [ ] The links build's drop at 05:07 explained: no store kill was logged before it (finding 4)
- [ ] The twelve refused loader logins explained (finding 9)
- [ ] `db_monitor.py` reads the instance's own telemetry (CPU by state, network by minute, waiting transactions, machine type) and times one connection's upload, so this reading is one command (finding 6)
- [ ] The worker container reaps exited children (`init: true` or a reaper) (finding 7)
- [ ] The links differences explained from the two runs' rows, or shown to be expected (finding 8)
- [ ] A hosted reload with no step killed for memory (status -9), more than 2 lanes at once and each step's workers named in its log (from ticket 03)
- [ ] Learning → skill
