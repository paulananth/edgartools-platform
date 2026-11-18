#!/usr/bin/env python3
"""Load every captured source into one store, in the order rules/load-chain.yaml gives.

    python load_chain.py --list               the steps, in order
    python load_chain.py --plan               what each step would load (documents and bundles); writes nothing
    python load_chain.py                      the whole chain, then the lookups and each silver table's master ids
    python load_chain.py --from <step>        carry on from a step (a done step costs one call: nothing is loaded twice)
    python load_chain.py --only <step>        one step
    python load_chain.py --lane <name>        the steps of one lane; run several lanes at once (see the chain file)
    python load_chain.py --finish             only what follows the loads, once every lane is done
    python load_chain.py --auto [--slots N]   watch the loads; start each step when its lane is free (see `auto`)

Each step is the same resumable `load` command, run again until it finishes (a stopped attempt names why in its log and
the next carries on from where it stopped). The chain stops at the first step that does not finish in its attempts.
STORES (default ~/.config/edgartools/hosted) is the stores folder, whose worker.env holds the logins; CAPTURES, PROVING
and LOGS name the captured files and the logs; RUN labels the capture runs. The machine stays awake for the whole chain
(a sleep once dropped a hosted connection and lost 74 minutes). Run it from the checkout whose code should load.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
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


def ready(steps: list[dict], done: set[str], running: set[str], failed: set[str], free: int,
          busy: frozenset | set = frozenset()) -> list[str]:
    """The steps to start now: each follows only done steps, is not blocked by a failure, and does not share its source
    and target with a load already running (two loads of one pair write the same outputs). The longest chain first,
    judged by the step's `minutes` (a bound on one attempt, so only a proxy for its length); at most `free`."""
    follows, stuck = needs(steps), blocked(steps, failed)
    taken = set(busy) | {(s["source"], s["target"]) for s in steps if s["name"] in running}
    chosen: list[dict] = []
    for step in sorted(steps, key=lambda s: -s["minutes"]):
        pair = (step["source"], step["target"])
        if (step["name"] in done or step["name"] in running or step["name"] in failed or step["name"] in stuck
                or not follows[step["name"]] <= done or pair in taken or len(chosen) >= free):
            continue
        chosen.append(step)
        taken.add(pair)
    return [step["name"] for step in chosen]


def stalled(steps: list[dict], done: set[str], running: set[str], failed: set[str]) -> list[str]:
    """The steps that can never start: nothing runs, and each is blocked by a failure or follows one that is."""
    if running:
        return []
    stuck = blocked(steps, failed)
    return [s["name"] for s in steps if s["name"] in stuck and s["name"] not in done]


def swap_fraction(text: str) -> float | None:
    """The share of swap in use, from `sysctl vm.swapusage` (macOS); None when it cannot be read."""
    found = re.search(r"total = ([\d.]+)M\s+used = ([\d.]+)M", text)
    return float(found.group(2)) / float(found.group(1)) if found and float(found.group(1)) else None


def has_headroom(load: float, cores: int, swap_used: float | None) -> bool:
    """A load average over one and a half times the cores, or swap over three quarters used, slows every running load."""
    return load <= 1.5 * cores and (swap_used is None or swap_used <= 0.75)


def machine_headroom() -> bool:
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], check=False, capture_output=True, text=True).stdout if sys.platform == "darwin" else ""
    return has_headroom(os.getloadavg()[0], os.cpu_count() or 1, swap_fraction(swap))


def external_loads() -> set[tuple[str, str]]:
    """The (source, target) of every `load` running on this machine, whoever started it."""
    listing = subprocess.run(["ps", "-Ao", "args"], check=False, capture_output=True, text=True).stdout
    return {(m.group(1), m.group(2)) for line in listing.splitlines() if "edgar-warehouse load " in line
            for m in [re.search(r"--source (\S+) --target (\S+)", line)] if m}


def auto(steps: list[dict], state: Path, slots: int, poll: int = 30) -> int:
    """Watch the loads and start the next ready step whenever a slot is free and the machine has headroom. One start
    a cycle: the load average lags, so a started step is counted running before the next is judged. Each step runs as
    `load_chain.py --only <step>` (the attempt loop); a step that uses up its attempts blocks what follows it and the
    rest carry on. Ends when every step is done (then the lookups and the links) or nothing more can start."""
    children: dict[str, subprocess.Popen] = {}
    failed: set[str] = set()
    names = {step["name"] for step in steps}
    while True:
        for name, child in list(children.items()):
            if child.poll() is not None:
                del children[name]
                if child.returncode != 0:
                    failed.add(name)
        done = done_steps(state)
        if names <= done:
            return 0
        busy = external_loads()
        free = slots - max(len(children), len(busy))
        starts = ready(steps, done, set(children), failed, 1, busy) if free > 0 and machine_headroom() else []
        for name in starts:
            note(f"scheduler starts {name}", state)
            children[name] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--only", name])
        if not starts and not children and not busy and (stuck := stalled(steps, done, set(), failed)):
            note(f"scheduler stops: {', '.join(sorted(failed))} failed, so {', '.join(stuck)} cannot start", state)
            return 1
        time.sleep(poll)


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
    env = {**os.environ, **load_env(STORES / "worker.env")}
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / f"chain-{RUN}.log"
    if args.plan:
        for step in steps:
            print(f"{step['name']:30} {plan(step, env)}", flush=True)
        return 0
    if sys.platform == "darwin":
        subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    if args.auto:
        if auto(steps, state, args.slots):
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
