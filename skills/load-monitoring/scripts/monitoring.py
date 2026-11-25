#!/usr/bin/env -S uv run --no-sync python
"""Run the load monitor: the exporter on the host, Prometheus and Grafana in the `edgartools-monitoring` Compose project.

    uv run --no-sync python monitoring.py up        start all three, push the data source and the dashboard, read it back
    uv run --no-sync python monitoring.py status    what runs, whether Prometheus scrapes the exporter, whether the dashboard is there
    uv run --no-sync python monitoring.py stop      stop the exporter and the containers; the dashboard's data stays

The admin login is generated once into a private file (mode 0600) and never printed. The dashboard is pushed from
`dashboard.py` every `up`, so it never drifts; the viewer needs no login (anonymous viewers cannot edit).
Run it from a checkout at current `origin/main`, with the repository's environment (`uv run --no-sync`).
"""
import argparse
import base64
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import dashboard  # noqa: E402

COMPOSE = ROOT / "infra/monitoring/docker-compose.yml"
PROJECT = "edgartools-monitoring"
PORT = "3001"
GRAFANA = f"http://127.0.0.1:{PORT}"
EXPORTER_URL = "http://127.0.0.1:9108/metrics"
PRIVATE = Path.home() / ".config/edgartools/monitoring/grafana.env"
STATE = Path.home() / ".local/share/edgartools/monitoring"
PID = STATE / "exporter.pid"
KEY = "MONITORING_ADMIN_PASSWORD"


def docker(*args: str, env: dict | None = None, check: bool = True) -> str:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=False, env={**os.environ, **(env or {})})
    if check and done.returncode:
        sys.exit(f"docker {args[0]} failed: {done.stderr.strip()[-400:]}")
    return done.stdout


def compose(*args: str, check: bool = True) -> str:
    return docker("compose", "-p", PROJECT, "-f", str(COMPOSE), *args, env={KEY: password(), "MONITORING_PORT": PORT}, check=check)


def password() -> str:
    """The admin login, generated into a private file on first use; the value never leaves this process."""
    if not PRIVATE.exists():
        PRIVATE.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE.touch(mode=0o600)
        PRIVATE.write_text(f"{KEY}={secrets.token_urlsafe(24)}\n")
    PRIVATE.chmod(0o600)
    for line in PRIVATE.read_text().splitlines():
        if line.startswith(f"{KEY}="):
            return line.split("=", 1)[1]
    sys.exit("the private monitoring file has no admin entry: remove it and run up again")


def problems_in(config: dict) -> list[str]:
    """What is wrong with the resolved compose document: another published port, or a path of a checkout mounted."""
    found = []
    published = [str(p.get("published")) for p in config["services"]["grafana"].get("ports", [])]
    if published != [PORT]:
        found.append(f"grafana publishes {published or 'no port'}, not {PORT}: a stale compose file")
    for name, service in config["services"].items():
        for volume in service.get("volumes", []):
            if volume.get("type") == "bind":
                found.append(f"{name} mounts a host path: the container would depend on that checkout")
    return found


def preflight() -> None:
    if not COMPOSE.is_file():
        sys.exit(f"no compose file at {COMPOSE}: run this from a checkout of the repository")
    found = problems_in(json.loads(compose("config", "--format", "json")))
    if found:
        sys.exit("refusing to start:\n  " + "\n  ".join(found) + "\nupdate this checkout to origin/main and run again")


