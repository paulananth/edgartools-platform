#!/usr/bin/env -S uv run --no-project python
"""Bring the local OpenMetadata server up, take it down, read it back and recover it.

    uv run --no-project python openmetadata.py status
        what runs, its health, its port, its mounts, its memory and the API; exit 0 only when all are right
    uv run --no-project python openmetadata.py up [--server-heap 768m] [--search-heap 512m]
        start the stack and wait for health, refusing a compose file that maps another port or mounts a path of a checkout
    uv run --no-project python openmetadata.py stop
        stop the containers; the data volumes stay
    uv run --no-project python openmetadata.py recover
        remove the server container (never a volume) and start it again

It touches only the Compose project `edgartools-openmetadata`. The data is in its two named volumes; no command here
removes a volume. Credentials, the AI Governance clearout and catalog resets are `infra/openmetadata/init.sh` and the
openmetadata skill. Run it from a checkout at current `origin/main`: it reads that checkout's compose file.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "infra/openmetadata/docker-compose.yml"
PROJECT = "edgartools-openmetadata"
PORT = "8587"
SERVER = "openmetadata-server"
VOLUMES = {f"{PROJECT}_db-data", f"{PROJECT}_es-data"}
URL = f"http://127.0.0.1:{PORT}/api/v1/system/version"


def docker(*args: str, env: dict | None = None, check: bool = True) -> str:
    """Run a docker command (no shell) and return its output."""
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=False,
                          env={**os.environ, **(env or {})})
    if check and done.returncode:
        sys.exit(f"docker {args[0]} failed: {done.stderr.strip()[-400:]}")
    return done.stdout


def compose(*args: str, env: dict | None = None, check: bool = True) -> str:
    return docker("compose", "-p", PROJECT, "-f", str(COMPOSE), *args,
                  env={"OPENMETADATA_HOST_PORT": PORT, **(env or {})}, check=check)


def problems_in(config: dict) -> list[str]:
    """What is wrong with a resolved compose document: the wrong port, or a path of a checkout mounted."""
    found = []
    published = [str(p.get("published")) for p in config["services"][SERVER].get("ports", [])]
    if published != [PORT]:
        found.append(f"the server publishes {published or 'no port'}, not {PORT}: this is a stale compose file")
    for name, service in config["services"].items():
        for volume in service.get("volumes", []):
            if volume.get("type") == "bind":
                found.append(f"{name} mounts a host path ({volume.get('source')}): the container would depend on that checkout")
    return found


def preflight() -> None:
    if not COMPOSE.is_file():
        sys.exit(f"no compose file at {COMPOSE}: run this from a checkout of the repository")
    found = problems_in(json.loads(compose("config", "--format", "json")))
    if found:
        sys.exit("refusing to start:\n  " + "\n  ".join(found) + "\nupdate this checkout to origin/main and run again")


def services() -> list[dict]:
    """One dict per container of the project, read from `compose ps` (a JSON array or one object a line)."""
    text = compose("ps", "--all", "--format", "json").strip()
    if not text:
        return []
    rows = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines()]
    return sorted(rows, key=lambda r: r["Service"])


def api_status() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=5) as answer:
            return answer.status
    except urllib.error.HTTPError as err:
        return err.code
    except OSError:
        return 0


def memory() -> dict:
    names = [r["Name"] for r in services() if r["State"] == "running"]
    if not names:
        return {}
    out = docker("stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}", *names)
    return dict(line.split("\t") for line in out.strip().splitlines())


def status() -> int:
    rows = services()
    used = memory()
    bad = [] if rows else ["no container of the project exists"]
    for row in rows:
        if row["Service"] == "execute-migrate-all":
            continue  # the one-off migration exits when it is done
        healthy = row["State"] == "running" and row.get("Health") == "healthy"
        bad += [] if healthy else [f"{row['Service']} is {row['State']} {row.get('Health', '')}".strip()]
        print(f"{row['Service']:<20} {row['State']:<9} {row.get('Health', ''):<9} {used.get(row['Name'], '')}")
    answer = api_status()
    print(f"version read         {answer}")
    if answer != 200:
        bad.append(f"the API answered {answer} on port {PORT}")
    server = next((r for r in rows if r["Service"] == SERVER), None)
    if server and server["State"] == "running":
        ports = {str(p["PublishedPort"]) for p in server.get("Publishers") or [] if p.get("PublishedPort")}
        mounts = docker("inspect", server["Name"], "-f", "{{range .Mounts}}{{.Type}} {{end}}").split()
        print(f"server port          {', '.join(sorted(ports))}   host-path mounts: {mounts.count('bind')}")
        if ports != {PORT}:
            bad.append(f"the server is published on {sorted(ports)}, not {PORT}")
        if "bind" in mounts:
            bad.append("the server mounts a host path")
    for line in bad:
        print(f"PROBLEM: {line}")
    return 1 if bad else 0


def up(server_heap: str | None, search_heap: str | None) -> int:
    preflight()
    env = {}
    if server_heap:
        env["CATALOG_SERVER_HEAP_OPTS"] = f"-Xms{server_heap} -Xmx{server_heap}"
    if search_heap:
        env["CATALOG_SEARCH_HEAP_OPTS"] = f"-Xms{search_heap} -Xmx{search_heap}"
    compose("up", "-d", "--wait", "--wait-timeout", "900", env=env)
    return status()


def stop() -> int:
    compose("stop")
    left = [r["Service"] for r in services() if r["State"] == "running"]
    kept = set(docker("volume", "ls", "--filter", f"label=com.docker.compose.project={PROJECT}",
                      "--format", "{{.Name}}").split())
    print(f"running: {left or 'none'}; volumes kept: {sorted(kept & VOLUMES)}")
    return 0 if not left and kept >= VOLUMES else 1


def recover(server_heap: str | None, search_heap: str | None) -> int:
    preflight()
    compose("rm", "-sf", SERVER)  # the server container only; `rm` never touches a volume without -v
    return up(server_heap, search_heap)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("up", "recover"):
        one = sub.add_parser(name)
        one.add_argument("--server-heap", help="server heap, for example 768m")
        one.add_argument("--search-heap", help="search heap, for example 512m")
    sub.add_parser("status")
    sub.add_parser("stop")
    args = parser.parse_args()
    if args.command == "status":
        return status()
    if args.command == "stop":
        return stop()
    return (up if args.command == "up" else recover)(args.server_heap, args.search_heap)


if __name__ == "__main__":
    sys.exit(main())
