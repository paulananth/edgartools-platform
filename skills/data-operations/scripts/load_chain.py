#!/usr/bin/env python3
"""Load every captured source into one store, in the order rules/load-chain.yaml gives.

    python load_chain.py --list               the steps, in order
    python load_chain.py --plan               what each step would load (documents and bundles); writes nothing
    python load_chain.py                      the whole chain, then the links table and each silver table's master ids
    python load_chain.py --from <step>        carry on from a step (a done step costs one call: nothing is loaded twice)
    python load_chain.py --only <step>        one step
    python load_chain.py --lane <name>        the steps of one lane; run several lanes at once (see the chain file)
    python load_chain.py --finish             only what follows the loads, once every lane is done
    python load_chain.py --catalog-status     publish the catalog status of every step already done (a catch-up)
    python load_chain.py --finish --lookups   the same, with the name-search lookups built first (only the context search needs them)
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
import hashlib
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
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(os.environ.get("ROOT") or Path(__file__).resolve().parents[3])
HOME = Path.home()
STORES = Path(os.environ.get("STORES") or HOME / ".config/edgartools/hosted")
ROOTS = {"captures": Path(os.environ.get("CAPTURES") or HOME / ".local/share/edgartools/mdm/captures"),
         "proving": Path(os.environ.get("PROVING") or HOME / ".local/share/edgartools/mdm/proving")}
LOGS = Path(os.environ.get("LOGS") or HOME / ".local/share/edgartools/load-logs")
RUN = os.environ.get("RUN", "fresh-v1")
def engine_command(environ: dict) -> list[str]:
    """The command that runs `edgar-warehouse`: the executable `EDGAR_WAREHOUSE` names (a checkout whose environment is
    built elsewhere), else `uv run --no-sync` in the checkout."""
    return [environ["EDGAR_WAREHOUSE"]] if environ.get("EDGAR_WAREHOUSE") else ["uv", "run", "--no-sync", "edgar-warehouse"]


ENGINE = engine_command(os.environ)


def load_env(path: Path) -> dict:
    """The shell-style `export KEY=value` lines of a private env file, parsed as data."""
    env = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
        if match:
            env[match.group(1)] = shlex.split(match.group(2))[0] if match.group(2) else ""
    return env


def worker_env() -> dict:
    """The stores folder's worker.env as data, or nothing when the folder has none (CI, a fresh checkout)."""
    path = STORES / "worker.env"
    return load_env(path) if path.exists() else {}


def chain_steps(path: Path = ROOT / "rules/load-chain.yaml") -> list[dict]:
    """The chain's steps, each with the chain's `defaults` for what it does not say itself."""
    chain = yaml.safe_load(path.read_text())
    steps = [{**(chain.get("defaults") or {}), **step} for step in chain["steps"]]
    for step in steps:
        measured = step.get("worker_gb")
        if measured is not None and not (isinstance(measured, (int, float)) and 0.01 <= measured <= 64):
            raise ValueError(f"{step['name']}: worker_gb must be a number from 0.01 to 64 gigabytes, not {measured!r}")
    return steps


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


MOVE_EVERY = timedelta(minutes=10)  # a step is moved (stopped and started again) at most this often: each move abandons its bundles in flight
WORKER_GB = 0.5  # the memory a worker is sized for
WORKERS_PER_VCPU = 4  # a worker waits on the database much of the time, so a vCPU carries several


def workers_range(vcpu: float, memory_gb: float, worker_gb: float = WORKER_GB) -> tuple[int, int]:
    """The workers a task can carry, from what it has: its memory in worker-sized shares (`worker_gb`, half a gigabyte
    unless a step has been measured smaller), at most four to a vCPU, never fewer than one. The range follows the compute
    (a 1 vCPU, 4 GB task carries up to 4; 2 vCPU, 8 GB up to 8), so it is the configuration's, never a fixed two to eight."""
    return 1, max(1, min(int(memory_gb / worker_gb + 1e-9), int(vcpu * WORKERS_PER_VCPU)))


def capacity_profiles(path: Path = ROOT / "rules/load-chain.yaml") -> dict[str, dict]:
    """The named compute sizes of the chain file (the AWS ECS task sizes the state machines run on)."""
    return yaml.safe_load(path.read_text()).get("capacity") or {}


def physical_gb() -> float:
    return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30


