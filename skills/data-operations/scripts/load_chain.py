#!/usr/bin/env python3
"""Load every captured source into one store, in the order rules/load-chain.yaml gives.

    python load_chain.py --list               the steps, in order
    python load_chain.py --plan               what each step would load (documents and bundles); writes nothing
    python load_chain.py                      the whole chain, then the lookups and each silver table's master ids
    python load_chain.py --from <step>        carry on from a step (a done step costs one call: nothing is loaded twice)
    python load_chain.py --only <step>        one step
    python load_chain.py --lane <name>        the steps of one lane; run several lanes at once (see the chain file)
    python load_chain.py --finish             only what follows the loads, once every lane is done
    python load_chain.py --status             what each running step is doing: progress, rate, processes, a verdict
    python load_chain.py --auto [--slots N] [--hours H | --deadline HH:MM]
                                              watch the loads: start each step when its lane is free, move its
                                              workers (within --capacity) with the machine, stop at the deadline (see `auto`)

Each step is the same resumable `load` command, run again until it finishes (a stopped attempt names why in its log and
the next carries on from where it stopped). The chain stops at the first step that does not finish in its attempts.
STORES (default ~/.config/edgartools/hosted) is the stores folder, whose worker.env holds the logins; CAPTURES, PROVING
and LOGS name the captured files and the logs; RUN labels the capture runs. The machine stays awake for the whole chain
(a sleep once dropped a hosted connection and lost 74 minutes). Run it from the checkout whose code should load.
"""
import argparse
import contextlib
import json
import os
import re
import shlex
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(os.environ.get("ROOT") or Path(__file__).resolve().parents[3])
HOME = Path.home()
STORES = Path(os.environ.get("STORES") or HOME / ".config/edgartools/hosted")
ROOTS = {"captures": Path(os.environ.get("CAPTURES") or HOME / ".local/share/edgartools/mdm/captures"),
         "proving": Path(os.environ.get("PROVING") or HOME / ".local/share/edgartools/mdm/proving")}
LOGS = Path(os.environ.get("LOGS") or HOME / ".local/share/edgartools/load-logs")
RUN = os.environ.get("RUN", "fresh-v1")
ENGINE = ["uv", "run", "--no-sync", "edgar-warehouse"]


def load_env(path: Path) -> dict:
    """The shell-style `export KEY=value` lines of a private env file, parsed as data."""
    env = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
        if match:
            env[match.group(1)] = shlex.split(match.group(2))[0] if match.group(2) else ""
    return env


def chain_steps(path: Path = ROOT / "rules/load-chain.yaml") -> list[dict]:
    """The chain's steps, each with the chain's `defaults` for what it does not say itself."""
    chain = yaml.safe_load(path.read_text())
    return [{**(chain.get("defaults") or {}), **step} for step in chain["steps"]]


def needs(steps: list[dict]) -> dict[str, set[str]]:
    """What each step follows: the step before it in its lane (a lane is a queue) and every step it waits for."""
    follows: dict[str, set[str]] = {}
    previous: dict[str, str] = {}
    for step in steps:
        follows[step["name"]] = set(step.get("waits_for") or [])
        if step["lane"] in previous:
            follows[step["name"]].add(previous[step["lane"]])
        previous[step["lane"]] = step["name"]
    return follows


def blocked(steps: list[dict], failed: set[str]) -> set[str]:
    """Every step that follows a failed step, through its lane and its waits, however far."""
    follows, stuck = needs(steps), set()
    while True:
        more = {name for name, before in follows.items() if name not in stuck and (before & (failed | stuck))}
        if not more:
            return stuck
        stuck |= more


def chain_length(steps: list[dict], minutes: dict[str, float] | None = None) -> dict[str, float]:
    """Each step's time plus the longest chain of steps that must follow it: its measured or estimated minutes when
    given, else its `minutes` (a bound on one attempt, so only a proxy). Starting the long chains first is its use."""
    after: dict[str, list[str]] = {step["name"]: [] for step in steps}
    for name, before in needs(steps).items():
        for earlier in before:
            after[earlier].append(name)
    minutes, memo, walking = minutes or {s["name"]: s["minutes"] for s in steps}, {}, set()

    def total(name: str) -> int:
        if name in walking:  # a cycle of waits: counted once, and `auto` stops on it
            return 0
        if name not in memo:
            walking.add(name)
            memo[name] = minutes[name] + max((total(later) for later in after[name]), default=0)
            walking.discard(name)
        return memo[name]

    return {name: total(name) for name in minutes}


