---
name: load-monitoring
description: Watch a platform load in Grafana - one dashboard of lanes, steps, stalls and restarts fed by the load jobs' own status. Use when asked to monitor, watch or dashboard a load, to bring the monitor up or down, or to change what it shows. The load itself is data-operations'; this skill only reads it.
---

# Load monitoring

The dashboard answers two questions at a glance: **is the load healthy, and why
is a step not running?** Colour carries the answer; numbers back it. It reads the
`load_jobs.status_snapshot` for the selected `RUN` (reader login, process list and log files only):

```bash
uv run --no-sync python <this skill>/scripts/monitoring.py up --run <label>
uv run --no-sync python <this skill>/scripts/monitoring.py status
uv run --no-sync python <this skill>/scripts/monitoring.py stop
```

Run it from a checkout at current `origin/main`, in the repository's environment.
It starts Prometheus and Grafana in the
`edgartools-monitoring` Compose project, pushes the data source and the dashboard,
and reads them back. Do not run `docker` for this work: if the script cannot do a
step, say so and fix the script. The viewer is `http://127.0.0.1:3001/d/load-monitor`
and needs no login; the admin login is generated into a private file and never printed.

| Need | Command | It answers |
|---|---|---|
| Bring it up | `up --run <label>` | Containers healthy, exporter up, Prometheus scraping it, dashboard present. Exit 0 only when all are |
| Is it working? | `status` | The same readback; every `PROBLEM:` line says what is wrong |
| Take it down | `stop` | Stops the exporter and the containers; Grafana's and Prometheus's data stay |
| Read another exporter | `target [<host:port>]` | Prometheus reads that exporter within 30 s; with no address, this Mac's |

## Where the exporter runs

The load pipeline's Compose project (`infra/load-pipeline`) runs the exporter from the loader image beside the worker and
inherits its `RUN`; it needs no checkout and sees a load running in a container. `monitoring.py up` starts a host exporter
only when nothing answers on the port; pass `--run <label>` for a standalone load.

Prometheus reads one exporter at a time, named in a file on its own named volume, so no count is summed twice. A load on
AWS (`infra/load-pipeline/aws-load.sh`) runs the same exporter in its Fargate task, sharing the task's processes (each
step's CPU and memory show), on a port open to this Mac's public address only: the script names the task's exporter
while the load runs and this Mac's again when it ends. Bring the monitor up before the load so it is there to read it.
The port serves counts and step names over plain HTTP to the one address the Mac shows the internet (every machine
behind the same router shares it); a changed address stops the scrape until the next load. A launch script killed
outright leaves Prometheus on the task's address: `monitoring.py target` names this Mac's again.

An exporter that reads a load's logs copied from another machine (none of its processes here) runs with
`LOAD_ELSEWHERE=1`: a step started and not ended is running, and its CPU and memory are not published (never a zero).

`load.sh` recreates the worker, and the exporter with it, at every start: for a minute `monitoring.py status` says the
exporter is not answering, then `load_monitor_up 1`. A host exporter served from a checkout goes blind when that
checkout is deleted (`load_monitor_up 0`): stop it, never repair it, and let the pipeline's exporter take the port.

A container runtime that stops answering blinds the exporter and freezes the load behind it: test the runtime first (a bounded
`docker version`), and restart it before looking at anything else (HOSTED-LOADS, "The shortest time to load everything").

The monitor shows the lane budget beside the lanes and workers running (`load_lane_budget`, `load_worker_budget`, `load_lanes_running`,
`load_workers_running`): the budget is data-operations' `lane_budget`, the lanes the compute carries when every step runs its declared workers (every lane starts, and each step is admitted by the memory free then), and its `limit` label names what sets it
(memory or vcpu). Lanes running below the budget while lanes wait is a defect to explain; lanes at the budget with CPU idle means the limit
is memory, not a setting.

