#!/usr/bin/env python3
"""Where did a load's time go? Two read-only views, for any source, with no knowledge of the source.

steps   Time per step of one Bookkeeping run, from its journal (BOOKKEEPING_DATABASE_URL).
sample  What the database was running, once a second: statements ranked by seconds seen, so the
        dominating statement shows (PROFILE_DATABASE_URL, a login that may read pg_stat_activity).

Counts, times and normalized statement shapes only: no value from the data is printed.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter

from sqlalchemy import create_engine, text

STEPS = text("""
    SELECT step, count(*) AS events, min(created_at) AS first, max(created_at) AS last
    FROM bookkeeping.journal_outbox WHERE run_id = :run GROUP BY step ORDER BY min(created_at)""")
LATEST = text("""
    SELECT run_id FROM bookkeeping.pipeline_run WHERE state = 'complete' AND expected_count = coalesce(CAST(:size AS BIGINT), expected_count)
    ORDER BY created_at DESC LIMIT 1""")
ACTIVE = text("""
    SELECT datname, query FROM pg_stat_activity
    WHERE state = 'active' AND pid <> pg_backend_pid() AND datname IS NOT NULL""")


def shape(query: str, width: int = 120) -> str:
    """A statement without its values: literals, identifiers of rows and numbers become placeholders."""
    query = re.sub(r"'(?:[^']|'')*'", "S", query)
    query = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b", "UUID", query)
    query = re.sub(r"\b\d+(?:\.\d+)?\b", "N", query)
    return re.sub(r"\s+", " ", query).strip()[:width]


def rank(seen: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
    """(database, statement shape, seconds seen), longest first. One sample is one second."""
    counts = Counter((database, shape(query)) for database, query in seen)
    return [(database, statement, seconds) for (database, statement), seconds in counts.most_common()]


def step_table(rows) -> list[tuple[str, int, float]]:
    """(step, events, seconds), in the order the steps began. A step's time runs from the last event of the step
    before it (the first step: from its own first event) to its own last event, so a one-event step is not zero."""
    table, before = [], None
    for step, events, first, last in rows:
        table.append((step, events, (last - (before if before is not None else first)).total_seconds()))
        before = max(before, last) if before is not None else last
    return table


def steps(url: str, run: str | None, size: int | None) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        run = run or conn.execute(LATEST, {"size": size}).scalar()
        if run is None:
            sys.exit("No complete run found")
        table = step_table(conn.execute(STEPS, {"run": run}).all())
    total = sum(seconds for _, _, seconds in table) or 1
    for step, events, seconds in table:
        print(f"{step:<14}{events:>8} events {seconds:>9.1f} s {100 * seconds / total:>5.1f}%")


def sample(url: str, seconds: int, top: int) -> None:
    engine = create_engine(url)
    seen: list[tuple[str, str]] = []
    deadline = time.monotonic() + seconds
    with engine.connect() as conn:
        while time.monotonic() < deadline:
            seen += [tuple(row) for row in conn.execute(ACTIVE)]
            conn.rollback()
            time.sleep(1)
    for database, statement, count in rank(seen)[:top]:
        print(f"{count:>5} s  {database:<14} {statement}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="view", required=True)
    one = sub.add_parser("steps")
    one.add_argument("--run", help="a run id (default: the latest complete run)")
    one.add_argument("--size", type=int, help="with no run: the latest complete run of this many units")
    two = sub.add_parser("sample")
    two.add_argument("--seconds", type=int, default=120)
    two.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    if args.view == "steps":
        steps(os.environ["BOOKKEEPING_DATABASE_URL"], args.run, args.size)
    else:
        sample(os.environ["PROFILE_DATABASE_URL"], args.seconds, args.top)


if __name__ == "__main__":
    main()