def measured(text: str) -> dict[str, float]:
    """Each done step's minutes, from its first `attempt 1 start` to its `done:` line in the chain's state file."""
    start, took = {}, {}
    for found in re.finditer(r"^(\d\d-\d\d \d\d:\d\d:\d\d) ET (\S+) (attempt \d+ start|done:)", text, re.M):
        when = datetime.strptime(found.group(1), "%m-%d %H:%M:%S")
        name = found.group(2)
        if found.group(3).startswith("attempt"):
            start.setdefault(name, when)
        elif name in start and name not in took:
            took[name] = (when - start[name]).total_seconds() / 60 % 1440
    return took


def estimates(steps: list[dict], took: dict[str, float]) -> dict[str, float]:
    """Each step's minutes: what it took when done, else its bound times the median share of its bound the done steps
    used (the bound itself while nothing has run). An estimate, labelled so wherever it is shown."""
    ratios = [took[s["name"]] / s["minutes"] for s in steps if s["name"] in took and s["minutes"]]
    share = statistics.median(ratios) if ratios else 1.0
    return {s["name"]: took.get(s["name"], s["minutes"] * share) for s in steps}


def remaining(steps: list[dict], done: set[str], running: dict[str, float], estimate: dict[str, float]) -> float:
    """The minutes left on the longest chain of steps not yet done. A running step counts what it has not yet used of its
    estimate (`running` gives each one's minutes so far); one that has outrun its estimate has disproved it, so its
    bound is all that is left to count and the figure is then an upper bound."""
    def left(step: dict) -> float:
        name, used = step["name"], running.get(step["name"], 0.0)
        return max((estimate[name] if used < estimate[name] else step["minutes"]) - used, 0.0)

    cost = {s["name"]: 0.0 if s["name"] in done else left(s) for s in steps}
    return max(chain_length(steps, cost).values(), default=0.0)


def room(level: str, connections: int, target: int) -> str:
    """Room to add workers needs the database's connections below the target as well as a machine with room: at the
    target, more workers add nothing the database was asked to carry."""
    return "ok" if level == "low" and connections >= target else level


def ready(steps: list[dict], done: set[str], running: set[str], failed: set[str], free: int,
          busy: frozenset | set = frozenset(), estimate: dict[str, float] | None = None) -> list[str]:
    """The steps to start now: each follows only done steps, is not blocked by a failure, and does not share its source
    and target with a load already running (two loads of one pair write the same outputs). The longest chain first (see
    `chain_length`); at most `free`."""
    follows, stuck = needs(steps), blocked(steps, failed)
    length = chain_length(steps, estimate)
    taken = set(busy) | {(s["source"], s["target"]) for s in steps if s["name"] in running}
    chosen: list[dict] = []
    for step in sorted(steps, key=lambda s: -length[s["name"]]):
        pair = (step["source"], step["target"])
        if (step["name"] in done or step["name"] in running or step["name"] in failed or step["name"] in stuck
                or not follows[step["name"]] <= done or pair in taken or len(chosen) >= free):
            continue
        chosen.append(step)
        taken.add(pair)
    return [step["name"] for step in chosen]


def swap_fraction(text: str) -> float | None:
    """The share of swap in use, from `sysctl vm.swapusage` (macOS); None when it cannot be read."""
    found = re.search(r"total = ([\d.]+)M\s+used = ([\d.]+)M", text)
    return float(found.group(2)) / float(found.group(1)) if found and float(found.group(1)) else None


WORKER_GB = 0.5  # the memory a worker is sized for
WORKERS_PER_VCPU = 4  # a worker waits on the database much of the time, so a vCPU carries several


