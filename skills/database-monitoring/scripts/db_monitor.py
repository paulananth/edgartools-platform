#!/usr/bin/env python3
"""Read the performance and locks of the hosted PostgreSQL instance as the read-only diagnostic login.

Usage: db_monitor.py summary | locks | sessions [--min-seconds N] | statements [--top N] [--by total|mean|calls]
                     | tables [--top N] | memory | databases | logs [--minutes N] | all   (--database NAME, --json)

The login is DIAGNOSE_DATABASE_URL (the stores folder's reader.env): a member of pg_monitor, never the owner or a runtime
login. Every connection is a read-only session with a statement timeout; the script refuses a superuser. It prints no
address, and shows a statement with its literals replaced, cut short, so no value from the data reaches the terminal.

`logs` reads the instance's PostgreSQL server log from the account's event table through a SnowCLI connection named by
MONITOR_SNOWFLAKE_CONNECTION, whose role can only read that table; it refuses an administrator role. It keeps the lines
that carry a level (PANIC, FATAL, ERROR, WARNING) and the memory and kill lines, and drops the DETAIL, STATEMENT and
CONTEXT lines, which quote values from the data. Addresses and literals are replaced.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
SQL["memory"] = """
    select (select setting::bigint from pg_settings where name = 'work_mem') / 1024 as work_mem_mb,
           (select setting::bigint from pg_settings where name = 'maintenance_work_mem') / 1024 as maintenance_work_mem_mb,
           (select setting::bigint * 8 from pg_settings where name = 'shared_buffers') / 1024 as shared_buffers_mb,
           (select setting::int from pg_settings where name = 'max_connections') as max_connections,
           count(*) as connections, count(*) filter (where state = 'active') as active,
           round((select setting::bigint from pg_settings where name = 'work_mem') / 1024.0
                 * count(*) filter (where state = 'active')) as work_mem_if_each_active_sorts_once_mb
    from pg_stat_activity where datname is not null"""
SQL["databases"] = """
    select datname as database, numbackends as sessions, xact_commit as commits, xact_rollback as rollbacks, deadlocks,
           temp_files, round(temp_bytes / 1048576.0) as temp_mb, conflicts, blks_read as blocks_read, blks_hit as blocks_hit
    from pg_stat_database where datname is not null order by temp_bytes desc"""
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


ADMIN_ROLES = {"ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "USERADMIN", "ORGADMIN"}
LEVEL = r"(PANIC|FATAL|ERROR|WARNING):  "
MEMORY = ("out of memory", "could not resize shared memory", "terminated by signal 9", "invalid memory alloc request",
          "cannot allocate memory", "could not fork new process", "remaining connection slots are reserved",
          "too many clients")
LOG_SQL = """
    with l as (select timestamp as t, value:MESSAGE::string as m from SNOWFLAKE.TELEMETRY.EVENTS
               where resource_attributes['snowflake.o11y.logtype'] = 'postgres-otelcol-vm-agent'
                 and resource_attributes['instance.id'] = '{instance}' and record_type = 'LOG'
                 and timestamp > current_timestamp() - interval '{minutes} minutes'
                 and regexp_like(m, '.*{level}.*|{memory}')),
    k as (select t, m, case when {is_memory} then 'memory' else lower(regexp_substr(m, '{level_word}')) end as kind from l)
    select kind, left(coalesce(regexp_substr(m, '{level}.{{0,110}}'), regexp_substr(m, '.{{0,110}}')), 140) as message,
           count(*) as n, min(t)::string as first_at, max(t)::string as last_at
    from k group by 1, 2 order by (kind = 'memory') desc, n desc limit {top}"""


def scrub(text: str | None) -> str:
    """A log message without addresses, quoted literals or the values of a key."""
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<ip>", text or "")
    text = re.sub(r"'(?:[^']|'')*'", "?", text)
    text = re.sub(r"\(([^()]*)\)=\(([^()]*)\)", "(?)=(?)", text)
    return " ".join(text.split())


def instance_id() -> str:
    """The instance's id: the first part of the diagnostic login's host name. Never printed."""
    found = re.search(r"@([a-z0-9]+)[.:/]", os.environ.get("DIAGNOSE_DATABASE_URL", ""))
    if not found:
        sys.exit("DIAGNOSE_DATABASE_URL does not name an instance: source the stores folder's reader.env")
    return found.group(1)


def snow(connection: str, sql: str) -> list[dict]:
    done = subprocess.run(["snow", "sql", "-c", connection, "--format", "json", "-q", sql], capture_output=True, text=True,
                          check=False)
    if done.returncode:  # its message can quote the account
        sys.exit("the Snowflake read failed (check MONITOR_SNOWFLAKE_CONNECTION and its role)")
    return json.loads(done.stdout or "[]")


def logs(minutes: int, top: int = 20) -> list[dict]:
    connection = os.environ.get("MONITOR_SNOWFLAKE_CONNECTION")
    if not connection:
        sys.exit("MONITOR_SNOWFLAKE_CONNECTION is not set: name the SnowCLI connection whose role reads only the event table")
    role = snow(connection, "select current_role() as role")[0]["ROLE"]
    if role.upper() in ADMIN_ROLES:
        sys.exit("the connection runs as an administrator role: use the read-only log role (see the skill, Postgres logs)")
    sql = LOG_SQL.format(instance=instance_id(), minutes=int(minutes), top=int(top), level=LEVEL,
                         level_word="(PANIC|FATAL|ERROR|WARNING)", memory="|".join(f".*{p}.*" for p in MEMORY),
                         is_memory=" or ".join(f"m ilike '%{p}%'" for p in MEMORY))
    return [{"kind": r["KIND"], "message": scrub(r["MESSAGE"]), "n": r["N"], "first_at": r["FIRST_AT"], "last_at": r["LAST_AT"]}
            for r in snow(connection, sql)]


def show(title: str, found: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps({title: found}, default=str))
        return
    print(f"== {title} ({len(found)})")
    for record in found:
        print("  " + "  ".join(f"{key}={value}" for key, value in record.items() if value not in ("", None)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["summary", "locks", "sessions", "statements", "tables", "memory", "databases", "logs", "all"])
    parser.add_argument("--database", help="a database of the instance (the statements and tables are per database)")
    parser.add_argument("--min-seconds", type=int, default=30, help="sessions: only those running at least this long")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--by", choices=sorted(ORDER), default="total", help="statements: order")
    parser.add_argument("--minutes", type=int, default=60, help="logs: how far back to read")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    conn = connect(args.database)
    options = {"sessions": {"min_seconds": args.min_seconds}, "statements": {"top": args.top, "by": args.by},
               "tables": {"top": args.top}}
    try:
        wanted = (["summary", "locks", "sessions", "memory", "databases", "statements", "tables"]
                  if args.command == "all" else [args.command])
        for name in wanted:
            if name != "logs":
                show(name, rows(conn, name, **options.get(name, {})), args.json)
        if args.command == "logs" or (args.command == "all" and os.environ.get("MONITOR_SNOWFLAKE_CONNECTION")):
            show("logs", logs(args.minutes), args.json)
        elif args.command == "all":
            print("== logs: not read (MONITOR_SNOWFLAKE_CONNECTION is not set)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
