#!/usr/bin/env python3
"""Read the performance and locks of the hosted PostgreSQL instance as the read-only diagnostic login.

Usage: db_monitor.py summary | locks | sessions [--min-seconds N] | statements [--top N] [--by total|mean|calls]
                     | tables [--top N] | all      (each takes --database NAME and --json)

The login is DIAGNOSE_DATABASE_URL (the stores folder's reader.env): a member of pg_monitor, never the owner or a runtime
login. Every connection is a read-only session with a statement timeout; the script refuses a superuser. It prints no
address, and shows a statement with its literals replaced, cut short, so no value from the data reaches the terminal.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SQL = {
    "summary": """
        select count(*) as connections,
               (select setting::int from pg_settings where name = 'max_connections') as max_connections,
               count(*) filter (where state = 'active') as active,
               count(*) filter (where state like 'idle in transaction%') as idle_in_transaction,
               count(*) filter (where wait_event_type = 'Lock') as waiting_on_locks,
               coalesce(round(max(extract(epoch from now() - xact_start))), 0) as longest_transaction_s,
               coalesce(round(max(extract(epoch from now() - state_change))
                              filter (where state like 'idle in transaction%')), 0) as longest_idle_in_transaction_s
        from pg_stat_activity where datname is not null""",
    "locks": """
        select blocked.pid as waiting_pid, blocked.datname as database, blocked.usename as login,
               round(extract(epoch from now() - blocked.state_change)) as waited_s,
               coalesce(l.locktype, '') as lock_kind, coalesce(l.mode, '') as lock_mode,
               coalesce(l.relation::regclass::text, '') as relation,
               b.pid as blocker_pid, b.usename as blocker_login, coalesce(b.state, '') as blocker_state,
               round(extract(epoch from now() - b.xact_start)) as blocker_transaction_s,
               blocked.query as waiting_query, b.query as blocker_query
        from pg_stat_activity blocked
        cross join lateral unnest(pg_blocking_pids(blocked.pid)) as blocker(pid)
        join pg_stat_activity b on b.pid = blocker.pid
        left join pg_locks l on l.pid = blocked.pid and not l.granted
        where cardinality(pg_blocking_pids(blocked.pid)) > 0
        order by waited_s desc""",
    "sessions": """
        select pid, datname as database, usename as login, state, coalesce(wait_event_type, '') as wait_kind,
               coalesce(wait_event, '') as wait_event, round(extract(epoch from now() - xact_start)) as transaction_s,
               round(extract(epoch from now() - query_start)) as statement_s, query
        from pg_stat_activity
        where datname is not null and pid <> pg_backend_pid() and state <> 'idle'
              and now() - coalesce(xact_start, query_start) >= make_interval(secs => %(min_seconds)s)
        order by transaction_s desc nulls last""",
    "statements": """
        select calls, round(total_exec_time::numeric / 1000, 1) as total_s, round(mean_exec_time::numeric, 1) as mean_ms,
               round(max_exec_time::numeric, 1) as max_ms, rows, shared_blks_read as blocks_read,
               shared_blks_hit as blocks_hit, query
        from pg_stat_statements where dbid = (select oid from pg_database where datname = current_database())
        order by {order} desc limit %(top)s""",
    "tables": """
        select schemaname || '.' || relname as table, n_live_tup as live, n_dead_tup as dead, seq_scan, idx_scan,
               n_tup_ins as inserted, n_tup_upd as updated, n_tup_del as deleted,
               coalesce(to_char(last_autovacuum, 'YYYY-MM-DD HH24:MI'), '') as last_autovacuum
        from pg_stat_user_tables order by n_dead_tup desc, seq_scan desc limit %(top)s""",
}
ORDER = {"total": "total_exec_time", "mean": "mean_exec_time", "calls": "calls"}
STATEMENT_COLUMNS = ("query", "waiting_query", "blocker_query")


def plain(text: str | None, width: int = 70) -> str:
    """A statement with its literals replaced and cut short."""
    text = re.sub(r"'(?:[^']|'')*'", "?", text or "")
    text = re.sub(r"\b\d+(?:\.\d+)?\b", "?", text)
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def url(database: str | None) -> str:
    value = os.environ.get("DIAGNOSE_DATABASE_URL")
    if not value:
        sys.exit("DIAGNOSE_DATABASE_URL is not set: source the stores folder's reader.env (it is never printed)")
    value = value.replace("postgresql+psycopg2", "postgresql")
    return re.sub(r"/[^/?]+((?:\?.*)?)$", rf"/{database}\1", value) if database else value


def connect(database: str | None = None):
    import psycopg2

    try:
        conn = psycopg2.connect(url(database), connect_timeout=10, options="-c statement_timeout=15000")
    except psycopg2.Error:  # a driver error can quote the address
        sys.exit("cannot connect as the diagnostic login (check reader.env and the database name)")
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("select rolsuper from pg_roles where rolname = current_user")
        if cur.fetchone()[0]:
            sys.exit("the diagnostic login is a superuser: monitoring uses a read-only login (pg_monitor) only")
    return conn


def rows(conn, name: str, **params) -> list[dict]:
    sql = SQL[name].replace("{order}", ORDER[params.pop("by", "total")]) if name == "statements" else SQL[name]
    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        names = [column.name for column in cur.description]
        found = [dict(zip(names, record)) for record in cur.fetchall()]
    for record in found:
        for column in STATEMENT_COLUMNS:
            if column in record:
                record[column] = plain(record[column])
    return found


def show(title: str, found: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps({title: found}, default=str))
        return
    print(f"== {title} ({len(found)})")
    for record in found:
        print("  " + "  ".join(f"{key}={value}" for key, value in record.items() if value not in ("", None)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["summary", "locks", "sessions", "statements", "tables", "all"])
    parser.add_argument("--database", help="a database of the instance (the statements and tables are per database)")
    parser.add_argument("--min-seconds", type=int, default=30, help="sessions: only those running at least this long")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--by", choices=sorted(ORDER), default="total", help="statements: order")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    conn = connect(args.database)
    try:
        wanted = ["summary", "locks", "sessions", "statements", "tables"] if args.command == "all" else [args.command]
        for name in wanted:
            show(name, rows(conn, name, **{"summary": {}, "locks": {}, "sessions": {"min_seconds": args.min_seconds},
                                           "statements": {"top": args.top, "by": args.by}, "tables": {"top": args.top}}[name]),
                 args.json)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