def capacity_of(name: str) -> tuple[float, float]:
    """The vCPUs and gigabytes of a capacity: a profile of the chain file, or `local`, this machine measured (half its
    memory, the rest being the operator's other work)."""
    if name == "local":
        return os.cpu_count() or 1, physical_gb() / 2
    profiles = capacity_profiles()
    if name not in profiles:
        raise SystemExit(f"No capacity named {name}: local or {', '.join(sorted(profiles))}")
    return profiles[name]["vcpu"], profiles[name]["memory_gb"]


def bounds_for(name: str, worker_gb: float = WORKER_GB) -> tuple[int, int]:
    """The workers range of a capacity, for a worker of `worker_gb`."""
    return workers_range(*capacity_of(name), worker_gb)


def memory_free_fraction(text: str) -> float | None:
    """The share of memory free, from `memory_pressure` (macOS); None when it cannot be read."""
    found = re.search(r"memory free percentage: (\d+)%", text)
    return int(found.group(1)) / 100 if found else None


def pressure(load: float, cores: int, swap_used: float | None, relaxed: bool = False, memory_free: float | None = None) -> str:
    """How hard the machine is pressed: `high` above one and a half times the cores in load average, or three quarters
    of swap used while memory is short (a run behind its deadline is `relaxed` to twice the cores and nine tenths of swap),
    or under a tenth of memory free; `low` below three quarters of the cores with half the swap or plenty of memory free
    (four tenths); else `ok`. Swap used is a stock the system keeps long after the load that filled it has gone, so it
    presses only when memory is short too (or unreadable); the memory free is the reading of now."""
    heavy, swap_limit = (2.0, 0.9) if relaxed else (1.5, 0.75)
    short = memory_free is None or memory_free < 0.25
    if load > heavy * cores or (swap_used is not None and swap_used > swap_limit and short) or (memory_free is not None and memory_free < 0.10):
        return "high"
    roomy = swap_used is None or swap_used < 0.5 or (memory_free is not None and memory_free >= 0.40)
    return "low" if load < 0.75 * cores and roomy else "ok"


def machine_pressure(relaxed: bool = False) -> str:
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], check=False, capture_output=True,
                          text=True).stdout if sys.platform == "darwin" else ""
    memory = subprocess.run(["memory_pressure"], check=False, capture_output=True,
                            text=True).stdout if sys.platform == "darwin" else ""
    return pressure(os.getloadavg()[0], os.cpu_count() or 1, swap_fraction(swap), relaxed, memory_free_fraction(memory))


def clamped(steps: list[dict], name: str, capacity: tuple[float, float] | None = None) -> list[dict]:
    """The steps with each one's workers held to the named capacity's range, whatever the run mode: the chain file asks
    for what a step wants, the compute says what a task carries. Each step's range uses its own measured `worker_gb`
    where the chain file has one (`capacity` replaces the named compute, for a test)."""
    held = []
    for step in steps:
        low, top = workers_range(*(capacity or capacity_of(name)), step.get("worker_gb", WORKER_GB))
        held.append({**step, "workers": min(max(step["workers"], low), top)})
    return held


