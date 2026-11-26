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
4. **The hosted store dropped connections five times**: `adv-funds` (23:08), `person` (23:13) and the links build (05:07) with
   `SSL connection has been closed unexpectedly` / `SSL SYSCALL error: EOF detected`; once silently: `gleif`'s attempt 2 had
   finished its document and then waited on a socket the store no longer held (no session in `pg_stat_activity`, the kernel's
   socket established with empty queues, keepalive timer about 40 min away). It was ended by hand at 04:54 ET (the same stop its
   bound would have made at 06:34); attempt 3 found the document loaded. The engine's connections have no client keepalive or
   timeout of their own.
5. **A failed links build reports success**: `links rc=1` was followed by `chain done`, and `load.sh` exited 0 (05:07 ET).
6. **The store slowed over the night**: MDM writes fell from about 100,000 rows a minute to about 10,000, the long steps' processes
   waited on the store at 0 to 10% CPU, and the links build read about 100 to 175 KB a second (measured from `/proc/<pid>/io`),
   taking 146 min against 7.8 before. Not stale statistics: every large MDM and silver table was analysed between 03:42 and
   06:49 ET. Not this machine: the Mac had 51% memory free and the container 206 GB of disk.
7. **Exited workers are not reaped**: about 100 zombie `python` processes in the worker container, children of moves and stops,
   whose parent is the activity worker as PID 1.
8. **The links differ slightly from the run before**: 417,640 links (+797) and 4,459,121 bindings (−1,119) from the same captures.

## Parts

- [ ] A step whose work is one document starts with its declared workers or waits for them (finding 1)
- [ ] The controller moves a step only between runs, never one it shed earlier in the same attempt (finding 2)
- [ ] A step's memory at admission is its measured peak where one is known, not `worker_gb` alone (finding 3)
- [ ] The engine's database connections carry client keepalives and a timeout, so a dropped connection fails within minutes (finding 4)
- [ ] A failed links build fails the load: no `chain done`, `load.sh` exits non-zero (finding 5)
- [ ] The store's slowdown read from its own monitoring (throughput limits, connection drops) before any engine change (finding 6)
- [ ] The worker container reaps exited children (`init: true` or a reaper) (finding 7)
- [ ] The links differences explained from the two runs' rows, or shown to be expected (finding 8)
- [ ] A hosted reload with no step killed for memory (status -9), more than 2 lanes at once and each step's workers named in its log (from ticket 03)
- [ ] Learning → skill
