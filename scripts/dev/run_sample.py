"""Two minutes on a running PostgreSQL job: what limits it, before trusting its speed or letting it run on.

    source <the store's worker.env>
    python scripts/dev/run_sample.py --database MDM_DATABASE_URL --count "select sum(records) from mastering_file"

Prints counts, statement openings and table names only. A long-open transaction keeps deleted rows
from being cleaned, so it is reported first. Swap and an emulated interpreter make any figure unreliable.
"""
import argparse
import collections
import os
import platform
import re
import subprocess
import time

from sqlalchemy import create_engine, text


def swap_outs() -> int:
    found = re.search(r"Swapouts:\s+(\d+)", subprocess.run(["vm_stat"], capture_output=True, text=True).stdout)
    return int(found[1]) if found else 0


def machine() -> dict:
    translated = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True).stdout.strip()
    return {"python": platform.machine(), "emulated": translated == "1"}


def label(query: str, state: str) -> str:
    opening = re.sub(r"\s+", " ", re.sub(r"\(.*", "", query, flags=re.S))[:50]
    return opening if state == "active" else f"client working, after: {opening}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default="MDM_DATABASE_URL", help="The environment variable holding the address")
    parser.add_argument("--count", required=True, help="SQL returning one number that grows as the job works")
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    engine = create_engine(os.environ[args.database], hide_parameters=True, isolation_level="AUTOCOMMIT")
    every = 0.25
    seen = collections.Counter()
    with engine.connect() as conn:
        name = conn.scalar(text("select current_database()"))
        first, swapped, began = conn.scalar(text(args.count)), swap_outs(), time.time()
        for _ in range(int(args.seconds / every)):
            row = conn.execute(text(
                "select coalesce(query,''),state from pg_stat_activity where datname=:n and pid<>pg_backend_pid() "
                "and state<>'idle' and backend_type='client backend' order by state limit 1"), {"n": name}).first()
            seen[label(*row) if row else "nothing open"] += 1
            time.sleep(every)
        last, spent = conn.scalar(text(args.count)), time.time() - began
        oldest = conn.execute(text(
            "select round(extract(epoch from now()-xact_start)),state,left(query,50) from pg_stat_activity "
            "where datname=:n and pid<>pg_backend_pid() and xact_start is not null order by xact_start limit 1"), {"n": name}).first()
        dead = conn.execute(text("select relname,n_live_tup,n_dead_tup from pg_stat_user_tables "
                                 "order by n_dead_tup desc limit 5")).all()
    done = float(last or 0) - float(first or 0)
    print("machine", machine(), "swap-outs a second", round((swap_outs() - swapped) / spent))
    print("oldest open transaction, seconds", tuple(oldest) if oldest else None)
    print("grew by", done, "ms each", round(spent * 1000 / done, 2) if done else None)
    for table, live, gone in dead:
        print(f"dead rows {table}: {gone} of {live + gone}")
    total = sum(seen.values())
    for statement, count in seen.most_common(10):
        print(f"{count / total * 100:5.1f}% {statement}")


if __name__ == "__main__":
    main()
