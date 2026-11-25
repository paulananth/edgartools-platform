#!/usr/bin/env python3
"""Drop and create again the platform's data and control databases on a hosted instance, with the owner and the grants each had.

    set -a; . <stores folder>/owner.env; set +a
    python infra/scripts/reset-hosted-databases.py            # lists sizes and session classes; drops nothing
    python infra/scripts/reset-hosted-databases.py --words "<the operator's exact words>"  # drops and creates them again

Uses the owner login's connection (owner.env, the instance's administrator), which must be able to
create databases. The roles stay (they belong to the instance), so no password changes and no login is rotated.
Each database's owner and CONNECT list are read before it is dropped and put back after, so the runtime, registration
and any read-only logins reach it as before. Refuses while a client session or a session with an open transaction is
connected. Idle PostgreSQL extension workers without a transaction are reported separately and disconnected by the
approved database drop (`WITH (FORCE)`). The config database (rules) is never named, so a reset keeps it.
The stores' schemas come next (docs/runbooks/edgar-intelligence/init.md, "Initialize a hosted store", step 3). Prints names and sizes only.

Dropping needs a sign-off: --words is the operator's exact approval of this drop, and the run refuses without it.
The words, the ET time and what was dropped (names and sizes) are appended to reinit-approvals.log in the stores
folder (the folder of the owner.env that was sourced; STORES_FOLDER names it when it cannot be found).

After the drop, the dropped stores' run files go too: the `load` folder under the BOOKKEEPING_MANIFEST_ROOT that the
stores folder's worker.env names. No store refers to them once Bookkeeping is dropped. The `extracts` folder stays: an
extract is kept by its content and rules, and a load reuses it.
"""
import argparse
import os
import json
import re
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.engine import make_url

# The data database (mdm, rdm, silver) and the control database (bookkeeping, change_journal). The config database (rules) is
# never reset: it says how the data is processed, and a reload needs it.
DATABASES = ("data", "control")
PRIVILEGES = {"C": "CREATE", "T": "TEMPORARY", "c": "CONNECT"}


def grants(acl: list[str], owner: str) -> list[tuple[str, str]]:
    """(grantee, privilege) pairs of an access list other than the owner's own; an empty grantee is PUBLIC."""
    found = []
    for item in acl or []:
        grantee, rest = item.split("=", 1)
        if grantee == owner:
            continue
        for letter in rest.split("/", 1)[0]:
            found.append((grantee or "PUBLIC", PRIVILEGES[letter]))
    return found


def sign_off(path: Path, words: str, dropped: dict, sessions_to_disconnect: dict | None = None) -> None:
    """Append the operator's words, ET time, affected databases and forced idle-worker sessions privately."""
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({
            "at": stamp,
            "words": words,
            "dropped": dropped,
            "sessions_to_disconnect": sessions_to_disconnect or {},
        }) + "\n")
    path.chmod(0o600)


def approvals_log() -> Path:
    folder = os.environ.get("STORES_FOLDER") or Path.home() / ".config" / "edgartools" / "hosted"
    return Path(folder) / "reinit-approvals.log"


def clear_run_files(stores: Path) -> Path | None:
    """Delete the run files of the stores this folder names (`<manifest root>/load`) and say which folder went; None
    when its worker.env names no manifest root or nothing is there."""
    env = stores / "worker.env"
    found = re.search(r"^(?:export\s+)?BOOKKEEPING_MANIFEST_ROOT=(.*)$", env.read_text(), re.M) if env.is_file() else None
    value = shlex.split(found.group(1))[0] if found and found.group(1).strip() else ""
    if not value:
        return None
    folder = Path(value.removeprefix("file://")) / "load"
    if not folder.is_dir():
        return None
    shutil.rmtree(folder)
    return folder


def classify_sessions(sessions) -> tuple[dict[str, int], dict[str, int]]:
    """Return blocking sessions and idle extension workers the approved reset may disconnect."""
    blockers: dict[str, int] = {}
    extension_workers: dict[str, int] = {}
    for database, backend_type, state, xact_start in sessions:
        if backend_type == "pg base extension worker" and state is None and xact_start is None:
            extension_workers[database] = extension_workers.get(database, 0) + 1
        else:
            blockers[database] = blockers.get(database, 0) + 1
    return blockers, extension_workers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--words", help="Drop and create them again: the operator's exact words approving this drop "
                                        "(without it, only list them)")
    args = parser.parse_args()
    if args.words is not None and not args.words.strip():
        print("--words must hold the operator's exact approval.", file=sys.stderr)
        return 2
    from edgar_warehouse.database_connections import instance_url

    try:
        url = instance_url()
    except KeyError as missing:
        print(f"{missing.args[0]} (source the stores folder's owner.env first).", file=sys.stderr)
        return 2
    engine = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    quote = engine.dialect.identifier_preparer.quote
    try:
        with engine.connect() as conn:
            held = {}
            for name in DATABASES:
                row = conn.execute(sa.text(
                    "SELECT pg_get_userbyid(datdba), datacl::text[], pg_size_pretty(pg_database_size(datname)) "
                    "FROM pg_database WHERE datname=:n"), {"n": name}).first()
                if row is None:
                    print(f"{name}: not there; it will be created with the connection login as its owner")
                    held[name] = (conn.scalar(sa.text("SELECT current_user")), [], None)
                    continue
                held[name] = (row[0], row[1], row[2])
                print(f"{name}: {row[2]}, owner {row[0]}, {len(grants(row[1], row[0]))} grants")
            sessions = conn.execute(sa.text(
                "SELECT datname, backend_type, state, xact_start FROM pg_stat_activity "
                "WHERE datname = ANY(:d) AND pid <> pg_backend_pid()"),
                {"d": list(DATABASES)}).all()
            blockers, extension_workers = classify_sessions(sessions)
            for name, count in extension_workers.items():
                print(f"{name}: {count} idle extension worker session(s); an approved reset will disconnect these")
            for name, count in blockers.items():
                print(f"{name}: {count} other session(s) connected")
            if blockers:
                print("Refusing: stop every client session and active transaction before resetting.", file=sys.stderr)
                return 3
            if args.words is None:
                print("Nothing dropped. A drop needs the operator's sign-off: run again with --words \"<their exact words>\".")
                return 0
            sign_off(approvals_log(), args.words.strip(), {n: held[n][2] for n in held}, extension_workers)
            for name, (owner, acl, _) in held.items():
                conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {quote(name)} WITH (FORCE)")
                conn.exec_driver_sql(f"CREATE DATABASE {quote(name)} OWNER {quote(owner)}")
                conn.exec_driver_sql(f"REVOKE ALL ON DATABASE {quote(name)} FROM PUBLIC")
                for grantee, privilege in grants(acl, owner):
                    who = grantee if grantee == "PUBLIC" else quote(grantee)
                    conn.exec_driver_sql(f"GRANT {privilege} ON DATABASE {quote(name)} TO {who}")
                print(f"{name}: created again, {len(grants(acl, owner))} grants put back")
            gone = clear_run_files(approvals_log().parent)
            print(f"Run files of the dropped stores deleted: {gone}" if gone else "No run files to delete")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
