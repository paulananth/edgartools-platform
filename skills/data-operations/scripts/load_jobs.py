#!/usr/bin/env python3
"""Load every captured source into one store, in the order rules/load-jobs.yaml gives.

    python load_jobs.py --list               the steps, in order
    python load_jobs.py --plan               what each step would load (documents and bundles); writes nothing
    python load_jobs.py                      all the load jobs, then the links tables and master_binding
    python load_jobs.py --from <step>        carry on from a step (a done step costs one call: nothing is loaded twice)
    python load_jobs.py --only <step>        one step
    python load_jobs.py --lane <name>        the steps of one lane; run several lanes at once (see the load jobs file)
    python load_jobs.py --begin              mark a load's start in the load jobs state, before its lanes start
    python load_jobs.py --finish             only what follows the loads, once every lane is done
    python load_jobs.py --catalog-status     publish the catalog status of every step already done (a catch-up)
    python load_jobs.py --finish --lookups   the same, with the name-search lookups built first (only the context search needs them)
    python load_jobs.py --status --run <label>  what the named load is doing: progress, rate, processes, a verdict
    python load_jobs.py --status --json --run <label>  the named load's state and the running steps, stores and machine
    python load_jobs.py --auto [--slots N] [--hours H | --deadline HH:MM]
                                              watch the loads: start each step when its lane is free, move its
                                              workers (within --capacity) with the machine, report a missed deadline and go on (see `auto`)

Each step is the same resumable `load` command, run again until it finishes (a stopped attempt names why in its log and
the next carries on from where it stopped). The load stops at the first step that does not finish in its attempts.
STORES (default ~/.config/edgartools/hosted) is the stores folder, whose worker.env holds the logins; CAPTURES, PROVING
and LOGS name the captured files and the logs; RUN names the run's state and log files, never a load's inputs (the
capture runs are the load jobs file's `capture_label`). The machine stays awake for all the load jobs
(a sleep once dropped a hosted connection and lost 74 minutes). Run it from the checkout whose code should load.
"""
import argparse
import contextlib
import fcntl
from collections import Counter
import hashlib
import json
import os
import re
import shlex
import signal
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(os.environ.get("ROOT") or Path(__file__).resolve().parents[3])
HOME = Path.home()
STORES = Path(os.environ.get("STORES") or HOME / ".config/edgartools/hosted")
ROOTS = {"captures": Path(os.environ.get("CAPTURES") or HOME / ".local/share/edgartools/mdm/captures"),
         "proving": Path(os.environ.get("PROVING") or HOME / ".local/share/edgartools/mdm/proving")}
LOGS = Path(os.environ.get("LOGS") or HOME / ".local/share/edgartools/load-logs")
RUN = os.environ.get("RUN", "fresh-v1")
FORCE = "LOAD_FORCE"  # set by `--force` to the load's time (UTC) for this process and the steps it starts: a load is forced as a whole
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


def resolve_input(step: dict, sources: Path) -> dict:
    """The step with its `deliveries`, read from its source's `inputs.yaml`, which holds the folders by name: the one the step
    names with `input`, else every one, in that file's order. A step is named after what it loads, never after a file. Each
    has its own capture run: the step's, then the delivery's name (or its `capture_name`; empty for a delivery loaded under
    the step's alone), so a delivery added to the file renames no earlier one's. The
    `facts` and `revision` that belong to one file are its delivery's."""
    if "source" not in step:
        return step
    path = sources / step["source"] / "inputs.yaml"
    held = {}
    if path.exists():
        held = (yaml.safe_load(path.read_text()) or {}).get("inputs") or {}
    if not held:
        raise ValueError(f"{step['name']}: names no input, and {step['source']} holds none")
    if "input" in step and step["input"] not in held:
        raise ValueError(f"{step['name']}: {step['source']} has no input {step['input']!r} (it holds {sorted(held)})")
    names = [step["input"]] if "input" in step else list(held)
    if "revision" in step:
        raise ValueError(f"{step['name']}: a revision belongs to one file: state it on the delivery in {step['source']}/inputs.yaml")
    deliveries = []
    for name in names:
        folder, root = held[name].get("folder"), held[name].get("root", "captures")
        if not isinstance(folder, str) or not folder or folder.startswith("/") or ".." in Path(folder).parts:
            raise ValueError(f"{step['name']}: input {name!r} needs a folder under its root, not {folder!r}")
        if root not in ROOTS:
            raise ValueError(f"{step['name']}: input {name!r} has root {root!r}, not one of {sorted(ROOTS)}")
        called = held[name].get("capture_name", name)
        run = step["capture_run"] + (f"-{called}" if called else "")
        deliveries.append({"delivery": name, "capture": folder, "capture_run": run, "minutes": step["minutes"],
                           "facts": {**(step.get("facts") or {}), **taken(held[name].get("facts") or {}, step, sources)},
                           **({"revision": held[name]["revision"]} if "revision" in held[name] else {}),
                           **({"capture_root": root} if root != "captures" else {})})
    # The step may take its minutes once a delivery: its bound is all of them, each load's is the file's.
    return {**step, "deliveries": deliveries, "minutes": step["minutes"] * len(deliveries)}


def taken(facts: dict, step: dict, sources: Path) -> dict:
    """The facts of a file that the step's target declares (`run: {facts: [...]}`): two targets of one file take different ones."""
    if not facts:
        return {}
    targets = (yaml.safe_load((sources / step["source"] / "source.yaml").read_text()).get("bookkeeping") or {}).get("targets") or {}
    declared = ((targets.get(step["target"]) or {}).get("run") or {}).get("facts") or []
    return {name: value for name, value in facts.items() if name in declared}


def loads(step: dict) -> list[dict]:
    """One load a delivery, in order: the step as `arguments` takes it, with the delivery's folder, capture run and position."""
    return [{**step, **delivery} for delivery in step["deliveries"]]


def load_jobs(path: Path = ROOT / "rules/load-jobs.yaml", sources: Path = ROOT / "sources") -> list[dict]:
    """The load jobs, each with the file's `defaults` for what it does not say itself and its deliveries."""
    chain = yaml.safe_load(path.read_text())
    steps = [resolve_input({**(chain.get("defaults") or {}), "capture_run": f"{chain['capture_label']}-{step['name']}", **step}, sources)
             for step in chain["steps"]]
    for place, delivery in enumerate(one for step in steps for one in step.get("deliveries", ())):
        delivery["position"] = place  # a forced load's revision ends with it: each delivery publishes its own
    for step in steps:
        priority = step.get("priority", 3)
        if type(priority) is not int or priority not in (1, 2, 3):  # `true` and `2.0` are not tiers
            raise ValueError(f"{step['name']}: priority must be 1, 2 or 3, not {priority!r}")
        if type(step.get("one_document", False)) is not bool:  # `1` and `0.0` compare equal to a boolean
            raise ValueError(f"{step['name']}: one_document is true or false, not {step['one_document']!r}")
        peak = step.get("peak_gb")
        if peak is not None and (type(peak) not in (int, float) or peak <= 0):
            raise ValueError(f"{step['name']}: peak_gb is a positive number of gigabytes, not {peak!r}")
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
    """Each done step's minutes, from its first `attempt 1 start` to its `done:` line in the run's state file."""
    start, took = {}, {}
    for found in re.finditer(r"^(\d\d-\d\d \d\d:\d\d:\d\d) ET (\S+) (attempt \d+ start|done:)", text, re.M):
        when = datetime.strptime(found.group(1), "%m-%d %H:%M:%S")
        name = found.group(2)
        if found.group(3).startswith("attempt"):
            start.setdefault(name, when)
        elif name in start and name not in took:
            took[name] = (when - start[name]).total_seconds() / 60 % 1440
    return took


def minutes_running(text: str, names: set[str], now: datetime) -> dict[str, float]:
    """Minutes since each named step's first `attempt 1 start` in the state file. The file outlives a scheduler, so a restart
    does not reset what a running step has used (a restarted scheduler once counted a 94-minute step as new and projected
    its end 3 hours too early)."""
    first = {}
    for found in re.finditer(r"^(\d\d-\d\d \d\d:\d\d:\d\d) ET (\S+) attempt 1 start", text, re.M):
        first.setdefault(found.group(2), datetime.strptime(found.group(1), "%m-%d %H:%M:%S").replace(year=now.year))
    clock_now = now.replace(tzinfo=None)
    return {n: (clock_now - first[n]).total_seconds() / 60 for n in names if n in first}


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
    and target with a load already running (two loads of one pair write the same outputs). The load jobs file's `priority` first
    (1 before 2 before 3), then the longest chain (see `chain_length`); at most `free`."""
    follows, stuck = needs(steps), blocked(steps, failed)
    length = chain_length(steps, estimate)
    taken = set(busy) | {(s["source"], s["target"]) for s in steps if s["name"] in running}
    chosen: list[dict] = []
    for step in sorted(steps, key=lambda s: (s.get("priority", 3), -length[s["name"]])):
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


MOVE_EVERY = timedelta(minutes=10)  # a step is raised (stopped and started again) at most this often: each move abandons its bundles in flight
BOUNDARY_MINUTES = 1.0  # a step is moved this soon after one of its bundles completes, so next to nothing is abandoned
MIN_LEFT_MINUTES = 30  # a step with less than this to go is left alone: a move costs a restart and the bundle in flight
SHED_AFTER = 4  # consecutive pressed cycles before a step is shed: a spike that passes costs a restart for nothing
RAISE_GAIN = 1.2  # a step is raised again only if the last raise raised its measured rate by this factor
WORKER_GB = 0.5  # the memory a worker is sized for
PEAK_SAMPLE_SECONDS = 10  # how often a running step's memory is read for the peak its done or stopped line names
WORKERS_PER_VCPU = 4  # a worker waits on the database much of the time, so a vCPU carries several


def workers_range(vcpu: float, memory_gb: float, worker_gb: float = WORKER_GB) -> tuple[int, int]:
    """The workers a task can carry, from what it has: its memory in worker-sized shares (`worker_gb`, half a gigabyte
    unless a step has been measured smaller), at most four to a vCPU, never fewer than one. The range follows the compute
    (a 1 vCPU, 4 GB task carries up to 4; 2 vCPU, 8 GB up to 8), so it is the configuration's, never a fixed two to eight."""
    return 1, max(1, min(int(memory_gb / worker_gb + 1e-9), int(vcpu * WORKERS_PER_VCPU)))