A watcher reads the log of the run label it watches, never "the newest log": the newest one replays an old run's events as if they
were new. After the runtime restarts, an execution it held no longer exists (`ExecutionDoesNotExist`): that is the restart, not a
failed load; read the new execution and the run's state file.

## The design

A step has one of seven states (the codes are never renumbered: Prometheus keeps what it stored, and a changed number repaints history; code 2, once `unclear`, stays unused), each with one of four colours that mean the same wherever a
step's state is shown (`scripts/design.py` is the only place that names them):
grey is not running (waiting, and every step once the whole load is complete), orange is running (progressing), green is finished (done), red needs a
look (failed, stalled, locked); the state's name, on hover and in the tiles, tells two of one colour apart. A change of colour is the event: nothing is
decorated, and a number is never rounded to look calm.

| Interaction | What carries it in Grafana |
|---|---|
| A step starts, works, stalls or ends | The lane board: one bar a step, coloured by state, grouped by lane |
| "Show me only the steps in one state" | A click on the Done, Running, Stalled-or-locked or Failed tile keeps only those steps on the lane board, by their state at the end of the time range; the Steps list at the top picks any filter, All shows every step. A tile counts with the same states it filters (`FILTERS` in `scripts/design.py`) |
| "Why is it not running?" | The Waiting-for table: each waiting step and the step it waits for; empty means a free slot |
| A restart | An annotation on the timelines at the moment an attempt count rises, and an amber Attempt cell |
| A stall | Log age turns amber at ten minutes and red at twenty; the bar and the Stalled-or-locked tile turn red from one |
| "Why is a running step not working?" | The Why panel: the five whys of each stalled or locked step (symptom, its own database sessions, its latest statement, what it waits on, the cause or what was not measured); the Why column of Running now holds the last. A step is never "unclear" |
| A failure | The Failed tile turns red from one, the bar goes red, an annotation marks the moment |
| The load ends | A green "Load complete" annotation at the `chain done` line; every lane goes grey, the tiles keep their counts |
| Database pressure | Lock waiters: amber at one, red at three (the scheduler's own limit) |
| Memory pressure | Memory free: amber under a quarter, red under a tenth (the controller's own limits) |
| A rate that has gone flat | Rows written a minute per store, beside the bars |

Grafana recolours and redraws; it does not animate. A pulse, a rewind shake or
dependency lines need a custom panel plugin, which is a separate decision.

## Rules for changing it

- **Skill first, then the dashboard.** A new reading starts as a metric in
  `exporter.py` and a token in `design.py`; the panel in `dashboard.py` takes its
  colour and limits from there. No colour or threshold is typed in a panel.
- **Every panel says in its description which interaction it carries and what a
  reading means.** A test holds this.
- **The same limits as the load jobs.** Thresholds are the verdict's and the
  controller's own, so the dashboard and `--status` never disagree.
- **Counts, states and times only.** Never a row value, a name from the data, an
  address or a login in a metric or a panel: the repository is public.
- **The dashboard is code.** It is pushed on every `up` and cannot be edited in
  the browser; change `dashboard.py`.
- **Nothing is mounted from a checkout.** The scrape file is inline Compose
  content; the script refuses a compose file that maps another port or binds a
  repository path.

## Not built yet

- A step's projected end and the deadline rail (the load jobs script computes both in its
  log; the status does not return them yet).
- Alert rules (a stall or a failure notifying someone) need a contact point.
- Animation (see above).
- Reading a hosted load run elsewhere: the exporter reads the process list of the
  worker it shares a process space with, so it sees only loads of this machine's pipeline.

## Handshake

Reads and shows; changes nothing. Tells [data-operations](../data-operations/SKILL.md) what stalls (the runtime first, then lanes against the budget), sends a lock or slow statement to [database-monitoring](../database-monitoring/SKILL.md) and an unexplained failure to [production-support](../production-support/SKILL.md). Its numbers come from data-operations' `lane_budget`; the two change together. The table of who owns what and hands off to whom is [OWNERSHIP.md](../data-platform/OWNERSHIP.md).
