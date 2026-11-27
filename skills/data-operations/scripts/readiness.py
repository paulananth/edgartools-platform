#!/usr/bin/env python3
"""The gate before a load: the infrastructure is built, tested and unchanged, or nothing starts.

    python readiness.py            # reads every fact, prints PASS or FAIL per check, writes readiness.json on a full pass
    python readiness.py --list     # the checks, without reading anything
    python readiness.py --build-engine   # rebuild the compiled engine from this checkout and record what it was built from

`load_jobs.py` refuses to start, resume or finish a load unless the stores folder's `readiness.json` was written by a full
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
IMAGE_COMMIT = "COMMIT"  # in a loader image: the commit CI built it from, only ever one that passed CI on main
GUARDS = ("work_mem", "statement_timeout", "idle_in_transaction_session_timeout")
CHECKS = {
    "CODE": "The code is committed and contains today's main",
    "DOCTOR": "doctor reports the stores ready under the loader's files",
    "GUARDS": "The loader holds its connection limit, memory ceiling and timeouts",
    "REFERENCE": "RDM holds its published codes, and silver holds a table for every spec",
    "CAPTURES": "Every step has a capture to load",
    "QUIET": "No load is running and the loader has no session",
    "ROOM": "The machine has disk and the load average has room",
    "AUDIT": "The access audit of the database has no failing control",
    "LOGINS": "Every duty file's login connects to the databases of its duty",
    "STATE": "The run's state file is this store's, or will be set aside, before any step runs",
    "REGISTERED": "The merge policy and every Dataset Contract are registered, and every worker profile is granted",
    "MIRRORED": "The managed mirror holds exactly the tables its record lists, each replicating, so Gold reads what the load writes",
}
MIRROR_OPERATOR = Path.home() / ".config" / "edgartools" / "mirror-operator" / "mirror-operator.env"
DUTY_FILES = ("worker.env", "governance.env", "reader.env")  # each connects to every store database; owner.env to `postgres`


def now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def image_commit(repo: Path) -> str:
    """The commit a loader image was built from, written by CI into the image; "" outside an image. A folder with `.git`
    is a checkout whatever files it holds, so a stray `COMMIT` file never stands in for git."""
    path = repo / IMAGE_COMMIT
    return path.read_text().strip() if path.is_file() and not (repo / ".git").exists() else ""


def current_sha(repo: Path = REPO) -> str:
    if image_commit(repo):
        return image_commit(repo)
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


def next_record(previous: dict | None, results: list[dict], generation: str, sha: str, at: datetime) -> dict | None:
    """The record a readiness run writes, or None to leave the record on disk. A run beside a load fails QUIET and nothing else;
    it must not close the gate under the scheduler running that load, so a passing record of this store and this code stands."""
    failed = {r["id"] for r in results if not r["ok"]}
    if (failed == {"QUIET"} and previous and previous.get("passed") is True and generation
            and previous.get("generation") == generation and previous.get("sha") == sha):
        return None
    return {"passed": not failed and bool(generation), "at": at.isoformat(), "generation": generation, "sha": sha,
            "checks": {r["id"]: r["ok"] for r in results}}


def evaluate(facts: dict) -> list[dict]:
    """Grade the facts into checks. A fact that could not be read is a failure, never a pass."""
    def check(cid, ok, evidence):
        return {"id": cid, "title": CHECKS[cid], "ok": bool(ok), "evidence": evidence}
    g, loader, ref = facts["git"], facts["loader"], facts["reference"]
    audit, logins, state = facts["audit"], facts["logins"], facts["state"]
    reg = facts["registered"]
    return [
        check("CODE", g["clean"] and g["contains_main"], {k: g[k] for k in ("clean", "contains_main")}),
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
        check("LOGINS", bool(logins) and all(v == "answers" for v in logins.values()), logins),
        check("STATE", state is not None and state["verdict"] in ("fresh", "set aside", "same"), state),
        check("REGISTERED", reg is not None and reg["policies"] > 0 and reg["datasets"] > 0 and reg["profiles_granted"] >= reg["profiles"] > 0, reg),
        check("MIRRORED", facts["mirror"] == "exact", {"mirror": facts["mirror"]}),
    ]


# --- gathering: each reads one fact, prints nothing sensitive, and returns None or False when it cannot ----------------
def git_facts(repo: Path) -> dict:
    if image_commit(repo):  # CI builds the image only from a commit that passed CI on main, and nothing edits it after
        return {"clean": True, "contains_main": True, "image": image_commit(repo)}

    def run(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return {"clean": not run("status", "--porcelain", "--untracked-files=no").stdout.strip(),
            "contains_main": run("merge-base", "--is-ancestor", "origin/main", "HEAD").returncode == 0}


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
    """(the loader's guards, the reference counts, the loader's sessions), read with the reader's and the loader's logins."""
    sys.path.insert(0, str(HERE))
    import load_jobs

    try:
        import psycopg2
        reader = load_jobs.in_database(load_jobs.data_url(reader_env), "postgres")
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
            with psycopg2.connect(load_jobs.in_database(load_jobs.data_url(env), database), connect_timeout=10) as conn, conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchone()[0]
        specs = len(list((REPO / "sources").glob("*/silver-*.yaml")))
        reference = {"codes": count("data", "select count(*) from rdm.published_code"), "specs": specs,
                     "silver_tables": count("data", "select count(*) from information_schema.tables where table_schema = 'silver'")}
    except Exception:  # noqa: BLE001
        reference = None
    return loader, reference, sessions


def registration_facts(reader_env: dict, env: dict) -> dict | None:
    """What init's steps 5 to 7 leave: the policies and Dataset Contract readings the loader reads in the Rules Database, and the worker profiles Bookkeeping
    has granted (the reader's login sees the memberships). None when a fact cannot be read."""
    sys.path.insert(0, str(HERE))
    import load_jobs

    try:
        import psycopg2
        from edgar_warehouse.workers import PROFILES

        def one(source: dict, database: str, sql: str) -> int:
            with psycopg2.connect(load_jobs.in_database(load_jobs.data_url(source), database), connect_timeout=10) as conn, conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchone()[0]
        return {"policies": one(env, "config", "select count(*) from rules.policy"),
                "datasets": one(env, "config", "select count(*) from rules.dataset_reading"),
                "profiles": len(PROFILES),
                "profiles_granted": one(reader_env, "control", "select count(*) from pg_auth_members m join pg_roles r on r.oid = m.roleid "
                                        "join pg_roles u on u.oid = m.member where u.rolname = 'bookkeeping_runtime' and r.rolname like 'bk\\_worker\\_%'")}
    except Exception:  # noqa: BLE001  a driver error can quote the address
        return None


def loads_running() -> int:
    listing = subprocess.run(["ps", "-Ao", "args"], capture_output=True, text=True, check=False).stdout
    return sum(1 for line in listing.splitlines() if re.search(r"load_jobs\.py|edgar-warehouse load ", line) and "readiness.py" not in line)


def plan_missing(env: dict) -> int:
    """The steps a load could not start: no readable receipts file in the capture folder (a load reads it first), or a
    target the source does not declare. Each is read, never planned. A load jobs file that does not read counts as every step."""
    sys.path.insert(0, str(HERE))
    import load_jobs
    from edgar_warehouse.mdm import raw_capture
    from edgar_warehouse.rules import files as rules_files

    def loadable(step: dict) -> bool:
        try:
            for one in load_jobs.loads(step):
                raw_capture.receipts(load_jobs.ROOTS[one.get("capture_root", "captures")] / one["capture"])
            return step["target"] in (rules_files.source(step["source"]).get("bookkeeping") or {}).get("targets", {})
        except Exception:  # noqa: BLE001  (missing, oversized or malformed receipts; an unknown source)
            return False

    try:
        steps = load_jobs.load_jobs()
    except Exception:  # noqa: BLE001
        return 99
    return sum(1 for step in steps if not loadable(step))


def audit_failures(env: dict | None = None) -> list[str] | None:
    script = REPO / "skills" / "access-audit" / "scripts" / "access_audit.py"
    if not script.exists():
        return None
    done = subprocess.run([sys.executable, str(script), "--platform", "postgres", "--json"], capture_output=True, text=True, check=False,
                          env={**os.environ, **(env or {})})
    try:
        return sorted(r["id"] for r in json.loads(done.stdout) if r["result"] == "FAIL")
    except ValueError:
        return None


def login_facts(stores: Path) -> dict:
    """Each duty file's login against each database of its duty, by the URL the file names for it: "answers", or the kind of
    failure. A duty file that names no URL for a store database is unreadable, so the gate never opens on a load that would
    stop at its first store call. A driver's error text can hold the address and the password, so only its class is kept."""
    import psycopg2
    sys.path.insert(0, str(HERE))
    import load_jobs
    from edgar_warehouse.database_connections import DATABASES, store_url

    found = {}
    for name in ("owner.env", *DUTY_FILES):
        try:
            env = load_jobs.load_env(stores / name)
            url = load_jobs.data_url(env)
            if url is None:
                raise KeyError("no data database")
            urls = [load_jobs.in_database(url, "postgres")] if name == "owner.env" else [
                store_url(group[0], env).set(drivername="postgresql").render_as_string(hide_password=False)
                for group in DATABASES.values()]
        except Exception as exc:  # noqa: BLE001
            found[name] = f"unreadable ({type(exc).__name__})"
            continue
        state = "answers"
        try:
            for each in urls:
                psycopg2.connect(each, connect_timeout=10).close()
        except Exception as exc:  # noqa: BLE001
            state = f"does not answer ({type(exc).__name__})"
        found[name] = state
    return found


def state_facts(env: dict) -> dict | None:
    """What the scheduler will do with the run's state file: use it (same), start one (fresh) or set it aside, and how many done
    steps it holds, so a surprise is seen before a step runs."""
    import load_jobs
    try:
        url = load_jobs.data_url(env)
        generation = load_jobs.database_generation(url)
        path = load_jobs.LOGS / f"chain-{load_jobs.RUN}.log"
        text = path.read_text() if path.exists() else ""
        return {"verdict": load_jobs.state_verdict(text, load_jobs.store_id(url), generation),
                "done_steps": len(load_jobs.done_steps(path)) if path.exists() else 0}
    except Exception:  # noqa: BLE001
        return None


def mirror_fact(listing=None) -> str:
    """"exact" when the mirror's listing is its record, every table REPLICATING; else what differs, or why it was not read. The
    listing is read as the mirror operator, the one identity that may (a key pair; nothing of its file is printed)."""
    sys.path.insert(0, str(REPO / "skills" / "data-platform" / "scripts" / "exposure"))
    import mirror_sql
    try:
        managed, exposure = mirror_sql.load(mirror_sql.MANAGED), mirror_sql.load(mirror_sql.EXPOSURE)
        rows = (listing or run_as_mirror_operator)(mirror_sql.verify(managed))
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            return "unreadable (the mirror operator could not list the mirror)"
        mirror_sql.readback(managed, exposure, [{k.lower(): v for k, v in row.items()} for row in rows])
    except SnowflakeRefused as refused:
        return f"unreadable (Snowflake error {refused})"
    except SystemExit as refused:
        return str(refused) or "the listing is empty"
    except Exception as exc:  # noqa: BLE001
        return f"unreadable ({type(exc).__name__})"
    return "exact"


class SnowflakeRefused(Exception):
    """The statement was not run: Snowflake's error number only (a driver error's text can name the account), or why it was not tried."""


def run_as_mirror_operator(sql: str) -> list[dict]:
    """One statement run as the mirror operator, through the Snowflake driver the loader image installs (the `mirror` extra), so
    the gate in the worker reads what the gate on the Mac reads. A refusal raises SnowflakeRefused with Snowflake's error number."""
    sys.path.insert(0, str(HERE))
    import load_jobs
    import snowflake.connector
    try:
        env = load_jobs.load_env(MIRROR_OPERATOR)
    except (KeyError, OSError):
        raise SnowflakeRefused("not tried: the mirror operator's login is missing") from None
    try:
        with snowflake.connector.connect(account=env["MIRROR_SNOWFLAKE_ACCOUNT"], user=env["MIRROR_SNOWFLAKE_USER"],
                                         authenticator="SNOWFLAKE_JWT", private_key_file=env["MIRROR_SNOWFLAKE_PRIVATE_KEY_PATH"],
                                         role=env["MIRROR_SNOWFLAKE_ROLE"], warehouse=env["MIRROR_SNOWFLAKE_WAREHOUSE"],
                                         login_timeout=60, query_timeout=120) as connection:
            return connection.cursor(snowflake.connector.DictCursor).execute(sql.strip().rstrip(";")).fetchall()
    except snowflake.connector.Error as exc:
        raise SnowflakeRefused(f"{exc.errno:06d}" if isinstance(exc.errno, int) and exc.errno >= 0 else "without a number") from None


def gather(stores: Path, repo: Path = REPO) -> dict:
    sys.path.insert(0, str(HERE))
    import load_jobs
    env = {**os.environ, **load_jobs.load_env(stores / "worker.env")}
    reader = load_jobs.load_env(stores / "reader.env") if (stores / "reader.env").exists() else {}
    loader, reference, sessions = sql_facts(reader, env)
    usage = shutil.disk_usage(Path.home())
    return {"git": git_facts(repo), "doctor": doctor_ok(stores, env), "loader": loader, "reference": reference,
            "plan_missing": plan_missing(env), "loads_running": loads_running(), "loader_sessions": sessions,
            "disk_gib": usage.free / 2**30, "load1": os.getloadavg()[0], "cores": os.cpu_count() or 1, "audit": audit_failures(reader),
            "logins": login_facts(stores), "state": state_facts(env),
            "registered": registration_facts(reader, env), "mirror": mirror_fact()}


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
    import load_jobs
    results = evaluate(gather(stores))
    for r in results:
        print(f"{'PASS' if r['ok'] else 'FAIL':5} {r['id']:10} {r['title']}\n      evidence: {r['evidence']}")
    env = load_jobs.load_env(stores / "worker.env")
    generation = load_jobs.database_generation(load_jobs.data_url(env)) if load_jobs.data_url(env) else ""
    passed = all(r["ok"] for r in results) and bool(generation)
    try:
        previous = json.loads((stores / READY).read_text())
    except (OSError, ValueError):
        previous = None
    written = next_record(previous, results, generation, current_sha(), now())
    if written is None:
        print("NOT READY: a load is running (QUIET); the passing record for this code and store stands, so the running load goes on")
        return 1
    (stores / READY).write_text(json.dumps(written))
    os.chmod(stores / READY, 0o600)
    print("READY: a load may start" if passed else "NOT READY: nothing starts until every check passes")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