CGROUP = Path("/sys/fs/cgroup")
GATE_SETTLE_SECONDS = 30  # a load takes this long to show its memory: the next step is admitted after it
GATE_POLL_SECONDS = 30


def free_gb(root: Path = CGROUP, meminfo: Path = Path("/proc/meminfo")) -> float | None:
    """The memory this container has free now: its cgroup limit less its use (the file cache counted free), or, where the cgroup
    has no limit (a container on a Docker VM, whose memory is the VM's), the memory the machine reports available; None where
    neither can be read."""
    try:
        limit = (root / "memory.max").read_text().strip()
        if limit != "max":
            cache = next((int(line.split()[1]) for line in (root / "memory.stat").read_text().splitlines()
                          if line.startswith("inactive_file ")), 0)
            return (int(limit) - int((root / "memory.current").read_text()) + cache) / 2**30
    except (OSError, ValueError):
        pass
    try:
        return next(int(line.split()[1]) for line in meminfo.read_text().splitlines() if line.startswith("MemAvailable:")) / 2**20
    except (OSError, ValueError, StopIteration):
        return None


def free_share(root: Path = CGROUP, meminfo: Path = Path("/proc/meminfo")) -> float | None:
    """The share of memory free: `free_gb` over the cgroup limit, or over the machine's total where the cgroup has none;
    None where either cannot be read."""
    free = free_gb(root, meminfo)
    try:
        limit = (root / "memory.max").read_text().strip()
        total = int(limit) / 2**30 if limit != "max" else None
    except (OSError, ValueError):
        total = None
    if total is None:
        try:
            total = next(int(line.split()[1]) for line in meminfo.read_text().splitlines() if line.startswith("MemTotal:")) / 2**20
        except (OSError, ValueError, StopIteration):
            return None
    return free / total if free is not None and total else None


def load_running() -> bool:
    return bool(external_loads())


def cpu_level() -> str:
    """The machine's CPU pressure now, as the controller reads it: `high` above one and a half times the cores in load average."""
    return pressure(os.getloadavg()[0], os.cpu_count() or 1, None)


