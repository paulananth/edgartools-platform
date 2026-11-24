---
name: load-monitoring
description: Watch a platform load in Grafana - one dashboard of lanes, steps, stalls and restarts fed by the load jobs' own status. Use when asked to monitor, watch or dashboard a load, to bring the monitor up or down, or to change what it shows. The load itself is data-operations'; this skill only reads it.
---

# Load monitoring

The dashboard answers two questions at a glance: **is the load healthy, and why
is a step not running?** Colour carries the answer; numbers back it. It reads the
load jobs' own status (`load_jobs.py --status --json`) and changes nothing: the
reader login, the process list and the log files only.

```
uv run --no-sync python <this skill>/scripts/monitoring.py <up|status|stop>
```

Run it from a checkout at current `origin/main`, in the repository's environment.
It starts Prometheus and Grafana in the
`edgartools-monitoring` Compose project, pushes the data source and the dashboard,
and reads them back. Do not run `docker` for this work: if the script cannot do a
step, say so and fix the script. The viewer is `http://127.0.0.1:3001/d/load-monitor`
and needs no login; the admin login is generated into a private file and never printed.

| Need | Command | It answers |
|---|---|---|
| Bring it up | `up` | Containers healthy, exporter up, Prometheus scraping it, dashboard present. Exit 0 only when all are |
| Is it working? | `status` | The same readback; every `PROBLEM:` line says what is wrong |
| Take it down | `stop` | Stops the exporter and the containers; Grafana's and Prometheus's data stay |

## Where the exporter runs

The load pipeline's Compose project (`infra/load-pipeline`) runs the exporter from the loader image, beside the worker,
sharing its process space, so it needs no checkout and sees a load that runs in a container. `monitoring.py up` starts a
host exporter only when nothing answers on the port (a load run by hand, outside the pipeline).

`load.sh` recreates the worker, and the exporter with it, at every start: for a minute `monitoring.py status` says the
exporter is not answering, then `load_monitor_up 1`. A host exporter served from a checkout goes blind when that
checkout is deleted (`load_monitor_up 0`): stop it, never repair it, and let the pipeline's exporter take the port.

A container runtime that stops answering blinds the exporter and freezes the load behind it: test the runtime first (a bounded
`docker version`), and restart it before looking at anything else (HOSTED-LOADS, "The shortest time to load everything").

The monitor shows the lane budget beside the lanes and workers running (`load_lane_budget`, `load_worker_budget`, `load_lanes_running`,
`load_workers_running`): the budget is data-operations' `lane_budget`, the number `load.sh` applied, and its `limit` label names what sets it
(memory or vcpu). Lanes running below the budget while lanes wait is a defect to explain; lanes at the budget with CPU idle means the limit
is memory, not a setting.

A watcher reads the log of the run label it watches, never "the newest log": the newest one replays an old run's events as if they
were new. After the runtime restarts, an execution it held no longer exists (`ExecutionDoesNotExist`): that is the restart, not a
failed load; read the new execution and the run's state file.

## The design

A step has one of six states (the codes are never renumbered: Prometheus keeps what it stored, and a changed number repaints history; code 2, once `unclear`, stays unused), each with one colour that means the same on every
panel (`scripts/design.py` is the only place that names them):
waiting (grey), progressing (green), stalled (orange), locked (red),
done (blue) and failed (dark red). A change of colour is the event: nothing is
decorated, and a number is never rounded to look calm.

| Interaction | What carries it in Grafana |
|---|---|
| A step starts, works, stalls or ends | The lane board: one bar a step, coloured by state, grouped by lane |
| "Why is it not running?" | The Waiting-for table: each waiting step and the step it waits for; empty means a free slot |
| A restart | An annotation on the timelines at the moment an attempt count rises, and an amber Attempt cell |
| A stall | Log age turns amber at ten minutes and red at twenty; the Stalled-or-locked tile turns orange from one |
| "Why is a running step not working?" | The Why panel: the five whys of each stalled or locked step (symptom, its own database sessions, its latest statement, what it waits on, the cause or what was not measured); the Why column of Running now holds the last. A step is never "unclear" |
| A failure | The Failed tile turns red from one, the bar goes dark red, an annotation marks the moment |
| Database pressure | Lock waiters: amber at one, red at three (the scheduler's own limit) |
| Memory pressure | Memory free: orange under a quarter, red under a tenth (the controller's own limits) |
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
