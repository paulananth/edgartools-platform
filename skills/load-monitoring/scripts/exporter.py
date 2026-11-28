#!/usr/bin/env -S uv run --no-sync python
"""Serve the load jobs' status as Prometheus metrics: counts, states and times only, never a row or an address.

    uv run --no-sync python exporter.py serve --run <label> [--port 9108] [--interval 30] [--sample 10]
    uv run --no-sync python exporter.py print --run <label>        one reading, written as metrics

A reading is `load_jobs.status_snapshot` (read-only: the reader login, `ps`, the log files). It is repeated every
`--interval` seconds in the background; a scrape returns the last reading, so a slow reading never holds one up.
Run it from the checkout whose code should be read, with the repository's environment (`uv run --no-sync`).
"""
import argparse
import importlib.util
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import design  # noqa: E402
import progress_relay  # noqa: E402


def jobs_module():
    spec = importlib.util.spec_from_file_location("load_jobs", ROOT / "skills/data-operations/scripts/load_jobs.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "skills/data-operations/scripts"))
    spec.loader.exec_module(module)
    return module


def escaped(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def sample(name: str, value, **labels) -> str:
    shown = ",".join(f'{key}="{escaped(text)}"' for key, text in labels.items())
    return f"{name}{{{shown}}} {float(value):g}" if shown else f"{name} {float(value):g}"


def render(snapshot: dict, age: float = 0.0) -> str:
    """The metrics of one reading, in the Prometheus text format."""
    run = snapshot.get("run")
    lines = ["# Counts, states and times of the load jobs; no row values.",
             sample("load_monitor_up", 1), sample("load_monitor_snapshot_age_seconds", age),
             sample("load_steps_total", snapshot["total"])]
    if run is not None:
        lines.append(sample("load_monitor_run_info", 1, run_hash=progress_relay.run_fingerprint(str(run))))
    complete = bool(snapshot.get("complete"))
    lines.append(sample("load_complete", int(complete)))
    counts = {name: 0 for name, *_ in design.STATES}
    for step in snapshot["steps"]:
        counts[step["state"]] += 1  # the tiles keep their counts; the lanes go grey once the load has finished
        lines.append(sample("load_step_state", design.CODE["complete" if complete else step["state"]], lane=step["lane"], step=step["name"]))
        lines.append(sample("load_step_info", 1, lane=step["lane"], step=step["name"], state=step["state"],
                            waits_for=", ".join(step["waits_for"])))
    lines += [sample("load_steps", count, state=state) for state, count in counts.items()]
    for row in snapshot["running"]:
        who = {"lane": row["lane"], "step": row["name"]}
        lines += [sample("load_step_attempt", row["attempt"], **who),
                  sample("load_step_workers", row["workers"], **who),
                  sample("load_step_elapsed_minutes", row["elapsed"], **who),
                  sample("load_step_bound_minutes", row["bound"], **who),
                  sample("load_step_log_age_minutes", row["log_age"], **who),
                  *([] if row["cpu"] is None else
                    [sample("load_step_cpu_percent", row["cpu"], **who),
                     sample("load_step_memory_mb", row["memory_mb"], **who)]),
                  sample("load_step_rows_per_minute", row["rows_per_min"], store=row["store"], **who),
                  sample("load_step_cause", 1, **who, cause=row["why"][-1])]
        if row.get("bundles") is not None:
            finished, total = row["bundles"]
            lines += [sample("load_step_bundles_completed", finished, **who),
                      sample("load_step_bundles_total", total, **who)]
        if row.get("kind") != "progressing":
            lines += [sample("load_step_why", 1, **who, number=str(number), why=words)
                      for number, words in enumerate(row["why"], 1)]
    for database, counts_ in snapshot["sessions"].items():
        lines += [sample("load_sessions", n, database=database, state=state) for state, n in counts_.items()]
    budget = snapshot.get("budget")
    if budget:  # the workers the load may hold at once, and what sets that limit (the store, the compute's memory or its vCPUs)
        running = snapshot["running"]
        lines += [sample("load_worker_budget", budget["workers"], limit=budget["limit"]),
                  sample("load_workers_running", sum(row["workers"] for row in running))]
    machine = snapshot["machine"]
    lines.append(sample("load_machine_load_per_core", machine["load"] / machine["cores"]))
    if machine["memory_free"] is not None:
        lines.append(sample("load_machine_memory_free_ratio", machine["memory_free"]))
    return "\n".join(lines) + "\n"


def down() -> str:
    return sample("load_monitor_up", 0) + "\n"


class Reading:
    """The last reading, refreshed in the background."""

    def __init__(self, interval: int, sample_seconds: int, run: str):
        self.text, self.at, self.interval, self.sample = down(), 0.0, interval, sample_seconds
        self.jobs = jobs_module()
        self.jobs.RUN = run

    def refresh(self) -> None:
        steps = self.jobs.load_jobs()
        counted, reader_url, _ = self.jobs.status_inputs()
        shot = self.jobs.status_snapshot(steps, counted, reader_url, self.sample)
        shot["budget"] = self.jobs.worker_budget(steps, os.environ.get("CAPACITY") or "local")
        self.text, self.at = render(shot), time.time()

    def loop(self) -> None:
        while True:
            try:
                self.refresh()
            except Exception as err:  # noqa: BLE001  a failed reading is a down metric, never a crash; no message holds an address
                self.text = down()
                print(f"reading failed: {type(err).__name__}", file=sys.stderr, flush=True)
            time.sleep(self.interval)


def serve(port: int, interval: int, sample_seconds: int, run: str) -> None:
    reading = Reading(interval, sample_seconds, run)
    threading.Thread(target=reading.loop, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.split("?")[0] != "/metrics":
                self.send_error(404)
                return
            age = time.time() - reading.at if reading.at else 0.0
            body = (reading.text.replace("load_monitor_snapshot_age_seconds 0", f"load_monitor_snapshot_age_seconds {age:g}", 1)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104  OrbStack reaches the host by its own address


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("serve")
    one.add_argument("--port", type=int, default=9108)
    one.add_argument("--interval", type=int, default=30)
    one.add_argument("--sample", type=int, default=10)
    one.add_argument("--run", default=os.environ.get("RUN"))
    printer = sub.add_parser("print")
    printer.add_argument("--sample", type=int, default=5)
    printer.add_argument("--run", default=os.environ.get("RUN"))
    args = parser.parse_args()
    if not args.run:
        parser.error("--run or the RUN environment variable is required")
    if args.command == "print":
        reading = Reading(30, args.sample, args.run)
        reading.refresh()
        print(reading.text, end="")
        return 0
    serve(args.port, args.interval, args.sample, args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