def rescale(workers: dict[str, int], priority: dict[str, int], level: str, bounds: dict[str, tuple[int, int]]) -> tuple[str, int] | None:
    """One change of workers within each step's own range (`bounds` by step: the capacity's, for the step's measured
    memory): with room (`low`) the step with the longest chain behind it doubles, up to its top; when pressed (`high`) the
    step with the shortest halves, down to its floor. Anything else changes nothing."""
    order = sorted(workers, key=lambda name: -priority[name])
    if level == "low":
        return next(((name, min(bounds[name][1], workers[name] * 2)) for name in order if workers[name] < bounds[name][1]), None)
    if level == "high":
        return next(((name, max(bounds[name][0], workers[name] // 2)) for name in reversed(order)
                     if workers[name] > bounds[name][0]), None)
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
         reader_url: str | None = None, connections: int = 250, bounds: tuple[int, int] | None = None,
         capacity: str = "local") -> int:
    """Watch the loads and start the next ready step whenever a slot is free and the machine is not pressed. One start
    a cycle: the load average lags, so a started step is counted running before the next is judged. Each step runs as
    `load_chain.py --only <step> --workers <n>` (the attempt loop). The workers follow the machine within the capacity's
    range (`bounds`; the machine's own when not given): with room
    the step with the longest chain behind it doubles, when pressed the step with the shortest halves, one change a
    cycle, by stopping the step's load and starting it again (a load resumes where it stopped). With a `deadline`, a run
    behind its schedule (more of the window used than of the work done) is allowed twice the cores in load; at the
    deadline every step this started is stopped and the run ends, naming what is left. A step that uses up its attempts
    blocks what follows it and the rest carry on. Ends when every step is done (then the links table and the master ids), when
    nothing more can start, or at the deadline."""
    def range_of(name: str) -> tuple[int, int]:
        return bounds or bounds_for(capacity, by_name[name].get("worker_gb", WORKER_GB))

    children: dict[str, subprocess.Popen] = {}
    workers: dict[str, int] = {}
    failed: set[str] = set()
    by_name = {step["name"]: step for step in steps}
    started, cycle, began, moved = clock(), 0, {}, {}
    total = sum(step["minutes"] for step in steps)

    def spawn(name: str, count: int) -> None:
        workers[name] = count
        began.setdefault(name, clock())
        children[name] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--only", name,
                                           "--workers", str(count), "--capacity", capacity], start_new_session=True)

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
            low, top = range_of(name)
            count = min(max(by_name[name].get("workers", low), low), top)
            note(f"scheduler starts {name} at {count} workers", state)
            spawn(name, count)
        settled = {name for name in workers if clock() - moved.get(name, began[name]) >= MOVE_EVERY}  # not moved lately
        if not starts and (change := rescale({n: workers[n] for n in settled}, {n: length[n] for n in settled}, level,
                                             {n: range_of(n) for n in settled})):
            name, count = change
            note(f"scheduler moves {name} from {workers[name]} to {count} workers ({level} load)", state)
            stop(children[name])
            spawn(name, count)
            moved[name] = clock()
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


def bundles_run(text: str) -> int:
    """The bundles this attempt ran (its `run ... complete in` lines), not the ones an earlier attempt already loaded."""
    return len(re.findall(r"^\s+run \S+ complete in", text, re.M))


def minutes_left(done: int, total: int, elapsed: float, ran: int) -> float | None:
    """The minutes left at this attempt's rate: its minutes over the bundles it ran (`ran`), for the bundles not yet done.
    None before it has run one (no rate yet); the bundles an earlier attempt skipped never enter the rate."""
    return None if ran <= 0 else max(total - done, 0) * elapsed / ran


def writes_per_minute(before: dict[str, int], after: dict[str, int], seconds: float) -> dict[str, float]:
    """Rows written a minute in each store, from two readings of its cumulative inserts, updates and deletes."""
    return {name: max(after.get(name, count) - count, 0) * 60.0 / seconds for name, count in before.items()}


def cpu_seconds(text: str) -> float:
    """The CPU time of the processes in `ps -o time=` output (`M:SS.ss` or `H:MM:SS.ss`, one per line), summed."""
    total = 0.0
    for line in text.split():
        try:
            days, _, clock_part = line.rpartition("-")
            parts = [float(part) for part in clock_part.split(":")]
        except ValueError:  # a time that is not one: no CPU counted, never an exception for the whole listing
            continue
        total += sum(value * 60 ** index for index, value in enumerate(reversed(parts))) + (float(days) * 86400 if days else 0.0)
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


def load_pids(listing: str, source: str, target: str) -> dict[int, float]:
    """The CPU seconds of every process of the load of one source and target: its driver and the workers it started,
    found by parentage (a spawned worker's command line names no source). `listing` is `ps -Ao pid,ppid,time,rss,args`."""
    rows = {}
    for line in listing.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4 and parts[0].isdigit() and parts[1].isdigit():
            rows[int(parts[0])] = (int(parts[1]), cpu_seconds(parts[2]), parts[4] if len(parts) == 5 else "")
    found = {pid for pid, (_, _, args) in rows.items() if is_load_process(args, source, target)}
    grown = True
    while grown:
        grown = False
        for pid, (parent, _, _) in rows.items():
            if pid not in found and parent in found:
                found.add(pid)
                grown = True
    return {pid: rows[pid][1] for pid in sorted(found)}


def load_workers(listing: str, source: str, target: str) -> int | None:
    """The `--workers` the running load of one source and target was started with, from its driver's command line."""
    for line in listing.splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and re.search(r"edgar[-_]warehouse load ", parts[4]) and is_load_process(parts[4], source, target):
            found = re.search(r"--workers (\d+)", parts[4])
            return int(found.group(1)) if found else None
    return None


