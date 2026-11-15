#!/usr/bin/env python3
"""Load every captured source into one store, in the order rules/load-chain.yaml gives.

    python load_chain.py --list               the steps, in order
    python load_chain.py --plan               what each step would load (documents and bundles); writes nothing
    python load_chain.py                      the whole chain, then the lookups and each silver table's master ids
    python load_chain.py --from <step>        carry on from a step (a done step costs one call: nothing is loaded twice)
    python load_chain.py --only <step>        one step
    python load_chain.py --finish             only what follows the loads

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


def arguments(step: dict) -> list[str]:
    capture = ROOTS[step.get("capture_root", "captures")] / step["capture"]
    args = ["--source", step["source"], "--target", step["target"], "--capture", str(capture),
            "--capture-run", f"{RUN}-{step['name']}", "--stores", str(STORES),
            "--workers", str(step["workers"]), "--bundles", str(step["bundles"]), "--minutes", str(step["minutes"])]
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


def attempt_loop(step: dict, env: dict, state: Path) -> bool:
    name, log = step["name"], LOGS / f"chain-{RUN}-{step['name']}.log"
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
    """After the loads: the lookups are built once, then each silver table's master ids are filled from MDM as it is now
    (a row that landed before its master was mastered keeps an empty id)."""
    note("lookups start", state)
    note(f"lookups rc={run(['mdm', 'build-lookups'], env, LOGS / f'chain-{RUN}-lookups.log')}", state)
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
    args = parser.parse_args()
    steps = yaml.safe_load((ROOT / "rules/load-chain.yaml").read_text())["steps"]
    names = [step["name"] for step in steps]
    for chosen in (args.start, args.only):
        if chosen and chosen not in names:
            print(f"No step named {chosen}", file=sys.stderr)
            return 2
    if args.list:
        for step in steps:
            print(f"{step['name']:30} {step['source']} {step['target']} {step['capture']}")
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
    if not args.finish:
        started = args.start is None
        for step in steps:
            started = started or step["name"] == args.start
            if not started or (args.only and step["name"] != args.only):
                continue
            if not attempt_loop(step, env, state):
                return 1
        if args.only:
            return 0
    finish(env, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