def admit(want: int, worker_gb: float, lock: Path, free=free_gb, running=load_running, pressed=lambda: cpu_level() == "high",
          sleep=time.sleep, settle: int = GATE_SETTLE_SECONDS, poll: int = GATE_POLL_SECONDS, say=lambda text: None,
          one_document: bool = False, peak_gb: float = 0.0, reserved=lambda: 0.0) -> int:
    """The workers a step starts with: its own `want` when the memory is there, fewer when it is not (at least half of them;
    all of them for a step of one document, which the controller never moves), and none until the memory of that floor is free and the CPU is not pressed (the controller would take back what a pressed
    machine admits), unless no other load runs, when waiting would never end. One step is
    admitted at a time: the lock is held through the settle window, so the next one reads the memory this one takes. A
    container whose memory cannot be read gives the step its own workers. One load runs in one container. The floor's memory is
    at least the step's measured `peak_gb`, and the free memory read leaves out what the running steps have yet to reach of
    theirs (`reserved`, `unreached_peaks`): a step still growing to its peak is not free memory."""
    floor = want if one_document else max(1, want // 2)
    handle = lock.open("a")
    fcntl.flock(handle, fcntl.LOCK_EX)
    waited = False
    try:
        while True:
            room, held = free(), 0.0
            if room is not None:
                held = reserved()
                room -= held
            need = max(floor * worker_gb, peak_gb)
            short = room is not None and room < need
            busy = not short and pressed()
            if not (short or busy) or not running():
                break
            if not waited:
                say(f"waits for {need:.1f} GB of free memory ({room:.1f} GB now"
                    + (f", {held:.1f} GB more held for running steps' peaks)" if held else ")") if short else
                    "waits for the CPU (the machine is pressed)")
                waited = True
            sleep(poll)
    except BaseException:
        handle.close()
        raise
    timer = threading.Timer(settle, handle.close)  # closing the file releases the lock
    timer.daemon = True
    timer.start()
    return want if room is None else max(floor, min(want, int(room / worker_gb + 1e-9)))


def capacity_profiles(path: Path = ROOT / "rules/load-jobs.yaml") -> dict[str, dict]:
    """The named compute sizes of the load jobs file (the AWS ECS task sizes the state machines run on)."""
    return yaml.safe_load(path.read_text()).get("capacity") or {}


def in_container() -> bool:
    return Path("/.dockerenv").exists()


def physical_gb() -> float:
    return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30


def capacity_of(name: str) -> tuple[float, float]:
    """The vCPUs and gigabytes of a capacity: a profile of the load jobs file, or `local`, this machine measured (half its
    memory, the rest being the operator's other work)."""
    if name == "local":  # in a container the memory seen is the whole allotment of the runtime: the operator's other work is outside it
        return os.cpu_count() or 1, physical_gb() if in_container() else physical_gb() / 2
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
    """The steps with each one's workers held to the named capacity's range, whatever the run mode: the load jobs file asks
    for what a step wants, the compute says what a task carries. Each step's range uses its own measured `worker_gb`
    where the load jobs file has one (`capacity` replaces the named compute, for a test)."""
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
    return total > 0 and (elapsed >= window or elapsed / window > done / total + 0.1)  # a window that has run out is behind


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


# The `load` command as a process line shows it: `edgar-warehouse load`, or, in the loader image, the same command written as
# a python one-liner (`from edgar_warehouse.cli import main; sys.exit(main()) load`).
LOAD_COMMAND = re.compile(r"edgar[-_]warehouse(?:\.cli import main; sys\.exit\(main\(\)\))? load ")


def external_loads() -> set[tuple[str, str]]:
    """The (source, target) of every `load` running on this machine, whoever started it."""
    listing = subprocess.run(["ps", "-Ao", "args"], check=False, capture_output=True, text=True).stdout
    return {(m.group(1), m.group(2)) for line in listing.splitlines() if LOAD_COMMAND.search(line)
            for m in [re.search(r"--source (\S+) --target (\S+)", line)] if m}


def stop(child: subprocess.Popen) -> None:
    """End a started step and the load under it (the load resumes where it stopped)."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=60)


@dataclass
class Memory:
    """What choosing a move keeps from one cycle to the next."""
    finished: dict[str, tuple[int, datetime]] = field(default_factory=dict)  # a step's bundles done, and when that count last changed
    rates: dict[str, dict[int, float]] = field(default_factory=dict)  # a step's measured bundles a minute at each worker count
    pressed: int = 0  # consecutive cycles at `high`


MOVE_LINE = re.compile(r" ET (?:controller|scheduler) moves (\S+) from (\d+) to (\d+) workers")
ATTEMPT_LINE = re.compile(r" ET (\S+) attempt (\d+) start")


def shed_this_attempt(text: str) -> set[str]:
    """The steps a move took workers from in their current attempt (a state file's lines, as `controller moves` and `scheduler
    moves` write them). Such a step is not moved again in it."""
    attempt: dict[str, str] = {}
    shed: set[str] = set()
    for line in text.splitlines():
        if started := ATTEMPT_LINE.search(line):
            name, number = started.groups()
            if attempt.get(name) != number:
                shed.discard(name)
            attempt[name] = number
        elif (moved := MOVE_LINE.search(line)) and int(moved.group(3)) < int(moved.group(2)):
            shed.add(moved.group(1))
    return shed


def unmovable(steps: list[dict], text: str) -> frozenset[str]:
    """The steps no move may touch: those the load jobs file declares one document each (`one_document: true`) and those shed
    earlier in their attempt (`shed_this_attempt` of the state file's `text`)."""
    return frozenset(step["name"] for step in steps if step.get("one_document")) | shed_this_attempt(text)


def choose_move(level: str, workers: dict[str, int], length: dict[str, float], bounds: dict[str, tuple[int, int]],
                logs: dict[str, str], since: dict[str, datetime], memory: Memory, now: datetime,
                fixed: frozenset[str] | set[str] = frozenset()) -> tuple[str, int] | None:
    """The one change of workers that pays in this cycle, or None. `workers`, `bounds`, `logs` and `since` (when the step last started
    or moved) name the running steps. A step in `fixed` is never moved: a step of one document (a move abandons it) or one shed
    earlier in its attempt (`shed_this_attempt`). Raising a step waits for it to settle; a pressed machine sheds the step with the shortest chain,
    whenever it last moved."""
    settled = set(workers) if level == "high" else {name for name in workers if now - since[name] >= MOVE_EVERY}
    memory.pressed = memory.pressed + 1 if level == "high" else 0
    left_of: dict[str, float | None] = {}
    for name, text in logs.items():  # what a move would cost and gain, read from each step's own log
        progress = bundle_progress(text)
        if progress is None:
            continue
        if memory.finished.get(name, (None, None))[0] != progress[0]:
            memory.finished[name] = (progress[0], now)
        attempt = (now - since[name]).total_seconds() / 60
        ran = bundles_run(text)
        if ran >= 2 and attempt >= 3:
            memory.rates.setdefault(name, {})[workers[name]] = ran / attempt
        left_of[name] = minutes_left(progress[0], progress[1], attempt, ran)
    settled = {name for name in settled if name not in fixed and movable(logs[name]) and worth_moving(
        level, left=left_of.get(name), abandoned=(now - memory.finished.get(name, (0, now))[1]).total_seconds() / 60, pressed=memory.pressed,
        rates=memory.rates.get(name, {}), workers=workers[name]) is None}  # a move abandons the bundle in flight
    return rescale({n: workers[n] for n in settled}, {n: length[n] for n in settled}, level, {n: bounds[n] for n in settled})


def memory_level(free: float | None) -> str:
    """The container's free memory as a level: `high` under one worker's share (`WORKER_GB`), `low` with two or more free, else `ok`
    (also where it cannot be read)."""
    if free is None:
        return "ok"
    return "high" if free < WORKER_GB else "low" if free >= 2 * WORKER_GB else "ok"


def both(one: str, other: str) -> str:
    """Pressed if either is; room only where both have it."""
    return "high" if "high" in (one, other) else "low" if one == other == "low" else "ok"


def headroom(workers: int, span: tuple[int, int], free: float | None, worker_gb: float) -> tuple[int, int]:
    """A running step's range: the capacity's, its top no higher than the free memory carries with one worker's share left over."""
    extra = 0 if free is None else max(0, int((free - WORKER_GB) / worker_gb + 1e-9))
    return span[0], min(span[1], workers + extra)


def gate_path(state: Path) -> Path:
    return state.with_name(state.name + ".gate")


def move_path(state: Path, name: str) -> Path:
    """The file that asks a running step to start again with another worker count."""
    return state.with_name(f"{state.name}.move-{name}")


def take_move(state: Path, name: str) -> int | None:
    """The worker count asked of a step, once: the request is removed as it is read."""
    try:
        count = int(move_path(state, name).read_text())
    except (OSError, ValueError):
        count = None
    move_path(state, name).unlink(missing_ok=True)
    return count


def last_starts(text: str, year: int) -> dict[str, datetime]:
    """When each step's load last started, from the `attempt N start` lines of the state file (a moved step writes one again)."""
    return {name: datetime.strptime(when, "%m-%d %H:%M:%S").replace(year=year, tzinfo=ZoneInfo("America/New_York"))
            for when, name in re.findall(r"^(\d\d-\d\d \d\d:\d\d:\d\d) ET (\S+) attempt \d+ start", text, re.M)}


def admitting(gate: Path) -> bool:
    """A step is being admitted (it waits for memory, or has not yet shown what it takes): the gate's lock is held."""
    with gate.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def ask_move(step: dict, count: int, state: Path) -> bool:
    """Ask a running step's loop for `count` workers and end its load (the driver first, so that its exit is the signal's, then the
    workers it started, which can outlive it). The loop starts the load again, where it stopped. False when its load has already
    ended: nothing is left asked."""
    listing = process_listing()
    driver = load_driver(listing, step["source"], step["target"])
    if not driver:
        return False
    move_path(state, step["name"]).write_text(str(count))
    try:
        os.kill(driver[0], signal.SIGTERM)
    except ProcessLookupError:
        move_path(state, step["name"]).unlink(missing_ok=True)
        return False
    for pid in load_pids(listing, step["source"], step["target"]):
        if pid != driver[0]:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGTERM)
    return True


def control_cycle(steps: list[dict], state: Path, memory: Memory, reader_url: str | None = None, connections: int = 250) -> None:
    """Move at most one running step of the lanes to another worker count, by the container's free memory, its CPU and the database.
    Nothing is raised while a step is being admitted: the memory read then is not yet what its load takes."""
    if not state.exists():
        return
    listing = process_listing()
    text, over, now = state.read_text(), done_steps(state) | failed_steps(state), clock()
    since = last_starts(text, now.year)
    running = {s["name"]: (s, count) for s in steps if s["name"] in since and s["name"] not in over
               for count in [load_workers(listing, s["source"], s["target"])] if count}
    if not running:
        return
    free, reading = free_gb(), database_load(reader_url)
    if free is not None:  # a running step still growing to its measured peak holds that memory already, for a raise too
        free -= unreached_peaks(steps, listing)
    level = worst(both(memory_level(free), cpu_level()), db_level(**reading) if reading else "ok")
    if reading:
        level = room(level, reading["connections"], connections)
    if level == "low" and admitting(gate_path(state)):
        level = "ok"
    workers = {name: count for name, (_, count) in running.items()}
    bounds = {name: headroom(count, bounds_for("local", s.get("worker_gb", WORKER_GB)), free, s.get("worker_gb", WORKER_GB))
              for name, (s, count) in running.items()}
    change = choose_move(level, workers, chain_length(steps, estimates(steps, measured(text))), bounds,
                         {name: step_log_text(name) for name in running}, {name: since[name] for name in running}, memory, now,
                         unmovable(steps, text))
    if change and ask_move(running[change[0]][0], change[1], state):
        name, count = change
        note(f"controller moves {name} from {workers[name]} to {count} workers ({level} load, "
             f"{'?' if free is None else f'{free:.1f}'} GB free)", state)
        memory.finished.pop(name, None)
        memory.pressed = 0  # the move shows in the readings before another is judged


def control(poll: int = 30) -> None:
    """The lane controller: a cycle every `poll` seconds for as long as the worker lives. A cycle that breaks is reported by its kind
    (a driver error can quote an address) and the next one goes on."""
    steps, state, memory = load_jobs(), LOGS / f"chain-{RUN}.log", Memory()
    reader = STORES / "reader.env"
    while True:
        try:
            control_cycle(steps, state, memory, data_url(load_env(reader)) if reader.exists() else None)
        except Exception as error:  # noqa: BLE001
            print(f"lane controller: {type(error).__name__}; next cycle", flush=True)
        time.sleep(poll)


def auto(steps: list[dict], state: Path, slots: int, poll: int = 30, deadline: datetime | None = None,
         reader_url: str | None = None, connections: int = 250, bounds: tuple[int, int] | None = None,
         capacity: str = "local") -> int:
    """Watch the loads and start the next ready step whenever a slot is free and the machine is not pressed. One start
    a cycle: the load average lags, so a started step is counted running before the next is judged. Each step runs as
    `load_jobs.py --only <step> --workers <n>` (the attempt loop). The workers follow the machine within the capacity's
    range (`bounds`; the machine's own when not given): with room
    the step with the longest chain behind it doubles, when pressed the step with the shortest halves, one change a
    cycle, by stopping the step's load and starting it again (a load resumes where it stopped). With a `deadline`, a run
    behind its schedule (more of the window used than of the work done) is allowed twice the cores in load; at the
    deadline the miss is reported once, naming what is left, and the loads go on: a deadline never stops one (a stopped step
    loses the work of its attempt), and the run says how long after the deadline it finished. A step that uses up its attempts
    blocks what follows it and the rest carry on. Ends when every step is done (then the links tables and master_binding) or when
    nothing more can start."""
    def range_of(name: str) -> tuple[int, int]:
        return bounds or bounds_for(capacity, by_name[name].get("worker_gb", WORKER_GB))

    children: dict[str, subprocess.Popen] = {}
    workers: dict[str, int] = {}
    failed: set[str] = set()
    by_name = {step["name"]: step for step in steps}
    started, cycle, began, moved, missed = clock(), 0, {}, {}, False
    memory = Memory()
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
            if deadline and clock() >= deadline:  # also when the deadline passed in this very cycle
                note(f"all steps done {(clock() - deadline).total_seconds() / 60:.0f} min after the deadline", state)
            return 0
        if deadline and clock() >= deadline and not missed:
            missed = True  # said once; the loads go on (a step stopped now would lose the work its attempt has done)
            note(f"deadline {deadline:%H:%M} ET passed: still loading; left: {', '.join(sorted(set(by_name) - done))}", state)
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
            running_now = {n for n in by_name if n not in done and (n in children or (by_name[n]["source"], by_name[n]["target"]) in external_loads())}
            minutes_in = minutes_running(state.read_text() if state.exists() else "", running_now, clock())
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
            note(f"scheduler starts {name} (priority {by_name[name].get('priority', 3)}) at {count} workers", state)
            spawn(name, count)
        change = choose_move(level, workers, length, {n: range_of(n) for n in workers}, {n: step_log_text(n) for n in workers},
                             {n: moved.get(n, began[n]) for n in workers}, memory, clock(),
                             unmovable(steps, state.read_text() if state.exists() else ""))
        if change and not starts:
            name, count = change
            note(f"scheduler moves {name} from {workers[name]} to {count} workers ({level} load)", state)
            stop(children[name])
            spawn(name, count)
            moved[name] = clock()
            memory.finished.pop(name, None)
        if not children and not busy and not ready(steps, done, set(), failed, len(steps)):
            left = sorted(set(by_name) - done)
            blockers = f"{', '.join(sorted(failed))} failed, so " if failed else "no step can follow what it waits for, so "
            note(f"scheduler stops: {blockers}{', '.join(left)} cannot start", state)
            return 1
        time.sleep(poll)


def bundle_progress(text: str) -> tuple[int, int] | None:
    """(bundles done, bundles in all) from a step's log: the `run ... complete in` lines, and the bundles an earlier
    attempt already loaded, against the last `Bundle i/N:` line. None when the log names no bundles. Of a step with several deliveries, the
    delivery it is at (after the log's last `Input` line)."""
    text = re.split(r"^Input \d+/\d+: .*$", text, flags=re.M)[-1]
    found = re.findall(r"^Bundle \d+/(\d+):", text, re.M)
    finished = len(re.findall(r"^\s+run \S+ complete in", text, re.M)) + len(re.findall(r"^Bundle \d+/\d+: all \d+ documents already loaded", text, re.M))
    return (finished, int(found[-1])) if found else None


def raise_pays(rates: dict[int, float], workers: int) -> bool:
    """Whether raising a step again is worth a restart: the last raise must have raised its measured rate (bundles a minute) by
    RAISE_GAIN. A step never raised before is tried; one whose last raise is not measured yet, or gained nothing, is held."""
    lower = [w for w in rates if w < workers]
    if not lower:
        return True  # the first raise is tried
    if workers not in rates:
        return False  # the last raise is not measured yet: wait for its rate before judging another
    return rates[workers] >= RAISE_GAIN * rates[max(lower)]


def worth_moving(level: str, *, left: float | None, abandoned: float, pressed: int, rates: dict[int, float], workers: int) -> str | None:
    """None when moving a step (a restart that abandons the bundle in flight) pays; otherwise why not, in a sentence.
    Either needs a moment just after a bundle completed, so nothing is abandoned. Shedding needs pressure that has lasted. Raising
    needs enough left to repay the restart and a measured gain from the last raise."""
    if level == "high":
        if pressed < SHED_AFTER:
            return "the pressure has not lasted"
        return "a bundle is in flight" if abandoned > BOUNDARY_MINUTES else None
    if level == "low":
        if left is None or left < MIN_LEFT_MINUTES:
            return "too little left to repay a restart"
        if abandoned > BOUNDARY_MINUTES:
            return "a bundle is in flight"
        if not raise_pays(rates, workers):
            return "the last raise did not raise the rate"
    return None


def step_log_text(name: str) -> str:
    log = LOGS / f"chain-{RUN}-{name}.log"
    return log.read_text() if log.exists() else ""


def movable(text: str) -> bool:
    """A step may be moved (stopped and started again with another worker count) only when its log names more than one bundle: a
    move abandons the bundles in flight, so a step of one bundle, or one that has named none yet, would lose everything it has done
    and start over. Two such steps were moved ten times in two hours and never finished."""
    progress = bundle_progress(text)
    return progress is not None and progress[1] > 1


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


IDLE_MINUTES = 10  # a session or a log silent this long is not work


def application_name(step: str) -> str:
    """The tag every database session of a step carries (libpq reads PGAPPNAME), so the store says whose a session is."""
    return f"chain-{step}"


def summarize_sessions(rows) -> dict[str, dict]:
    """Each step's sessions from rows of (application_name, state, wait event type, wait event, seconds since the last state
    change, statement): how many are active or idle in a transaction, the minutes since any changed, the commonest wait, and the
    newest statement by its verb and table only, never a value."""
    found: dict[str, dict] = {}
    for tag, state, wtype, wevent, seconds, statement in rows:
        if not str(tag).startswith("chain-"):
            continue
        one = found.setdefault(tag[len("chain-"):], {"active": 0, "idle_in_transaction": 0, "changed_min": None, "waits": Counter(),
                                                     "statement": "", "newest": None, "lock_waiting": 0})
        if state == "active":
            one["active"] += 1
            one["waits"][f"{wtype}:{wevent}" if wtype else "-"] += 1
        elif state == "idle in transaction":
            one["idle_in_transaction"] += 1
            one["waits"][f"{wtype}:{wevent}" if wtype else "-"] += 1
        if state in ("active", "idle in transaction"):
            one["lock_waiting"] += wtype == "Lock"
            minutes = max(float(seconds), 0.0) / 60
            one["changed_min"] = minutes if one["changed_min"] is None else min(one["changed_min"], minutes)
            if one["newest"] is None or minutes < one["newest"]:
                shape = re.match(r"\s*(insert\s+into|update|delete\s+from|select\b.*?\bfrom|copy)\s+([\w.\"]+)", statement or "", re.I | re.S)
                one["newest"], one["statement"] = minutes, (
                    f"{shape.group(1).split()[0].lower()} {shape.group(2)}" if shape else (statement or "").split(" ")[0].lower())
    return {step: {"active": one["active"], "idle_in_transaction": one["idle_in_transaction"], "lock_waiting": one["lock_waiting"],
                   "changed_min": 1e9 if one["changed_min"] is None else one["changed_min"], "statement": one["statement"],
                   "wait": one["waits"].most_common(1)[0][0] if one["waits"] else "-"} for step, one in found.items()}


def step_sessions(reader_url: str) -> dict[str, dict]:
    """The sessions of every load job, read as the diagnostic login (state, wait and statement shape, never a value)."""
    import psycopg2

    try:
        with psycopg2.connect(reader_url.replace("postgresql+psycopg2", "postgresql"), connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("""SELECT application_name, state, wait_event_type, wait_event,
                                  extract(epoch FROM now() - state_change), left(query, 200)
                           FROM pg_stat_activity WHERE application_name LIKE 'chain-%%' AND state IS NOT NULL AND pid <> pg_backend_pid()""")
            return summarize_sessions(cur.fetchall())
    except Exception:  # noqa: BLE001  a driver error can quote the address: no reading
        return {}


def verdict_kind(log_age: float, cpu: float, lock_waiters: int, evidence: dict | None = None) -> str:
    """A step's state by its own evidence, never by a neighbour's: `locked` (a session of its own waits on a lock while the store has three
    or more waiting), `progressing` (its processes work, its log moved, or one of its own database sessions is active or changed
    state lately) or `stalled` (none of them). A step whose work is on the database side uses no CPU and writes no log, so its own
    sessions are the evidence."""
    if lock_waiters >= 3 and evidence and evidence["lock_waiting"]:  # three waiting is the scheduler's own threshold: one is normal
        return "locked"
    if cpu >= 5 or log_age < IDLE_MINUTES or (evidence and (evidence["active"] > 0 or evidence["changed_min"] < IDLE_MINUTES)):
        return "progressing"
    return "stalled"


WAIT_CAUSES = (("IO:", "the store reads the table from disk (cache misses): the store's disk is the limit, not this step"),
               ("Lock:", "another session holds a lock this step needs"),
               ("LWLock:", "a short internal lock of the database under many writers"),
               ("Client:", "client-bound: the step's own round trips or compute, while the database is idle"))


def five_whys(name: str, kind: str, elapsed: float, bound: int, log_age: float, cpu: float, evidence: dict | None) -> list[str]:
    """Why this step reads as it does, five links, each from a reading: never a guess. A link that cannot be read says what would read it."""
    late = f", past its bound of {bound} min" if elapsed > bound else ""
    why = [f"{name} is {kind}{late}: its log is {log_age:.0f} min old and its processes use {cpu:.0f}% CPU"]
    if evidence is None:
        return why + ["it has no database session: none carries the tag chain-" + name,
                      "so it is asking the database for nothing, and its processes are idle",
                      "nothing it could be waiting on can be read from the database",
                      "not measured: read its log and its processes; no session and no CPU is no sign of work"]
    states = f"{evidence['active']} active and {evidence['idle_in_transaction']} idle in a transaction"
    last = "none" if evidence["changed_min"] >= 1e8 else f"{evidence['changed_min']:.1f} min ago"
    why.append(f"its database sessions: {states}; the last state change {last}")
    why.append(f"its latest statement: {evidence['statement'] or 'none'}")
    wait = evidence["wait"]
    why.append("it waits on " + (wait if wait != "-" else "nothing: the database is running its statement"))
    cause = next((words for prefix, words in WAIT_CAUSES if wait.startswith(prefix)), None)
    if kind == "stalled" and evidence["active"] + evidence["idle_in_transaction"] == 0:
        cause = "no session of this step is doing anything: it is between bundles or stopped"
    why.append(cause or ("the database is running its statement" if wait == "-" else f"not measured: the wait {wait} has no cause named here"))
    return why


def verdict(elapsed: float, bound: int, log_age: float, cpu: float, lock_waiters: int, evidence: dict | None = None) -> str:
    """The words of `verdict_kind`; being past the step's bound is said first."""
    late = f"past its bound of {bound} min; " if elapsed > bound else ""
    kind = verdict_kind(log_age, cpu, lock_waiters, evidence)
    if kind == "locked":
        return f"{late}waiting on database locks ({lock_waiters} sessions on the store)"
    if kind == "progressing":
        return f"{late}progressing"
    return f"{late}no sign of work: no CPU, no session of its own working, log silent for {log_age:.0f} min"


def store_databases() -> tuple[str, ...]:
    """The databases the stores live in, each store a schema of one of them."""
    from edgar_warehouse.database_connections import DATABASES

    return tuple(DATABASES)


SCHEMA_STORES = {"mdm": "mdm", "rdm": "rdm", "silver": "silver", "rules": "rules", "bookkeeping": "bookkeeping", "journal": "change_journal"}


def database_writes(reader_url: str) -> dict[str, int]:
    """Each store's cumulative rows inserted, updated and deleted, read as the diagnostic login (statistics, no table), by
    the schema that holds the store."""
    import psycopg2

    totals = {}
    for name in store_databases():
        url = in_database(reader_url.replace("postgresql+psycopg2", "postgresql"), name)
        try:
            with psycopg2.connect(url, connect_timeout=10) as conn, conn.cursor() as cur:
                cur.execute("SELECT schemaname, coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) FROM pg_stat_user_tables GROUP BY 1")
                for schema, count in cur.fetchall():
                    if schema in SCHEMA_STORES:
                        totals[SCHEMA_STORES[schema]] = int(count)
        except Exception:  # noqa: BLE001  a driver error can quote the address: no reading for this database
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
                           AND usename <> current_user AND state IS NOT NULL GROUP BY 1, 2""", (list(store_databases()),))
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


def held_gb(listing: str, source: str, target: str) -> float | None:
    """The resident memory, in GB, of the running load of one source and target (its driver and the workers it started), from
    `listing` (`ps -Ao pid,ppid,time,rss,args`, rss in KB); None when no such load runs."""
    rss = {}
    for line in listing.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4 and parts[0].isdigit() and parts[3].isdigit():
            rss[int(parts[0])] = int(parts[3])
    pids = load_pids(listing, source, target)
    return sum(rss.get(pid, 0) for pid in pids) / 2**20 if pids else None


def unreached_peaks(steps: list[dict], listing: str, besides: str | None = None) -> float:
    """The gigabytes the running steps (other than `besides`) have yet to reach of their measured `peak_gb`: each one's peak less
    the resident memory its driver and workers hold now (`held_gb`)."""
    held = 0.0
    for step in steps:
        if "peak_gb" not in step or step["name"] == besides:
            continue
        now = held_gb(listing, step["source"], step["target"])
        if now is not None:
            held += max(0.0, step["peak_gb"] - now)
    return held


@contextlib.contextmanager
def sampled_peak(source: str, target: str):
    """While the block runs, the most resident memory the load of one source and target is seen to hold, read every
    `PEAK_SAMPLE_SECONDS`: a list whose one value is the peak in GB so far. A peak between two readings is missed, and resident
    memory counts a page the processes share once for each, so the sum can be more than the memory they take together."""
    peak, done = [0.0], threading.Event()

    def sample() -> None:
        while not done.wait(PEAK_SAMPLE_SECONDS):
            with contextlib.suppress(Exception):  # a reading that fails is skipped: it never fails the load
                now = held_gb(process_listing(), source, target)
                if now is not None:
                    peak[0] = max(peak[0], now)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        yield peak
    finally:
        done.set()
        thread.join()


def process_listing() -> str:
    return subprocess.run(["ps", "-Ao", "pid,ppid,time,rss,args"], check=False, capture_output=True, text=True).stdout


def load_driver(listing: str, source: str, target: str) -> tuple[int, int | None] | None:
    """The pid and the `--workers` of the running load's driver of one source and target, from its command line; a `--plan`, which
    loads nothing, is none."""
    for line in listing.splitlines():
        parts = line.split(None, 4)
        if (len(parts) == 5 and parts[0].isdigit() and LOAD_COMMAND.search(parts[4]) and is_load_process(parts[4], source, target)
                and not re.search(r" --plan( |$)", parts[4])):
            found = re.search(r"--workers (\d+)", parts[4])
            return int(parts[0]), int(found.group(1)) if found else None
    return None


def load_workers(listing: str, source: str, target: str) -> int | None:
    """The `--workers` the running load of one source and target was started with."""
    driver = load_driver(listing, source, target)
    return driver[1] if driver else None


def process_use(source: str, target: str) -> tuple[dict[int, float], float]:
    """Each process's CPU seconds so far, by pid, and the memory in MB, of the load running one source and target (its
    driver and the workers it started); two readings give the CPU percent."""
    listing = process_listing()
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


def machine_reading() -> dict:
    """The machine now: one-minute load average, cores, and the share of memory free (macOS's own reading, else the
    container's; None where it cannot be read)."""
    if sys.platform == "darwin":
        free = memory_free_fraction(subprocess.run(["memory_pressure"], check=False, capture_output=True, text=True).stdout)
    else:
        free = free_share()
    return {"load": os.getloadavg()[0], "cores": os.cpu_count() or 1, "memory_free": free}


def status_snapshot(steps: list[dict], state: Path, reader_url: str | None, sample: int = 20) -> dict:
    """What every step and the stores are doing, as plain data: each step's state (`done`, `waiting`, or the kind of its
    verdict while it runs) and, for each running step, how long, how far, how fast, what it holds and its verdict. The
    log gives the bundles done and the minutes left; the database (two readings `sample` seconds apart) the rows written a
    minute; the processes their CPU and memory; the log's file its age. `status_lines` writes it as text."""
    text = state.read_text() if state.exists() else ""
    done = done_steps(state)
    failed = failed_steps(state)
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
    listing = process_listing()
    sessions = database_sessions(reader_url) if reader_url else {}
    tagged = step_sessions(reader_url) if reader_url else {}
    rows = []
    for step in running:
        began, attempt = started[step["name"]]
        elapsed = (clock().replace(tzinfo=None) - began).total_seconds() / 60
        log = LOGS / f"chain-{RUN}-{step['name']}.log"
        age = (time.time() - log.stat().st_mtime) / 60 if log.exists() else elapsed
        progress = bundle_progress(log.read_text()) if log.exists() else None
        seconds, memory = process_use(step["source"], step["target"])
        cpu = cpu_percent(0.0, window_cpu(cpu_before[step["name"]], seconds), sample)
        store = store_of(step["target"])
        mine = rate.get(store, 0.0)
        sharing = [o["name"] for o in running if o is not step and store_of(o["target"]) == store]
        evidence = tagged.get(step["name"])
        kind = verdict_kind(age, cpu, waiters, evidence)
        one = len(step.get("deliveries", ())) < 2  # a step of several deliveries does not know the bundles still to come
        left = minutes_left(*progress, elapsed, bundles_run(log.read_text())) if one and progress and progress[1] > 1 else None
        rows.append({
            "name": step["name"], "lane": step["lane"], "attempt": attempt, "attempts": step["attempts"],
            "workers": load_workers(listing, step["source"], step["target"]) or step.get("workers", 2),
            "elapsed": elapsed, "bound": step["minutes"], "bundles": progress, "left": left,
            "processes": len(seconds), "cpu": cpu, "memory_mb": memory, "store": store, "rows_per_min": mine,
            "shared_with": sharing, "log_age": age, "kind": kind, "evidence": evidence,
            "why": five_whys(step["name"], kind, elapsed, step["minutes"], age, cpu, evidence),
            "verdict": verdict(elapsed, step["minutes"], age, cpu, waiters, evidence),
            "warning": outlook(left, elapsed, step["minutes"], attempt, step["attempts"])})
    kinds = {row["name"]: row["kind"] for row in rows}
    names = {s["name"] for s in steps}
    return {"run": RUN, "time": f"{clock():%H:%M}", "total": len(steps), "done": len(done & names), "failed": len(failed & names),
            "complete": load_complete(text), "writes": rate,
            "lock_waiters": waiters, "sessions": sessions, "machine": machine_reading(), "running": rows,
            "steps": [{"name": s["name"], "lane": s["lane"], "waits_for": sorted(s.get("waits_for") or []),
                       "state": "done" if s["name"] in done else "failed" if s["name"] in failed and s["name"] not in kinds
                       else kinds.get(s["name"], "waiting")} for s in steps]}


def status_lines(snapshot: dict) -> list[str]:
    """One report line a running step: how long, how far, how fast, what it holds, and a verdict from the evidence."""
    rate, running = snapshot["writes"], snapshot["running"]
    lines = [f"run {snapshot['run']} — {snapshot['time']} ET: {len(running)} running, "
             f"{snapshot['done']} of {snapshot['total']} done; "
             f"database writes a minute: " + (", ".join(f"{k} {v:,.0f}" for k, v in rate.items() if v) or "none") +
             f"; lock waiters {snapshot['lock_waiters']} ({WRITES_NOTE})"]
    lines += [f"  {session_note(name, counts)}" for name, counts in sorted(snapshot["sessions"].items())
              if counts["active"] + counts["waiting_on_client"] > 1]
    for row in running:
        progress, left = row["bundles"], row["left"]
        wrote = f"{row['store']} {row['rows_per_min']:,.0f} rows/min" + (
            f" shared with {', '.join(row['shared_with'])}" if row["shared_with"] else "")
        shown = (f"bundles {progress[0]} of {progress[1]}" + (f", about {left:.0f} min left" if left else "")
                 if progress and progress[1] > 1 else "one document, so its log shows no progress; the database does")
        lines.append(f"  {row['name']} (lane {row['lane']}, attempt {row['attempt']}, {row['workers']} workers): {row['elapsed']:.0f} min of {row['bound']}; "
                     f"{shown}; {row['processes']} processes, {row['cpu']:.0f}% CPU, {row['memory_mb']:,.0f} MB; wrote {wrote}; log {row['log_age']:.0f} min old; "
                     + row["verdict"] + (f"; {row['warning']}" if row["warning"] else ""))
        if row["kind"] != "progressing" or row["elapsed"] > row["bound"]:  # something is wrong: every why, symptom to cause
            lines += [f"      why {number}: {words}" for number, words in enumerate(row["why"], 1)]
        elif row["evidence"]:
            lines.append(f"      {row['why'][1]}; {row['why'][2]}")
    return lines


def status(steps: list[dict], state: Path, reader_url: str | None, sample: int = 20) -> list[str]:
    return status_lines(status_snapshot(steps, state, reader_url, sample))


def status_inputs() -> tuple[Path, str | None, str]:
    """What a read-only status needs: the state file to count (set aside when it was not written for this store), the
    reader login's URL (None when there is no reader login), and a notice for the operator (empty when none). Only the
    reader login is used: nothing is written."""
    state = LOGS / f"chain-{RUN}.log"
    reader = STORES / "reader.env"
    reader_url = data_url(load_env(reader)) if reader.exists() else None
    notice = ""
    if reader_url and state.exists():  # the file the next run would set aside is no evidence about this store
        try:
            if state_verdict(state.read_text(), store_id(reader_url), database_generation(reader_url)) == "set aside":
                notice = (f"{state.name} was not written for this store (another store, a database made again, or no marker): "
                          "the next run sets it aside, and its done lines are not counted here")
                state = state.with_name(state.name + ".not-this-store")
        except ValueError:
            pass
    return state, reader_url, notice


def forced_at() -> str:
    """The time (UTC, the engine's `--as-of` form) a forced load is named by: taken once, so every attempt of it names one run."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carried(steps: list[dict], capacity: str = "local") -> tuple[int, str, int]:
    """The workers a compute carries, what limits them (`memory` when worker-sized shares of memory carry fewer than the vCPUs
    allow, else `vcpu`), and the widest first step of a lane. A worker's size is the load jobs file's measured `worker_gb`
    (the widest of the first steps), else half a gigabyte."""
    heads = {}
    for step in steps:
        heads.setdefault(step["lane"], step)
    widest = max((head["workers"] for head in heads.values()), default=1)
    worker_gb = max((head.get("worker_gb", WORKER_GB) for head in heads.values()), default=WORKER_GB)
    vcpu, memory_gb = capacity_of(capacity)
    workers = bounds_for(capacity, worker_gb)[1]
    return workers, ("memory" if int(memory_gb / worker_gb + 1e-9) <= int(vcpu * WORKERS_PER_VCPU) else "vcpu"), widest


def lanes_at_once(steps: list[dict], capacity: str = "local") -> int:
    """How many lanes a compute carries at once: the workers it carries (its memory in worker-sized shares, at most four to a
    vCPU, the same sizing a step's workers follow) over the workers of the widest first step of a lane. The one budget, in no
    platform's terms: whatever starts the lanes (a state machine, the local scheduler) starts no more than this and queues the
    rest, and the load monitor reads this same number."""
    workers, _, widest = carried(steps, capacity)
    return max(1, workers // widest)


def lane_budget(steps: list[dict], capacity: str = "local") -> dict:
    """The lane budget with what sets it, for the monitor: lanes at once, the workers the compute carries and its limit."""
    workers, limit, _ = carried(steps, capacity)
    return {"lanes": lanes_at_once(steps, capacity), "workers": max(1, workers), "limit": limit}


def arguments(step: dict) -> list[str]:
    capture = ROOTS[step.get("capture_root", "captures")] / step["capture"]
    args = ["--source", step["source"], "--target", step["target"], "--capture", str(capture),
            "--capture-run", step["capture_run"], "--stores", str(STORES),
            "--workers", str(step["workers"]), "--bundles", str(step["bundles"]), "--minutes", str(step["minutes"]),
            "--no-links"]  # the links table is built once, in `finish`
    if "revision" in step and not os.environ.get(FORCE):
        args += ["--revision", str(step["revision"])]
    for name, value in (step.get("facts") or {}).items():
        args += ["--fact", f"{name}={value}"]
    if os.environ.get(FORCE):  # a forced load: the Change Journal is ignored and every document is processed again
        # The engine names a forced run `<run>+force-<its time>`: one time for every attempt, so an attempt that is stopped
        # at its bound carries on in the same run, as an unforced one does, instead of starting a run of its own.
        # A forced load is a new publication: the engine refuses the same revision with other content (the run name changed), so
        # its revision is the forced time as digits (YYYYMMDDHHMMSS) and the job's place: above every delivery date and every earlier forced run.
        # The engine refuses one revision with other content, and a source's jobs (its quarters) each publish their own: so each job's
        # revision is the forced time's digits, then its place in the file in three digits (monotonic with the file's order).
        args += ["--force", "--as-of", os.environ[FORCE],
                 "--revision", re.sub(r"[^0-9]", "", os.environ[FORCE]) + f"{step.get('position', 0):03d}"]
    return args


def note(message: str, state: Path) -> None:
    line = f"{datetime.now(ZoneInfo('America/New_York')):%m-%d %H:%M:%S} ET {message}"
    print(line, flush=True)
    with state.open("a") as handle:
        handle.write(line + "\n")


def run(args: list[str], env: dict, log: Path | None = None, append: bool = False) -> int:
    with (log.open("a" if append else "w") if log else open(os.devnull, "w")) as out:
        return subprocess.run([*ENGINE, *args], env=env, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT).returncode


def plan(step: dict, env: dict) -> str:
    """What each delivery of the step would load."""
    return "; ".join(plan_one(one, env) for one in loads(step))


def plan_one(step: dict, env: dict) -> str:
    done = subprocess.run([*ENGINE, "load", *arguments(step), "--plan"], env=env, cwd=ROOT, capture_output=True, text=True)
    found = re.search(r"\{.*\}", done.stdout, re.S)
    try:
        body = json.loads(found.group(0))
        return (f"documents {body.get('documents')} bundles {body.get('bundles')} blocked {body.get('blocked')} "
                f"open runs: {len(body.get('finishable_runs') or [])} to finish first, "
                f"{len(body.get('left_as_they_are') or {})} left")
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


def in_database(url: str, database: str) -> str:
    """The same login on another database of the instance (a monitor reads each store database in turn)."""
    part = urlsplit(url)
    return urlunsplit(part._replace(path="/" + database))


def data_url(env: dict) -> str | None:
    """A duty file's data database URL with the plain driver, or None when the file names none. Its generation names the
    store in the state file."""
    from edgar_warehouse.database_connections import configured, store_url

    if not configured("mdm", env):
        return None
    return store_url("mdm", env).set(drivername="postgresql").render_as_string(hide_password=False)


STORE_MARKER = re.compile(r"chain store (\w+)(?: generation (\w+|\?))?$", re.M)
UNREAD = "?"  # a marker written while the generation could not be read; the next readable start learns it


def state_verdict(text: str, store: str, generation: str = "", adopt: bool = False) -> str:
    """What a state file's text is to this store, as a pure answer the run and `--status` share: "same" (written for this
    store; a marker that names no generation, or a generation not readable now, is not compared), "fresh" (no file), "adopted"
    (no marker, and the operator says it is this store's) or "set aside" (another store, another generation of this one, or lines
    and no marker)."""
    found = STORE_MARKER.findall(text)
    # A marker with no generation at all is a file from before generations were recorded: it cannot show that this store was not
    # made again since, so it is trusted only while the generation cannot be read now. One marked UNREAD was written by a blip.
    if found and found[-1][0] == store and (not generation or found[-1][1] in (UNREAD, generation)):
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
             f" generation {generation or UNREAD}\n")
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
            if generation and found[-1][1] == UNREAD:
                with state.open("a") as handle:  # appended, as the run's own lines are
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


NEVER_CLEARS = re.compile(r"contradictory publications")


def cause_of(errors: str) -> str:
    """The error the attempt's kept errors end in most often, with how many times: one line where the log has hundreds."""
    raised = Counter(redact(line.strip())[:300] for line in errors.splitlines()
                     if re.match(r"\w+(?:Error|Exception|Conflict|Blocked|Stopped)\b", line))
    if not raised:
        return ""
    line, count = raised.most_common(1)[0]
    return f"{count} time{'s' if count != 1 else ''}: {line}"


def retry_is_pointless(previous: str, current: str, errors: str = "") -> bool:
    """A failure that comes back exactly as it was, with nothing moved (its bundle and counts are the same), is not one
    a retry can change. A window that ran out, a lock or deadlock, and a lost connection are not that: they clear when
    the other load ends or the connection returns, and the next attempt resumes where this one stopped. A refusal the
    same inputs always give (`errors`, the attempt's kept errors) stops at the first attempt: a retry only adds runs."""
    if NEVER_CLEARS.search(current) or NEVER_CLEARS.search(errors):
        return True
    return bool(previous) and previous == current and not CLEARS_ITSELF.search(current)


SECRET_KEY = r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|dsn|url|credential)\w*"


def redact(text: str) -> str:
    """Hide every address (`postgres://`, `postgresql+driver://`, `https://`) and the value of any key named like a secret
    (`password=`, `token:`, `api_key=`, `dsn=`, `url=`), so a log line kept on disk never carries one."""
    text = re.sub(r"(?:postgres(?:ql)?(?:\+\w+)?|https?)://\S+", "<addr>", text)
    text = re.sub(rf"(\b{SECRET_KEY}\s*[=:]\s*)(?:'[^']*'|\"[^\"]*\"|\S+)", r"\1<hidden>", text, flags=re.I)
    return re.sub(r"\bhost=\S+", "host=<hidden>", text)


def errors_since(path: Path, start, source: str | None = None, target: str | None = None) -> str:
    """What was written to the shared error log after `start` (a position taken before the attempt: the log is rotated by
    size, and the position follows it across one rotation), addresses hidden, and, given a source and target, only
    the blocks of that step's own commands (a block opens with `$ <command> --source X --target Y`): the file is shared
    by every lane and every run, so another lane's errors in the same window are not this step's."""
    from edgar_warehouse.rules import error_log

    text = error_log.since(path, start)
    if source and target:
        wanted = re.compile(rf"--source {re.escape(source)} --target {re.escape(target)}( |$)")
        text = "".join(block for block in re.split(r"(?m)^(?=\$ )", text) if wanted.search(block.split("\n", 1)[0]))
    return redact(text)


BEGINS = re.compile(r" ET load begins(?:: (.*))?$")


def this_load(lines: list[str]) -> tuple[int, set[str] | None]:
    """Where the last load began in the state file's lines, and the steps it runs (None: every step; no begin: none)."""
    for i in range(len(lines) - 1, -1, -1):
        found = BEGINS.search(lines[i])
        if found:
            return i, (set(found.group(1).split(",")) if found.group(1) else None)
    return -1, set()


def done_steps(state: Path) -> set[str]:
    """The steps finished, read from the shared state file. A step this load runs is done only once this load finishes it
    (it may run again under a changed rule); one it does not run counts as done by any earlier load."""
    if not state.exists():
        return set()
    lines = state.read_text().splitlines()
    start, runs = this_load(lines)
    done = set()
    for i, line in enumerate(lines):
        found = re.search(r" ET (\S+) done:", line)
        if found and (i > start or (runs is not None and found.group(1) not in runs)):
            done.add(found.group(1))
    return done


LOAD_BEGINS = "load begins"


def begin_load(state: Path, named: list[str] | None = None) -> None:
    """Mark where this load begins in the shared state file, with the steps it runs (none named: every step). A failure
    before it belongs to an earlier load, and so does a step done before it that this load runs again."""
    note(f"{LOAD_BEGINS}: {','.join(named)}" if named else LOAD_BEGINS, state)


def mark_lane_stopped(steps: list[dict], state: Path, lane: str) -> None:
    """Record every step of a lane that this load has not finished as stopped: its process ended without saying so (a
    signal, a lost container), and a step of another lane waiting on one of them must stop, not wait."""
    done = done_steps(state)
    for step in steps:
        if step["lane"] == lane and step["name"] not in done:
            note(f"{step['name']} stopped: not done, its lane's process ended", state)


def wait_problems(steps: list[dict], named: list[str] | None = None, done: set[str] = frozenset()) -> list[str]:
    """Every wait that could never end, before any step runs: a needed step that does not exist; lanes that cannot finish
    (a step waiting, through other lanes, on a later step of its own lane); and, for named steps run in order, a needed step
    neither done nor earlier in the run. Empty when every wait can end."""
    by_name = {step["name"]: step for step in steps}
    problems = [f"{step['name']} needs {need}: no such step" for step in steps
                for need in step.get("waits_for") or [] if need not in by_name]
    if problems:
        return problems
    if named is not None:
        earlier = set(done)
        for name in named:  # a named step runs alone, in the given order: only its waits count, never its lane's order
            if name not in by_name:
                problems.append(f"{name}: no such step")
                continue
            problems += [f"{name} needs {need}: not done, and not before it in this run"
                         for need in by_name[name].get("waits_for") or [] if need not in earlier]
            earlier.add(name)
        return problems
    follows, finished = needs(steps), set(done)
    while True:  # every lane at once: a step moves once the step before it in its lane and its waits are done
        moved = {name for name, before in follows.items() if name not in finished and before <= finished}
        if not moved:
            break
        finished |= moved
    stuck = sorted(set(follows) - finished)
    return [f"the lanes cannot finish: {', '.join(stuck)} wait on each other"] if stuck else []


def begin(steps: list[dict], state: Path, named: list[str] | None = None, plan: bool = False) -> int:
    """Before a load's first step: refuse it when a wait could never end, else mark its start (a plan checks, writes nothing)."""
    problems = wait_problems(steps, named, done_steps(state))
    if problems:
        print("Not started: a step would wait for what cannot come: " + "; ".join(problems), file=sys.stderr)
        return 2
    if not plan:
        begin_load(state, named)
    return 0


def load_complete(text: str) -> bool:
    """The load has finished: a `chain done` line follows its last `load begins` line in the state file."""
    lines = text.splitlines()
    return any(line.endswith(" ET chain done") for line in lines[this_load(lines)[0] + 1:])


def failed_steps(state: Path) -> set[str]:
    """The steps this load gave up on: a step-level `stopped:` line (not an attempt's) with no later attempt or finish,
    after the last `load begins` line."""
    last: dict[str, str] = {}
    if state.exists():
        lines = state.read_text().splitlines()
        for line in lines[this_load(lines)[0] + 1:]:
            found = re.search(r" ET (\S+) (?:attempt \d+ start|done:|stopped: )", line)
            if found:
                last[found.group(1)] = "stopped" if " stopped: " in line else "other"
    return {name for name, event in last.items() if event == "stopped"}


def wait_for(step: dict, state: Path, poll: int = 30, others_run: bool = True) -> set[str]:
    """Hold a step until the steps of other lanes it needs are done, and until no other load of its target is running
    (two loads of one source and target at once write the same outputs). Returns the needed steps that failed: then the
    step stops at once, recorded as failed so the steps that need it stop too, and never waits on work that cannot come.
    A step run alone (`others_run` false) has no other lane to wait for: a needed step not done blocks it at once."""
    needed = set(step.get("waits_for") or [])
    if needed - done_steps(state) and others_run:
        note(f"{step['name']} waits for {', '.join(sorted(needed - done_steps(state)))}", state)
    while needed - done_steps(state):
        blocked = needed & failed_steps(state) if others_run else needed - done_steps(state)
        if blocked:
            note(f"{step['name']} stopped: blocked by {', '.join(sorted(blocked))}", state)
            return blocked
        time.sleep(poll)
    pattern = f"edgar-warehouse load .*--source {re.escape(step['source'])} --target {re.escape(step['target'])}( |$)"
    if subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0:
        note(f"{step['name']} waits for another load of its source and target to end", state)
        while subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0:
            time.sleep(poll)
    return set()


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
    numbered = [(int(found.group(1)), p) for p in log.parent.glob(log.name + ".attempt-*") if (found := re.search(r"\.attempt-(\d+)$", p.name))]
    attempts = [p for _, p in sorted(numbered, key=lambda pair: pair[0], reverse=True)]  # `.attempt-1.errors` is no attempt's log
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
        child.communicate()  # reaped, so the killed command leaves no zombie
        return "", "the command did not answer in time"


SAFE_BASE = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "UV_CACHE_DIR", "UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")


def status_env(base: dict, worker: dict, catalog: dict) -> dict:
    """The environment of `rules catalog status`: a short allowlist of the process's own (a path, a home), the Bookkeeping
    login it reads the run with, and the catalog's address and token. No other login, key or password reaches it."""
    from edgar_warehouse.database_connections import url_variable

    given = {key: base[key] for key in SAFE_BASE if key in base}
    for name in {url_variable("bookkeeping"), url_variable("mdm")}:
        if worker.get(name):
            given[name] = worker[name]
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


def run_deliveries(step: dict, env: dict, log: Path) -> tuple[int, str]:
    """Load every delivery of the step in order into one log, up to the first that does not finish; its exit code and the log's
    text. One an earlier attempt loaded is a short call that finds it done."""
    code, parts = 0, loads(step)
    log.write_text("")
    for number, one in enumerate(parts, 1):
        if len(parts) > 1:
            with log.open("a") as handle:
                handle.write(f"Input {number}/{len(parts)}: {one['delivery']}\n")
        code = run(["load", *arguments(one)], env, log, append=True)
        if code or "Load stopped" in log.read_text():
            break
    return code, log.read_text()


def done_line(text: str) -> str:
    """A step's `Done:` line: its one delivery's, or the documents of all its deliveries together."""
    found = re.findall(r"^Done: (\d+) documents loaded, (\d+) already loaded before", text, re.M)
    if len(found) > 1:
        return (f"Done: {sum(int(new) for new, _ in found)} documents loaded, {sum(int(old) for _, old in found)} already loaded "
                f"before, in {len(found)} deliveries")
    lines = [line for line in text.splitlines() if line.startswith("Done: ")]
    return lines[-1][:200] if lines else ""


ENDED_BY_SIGNAL = (-signal.SIGTERM, 128 + signal.SIGTERM)  # as a child of this process, or through a shell or launcher


def attempt_loop(step: dict, env: dict, state: Path, others_run: bool = True) -> bool:
    name, log = step["name"], LOGS / f"chain-{RUN}-{step['name']}.log"
    if wait_for(step, state, others_run=others_run):
        return False
    from edgar_warehouse.rules import error_log

    errors, offset, previous = STORES / "load-errors.log", (0, 0), ""
    peaked = [one for one in load_jobs() if "peak_gb" in one]  # the steps whose unreached peak this one's admission leaves out
    attempt, want, attempt_peak = 1, step["workers"], 0.0  # the peak of every load of this attempt, moves included
    while attempt <= step["attempts"]:
        workers = admit(want, step.get("worker_gb", WORKER_GB), gate_path(state), say=lambda text: note(f"{name} {text}", state),
                        one_document=step.get("one_document", False), peak_gb=step.get("peak_gb", 0.0),
                        reserved=(lambda: unreached_peaks(peaked, process_listing(), besides=name)) if peaked else lambda: 0.0)
        note(f"{name} attempt {attempt} start" + (f" with {workers} of its {step['workers']} workers" if workers != step["workers"] else ""), state)
        offset = error_log.position(errors)
        take_move(state, name)  # a request left for a load that had ended is not this one's
        with sampled_peak(step["source"], step["target"]) as peak:
            code, text = run_deliveries({**step, "workers": workers}, env, log)
        attempt_peak = max(attempt_peak, peak[0])
        asked = take_move(state, name)
        sampled = f"; sampled peak {attempt_peak:.2f} GB" if attempt_peak else ""
        if code == 0 and "Load stopped" not in text:
            note(f"{name} done: {done_line(text)}{sampled}", state)
            return True
        if asked and code in ENDED_BY_SIGNAL:  # moved, not failed: the same attempt goes on with other workers
            want = asked
            continue
        why = [line for line in text.splitlines() if re.search(r"stopped|did not finish|Error", line)]
        note(f"{name} attempt {attempt} stopped rc={code}: "
             f"{redact(why[-1])[:200] if why else ''}{sampled}", state)
        log.rename(log.with_name(log.name + f".attempt-{attempt}"))
        kept = errors_since(errors, offset, step["source"], step["target"])
        if kept:
            log.with_name(log.name + f".attempt-{attempt}.errors").write_text(kept)
        current = why[-1] if why else ""
        if retry_is_pointless(previous, current, kept):
            note(f"{name} stopped: a retry cannot change this failure; {cause_of(kept) or current[:200]} (its errors: "
                 f"{log.name}.attempt-{attempt}.errors)", state)
            return False
        previous = current
        attempt += 1
        attempt_peak = 0.0
    note(out_of_attempts(name, step["attempts"]), state)
    return False


def out_of_attempts(name: str, attempts: int) -> str:
    """The note of a step that used every attempt: a `stopped:` line, so the steps that need it stop instead of waiting."""
    return f"{name} stopped: did not finish in {attempts} attempts: the load stops here"


def run_steps(steps: list[dict], env: dict, state: Path, lane: str | None = None, only: str | None = None,
              start: str | None = None) -> bool:
    """Run the steps in file order (one lane's, one step, or all from `start`), each through its attempts. A lane that stops
    records its later steps as not started, so a step of another lane that needs one stops instead of waiting for it."""
    chosen = [step for step in steps if (not only or step["name"] == only) and (not lane or step["lane"] == lane)]
    named = this_load(state.read_text().splitlines())[1] if lane and state.exists() else None
    if named:  # a load that named its steps (`--in-lanes`) runs those in each lane; the rest were done by an earlier load
        chosen = [step for step in chosen if step["name"] in named]
    if start is not None:
        chosen = chosen[next((i for i, step in enumerate(chosen) if step["name"] == start), len(chosen)):]
    for i, step in enumerate(chosen):
        try:
            ok = attempt_loop(step, env, state, **({"others_run": False} if only else {}))
        except BaseException:  # the lane broke: record what it will not do, so no other lane waits on it
            for left in chosen[i:]:
                if left["name"] not in done_steps(state):
                    note(f"{left['name']} stopped: not done, its lane broke at {step['name']}", state)
            raise
        if not ok:
            if lane:
                for later in chosen[i + 1:]:
                    note(f"{later['name']} stopped: not started, its lane stopped at {step['name']}", state)
            return False
    return True


def finish(env: dict, state: Path, lookups: bool = False) -> bool:
    """After the loads: the links tables and master_binding are built once (a silver row finds its master by a join on master_binding, so no id is filled). The name-search lookups are built only when asked
    (`lookups`): a load reads none of them, only the context search does, and building them re-derives every master.
    The load is done (`chain done`) only when every build exits 0; otherwise a `finish stopped:` line names the build that failed."""
    began = time.monotonic()
    codes = {}
    if lookups:
        note("lookups start", state)
        codes["lookups"] = run(['mdm', 'build-lookups'], env, LOGS / f'chain-{RUN}-lookups.log')
        note(f"lookups rc={codes['lookups']}", state)
    codes["links"] = run(['silver', 'links'], env, LOGS / f'chain-{RUN}-links.log')
    note(f"links rc={codes['links']}", state)
    note(f"finish took {(time.monotonic() - began) / 60:.1f} min (the bound is 5 min without lookups)", state)
    failed = [f"{name} rc={code}" for name, code in codes.items() if code]
    if failed:
        note(f"finish stopped: {', '.join(failed)}: the load is not done; its log is chain-{RUN}-<build>.log", state)
        return False
    note("chain done", state)
    return True


def main() -> int:
    global RUN
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for flag in ("list", "plan", "finish", "lookups"):
        parser.add_argument(f"--{flag}", action="store_true")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--only")
    parser.add_argument("--lanes-at-once", action="store_true",
                        help="print how many lanes the --capacity carries at once (its vCPUs over the widest first step's workers)")
    parser.add_argument("--lane-count", action="store_true", help="print how many lanes the load jobs file has")
    parser.add_argument("--force", action="store_true",
                        help="force publish: every load of this run ignores the Change Journal and processes every document of its source again")
    parser.add_argument("--lane")
    parser.add_argument("--adopt-state", action="store_true",
                        help="keep a run state file that has done lines and no store marker, as this store's (otherwise it is set aside)")
    parser.add_argument("--catalog-status", action="store_true",
                        help="publish the catalog status of every step already done (a catch-up); needs the catalog configured")
    parser.add_argument("--run", default=RUN, help="run label for state and log selection (defaults to RUN, then fresh-v1)")
    parser.add_argument("--status", action="store_true",
                        help="one line a running step: progress, rate, processes, database writes and a verdict")
    parser.add_argument("--json", action="store_true", help="with --status: the same readings as one JSON document (counts, states and times only)")
    parser.add_argument("--workers", type=int, help="with --only: the step's workers, within the capacity's range, instead of the load jobs file's")
    parser.add_argument("--capacity", default="local",
                        help="the compute: local (this machine, measured) or a profile of the load jobs file (aws-small, aws-medium, aws-large)")
    parser.add_argument("--connections", type=int, default=250,
                        help="with --auto: the database connections to aim for; workers rise until they are used")
    parser.add_argument("--deadline", help="with --auto: HH:MM ET today, the run's schedule: a miss is reported once and the loads go on")
    parser.add_argument("--hours", type=float, help="with --auto: a deadline this many hours from now")
    parser.add_argument("--begin", action="store_true",
                        help="before a load's first step: refuse it when a wait could never end, else mark its start (the "
                             "pipeline runs it; with --plan it only checks)")
    parser.add_argument("--mark-stopped", action="store_true",
                        help="with --lane: record its steps not done as stopped (the pipeline, after a lane's process ended)")
    parser.add_argument("--steps", help="with --begin: the named steps of the load, in order, comma-separated")
    parser.add_argument("--auto", action="store_true", help="watch the loads and start each step when its lane is free")
    parser.add_argument("--slots", type=int, default=max(2, min(os.cpu_count() or 2, int(
        os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30 // 2))), help="loads running at once")
    args = parser.parse_args()
    RUN = args.run
    if args.force:
        if args.finish or args.list or args.status or args.begin or args.plan:
            print("--force goes with loads (the whole run, --lane, --only or --auto): the rest has no document to force", file=sys.stderr)
            return 2
        os.environ[FORCE] = forced_at()
    steps = clamped(load_jobs(), args.capacity)
    names = [step["name"] for step in steps]
    for chosen in (args.start, args.only):
        if chosen and chosen not in names:
            print(f"No step named {chosen}", file=sys.stderr)
            return 2
    if args.lane and args.lane not in {step["lane"] for step in steps}:
        print(f"No lane named {args.lane}", file=sys.stderr)
        return 2
    if args.lookups and (args.only or args.lane or not args.finish and (args.list or args.plan)):
        print("--lookups goes with --finish (or all the load jobs), never a partial run that does not reach the finish", file=sys.stderr)
        return 2
    if args.lanes_at_once:
        print(lanes_at_once(steps, args.capacity))
        return 0
    if args.lane_count:
        print(len({step["lane"] for step in steps}))
        return 0
    if args.list:
        for step in steps:
            print(f"{step['lane']} p{step.get('priority', 3)} {step['name']:30} {step['source']} {step['target']} {' '.join(one['capture'] for one in loads(step))}")
        return 0
    state = LOGS / f"chain-{RUN}.log"
    if args.status:  # read-only: the reader login only, no loader login, no wake lock, nothing written
        counted, reader_url, notice = status_inputs()
        if args.json:
            print(json.dumps(status_snapshot(steps, counted, reader_url), indent=1))
            return 0
        if notice:
            print(notice)
        print("\n".join(status(steps, counted, reader_url)))
        return 0
    if args.only:
        os.environ["PGAPPNAME"] = application_name(args.only)  # every session of this step's loads carries its name
    env = {**os.environ, **load_env(STORES / "worker.env")}
    if not (args.plan or args.catalog_status):
        # Every other path starts a load, resumes one or writes the finish: the infrastructure must have passed its checks.
        import readiness

        if not readiness.image_commit(ROOT):
            print("Not started: a load runs only in the loader image CI built from main, never from a checkout: "
                  "infra/load-pipeline/load.sh <step>...", file=sys.stderr)
            return 2
        refused = readiness.gate(STORES, database_generation(data_url(env)) if data_url(env) else "",
                                 readiness.current_sha())
        if refused:
            print(f"Not started: {refused}", file=sys.stderr)
            return 2
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
    if not args.plan and data_url(env):
        try:
            outcome = ensure_store(state, store_id(data_url(env)), adopt=args.adopt_state,
                                   generation=database_generation(data_url(env)))
        except ValueError as refused:
            print(refused, file=sys.stderr)
            return 2
        if outcome == "set aside":
            print(f"{state.name} was not written for this store (another store, a database made again, or no marker): set aside "
                  "and kept beside it, and this store starts a fresh run state", flush=True)
        elif outcome == "adopted":
            print(f"{state.name} adopted as this store's, on your word", flush=True)
    if args.begin:  # once, before the first step: every wait can end, and a failure before this line is an earlier load's
        return begin(steps, state, args.steps.split(",") if args.steps else None, plan=args.plan)
    if args.mark_stopped:  # the worker, after a lane's process ended without success
        mark_lane_stopped(steps, state, args.lane)
        return 0
    if args.plan:
        for step in steps:
            if (args.only and step["name"] != args.only) or (args.lane and step["lane"] != args.lane):
                continue
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
                reader_url=data_url(load_env(STORES / "reader.env")) if (STORES / "reader.env").exists() else None):
            return 1
        return 0 if finish(env, state, args.lookups) else 1
    if not args.finish:
        if not (args.lane or args.only):  # all the load jobs, one step after another in file order
            order = [step["name"] for step in steps]
            if begin(steps, state, order[order.index(args.start):] if args.start in order else order):
                return 2
        if not run_steps(steps, env, state, lane=args.lane, only=args.only, start=args.start):
            return 1
        if args.only or args.lane:
            return 0
    return 0 if finish(env, state, args.lookups) else 1


if __name__ == "__main__":
    raise SystemExit(main())