def process_use(source: str, target: str) -> tuple[dict[int, float], float]:
    """Each process's CPU seconds so far, by pid, and the memory in MB, of the load running one source and target (its
    driver and the workers it started); two readings give the CPU percent."""
    listing = subprocess.run(["ps", "-Ao", "pid,ppid,time,rss,args"], check=False, capture_output=True, text=True).stdout
    seconds = load_pids(listing, source, target)
    memory = 0.0
    for pid in seconds:
        footprint = subprocess.run(["footprint", "-p", str(pid)], check=False, capture_output=True, text=True).stdout \
            if sys.platform == "darwin" else ""
        sized = re.search(r"Footprint: ([\d.]+) (KB|MB|GB)", footprint)
        rss = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], check=False, capture_output=True, text=True).stdout.strip()
        memory += float(sized.group(1)) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[sized.group(2)] if sized else int(rss or 0) / 1024
    return seconds, memory


WRITES_NOTE = "rows written a minute are counted when a transaction commits, so a long transaction shows none until it ends"


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
    listing = subprocess.run(["ps", "-Ao", "pid,ppid,time,rss,args"], check=False, capture_output=True, text=True).stdout
    sessions = database_sessions(reader_url) if reader_url else {}
    lines = [f"{clock():%H:%M} ET: {len(running)} running, {len(done & {s['name'] for s in steps})} of {len(steps)} done; "
             f"database writes a minute: " + (", ".join(f"{k} {v:,.0f}" for k, v in rate.items() if v) or "none") +
             f"; lock waiters {waiters} ({WRITES_NOTE})"]
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
        left = minutes_left(*progress, elapsed, bundles_run(log.read_text())) if progress and progress[1] > 1 else None
        warn = outlook(left, elapsed, step["minutes"], attempt, step["attempts"])
        shown = (f"bundles {progress[0]} of {progress[1]}" + (f", about {left:.0f} min left" if left else "")
                 if progress and progress[1] > 1 else "one document, so its log shows no progress; the database does")
        started_with = load_workers(listing, step["source"], step["target"])
        lines.append(f"  {step['name']} (lane {step['lane']}, attempt {attempt}, {started_with or step.get('workers', 2)} workers): {elapsed:.0f} min of {step['minutes']}; "
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


def store_id(url: str) -> str:
    """Eight hex digits naming a store by its instance's address, so a state file can tell which store its lines belong
    to without showing the address. Any login and database of one instance give the same name; the host's case and the
    default port do not matter; a socket's directory (`?host=/dir`) is its host. A URL that names no host is an error: it
    would give distinct stores one name. (`localhost` and `127.0.0.1` are different names.)"""
    text = url.replace("postgresql+psycopg2", "postgresql")
    try:
        part = urlsplit(text)
        host, port = part.hostname, part.port
    except ValueError:  # an unescaped `/` or `:` in a password: read the address after the last `@`
        part = urlsplit("postgresql://" + text.split("@")[-1])
        host, port = part.hostname, part.port
    host = host or (parse_qs(part.query).get("host") or [""])[0]
    if not host:
        raise ValueError("The URL names no host: a store cannot be told from another")
    return hashlib.sha256(f"{host.lower()}:{port or 5432}".encode()).hexdigest()[:8]


def database_generation(url: str) -> str:
    """The creation identity of the database the URL names (its `pg_database` oid): a database made again after a reset has a
    new one, while the instance's address, and so the store's name, stays the same. Empty when it cannot be read; nothing
    about the connection is ever reported."""
    try:
        import psycopg2

        with contextlib.closing(psycopg2.connect(url.replace("postgresql+psycopg2", "postgresql"), connect_timeout=5)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select oid from pg_database where datname = current_database()")
                return str(cursor.fetchone()[0])
    except Exception:  # an unreadable store is no reason to touch a running load's file
        return ""


def mdm_url_of(url: str) -> str:
    """The same login and instance with the `mdm` database: the one whose generation names a store in the state file, read
    through the diagnostic login, which may name another database."""
    return re.sub(r"/[^/?]+(\?|$)", r"/mdm\1", url, count=1)


STORE_MARKER = re.compile(r"chain store (\w+)(?: generation (\w+))?$", re.M)


def state_verdict(text: str, store: str, generation: str = "", adopt: bool = False) -> str:
    """What a state file's text is to this store, as a pure answer the run and `--status` share: "same" (written for this
    store; a marker that names no generation, or a generation not readable now, is not compared), "fresh" (no file), "adopted"
    (no marker, and the operator says it is this store's) or "set aside" (another store, another generation of this one, or lines
    and no marker)."""
    found = STORE_MARKER.findall(text)
    if found and found[-1][0] == store and (not generation or not found[-1][1] or found[-1][1] == generation):
        return "same"
    if not text:
        return "fresh"
    return "adopted" if adopt and not found else "set aside"


def ensure_store(state: Path, store: str, adopt: bool = False, generation: str = "") -> str:
    """Make the state file this store's (`state_verdict`), under a lock so lanes starting together do it once. A store is its
    instance's name and, when it can be read, its database's `generation`; a file is trusted only when it was written for both.
    A file whose marker names no generation learns it the next time it is readable, so a blip at creation never leaves a reset
    unseen. A file that is set aside is renamed, never deleted or overwritten, and its `done` lines never satisfy a wait this store
    has not earned; `adopt` keeps an unmarked file on the operator's word."""
    import fcntl

    stamp = (f"{datetime.now(ZoneInfo('America/New_York')):%m-%d %H:%M:%S} ET chain store {store}"
             f"{f' generation {generation}' if generation else ''}\n")
    state.parent.mkdir(parents=True, exist_ok=True)

    def keep(suffix: str) -> None:
        target = state.with_name(f"{state.name}.{suffix}")
        number = 1
        while target.exists():  # a file set aside before is never overwritten
            number += 1
            target = state.with_name(f"{state.name}.{suffix}.{number}")
        state.rename(target)

    with state.with_name(state.name + ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        text = state.read_text() if state.exists() else ""  # read again under the lock: another lane may have done it
        found = STORE_MARKER.findall(text)
        verdict = state_verdict(text, store, generation, adopt)
        if verdict == "same":
            if generation and not found[-1][1]:
                with state.open("a") as handle:  # appended, as the chain's own lines are
                    handle.write(stamp)
            return "same"
        if verdict == "adopted":
            state.write_text(text + stamp)
            return "adopted"
        if text:
            if not found:
                suffix = "unmarked"
            elif found[-1][0] == store:
                suffix = f"{store}-{found[-1][1]}"  # this store, made again: its old generation
            else:
                suffix = found[-1][0]
            keep(suffix)
        state.write_text(stamp)
        return verdict


CLEARS_ITSELF = re.compile(r"deadline|deadlock|lock timeout|lock not available|could not obtain lock|could not connect|"
                           r"connection (?:timed out|refused|reset|closed)|server closed the connection|timed out", re.I)


def retry_is_pointless(previous: str, current: str) -> bool:
    """A failure that comes back exactly as it was, with nothing moved (its bundle and counts are the same), is not one
    a retry can change. A window that ran out, a lock or deadlock, and a lost connection are not that: they clear when
    the other load ends or the connection returns, and the next attempt resumes where this one stopped."""
    return bool(previous) and previous == current and not CLEARS_ITSELF.search(current)


SECRET_KEY = r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|dsn|url|credential)\w*"


def redact(text: str) -> str:
    """Hide every address (`postgres://`, `postgresql+driver://`, `https://`) and the value of any key named like a secret
    (`password=`, `token:`, `api_key=`, `dsn=`, `url=`), so a log line kept on disk never carries one."""
    text = re.sub(r"(?:postgres(?:ql)?(?:\+\w+)?|https?)://\S+", "<addr>", text)
    text = re.sub(rf"(\b{SECRET_KEY}\s*[=:]\s*)(?:'[^']*'|\"[^\"]*\"|\S+)", r"\1<hidden>", text, flags=re.I)
    return re.sub(r"\bhost=\S+", "host=<hidden>", text)


def errors_since(path: Path, offset: int, source: str | None = None, target: str | None = None) -> str:
    """What was written to the shared error log after `offset`, addresses hidden, and, given a source and target, only
    the blocks of that step's own commands (a block opens with `$ <command> --source X --target Y`): the file is shared
    by every lane and every run, so another lane's errors in the same window are not this step's."""
    if not path.exists() or path.stat().st_size <= offset:
        return ""
    with path.open("rb") as handle:
        handle.seek(offset)
        text = handle.read().decode(errors="replace")
    if source and target:
        wanted = re.compile(rf"--source {re.escape(source)} --target {re.escape(target)}( |$)")
        text = "".join(block for block in re.split(r"(?m)^(?=\$ )", text) if wanted.search(block.split("\n", 1)[0]))
    return redact(text)


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


CATALOG_KEYS = ("OPENMETADATA_URL", "OPENMETADATA_TOKEN")


def last_run_id(text: str) -> str | None:
    """The Bookkeeping run a step completed last, from its log: the catalog's status is that of the latest run."""
    found = re.findall(r"^\s+run ([0-9a-f-]{36}) complete", text, re.M)
    return found[-1] if found else None


def catalog_env_file(environ: dict, home: Path, root: Path) -> Path:
    """Where the catalog's address and token are kept, first that exists: the file `OPENMETADATA_ENV_FILE` names, the private
    folder outside every checkout (`~/.config/edgartools/openmetadata.env`), then the checkout's own `.env` (the older place)."""
    named = environ.get("OPENMETADATA_ENV_FILE")
    for path in ([Path(named)] if named else []) + [home / ".config/edgartools/openmetadata.env", root / ".env"]:
        if path.exists():
            return path
    return root / ".env"


def catalog_env(path: Path) -> dict[str, str]:
    """Only the catalog's address and token, from the private env file, and only when both are there: nothing else the
    file holds (a login, a password) reaches the command, and no half-set pair does."""
    if not path.exists():
        return {}
    found = {}
    for line in path.read_text().splitlines():  # only the two keys are read: another line, however odd, is never parsed
        match = re.match(rf"^(?:export\s+)?({'|'.join(CATALOG_KEYS)})=(.*)$", line.strip())
        if match:
            try:
                value = shlex.split(match.group(2))
            except ValueError:
                continue
            found[match.group(1)] = value[0] if value else ""
    return {key: found[key] for key in CATALOG_KEYS} if all(found.get(key) for key in CATALOG_KEYS) else {}


def catalog_outcome(answer: str, error: str = "") -> str:
    """What `rules catalog status` answered (its JSON report on stdout), in a few words: confirmed as the status it read back,
    or not published and why. Never raises."""
    try:
        body = json.JSONDecoder().raw_decode(answer[answer.index("{"):])[0] if "{" in answer else None  # the first whole object
    except ValueError:
        body = None
    if not isinstance(body, dict):
        lines = [line.strip() for line in redact(error).splitlines() if line.strip()]
        return f"not published: no readable answer ({lines[-1][:120]})" if lines else "not published: no readable answer"
    if body.get("ok"):
        return f"confirmed as {(body.get('pipeline_status') or {}).get('execution_status', 'its status')}"
    return f"not published: {redact(str(body.get('cause') or 'no cause given'))[:120]}"


def step_run_id(step_name: str) -> str | None:
    """The Bookkeeping run to publish for a step: its last completed run, from its log or, when its last attempt found
    everything already loaded and ran none, from its newest earlier attempt's."""
    log = LOGS / f"chain-{RUN}-{step_name}.log"
    attempts = sorted(log.parent.glob(log.name + ".attempt-*"), key=lambda p: int(p.name.rsplit("-", 1)[1]), reverse=True)
    for path in [log, *attempts]:
        if path.exists() and (run := last_run_id(path.read_text())):
            return run
    return None


def run_catalog_status(command: list[str], env: dict, timeout: int = 60) -> tuple[str, str]:
    """Run a command and return its stdout and stderr, cut off at `timeout` seconds with its whole process group: a catalog
    that hangs must not stall the lane or leave a process calling it."""
    child = subprocess.Popen(command, env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    try:
        return child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
        return "", "the command did not answer in time"


SAFE_BASE = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "UV_CACHE_DIR", "UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")


def status_env(base: dict, worker: dict, catalog: dict) -> dict:
    """The environment of `rules catalog status`: a short allowlist of the process's own (a path, a home), the Bookkeeping
    login it reads the run with, and the catalog's address and token. No other login, key or password reaches it."""
    given = {key: base[key] for key in SAFE_BASE if key in base}
    if worker.get("BOOKKEEPING_DATABASE_URL"):
        given["BOOKKEEPING_DATABASE_URL"] = worker["BOOKKEEPING_DATABASE_URL"]
    return {**given, **catalog}


def latest_run(rows: list[dict], source: str, target: str) -> str | None:
    """The newest completed Bookkeeping run of a source and target, from Bookkeeping's own run rows."""
    done = [row for row in rows if row.get("name") == source and row.get("target") == target
            and row.get("state") == "complete" and row.get("completed_at")]
    return max(done, key=lambda row: row["completed_at"])["run_id"] if done else None


_RUNS: list[dict] | None = None
RUNS_LIMIT = 1000  # `bookkeeping runs` refuses a larger page


def runs_may_be_cut(rows: list[dict]) -> bool:
    """A full page may have more runs behind it (newest first): the oldest steps' runs could be missing."""
    return len(rows) >= RUNS_LIMIT


def bookkeeping_runs() -> list[dict]:
    """Bookkeeping's run rows (`bookkeeping runs`), read once and kept for the process: the authority on which run is a step's,
    where its logs name none (a step the lanes re-ran logged only `already loaded`)."""
    global _RUNS
    if _RUNS is None:
        answer, _ = run_catalog_status([*ENGINE, "bookkeeping", "runs", "--limit", str(RUNS_LIMIT)],
                                       status_env(os.environ, worker_env(), {}), timeout=300)
        try:
            _RUNS = json.JSONDecoder().raw_decode(answer[answer.index("["):])[0] if "[" in answer else []
        except ValueError:
            _RUNS = []
    return _RUNS


def run_to_publish(step: dict) -> str | None:
    """A step's run for the catalog: the last one its logs completed, else Bookkeeping's latest for its source and target."""
    return step_run_id(step["name"]) or latest_run(bookkeeping_runs(), step["source"], step["target"])


def publish_catalog_status(step: dict) -> str:
    """Publish a finished step's latest Bookkeeping run as its target Pipeline's status in the catalog
    (`rules catalog status --bookkeeping-run`), when the catalog's address and token are configured."""
    run = run_to_publish(step)
    env = catalog_env(catalog_env_file(os.environ, Path.home(), ROOT))
    if not run:
        return "not published: the step completed no run of its own"
    if not env:
        return "not published: no catalog address and token configured"
    answer, error = run_catalog_status(
        [*ENGINE, "rules", "catalog", "status", "--bookkeeping-run", run, "--root", str(ROOT / "rules")],
        status_env(os.environ, worker_env(), env))
    return catalog_outcome(answer, error)


def tell_catalog(step: dict, state: Path) -> str:
    """Publish a step's status and note the outcome. A status that cannot be published is a note, never a failed load: the
    catalog describes the load and never decides it."""
    try:
        outcome = publish_catalog_status(step)
    except Exception as error:  # noqa: BLE001  whatever went wrong, the step stays done
        outcome = f"not published: {type(error).__name__}"
    note(f"{step['name']} catalog status: {outcome}", state)
    return outcome


def after_done(step: dict, state: Path) -> None:
    """After a step is done: tell the catalog."""
    tell_catalog(step, state)


def catch_up(steps: list[dict], state: Path) -> dict[str, str | None]:
    """Publish the status of every step already done, from the step's own log (a step done before the catalog was configured,
    or while it was unreachable). None for a step not done; a step with no run in any attempt's log is not published."""
    done, outcomes = done_steps(state), {}
    for step in steps:
        if step["name"] not in done:
            outcomes[step["name"]] = None
            continue
        outcomes[step["name"]] = tell_catalog(step, state)
    return outcomes


def attempt_loop(step: dict, env: dict, state: Path) -> bool:
    name, log = step["name"], LOGS / f"chain-{RUN}-{step['name']}.log"
    wait_for(step, state)
    errors, offset, previous = STORES / "load-errors.log", 0, ""
    for attempt in range(1, step["attempts"] + 1):
        note(f"{name} attempt {attempt} start", state)
        offset = errors.stat().st_size if errors.exists() else 0
        code = run(["load", *arguments(step)], env, log)
        text = log.read_text()
        if code == 0 and "Load stopped" not in text:
            done = [line for line in text.splitlines() if line.startswith("Done: ")]
            note(f"{name} done: {done[-1][:200] if done else ''}", state)
            after_done(step, state)
            return True
        why = [line for line in text.splitlines() if re.search(r"stopped|did not finish|Error", line)]
        note(f"{name} attempt {attempt} stopped rc={code}: "
             f"{redact(why[-1])[:200] if why else ''}", state)
        log.rename(log.with_name(log.name + f".attempt-{attempt}"))
        kept = errors_since(errors, offset, step["source"], step["target"])
        if kept:
            log.with_name(log.name + f".attempt-{attempt}.errors").write_text(kept)
        current = why[-1] if why else ""
        if retry_is_pointless(previous, current):
            note(f"{name} stopped: the same failure came back, so a retry cannot change it (its errors: "
                 f"{log.name}.attempt-{attempt}.errors)", state)
            return False
        previous = current
    note(f"{name} did not finish in {step['attempts']} attempts: the chain stops here", state)
    return False


def finish(env: dict, state: Path, lookups: bool = False) -> None:
    """After the loads: the links table is built once, then each silver table's master ids are filled from MDM as it is now
    (a row that landed before its master was mastered keeps an empty id). The name-search lookups are built only when asked
    (`lookups`): a load reads none of them, only the context search does, and building them re-derives every master."""
    if lookups:
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
    for flag in ("list", "plan", "finish", "lookups"):
        parser.add_argument(f"--{flag}", action="store_true")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--only")
    parser.add_argument("--lane")
    parser.add_argument("--adopt-state", action="store_true",
                        help="keep a chain state file that has done lines and no store marker, as this store's (otherwise it is set aside)")
    parser.add_argument("--catalog-status", action="store_true",
                        help="publish the catalog status of every step already done (a catch-up); needs the catalog configured")
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
    steps = clamped(chain_steps(), args.capacity)
    names = [step["name"] for step in steps]
    for chosen in (args.start, args.only):
        if chosen and chosen not in names:
            print(f"No step named {chosen}", file=sys.stderr)
            return 2
    if args.lane and args.lane not in {step["lane"] for step in steps}:
        print(f"No lane named {args.lane}", file=sys.stderr)
        return 2
    if args.lookups and (args.only or args.lane or not args.finish and (args.list or args.plan)):
        print("--lookups goes with --finish (or the whole chain), never a partial run that does not reach the finish", file=sys.stderr)
        return 2
    if args.list:
        for step in steps:
            print(f"{step['lane']} {step['name']:30} {step['source']} {step['target']} {step['capture']}")
        return 0
    state = LOGS / f"chain-{RUN}.log"
    if args.status:  # read-only: the reader login only, no loader login, no wake lock, nothing written
        reader = STORES / "reader.env"
        reader_url = load_env(reader).get("DIAGNOSE_DATABASE_URL") if reader.exists() else None
        counted = state
        if reader_url and state.exists():  # the file the next run would set aside is no evidence about this store
            try:
                if state_verdict(state.read_text(), store_id(reader_url), database_generation(mdm_url_of(reader_url))) == "set aside":
                    print(f"{state.name} was not written for this store (another store, a database made again, or no marker): "
                          "the next run sets it aside, and its done lines are not counted here")
                    counted = state.with_name(state.name + ".not-this-store")
            except ValueError:
                pass
        print("\n".join(status(steps, counted, reader_url)))
        return 0
    env = {**os.environ, **load_env(STORES / "worker.env")}
    LOGS.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    if args.workers is not None:
        wanted = next((step for step in steps if step["name"] == args.only), {})
        low, top = bounds_for(args.capacity, wanted.get("worker_gb", WORKER_GB))
        if not args.only or not low <= args.workers <= top:
            print(f"--workers goes with --only and is {low} to {top} on {args.capacity}", file=sys.stderr)
            return 2
        steps = [{**step, "workers": args.workers} if step["name"] == args.only else step for step in steps]
    if not args.plan and env.get("MDM_DATABASE_URL"):
        try:
            outcome = ensure_store(state, store_id(env["MDM_DATABASE_URL"]), adopt=args.adopt_state,
                                   generation=database_generation(env["MDM_DATABASE_URL"]))
        except ValueError as refused:
            print(refused, file=sys.stderr)
            return 2
        if outcome == "set aside":
            print(f"{state.name} was not written for this store (another store, a database made again, or no marker): set aside "
                  "and kept beside it, and this store starts a fresh chain state", flush=True)
        elif outcome == "adopted":
            print(f"{state.name} adopted as this store's, on your word", flush=True)
    if args.plan:
        for step in steps:
            print(f"{step['name']:30} {plan(step, env)}", flush=True)
        return 0
    if args.catalog_status:
        for name, outcome in catch_up(steps, state).items():
            print(f"{name:30} {outcome or 'not done'}")
        return 0
    if args.auto:
        deadline = None
        if args.hours:
            deadline = clock() + timedelta(hours=args.hours)
        elif args.deadline:
            hour, minute = map(int, args.deadline.split(":"))
            deadline = clock().replace(hour=hour, minute=minute, second=0, microsecond=0)
        if auto(steps, state, args.slots, deadline=deadline, connections=args.connections, capacity=args.capacity,
                reader_url=load_env(STORES / "reader.env").get("DIAGNOSE_DATABASE_URL") if (STORES / "reader.env").exists() else None):
            return 1
        finish(env, state, args.lookups)
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
    finish(env, state, args.lookups)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
