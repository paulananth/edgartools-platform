#!/usr/bin/env python3
"""Count the statements a run sends to a disposable local PostgreSQL server, grouped by shape.

    docker exec <container> psql -U postgres -c "ALTER SYSTEM SET log_statement='all'" \
        -c "ALTER SYSTEM SET log_line_prefix='%m [%p] %d '" -c "select pg_reload_conf()"
    docker logs -f --since 0s <container> > statements.log &     (then run the load, then stop the follow)
    python count_statements.py <container> --log statements.log [--bundles N]

Stream the log to a file: Docker keeps only its last few log files, and a minute of loading can write hundreds of
megabytes of statements, so reading `docker logs` afterwards (`--since`) silently loses the start of the run. With the
database in the prefix, the count is also given per database.

On a hosted store a bundle's time is its statements times the round trip, so the count says what a load costs there before
any hosted run: groups with a count that grows with the bundle's files, liveness checks, transactions that only read, and
sessions opened (each with its setup statements). Prints counts and statement shapes only, never a value.
"""
import argparse
import collections
import re
import subprocess

# The session, then the database and user when the prefix adds them (`%d`, `%u`, in that order), then the statement.
STATEMENT = re.compile(r"\[(\d+)\] (?:([^\s\[\]]+) )?(?:\S+ )?LOG:\s+(?:statement|execute [^:]*):\s*(.*)$")


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


def tally(lines):
    """Statements, sessions, statements by shape, and statements and sessions by database (when the prefix holds it)."""
    counts, sessions, total = collections.Counter(), set(), 0
    databases, sessions_of = collections.Counter(), collections.defaultdict(set)
    for line in lines:
        found = STATEMENT.search(line)
        if found:
            session, database, statement = found.groups()
            total += 1
            sessions.add(session)
            counts[shape(" ".join(statement.split()))] += 1
            if database:
                databases[database] += 1
                sessions_of[database].add(session)
    return total, sessions, counts, databases, sessions_of


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("container")
    parser.add_argument("--since", help="Unix time the load started (a short run; Docker may have dropped older lines)")
    parser.add_argument("--log", help="A log streamed to a file while the load ran (`docker logs -f`)")
    parser.add_argument("--bundles", type=int, default=1, help="Bundles the load finished, to give a count each")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    if args.log:
        lines = open(args.log, errors="replace")
    elif args.since:
        log = subprocess.run(["docker", "logs", "--since", args.since, args.container], capture_output=True, text=True)
        lines = (log.stdout + log.stderr).splitlines()
    else:
        parser.error("give --log or --since")
    total, sessions, counts, databases, sessions_of = tally(lines)
    each = max(args.bundles, 1)
    print(f"{total} statements in {len(sessions)} sessions: {total / each:.0f} statements and {len(sessions) / each:.1f} sessions a bundle")
    for name, count in databases.most_common():
        print(f"{name:>16} {count / each:8.1f} a bundle in {len(sessions_of[name]) / each:.1f} sessions")
    for name, count in counts.most_common(args.top):
        print(f"{count:7d} {count / each:8.1f} a bundle  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
