#!/usr/bin/env python3
"""The gate before a load: the infrastructure is built, tested and unchanged, or nothing starts.

    python readiness.py            # reads every fact, prints PASS or FAIL per check, writes readiness.json on a full pass
    python readiness.py --list     # the checks, without reading anything
    python readiness.py --build-engine   # rebuild the compiled engine from this checkout and record what it was built from

`load_chain.py` refuses to start, resume or finish a load unless the stores folder's `readiness.json` was written by a full
pass for this store generation (the creation identity of its databases) and this code (the commit) in the last day. A reset of
the databases, a new commit or a day's age each make the gate close again. Every check is read-only and prints counts and
names, never a connection value. Evidence that the code is tested is its commit's green CI, never a local run alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

READY = "readiness.json"
MAX_AGE = timedelta(hours=24)
MIN_DISK_GIB = 100
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LOADER = "edgar_loader"
GUARDS = ("work_mem", "statement_timeout", "idle_in_transaction_session_timeout")
CHECKS = {
    "CODE": "The code is committed, contains today's main, and its commit has green CI",
    "ENGINE": "The compiled engine was built from the source of this checkout",
    "DOCTOR": "doctor reports the stores ready under the loader's files",
    "GUARDS": "The loader holds its connection limit, memory ceiling and timeouts",
    "REFERENCE": "RDM holds its published codes, and silver holds a table for every spec",
    "CAPTURES": "Every step has a capture to load",
    "QUIET": "No load is running and the loader has no session",
    "ROOM": "The machine has disk and the load average has room",
    "AUDIT": "The access audit of the database has no failing control",
}


def now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def current_sha(repo: Path = REPO) -> str:
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def gate(stores: Path, generation: str, sha: str, at: datetime | None = None) -> str | None:
    """None when a load may start; otherwise why not, in a sentence."""
    path = stores / READY
    if not path.exists():
        return f"no {READY} in the stores folder: run readiness.py (the infrastructure is not known to be ready and tested)"
    try:
        record = json.loads(path.read_text())
        written = datetime.fromisoformat(record["at"])
    except (ValueError, KeyError):
        return f"{READY} cannot be read: run readiness.py again"
    if record.get("passed") is not True:
        return "the last readiness run failed: fix what it names and run readiness.py again"
    if not generation or record.get("generation") != generation:
        return "the stores were made again since the last readiness pass: run readiness.py again"
    if not sha or record.get("sha") != sha:
        return "the code changed since the last readiness pass: run readiness.py again"
    if (at or now()) - written > MAX_AGE:
        return "the last readiness pass is more than a day old: run readiness.py again"
    return None


def evaluate(facts: dict) -> list[dict]:
    """Grade the facts into checks. A fact that could not be read is a failure, never a pass."""
    def check(cid, ok, evidence):
        return {"id": cid, "title": CHECKS[cid], "ok": bool(ok), "evidence": evidence}
    g, e, loader, ref = facts["git"], facts["engine"], facts["loader"], facts["reference"]
    audit = facts["audit"]
    return [
        check("CODE", g["clean"] and g["contains_main"] and g["ci"] == "success", {k: g[k] for k in ("clean", "contains_main", "ci")}),
        check("ENGINE", e["applicable"] is False or (e["built"] is not None and e["built"] == e["source"]),
              {"applicable": e["applicable"], "built_from_this_source": None if e["built"] is None else e["built"] == e["source"]}),
        check("DOCTOR", facts["doctor"] is True, {"doctor_ok": facts["doctor"]}),
        check("GUARDS", loader is not None and (loader["limit"] or -1) > 0 and all(k in loader["settings"] for k in GUARDS),
              None if loader is None else {"connection_limit": loader["limit"], "guards_set": sorted(k for k in GUARDS if k in loader["settings"])}),
        check("REFERENCE", ref is not None and ref["codes"] > 0 and ref["silver_tables"] >= ref["specs"] > 0, ref),
        check("CAPTURES", facts["plan_missing"] == 0, {"steps_without_a_capture": facts["plan_missing"]}),
        check("QUIET", facts["loads_running"] == 0 and facts["loader_sessions"] == 0,
              {"loads_running": facts["loads_running"], "loader_sessions": facts["loader_sessions"]}),
        check("ROOM", facts["disk_gib"] >= MIN_DISK_GIB and facts["load1"] < facts["cores"],
              {"disk_free_gib": round(facts["disk_gib"]), "load_average": round(facts["load1"], 1), "cores": facts["cores"]}),
        check("AUDIT", audit is not None and not audit, {"failing_controls": audit if audit is not None else "audit not available"}),
    ]


# --- gathering: each reads one fact, prints nothing sensitive, and returns None or False when it cannot ----------------
def git_facts(repo: Path) -> dict:
    def run(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    sha = current_sha(repo)
    ci = "unknown"
    if sha:
        listed = subprocess.run(["gh", "run", "list", "--commit", sha, "--json", "conclusion,status", "-L", "20"], capture_output=True, text=True,
                                cwd=repo, check=False)
        try:
            runs = json.loads(listed.stdout or "[]")
            done = [r for r in runs if r["status"] == "completed"]
            ci = "success" if done and all(r["conclusion"] in ("success", "skipped") for r in done) and len(done) == len(runs) else "not green"
        except ValueError:
            ci = "unknown"
    return {"clean": not run("status", "--porcelain", "--untracked-files=no").stdout.strip(),
            "contains_main": run("merge-base", "--is-ancestor", "origin/main", "HEAD").returncode == 0, "ci": ci}


ENGINE_FILES = ("src", "Cargo.toml", "Cargo.lock", "pyproject.toml")


def engine_hash(crate: Path) -> str:
    """One hash of the engine's source: each file's relative path and bytes, in a fixed order."""
    digest = hashlib.sha256()
    for name in ENGINE_FILES:
        base = crate / name
        for path in sorted([base] if base.is_file() else base.rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(crate)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def engine_marker() -> Path | None:
    try:
        import source_contract
    except ImportError:
        return None
    return Path(source_contract.__file__).parent / "BUILT_FROM"


def engine_facts(repo: Path) -> dict:
    crate = repo / "crates" / "source-contract"
    if not (crate / "src").exists():
        return {"applicable": False, "built": None, "source": ""}  # an installed bundle carries its own engine
    marker = engine_marker()
    built = marker.read_text().strip() if marker and marker.exists() else None
    return {"applicable": True, "built": built, "source": engine_hash(crate)}


def build_engine(repo: Path = REPO) -> int:
    """Install the engine from this checkout into the running environment and record the source it was built from."""
    crate = repo / "crates" / "source-contract"
    done = subprocess.run(["uv", "pip", "install", "--python", sys.executable, "--reinstall", str(crate)], check=False)
    marker = engine_marker()
    if done.returncode or marker is None:
        return 1
    marker.write_text(engine_hash(crate) + "\n")
    print("engine built and recorded")
    return 0


def doctor_ok(stores: Path, env: dict) -> bool:
    exe = env.get("EDGAR_WAREHOUSE") or "edgar-warehouse"
    done = subprocess.run([exe, "doctor"], capture_output=True, text=True, env=env, check=False, timeout=900)
    return '"ok": true' in done.stdout


def sql_facts(reader_env: dict, env: dict) -> tuple[dict | None, dict | None, int]:
    """(the loader's guards, the reference counts, the loader's sessions), read with the reader's and the loader's logins
    (each file's `DB_URL`, a database added per read)."""
    from urllib.parse import urlsplit, urlunsplit

    def url(value: str, database: str) -> str:
        return urlunsplit(urlsplit(re.sub(r"^postgresql\+\w+", "postgresql", value))._replace(path="/" + database))

    try:
        import psycopg2
        reader = url(reader_env["DB_URL"], "postgres")
        with psycopg2.connect(reader, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("select rolconnlimit from pg_roles where rolname = %s", (LOADER,))
            limit = cur.fetchone()[0]
            cur.execute("select s.setconfig from pg_db_role_setting s join pg_roles r on r.oid = s.setrole where r.rolname = %s and s.setdatabase = 0", (LOADER,))
            config = cur.fetchone()
            cur.execute("select count(*) from pg_stat_activity where usename = %s", (LOADER,))
            sessions = cur.fetchone()[0]
        loader = {"limit": limit, "settings": dict(item.split("=", 1) for item in (config[0] if config else []))}
    except Exception:  # noqa: BLE001  a driver error can quote the address
        return None, None, 1
    try:
        def count(database: str, sql: str) -> int:
            with psycopg2.connect(url(env["DB_URL"], database), connect_timeout=10) as conn, conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchone()[0]
        specs = len(list((REPO / "rules" / "sources").glob("*/silver-*.yaml")))
        reference = {"codes": count("rdm", "select count(*) from rdm.published_code"), "specs": specs,
                     "silver_tables": count("silver", "select count(*) from information_schema.tables where table_schema = 'silver'")}
    except Exception:  # noqa: BLE001
        reference = None
    return loader, reference, sessions


def loads_running() -> int:
    listing = subprocess.run(["ps", "-Ao", "args"], capture_output=True, text=True, check=False).stdout
    return sum(1 for line in listing.splitlines() if re.search(r"load_chain\.py|edgar-warehouse load ", line) and "readiness.py" not in line)


def plan_missing(env: dict) -> int:
    done = subprocess.run([sys.executable, str(HERE / "load_chain.py"), "--plan"], capture_output=True, text=True, env=env, check=False, timeout=900)
    return sum(1 for line in done.stdout.splitlines() if "no plan" in line) if done.returncode == 0 else 99


def audit_failures() -> list[str] | None:
    script = REPO / "skills" / "access-audit" / "scripts" / "access_audit.py"
    if not script.exists():
        return None
    done = subprocess.run([sys.executable, str(script), "--platform", "postgres", "--json"], capture_output=True, text=True, check=False)
    try:
        return sorted(r["id"] for r in json.loads(done.stdout) if r["result"] == "FAIL")
    except ValueError:
        return None


def gather(stores: Path, repo: Path = REPO) -> dict:
    sys.path.insert(0, str(HERE))
    import load_chain
    env = {**os.environ, **load_chain.load_env(stores / "worker.env")}
    reader = load_chain.load_env(stores / "reader.env") if (stores / "reader.env").exists() else {}
    loader, reference, sessions = sql_facts(reader, env)
    usage = shutil.disk_usage(Path.home())
    return {"git": git_facts(repo), "engine": engine_facts(repo), "doctor": doctor_ok(stores, env), "loader": loader, "reference": reference,
            "plan_missing": plan_missing(env), "loads_running": loads_running(), "loader_sessions": sessions,
            "disk_gib": usage.free / 2**30, "load1": os.getloadavg()[0], "cores": os.cpu_count() or 1, "audit": audit_failures()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--build-engine", action="store_true", help="rebuild the engine from this checkout, then stop")
    parser.add_argument("--stores", default=os.environ.get("STORES") or str(Path.home() / ".config/edgartools/hosted"))
    args = parser.parse_args(argv)
    if args.build_engine:
        return build_engine()
    if args.list:
        for cid, title in CHECKS.items():
            print(f"{cid:10} {title}")
        return 0
    stores = Path(args.stores)
    sys.path.insert(0, str(HERE))
    import load_chain
    results = evaluate(gather(stores))
    for r in results:
        print(f"{'PASS' if r['ok'] else 'FAIL':5} {r['id']:10} {r['title']}\n      evidence: {r['evidence']}")
    env = load_chain.load_env(stores / "worker.env")
    generation = load_chain.database_generation(load_chain.mdm_url_of(env["DB_URL"])) if env.get("DB_URL") else ""
    passed = all(r["ok"] for r in results) and bool(generation)
    (stores / READY).write_text(json.dumps({"passed": passed, "at": now().isoformat(), "generation": generation, "sha": current_sha(),
                                            "checks": {r["id"]: r["ok"] for r in results}}))
    os.chmod(stores / READY, 0o600)
    print("READY: a load may start" if passed else "NOT READY: nothing starts until every check passes")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