def workers_range(vcpu: float, memory_gb: float) -> tuple[int, int]:
    """The workers a task can carry, from what it has: its memory in worker-sized shares, at most four to a vCPU, never
    fewer than one. The range follows the compute (a 1 vCPU, 4 GB task carries up to 4; 2 vCPU, 8 GB up to 8), so it is
    the configuration's, never a fixed two to eight."""
    return 1, max(1, min(int(memory_gb // WORKER_GB), int(vcpu * WORKERS_PER_VCPU)))


def capacity_profiles(path: Path = ROOT / "rules/load-chain.yaml") -> dict[str, dict]:
    """The named compute sizes of the chain file (the AWS ECS task sizes the state machines run on)."""
    return yaml.safe_load(path.read_text()).get("capacity") or {}


def physical_gb() -> float:
    return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30


def bounds_for(name: str) -> tuple[int, int]:
    """The workers range of a capacity: a profile of the chain file, or `local`, this machine measured (half its memory,
    the rest being the operator's other work)."""
    if name == "local":
        return workers_range(os.cpu_count() or 1, physical_gb() / 2)
    profiles = capacity_profiles()
    if name not in profiles:
        raise SystemExit(f"No capacity named {name}: local or {', '.join(sorted(profiles))}")
    return workers_range(**profiles[name])


def pressure(load: float, cores: int, swap_used: float | None, relaxed: bool = False) -> str:
    """How hard the machine is pressed: `high` above one and a half times the cores in load average, or three quarters
    of swap used (a run behind its deadline is `relaxed` to twice the cores and nine tenths of swap); `low` below three
    quarters of the cores and half the swap; else `ok`."""
    heavy, swap_limit = (2.0, 0.9) if relaxed else (1.5, 0.75)
    if load > heavy * cores or (swap_used is not None and swap_used > swap_limit):
        return "high"
    return "low" if load < 0.75 * cores and (swap_used is None or swap_used < 0.5) else "ok"


def has_headroom(load: float, cores: int, swap_used: float | None, relaxed: bool = False) -> bool:
    return pressure(load, cores, swap_used, relaxed) != "high"


def machine_pressure(relaxed: bool = False) -> str:
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], check=False, capture_output=True,
                          text=True).stdout if sys.platform == "darwin" else ""
    return pressure(os.getloadavg()[0], os.cpu_count() or 1, swap_fraction(swap), relaxed)


def rescale(workers: dict[str, int], priority: dict[str, int], level: str, bounds: tuple[int, int]) -> tuple[str, int] | None:
    """One change of workers within the capacity's `bounds`: with room (`low`) the step with the longest chain behind it
    doubles, up to the top; when pressed (`high`) the step with the shortest halves, down to the floor. Anything else
    changes nothing."""
    low, top = bounds
    order = sorted(workers, key=lambda name: -priority[name])
    if level == "low":
        return next(((name, min(top, workers[name] * 2)) for name in order if workers[name] < top), None)
    if level == "high":
        return next(((name, max(low, workers[name] // 2)) for name in reversed(order) if workers[name] > low), None)
    return None


def behind(elapsed: float, window: float, done: int, total: int) -> bool:
    """More of the window used than of the work done (by the steps' `minutes`), with a tenth of slack."""
    return total > 0 and elapsed / window > done / total + 0.1


def db_level(active: int, connections: int, max_connections: int, lock_waiters: int, longest_wait: float) -> str:
    """`high` when the database is pressed: three sessions waiting on locks, one waiting a minute, or four fifths of its
    connections in use. More workers on a store that is already locking only lengthens the queue."""
    return "high" if lock_waiters >= 3 or longest_wait >= 60 or connections >= 0.8 * max_connections else "ok"


def worst(machine: str, database: str) -> str:
    """Pressed if either is; room only when the machine has room and the database is not pressed."""
    return "high" if "high" in (machine, database) else machine


def database_load(reader_url: str | None) -> dict | None:
    """Active sessions, sessions waiting on locks and the longest wait, and connections against the limit, read as the
    diagnostic login (pg_monitor: sessions and locks, no table; never the owner or a runtime login); None when it cannot
    be read (no reading is no reason to wait). Prints no address."""
    if not reader_url:
        return None
    query = """select count(*) filter (where state = 'active'), count(*) filter (where wait_event_type = 'Lock'),
        coalesce(max(extract(epoch from now() - state_change)) filter (where wait_event_type = 'Lock'), 0), count(*),
        (select setting::int from pg_settings where name = 'max_connections') from pg_stat_activity where datname is not null"""
    try:
        import psycopg2

        with psycopg2.connect(reader_url.replace("postgresql+psycopg2", "postgresql"), connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute(query)
            active, waiters, longest, connections, limit = cur.fetchone()
        return {"active": active, "connections": connections, "max_connections": limit, "lock_waiters": waiters,
                "longest_wait": float(longest)}
    except Exception:  # noqa: BLE001  a driver error can quote the address: no reading
        return None


def clock() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def external_loads() -> set[tuple[str, str]]:
    """The (source, target) of every `load` running on this machine, whoever started it."""
    listing = subprocess.run(["ps", "-Ao", "args"], check=False, capture_output=True, text=True).stdout
    return {(m.group(1), m.group(2)) for line in listing.splitlines() if "edgar-warehouse load " in line
            for m in [re.search(r"--source (\S+) --target (\S+)", line)] if m}


def stop(child: subprocess.Popen) -> None:
    """End a started step and the load under it (the load resumes where it stopped)."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=60)


def auto(steps: list[dict], state: Path, slots: int, poll: int = 30, deadline: datetime | None = None,
         reader_url: str | None = None, connections: int = 250, bounds: tuple[int, int] | None = None) -> int:
    """Watch the loads and start the next ready step whenever a slot is free and the machine is not pressed. One start
    a cycle: the load average lags, so a started step is counted running before the next is judged. Each step runs as
    `load_chain.py --only <step> --workers <n>` (the attempt loop). The workers follow the machine within the capacity's
    range (`bounds`; the machine's own when not given): with room
    the step with the longest chain behind it doubles, when pressed the step with the shortest halves, one change a
    cycle, by stopping the step's load and starting it again (a load resumes where it stopped). With a `deadline`, a run
    behind its schedule (more of the window used than of the work done) is allowed twice the cores in load; at the
    deadline every step this started is stopped and the run ends, naming what is left. A step that uses up its attempts
    blocks what follows it and the rest carry on. Ends when every step is done (then the lookups and the links), when
    nothing more can start, or at the deadline."""
    bounds = bounds or bounds_for("local")
    children: dict[str, subprocess.Popen] = {}
    workers: dict[str, int] = {}
    failed: set[str] = set()
    by_name = {step["name"]: step for step in steps}
    started, cycle, began = clock(), 0, {}
    total = sum(step["minutes"] for step in steps)

    def spawn(name: str, count: int) -> None:
        workers[name] = count
        began.setdefault(name, clock())
        children[name] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--only", name,
                                           "--workers", str(count)], start_new_session=True)

    while True:
        for name, child in list(children.items()):
            if child.poll() is not None:
                del children[name]
                workers.pop(name, None)
                if child.returncode != 0:
                    failed.add(name)
        done = done_steps(state)
        if set(by_name) <= done:
            return 0
        if deadline and clock() >= deadline:
            for child in children.values():
                stop(child)
            note(f"deadline: stopped {', '.join(sorted(children)) or 'nothing'}; left: {', '.join(sorted(set(by_name) - done))}", state)
            return 2
        slow = bool(deadline) and behind((clock() - started).total_seconds(), (deadline - started).total_seconds(),
                                         sum(by_name[n]["minutes"] for n in done if n in by_name), total)
        reading = database_load(reader_url)
        database = db_level(**reading) if reading else "ok"
        if database == "high":
            note(f"database pressed: {reading['lock_waiters']} waiting on locks (longest {reading['longest_wait']:.0f} s), "
                 f"{reading['connections']} of {reading['max_connections']} connections", state)
        level = worst(machine_pressure(relaxed=slow), database)
        if reading:
            level = room(level, reading["connections"], connections)
        estimate = estimates(steps, measured(state.read_text()) if state.exists() else {})
        length = chain_length(steps, estimate)
        cycle += 1
        if cycle % 10 == 1:
            minutes_in = {n: (clock() - began.get(n, clock())).total_seconds() / 60 for n in children}
            left = remaining(steps, done, minutes_in, estimate)
            ends = clock() + timedelta(minutes=left)
            note(f"projected end {ends:%H:%M} ET (an estimate from the {len(measured(state.read_text()) if state.exists() else {})} "
                 f"steps done){f' against the deadline {deadline:%H:%M} ET' if deadline else ''}; "
                 f"{reading['connections'] if reading else '?'} of {connections} target connections in use", state)
        busy = external_loads()
        free = slots - max(len(children), len(busy))
        starts = ready(steps, done, set(children), failed, 1, busy, estimate) if free > 0 and level != "high" else []
        for name in starts:
            count = min(max(by_name[name].get("workers", bounds[0]), bounds[0]), bounds[1])
            note(f"scheduler starts {name} at {count} workers", state)
            spawn(name, count)
        if not starts and (change := rescale(workers, {name: length[name] for name in workers}, level, bounds)):
            name, count = change
            note(f"scheduler moves {name} from {workers[name]} to {count} workers ({level} load)", state)
            stop(children[name])
            spawn(name, count)
        if not children and not busy and not ready(steps, done, set(), failed, len(steps)):
            left = sorted(set(by_name) - done)
            blockers = f"{', '.join(sorted(failed))} failed, so " if failed else "no step can follow what it waits for, so "
            note(f"scheduler stops: {blockers}{', '.join(left)} cannot start", state)
            return 1
        time.sleep(poll)


def bundle_progress(text: str) -> tuple[int, int] | None:
    """(bundles done, bundles in all) from a step's log: the `run ... complete in` lines, and the bundles an earlier
    attempt already loaded, against the last `Bundle i/N:` line. None when the log names no bundles."""
    found = re.findall(r"^Bundle \d+/(\d+):", text, re.M)
    finished = len(re.findall(r"^\s+run \S+ complete in", text, re.M)) + len(re.findall(r"^Bundle \d+/\d+: all \d+ documents already loaded", text, re.M))
    return (finished, int(found[-1])) if found else None


def minutes_left(done: int, total: int, elapsed: float) -> float | None:
    """The minutes left at the rate so far; None before a bundle is done (no rate yet)."""
    return None if done <= 0 else max(total - done, 0) * elapsed / done


def writes_per_minute(before: dict[str, int], after: dict[str, int], seconds: float) -> dict[str, float]:
    """Rows written a minute in each store, from two readings of its cumulative inserts, updates and deletes."""
    return {name: max(after.get(name, count) - count, 0) * 60.0 / seconds for name, count in before.items()}


def cpu_seconds(text: str) -> float:
    """The CPU time of the processes in `ps -o time=` output (`M:SS.ss` or `H:MM:SS.ss`, one per line), summed."""
    total = 0.0
    for line in text.split():
        parts = [float(part) for part in line.split(":")]
        total += sum(value * 60 ** index for index, value in enumerate(reversed(parts)))
    return total


def cpu_percent(before: float, after: float, seconds: float) -> float:
    """CPU percent over a window, from the CPU time used in it (`ps` shows a lifetime average, which hides work)."""
    return max(after - before, 0.0) / seconds * 100.0


def store_of(target: str) -> str:
    """The store a target writes: the silver target writes silver; every other target is mastering's, in MDM."""
    return "silver" if target == "silver" else "mdm"


def outlook(left: float | None, elapsed: float, bound: int, attempt: int, attempts: int) -> str:
    """A warning when the minutes left at the current rate exceed the time its remaining attempts allow (an attempt is
    `bound` minutes; a stopped one resumes where it stopped). Empty when it fits, or when there is no rate yet."""
    remaining = max(bound - elapsed, 0.0) + bound * (attempts - attempt)
    if left is None or left <= remaining:
        return ""
    return (f"needs about {left:.0f} min but has {remaining:.0f} min left in its {attempts - attempt} remaining attempts: "
            "raise its workers or its minutes")


def verdict(elapsed: float, bound: int, log_age: float, cpu: float, writes_per_min: float, lock_waiters: int,
            shares_store: list[str] | None = None) -> str:
    """A step's state by its own evidence: waiting on locks; progressing (it wrote rows, its processes work, or its log
    moved in the last ten minutes); or no sign of work, which names what is silent. Past its bound is said first."""
    late = f"past its bound of {bound} min; " if elapsed > bound else ""
    if lock_waiters >= 3:  # the scheduler's own threshold: one waiting session is normal
        return f"{late}waiting on database locks ({lock_waiters} sessions on the store)"
    if shares_store and cpu < 5 and log_age >= 10:
        return (f"{late}unclear: its own processes used no CPU and its log is {log_age:.0f} min old, and the rows written "
                f"are the store's, shared with {', '.join(shares_store)}, so they may be theirs; check its log and processes")
    if writes_per_min > 0 or cpu >= 5 or log_age < 10:
        return f"{late}progressing"
    return f"{late}no sign of work: no CPU, no rows written, log silent for {log_age:.0f} min; read its log, it may be stalled"


STORE_DATABASES = ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")


def database_writes(reader_url: str) -> dict[str, int]:
    """Each store's cumulative rows inserted, updated and deleted, read as the diagnostic login (statistics, no table)."""
    import psycopg2

    totals = {}
    for name in STORE_DATABASES:
        url = re.sub(r"/[^/?]+((?:\?.*)?)$", rf"/{name}\1", reader_url.replace("postgresql+psycopg2", "postgresql"))
        try:
            with psycopg2.connect(url, connect_timeout=10) as conn, conn.cursor() as cur:
                cur.execute("SELECT coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) FROM pg_stat_user_tables")
                totals[name] = int(cur.fetchone()[0])
        except Exception:  # noqa: BLE001  a driver error can quote the address: no reading for this store
            continue
    return totals


def session_summary(rows: list[tuple[str, str, int]]) -> dict[str, dict[str, int]]:
    """Each store's sessions by what they do: working (active), or waiting on the client (idle, or idle in a
    transaction): a session waiting on the client has asked the database for nothing, so the work is on the client."""
    summary: dict[str, dict[str, int]] = {}
    for database, state, count in rows:
        counts = summary.setdefault(database, {"active": 0, "waiting_on_client": 0})
        counts["active" if state == "active" else "waiting_on_client"] += count
    return summary


def session_note(database: str, counts: dict[str, int]) -> str:
    note = f"{database}: {counts['active']} sessions working, {counts['waiting_on_client']} waiting on the client"
    return note + ": client-bound, not the database" if counts["waiting_on_client"] > counts["active"] else note


def database_sessions(reader_url: str) -> dict[str, dict[str, int]]:
    """Sessions of the loads on each store by state, read as the diagnostic login (state only, never a query)."""
    import psycopg2

    try:
        with psycopg2.connect(reader_url.replace("postgresql+psycopg2", "postgresql"), connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("""SELECT datname, state, count(*) FROM pg_stat_activity WHERE datname = ANY(%s)
                           AND usename <> current_user AND state IS NOT NULL GROUP BY 1, 2""", (list(STORE_DATABASES),))
            return session_summary(cur.fetchall())
    except Exception:  # noqa: BLE001  a driver error can quote the address: no reading
        return {}


def window_cpu(before: dict[int, float], after: dict[int, float]) -> float:
    """CPU seconds used in a window by the processes present in both readings: one that began in the window has only
    its lifetime to show, which is not the window's."""
    return sum(max(after[pid] - used, 0.0) for pid, used in before.items() if pid in after)


def is_load_process(args: str, source: str, target: str) -> bool:
    """A process of the platform's load of one source and target: its driver or a worker, never another command that
    happens to carry the same words."""
    return bool(re.search(r"edgar[-_]warehouse", args)) and bool(
        re.search(rf"--source {re.escape(source)} --target {re.escape(target)}( |$)", args))


def process_use(source: str, target: str) -> tuple[dict[int, float], float]:
    """Each process's CPU seconds so far, by pid, and the memory in MB, of the load running one source and target (its
    driver and workers); two readings give the CPU percent."""
    listing = subprocess.run(["ps", "-Ao", "pid,time,rss,args"], check=False, capture_output=True, text=True).stdout
    seconds: dict[int, float] = {}
    memory = 0.0
    for line in listing.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and is_load_process(parts[3], source, target):
            pid, used, rss = parts[:3]
            seconds[int(pid)] = cpu_seconds(used)
            footprint = subprocess.run(["footprint", "-p", pid], check=False, capture_output=True, text=True).stdout \
                if sys.platform == "darwin" else ""
            sized = re.search(r"Footprint: ([\d.]+) (KB|MB|GB)", footprint)
            memory += float(sized.group(1)) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[sized.group(2)] if sized else int(rss) / 1024
    return seconds, memory


def status(steps: list[dict], state: Path, reader_url: str | None, sample: int = 20) -> list[str]:
    """One report line a running step: how long, how far, how fast, what it holds, and a verdict from the evidence.
    The log gives the bundles done and the minutes left; the database (two readings `sample` seconds apart) the rows
    written a minute; the processes their CPU and memory; the log's file its age."""
    text = state.read_text() if state.exists() else ""
    done = done_steps(state)
    started = {}
    for found in re.finditer(r"^(\d\d-\d\d \d\d:\d\d:\d\d) ET (\S+) attempt (\d+) start", text, re.M):
        started[found.group(2)] = (datetime.strptime(found.group(1), "%m-%d %H:%M:%S").replace(year=clock().year), int(found.group(3)))
    busy = external_loads()
    running = [s for s in steps if (s["source"], s["target"]) in busy and s["name"] not in done and s["name"] in started]
    before = database_writes(reader_url) if reader_url else {}
    cpu_before = {s["name"]: process_use(s["source"], s["target"])[0] for s in running}
    time.sleep(sample if before or running else 0)
    rate = writes_per_minute(before, database_writes(reader_url), sample) if before else {}
    waiters = (database_load(reader_url) or {}).get("lock_waiters", 0)
    sessions = database_sessions(reader_url) if reader_url else {}
    lines = [f"{clock():%H:%M} ET: {len(running)} running, {len(done & {s['name'] for s in steps})} of {len(steps)} done; "
             f"database writes a minute: " + (", ".join(f"{k} {v:,.0f}" for k, v in rate.items() if v) or "none") +
             f"; lock waiters {waiters}"]
    lines += [f"  {session_note(name, counts)}" for name, counts in sorted(sessions.items()) if counts["active"] + counts["waiting_on_client"] > 1]
    for step in running:
        began, attempt = started[step["name"]]
        elapsed = (clock().replace(tzinfo=None) - began).total_seconds() / 60
        log = LOGS / f"chain-{RUN}-{step['name']}.log"
        age = (time.time() - log.stat().st_mtime) / 60 if log.exists() else elapsed
        progress = bundle_progress(log.read_text()) if log.exists() else None
        seconds, memory = process_use(step["source"], step["target"])
        count = len(seconds)
        cpu = cpu_percent(0.0, window_cpu(cpu_before[step["name"]], seconds), sample)
        store = store_of(step["target"])
        mine = rate.get(store, 0.0)
        sharing = [o["name"] for o in running if o is not step and store_of(o["target"]) == store]
        wrote = f"{store} {mine:,.0f} rows/min" + (f" shared with {', '.join(sharing)}" if sharing else "")
        left = minutes_left(*progress, elapsed) if progress and progress[1] > 1 else None
        warn = outlook(left, elapsed, step["minutes"], attempt, step["attempts"])
        shown = (f"bundles {progress[0]} of {progress[1]}" + (f", about {left:.0f} min left" if left else "")
                 if progress and progress[1] > 1 else "one document, so its log shows no progress; the database does")
        lines.append(f"  {step['name']} (lane {step['lane']}, attempt {attempt}, {step.get('workers', 2)} workers): {elapsed:.0f} min of {step['minutes']}; "
                     f"{shown}; {count} processes, {cpu:.0f}% CPU, {memory:,.0f} MB; wrote {wrote}; log {age:.0f} min old; "
                     + verdict(elapsed, step["minutes"], age, cpu, mine, waiters, sharing) + (f"; {warn}" if warn else ""))
    return lines


def arguments(step: dict) -> list[str]:
    capture = ROOTS[step.get("capture_root", "captures")] / step["capture"]
    args = ["--source", step["source"], "--target", step["target"], "--capture", str(capture),
            "--capture-run", f"{RUN}-{step['name']}", "--stores", str(STORES),
            "--workers", str(step["workers"]), "--bundles", str(step["bundles"]), "--minutes", str(step["minutes"]),
            "--no-links"]  # the links table is built once, in `finish`
    if "revision" in step:
        args += ["--revision", str(step["revision"])]
    for name, value in (step.get("facts") or {}).items():
        args += ["--fact", f"{name}={value.format(run=RUN)}"]
    return args


def note(message: str, state: Path) -> None:
    line = f"{datetime.now(ZoneInfo('America/New_York')):%m-%d %H:%M:%S} ET {message}"
    print(line, flush=True)
    with state.open("a") as handle:
        handle.write(line + "\n")


def run(args: list[str], env: dict, log: Path | None = None) -> int:
    with (log.open("w") if log else open(os.devnull, "w")) as out:
        return subprocess.run([*ENGINE, *args], env=env, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT).returncode


def plan(step: dict, env: dict) -> str:
    done = subprocess.run([*ENGINE, "load", *arguments(step), "--plan"], env=env, cwd=ROOT, capture_output=True, text=True)
    found = re.search(r"\{.*\}", done.stdout, re.S)
    try:
        body = json.loads(found.group(0))
        return f"documents {body.get('documents')} bundles {body.get('bundles')} blocked {body.get('blocked')}"
    except (AttributeError, ValueError):
        return "no plan: " + (done.stderr.strip().splitlines() or ["?"])[-1][:140]


def done_steps(state: Path) -> set[str]:
    """The steps any lane has finished, read from the shared state file."""
    return set(re.findall(r" ET (\S+) done:", state.read_text())) if state.exists() else set()


def wait_for(step: dict, state: Path, poll: int = 30) -> None:
    """Hold a step until the steps of other lanes it needs are done, and until no other load of its target is running
    (two loads of one source and target at once write the same outputs)."""
    needed = set(step.get("waits_for") or [])
    if needed - done_steps(state):
        note(f"{step['name']} waits for {', '.join(sorted(needed - done_steps(state)))}", state)
    while needed - done_steps(state):
        time.sleep(poll)
    pattern = f"edgar-warehouse load .*--source {re.escape(step['source'])} --target {re.escape(step['target'])}( |$)"
    if subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0:
        note(f"{step['name']} waits for another load of its source and target to end", state)
        while subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0:
            time.sleep(poll)


def attempt_loop(step: dict, env: dict, state: Path) -> bool:
    name, log = step["name"], LOGS / f"chain-{RUN}-{step['name']}.log"
    wait_for(step, state)
    for attempt in range(1, step["attempts"] + 1):
        note(f"{name} attempt {attempt} start", state)
        code = run(["load", *arguments(step)], env, log)
        text = log.read_text()
        if code == 0 and "Load stopped" not in text:
            done = [line for line in text.splitlines() if line.startswith("Done: ")]
            note(f"{name} done: {done[-1][:200] if done else ''}", state)
            return True
        why = [line for line in text.splitlines() if re.search(r"stopped|did not finish|Error", line)]
        note(f"{name} attempt {attempt} stopped rc={code}: "
             f"{re.sub(r'(postgres(ql)?|https?)://[^ ]+', '<addr>', why[-1])[:200] if why else ''}", state)
        log.rename(log.with_name(log.name + f".attempt-{attempt}"))
    note(f"{name} did not finish in {step['attempts']} attempts: the chain stops here", state)
    return False


def finish(env: dict, state: Path) -> None:
    """After the loads: the lookups and the links table are built once each, then each silver table's master ids are
    filled from MDM as it is now (a row that landed before its master was mastered keeps an empty id)."""
    note("lookups start", state)
    note(f"lookups rc={run(['mdm', 'build-lookups'], env, LOGS / f'chain-{RUN}-lookups.log')}", state)
    note(f"links rc={run(['silver', 'links'], env, LOGS / f'chain-{RUN}-links.log')}", state)
    for spec in sorted((ROOT / "rules/sources").glob("*/silver-*.yaml")):
        table = yaml.safe_load(spec.read_text())["table"]
        code = run(["silver", "refresh-ids", table], env, LOGS / f"chain-{RUN}-refresh-{table}.log")
        note(f"refresh-ids {table} rc={code}", state)
    note("chain done", state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for flag in ("list", "plan", "finish"):
        parser.add_argument(f"--{flag}", action="store_true")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--only")
    parser.add_argument("--lane")
    parser.add_argument("--status", action="store_true",
                        help="one line a running step: progress, rate, processes, database writes and a verdict")
    parser.add_argument("--workers", type=int, help="with --only: the step's workers, within the capacity's range, instead of the chain file's")
    parser.add_argument("--capacity", default="local",
                        help="the compute: local (this machine, measured) or a profile of the chain file (aws-small, aws-medium, aws-large)")
    parser.add_argument("--connections", type=int, default=250,
                        help="with --auto: the database connections to aim for; workers rise until they are used")
    parser.add_argument("--deadline", help="with --auto: HH:MM ET today, when every step this started is stopped")
    parser.add_argument("--hours", type=float, help="with --auto: a deadline this many hours from now")
    parser.add_argument("--auto", action="store_true", help="watch the loads and start each step when its lane is free")
    parser.add_argument("--slots", type=int, default=max(2, min(os.cpu_count() or 2, int(
        os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30 // 2))), help="loads running at once")
    args = parser.parse_args()
    steps = chain_steps()
    names = [step["name"] for step in steps]
    for chosen in (args.start, args.only):
        if chosen and chosen not in names:
            print(f"No step named {chosen}", file=sys.stderr)
            return 2
    if args.lane and args.lane not in {step["lane"] for step in steps}:
        print(f"No lane named {args.lane}", file=sys.stderr)
        return 2
    if args.list:
        for step in steps:
            print(f"{step['lane']} {step['name']:30} {step['source']} {step['target']} {step['capture']}")
        return 0
    state = LOGS / f"chain-{RUN}.log"
    if args.status:  # read-only: the reader login only, no loader login, no wake lock, nothing written
        reader = STORES / "reader.env"
        print("\n".join(status(steps, state, load_env(reader).get("DIAGNOSE_DATABASE_URL") if reader.exists() else None)))
        return 0
    env = {**os.environ, **load_env(STORES / "worker.env")}
    LOGS.mkdir(parents=True, exist_ok=True)
    if args.plan:
        for step in steps:
            print(f"{step['name']:30} {plan(step, env)}", flush=True)
        return 0
    if sys.platform == "darwin":
        subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    if args.workers is not None:
        low, top = bounds_for(args.capacity)
        if not args.only or not low <= args.workers <= top:
            print(f"--workers goes with --only and is {low} to {top} on {args.capacity}", file=sys.stderr)
            return 2
        steps = [{**step, "workers": args.workers} if step["name"] == args.only else step for step in steps]
    if args.auto:
        deadline = None
        if args.hours:
            deadline = clock() + timedelta(hours=args.hours)
        elif args.deadline:
            hour, minute = map(int, args.deadline.split(":"))
            deadline = clock().replace(hour=hour, minute=minute, second=0, microsecond=0)
        if auto(steps, state, args.slots, deadline=deadline, connections=args.connections, bounds=bounds_for(args.capacity),
                reader_url=load_env(STORES / "reader.env").get("DIAGNOSE_DATABASE_URL") if (STORES / "reader.env").exists() else None):
            return 1
        finish(env, state)
        return 0
    if not args.finish:
        started = args.start is None
        for step in steps:
            started = started or step["name"] == args.start
            if not started or (args.only and step["name"] != args.only) or (args.lane and step["lane"] != args.lane):
                continue
            if not attempt_loop(step, env, state):
                return 1
        if args.only or args.lane:
            return 0
    finish(env, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
