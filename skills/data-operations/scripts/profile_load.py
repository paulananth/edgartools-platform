#!/usr/bin/env python3
"""How far is a load, and where did its time go? Read-only views, for any source, with no knowledge of the source.

progress  Units per step and state of the running runs (or one run), and how long they have run
          (BOOKKEEPING_DATABASE_URL).
failures  Units that hold an error, grouped by step, state and error shape, with counts
          (BOOKKEEPING_DATABASE_URL).
quality   The data quality counts each merge run retained: records, records set aside by a failed check,
          open reviews and the fields that have empty values (MDM_DATABASE_URL).
steps   Time per step of one Bookkeeping run, from its journal (BOOKKEEPING_DATABASE_URL).
sample  What the database was running, once a second: statements ranked by seconds seen, so the
        dominating statement shows (PROFILE_DATABASE_URL, a login that may read pg_stat_activity).

Counts, times and normalized statement shapes only: no value from the data is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

STEPS = text("""
    SELECT step, count(*) AS events, min(created_at) AS first, max(created_at) AS last
    FROM bookkeeping.journal_outbox WHERE run_id = :run GROUP BY step ORDER BY min(created_at)""")
LATEST = text("""
    SELECT run_id FROM bookkeeping.pipeline_run WHERE state = 'complete' AND expected_count = coalesce(CAST(:size AS BIGINT), expected_count)
    ORDER BY created_at DESC LIMIT 1""")
PROGRESS = text("""
    SELECT w.step, min(w.ordinal) AS position, w.state, count(*) AS units
    FROM bookkeeping.work_item w JOIN bookkeeping.pipeline_run r USING (run_id)
    WHERE CASE WHEN :run IS NULL THEN r.state = 'running' ELSE r.run_id = CAST(:run AS uuid) END
    GROUP BY w.step, w.state""")
RUNNING_SINCE = text("""
    SELECT count(*), min(created_at), now() FROM bookkeeping.pipeline_run
    WHERE CASE WHEN :run IS NULL THEN state = 'running' ELSE run_id = CAST(:run AS uuid) END""")
FAILURES = text("""
    SELECT w.step, w.state, w.error, count(*) AS units
    FROM bookkeeping.work_item w JOIN bookkeeping.pipeline_run r USING (run_id)
    WHERE w.error IS NOT NULL
      AND CASE WHEN :run IS NULL THEN r.state = 'running' ELSE r.run_id = CAST(:run AS uuid) END
    GROUP BY w.step, w.state, w.error""")
REPORTS = text("""
    SELECT convert_from(id_bytes, 'UTF8') AS run, recorded_at, convert_from(body, 'UTF8') AS report
    FROM public.mdm_store_metadata WHERE type_bytes = convert_to('run_report', 'UTF8')
    ORDER BY recorded_at DESC LIMIT :limit""")
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


def progress_table(rows) -> list[tuple[str, int, dict, float]]:
    """(step, units, units per state, share verified), in the order the steps run."""
    steps: dict[str, dict] = {}
    for step, position, state, units in rows:
        entry = steps.setdefault(step, {"position": position, "states": {}})
        entry["position"] = min(entry["position"], position)
        entry["states"][state] = entry["states"].get(state, 0) + units
    table = []
    for step, entry in sorted(steps.items(), key=lambda item: (item[1]["position"], item[0])):
        total = sum(entry["states"].values())
        table.append((step, total, entry["states"], entry["states"].get("verified", 0) / total))
    return table


def quality_rows(reports) -> list[dict]:
    """One row per source of each retained run report: its counts and the fields that have empty values."""
    rows = []
    for run, recorded_at, report in reports:
        body = json.loads(report)
        when = datetime.fromtimestamp(recorded_at / 1_000_000, ZoneInfo("America/New_York"))
        for source, counts in sorted((body.get("checks") or {}).items()):
            rows.append({
                "run": run[:8], "at": when.strftime("%Y-%m-%d %H:%M"), "source": source,
                "records": counts.get("records"), "set_aside": counts.get("set_aside"),
                "reviews": body.get("unresolved_reviews"), "complete": body.get("end_to_end_complete"),
                "empty": {field: rate for field, rate in sorted((counts.get("empty_rate") or {}).items()) if rate}})
    return rows


def quality(url: str, limit: int) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = quality_rows(conn.execute(REPORTS, {"limit": limit}).all())
    if not rows:
        print("No run report retained")
    for row in rows:
        empty = ", ".join(f"{field} {100 * rate:.1f}%" for field, rate in row["empty"].items()) or "none"
        print(f"{row['at']} {row['run']} {row['source']:<22} records {row['records']} set aside {row['set_aside']} "
              f"open reviews {row['reviews']} complete {row['complete']}  empty: {empty}")


def failure_table(rows) -> list[tuple[str, str, str, int]]:
    """(step, state, error shape, units), the most units first. The error text is reduced to its shape."""
    counts: Counter = Counter()
    for step, state, error, units in rows:
        counts[(step, state, shape(error))] += units
    return [(step, state, error, units) for (step, state, error), units in
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def failures(url: str, run: str | None) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        table = failure_table(conn.execute(FAILURES, {"run": run}).all())
    if not table:
        print("No unit holds an error")
    for step, state, error, units in table:
        print(f"{units:>6} units  {step:<22}{state:<10}{error}")


def progress(url: str, run: str | None) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        runs, since, now = conn.execute(RUNNING_SINCE, {"run": run}).one()
        table = progress_table(conn.execute(PROGRESS, {"run": run}).all())
    if not runs:
        sys.exit("No running run found")
    print(f"{runs} run(s), running for {(now - since).total_seconds() / 60:.0f} min")
    for step, units, states, share in table:
        detail = ", ".join(f"{state} {count}" for state, count in sorted(states.items()) if state != "verified")
        print(f"{step:<14}{units:>7} units {100 * share:>6.1f}% verified   {detail}")


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
    zero = sub.add_parser("progress")
    zero.add_argument("--run", help="a run id (default: every running run)")
    good = sub.add_parser("quality")
    good.add_argument("--limit", type=int, default=10, help="how many of the latest run reports")
    bad = sub.add_parser("failures")
    bad.add_argument("--run", help="a run id (default: every running run)")
    one = sub.add_parser("steps")
    one.add_argument("--run", help="a run id (default: the latest complete run)")
    one.add_argument("--size", type=int, help="with no run: the latest complete run of this many units")
    two = sub.add_parser("sample")
    two.add_argument("--seconds", type=int, default=120)
    two.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    if args.view == "progress":
        progress(os.environ["BOOKKEEPING_DATABASE_URL"], args.run)
    elif args.view == "quality":
        quality(os.environ["MDM_DATABASE_URL"], args.limit)
    elif args.view == "failures":
        failures(os.environ["BOOKKEEPING_DATABASE_URL"], args.run)
    elif args.view == "steps":
        steps(os.environ["BOOKKEEPING_DATABASE_URL"], args.run, args.size)
    else:
        sample(os.environ["PROFILE_DATABASE_URL"], args.seconds, args.top)


if __name__ == "__main__":
    main()