def api(method: str, path: str, body: dict | None = None, login: bool = True) -> tuple[int, dict]:
    request = urllib.request.Request(GRAFANA + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    request.add_header("Content-Type", "application/json")
    if login:
        request.add_header("Authorization", "Basic " + base64.b64encode(f"admin:{password()}".encode()).decode())
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:
            return answer.status, json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, {}
    except OSError:
        return 0, {}


def provision() -> None:
    source = {"name": "Prometheus", "uid": "prometheus", "type": "prometheus", "access": "proxy",
              "url": "http://prometheus:9090", "isDefault": True}
    code, _ = api("POST", "/api/datasources", source)
    if code in (409, 400):
        code, _ = api("PUT", "/api/datasources/uid/prometheus", source)
    if code not in (200, 201):
        sys.exit(f"the data source was not accepted (HTTP {code})")
    code, _ = api("POST", "/api/dashboards/db", {"dashboard": dashboard.build(), "overwrite": True})
    if code != 200:
        sys.exit(f"the dashboard was not accepted (HTTP {code})")


def exporter_pid() -> int | None:
    try:
        pid = int(PID.read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def start_exporter(run: str | None = None) -> None:
    if exporter_pid() or exporter_answer() != "not answering":  # the load pipeline's exporter already serves the port
        return
    run = run or os.environ.get("RUN")
    if not run:
        sys.exit("start a standalone monitor with --run <label>")
    STATE.mkdir(parents=True, exist_ok=True)
    log = (STATE / "exporter.log").open("a")
    child = subprocess.Popen([sys.executable, str(HERE / "exporter.py"), "serve", "--run", run], cwd=ROOT, stdout=log,
                             stderr=log, start_new_session=True)
    PID.write_text(str(child.pid))


def stop_exporter() -> None:
    pid = exporter_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
    PID.unlink(missing_ok=True)


def services() -> list[dict]:
    text = compose("ps", "--all", "--format", "json").strip()
    if not text:
        return []
    rows = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines()]
    return sorted(rows, key=lambda r: r["Service"])


def exporter_answer() -> str:
    try:
        with urllib.request.urlopen(EXPORTER_URL, timeout=5) as answer:
            return "up" if b"load_monitor_up 1" in answer.read() else "answering, last reading failed"
    except OSError:
        return "not answering"


def scrape_health() -> str:
    code, body = api("GET", "/api/datasources/proxy/uid/prometheus/api/v1/targets")
    targets = (body.get("data") or {}).get("activeTargets") or []
    return targets[0]["health"] if code == 200 and targets else f"unknown (HTTP {code})"


def status() -> int:
    bad = []
    for row in services():
        healthy = row["State"] == "running" and row.get("Health") == "healthy"
        print(f"{row['Service']:<12} {row['State']:<9} {row.get('Health', '')}")
        if not healthy:
            bad.append(f"{row['Service']} is {row['State']} {row.get('Health', '')}".strip())
    if not services():
        bad.append("no container of the project exists")
    exporter = exporter_answer()
    print(f"{'exporter':<12} {exporter}")
    if exporter != "up":
        bad.append(f"the exporter is {exporter}")
    scrape = scrape_health()
    print(f"{'prometheus':<12} scrape target {scrape}")
    if scrape != "up":
        bad.append(f"Prometheus's scrape target is {scrape}")
    code, _ = api("GET", f"/api/dashboards/uid/{dashboard.UID}")
    print(f"{'dashboard':<12} {GRAFANA}/d/{dashboard.UID}  (HTTP {code})")
    if code != 200:
        bad.append(f"the dashboard answers HTTP {code}")
    for line in bad:
        print(f"PROBLEM: {line}")
    return 1 if bad else 0


def up(run: str | None = None) -> int:
    preflight()
    start_exporter(run)
    compose("up", "-d", "--wait", "--wait-timeout", "300")
    provision()
    time.sleep(20)  # Prometheus scrapes every 15 s: the first reading must land before it is read back
    return status()


def stop() -> int:
    stop_exporter()
    compose("stop")
    left = [r["Service"] for r in services() if r["State"] == "running"]
    print(f"running: {left or 'none'}; exporter {'stopped' if not exporter_pid() else 'still running'}")
    return 0 if not left and not exporter_pid() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["up", "status", "stop"])
    parser.add_argument("--run", help="load run whose status the exporter reads when started here")
    args = parser.parse_args()
    if args.run:
        os.environ["RUN"] = args.run
    return up(args.run) if args.command == "up" else {"status": status, "stop": stop}[args.command]


if __name__ == "__main__":
    sys.exit(main())
