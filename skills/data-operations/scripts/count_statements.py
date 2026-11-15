#!/usr/bin/env python3
"""Count the statements a run sends to a disposable local PostgreSQL server, grouped by shape.

    docker exec <container> psql -U postgres -c "ALTER SYSTEM SET log_statement='all'" -c "select pg_reload_conf()"
    python count_statements.py <container> --since $(date +%s) [--bundles N]     (run the load in between)

On a hosted store a bundle's time is its statements times the round trip, so the count says what a load costs there before
any hosted run: groups with a count that grows with the bundle's files, liveness checks, transactions that only read, and
sessions opened (each with its setup statements). Prints counts and statement shapes only, never a value.
"""
import argparse
import collections
import re
import subprocess

STATEMENT = re.compile(r"\[(\d+)\] LOG:\s+(?:statement|execute [^:]*):\s*(.*)$")


def shape(text: str) -> str:
    words = text.split()
    if not words:
        return "?"
    head = words[0].upper()
    if head in ("SELECT", "WITH"):
        found = re.search(r"\bfrom\s+([\w.\"]+)", text, re.I)
        return f"SELECT {found.group(1)}" if found else "SELECT (no table)" if text.strip().upper() != "SELECT 1" else "SELECT 1"
    if head in ("INSERT", "UPDATE", "DELETE"):
        found = re.search(r"(?:into|update|from)\s+([\w.\"]+)", text, re.I)
        return f"{head} {found.group(1)}" if found else head
    return head if head in ("BEGIN", "COMMIT", "ROLLBACK", "SET", "SHOW") else " ".join(words[:2]).upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("container")
    parser.add_argument("--since", required=True, help="Unix time the load started")
    parser.add_argument("--bundles", type=int, default=1, help="Bundles the load finished, to give a count each")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    log = subprocess.run(["docker", "logs", "--since", args.since, args.container], capture_output=True, text=True)
    counts, sessions, total = collections.Counter(), set(), 0
    for line in (log.stdout + log.stderr).splitlines():
        found = STATEMENT.search(line)
        if found:
            total += 1
            sessions.add(found.group(1))
            counts[shape(" ".join(found.group(2).split()))] += 1
    each = max(args.bundles, 1)
    print(f"{total} statements in {len(sessions)} sessions: {total / each:.0f} statements and {len(sessions) / each:.0f} sessions a bundle")
    for name, count in counts.most_common(args.top):
        print(f"{count:7d} {count / each:8.1f} a bundle  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
