#!/usr/bin/env python3
"""Read the performance and locks of the hosted PostgreSQL instance as the read-only diagnostic login.

Usage: db_monitor.py summary | locks | sessions [--min-seconds N] | statements [--top N] [--by total|mean|calls]
                     | tables [--top N] | memory | databases | logs [--minutes N] | telemetry [--minutes N] [--every N]
                     | upload | all   (--database NAME, --json)

The login is the stores folder's reader.env: a member of pg_monitor, never the owner or a runtime
login. Every connection is a read-only session with a statement timeout; the script refuses a superuser. It prints no
address, and shows a statement with its literals replaced, cut short, so no value from the data reaches the terminal.

`logs` reads the instance's PostgreSQL server log from the account's event table through a SnowCLI connection named by
MONITOR_SNOWFLAKE_CONNECTION, whose role can only read that table; it refuses an administrator role. It keeps the lines
that carry a level (PANIC, FATAL, ERROR, WARNING) and the memory and kill lines, and drops the DETAIL, STATEMENT and
CONTEXT lines, which quote values from the data. Addresses and literals are replaced.

`telemetry` reads the instance's own metrics from the same event table and connection: its machine type, and for each
`--every` minutes its CPU by state, the bytes it received and sent (eth0), the transactions waiting on locks and the
connections. `upload` times one connection of the diagnostic login: its round trip, a download, and `select length(%s)` of
4 MB sent up to eight times, none started after 60 s, so the sustained upload rate shows beside the first burst. The statement
timeout starts once a statement has arrived, so it never bounds a send: a send in flight runs to its end. A send over the
server's `log_min_duration_statement` (2 s) is written to its log with its text: 4 MB of `x`, no value from the data.
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
    "size": """
        select round(sum(pg_database_size(datname)) / 1048576) as size_mb,
               (select coalesce(round(sum(temp_bytes) / 1048576), 0) from pg_stat_database) as temp_mb
        from pg_database where not datistemplate""",
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
    """The reader file's login on the database asked for (`data`, `control`, `config`), else the `postgres` one."""
    from edgar_warehouse.database_connections import instance_url

    try:
        value = instance_url(database=database or "postgres")
    except KeyError as missing:
        sys.exit(f"{missing.args[0]} (source the stores folder's reader.env)")
    return value.set(drivername="postgresql").render_as_string(hide_password=False)


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
    with l as (select timestamp as t, value:MESSAGE::string as m from SNOWFLAKE.TELEMETRY.EVENTS_VIEW
               where resource_attributes['snowflake.o11y.logtype'] = 'postgres-otelcol-vm-agent'
                 and resource_attributes['instance.id'] = '{instance}' and record_type = 'LOG'
                 and timestamp > dateadd(minute, -{minutes}, sysdate())
                 and regexp_like(m, '.*{level}.*|{memory}')),
    k as (select t, m, case when {is_memory} then 'memory' else lower(regexp_substr(m, '{level_word}')) end as kind from l)
    select kind, left(coalesce(regexp_substr(m, '{level}.{{0,110}}'), regexp_substr(m, '.{{0,110}}')), 140) as message,
           count(*) as n, min(t)::string as first_at, max(t)::string as last_at
    from k group by 1, 2 order by (kind = 'memory') desc, n desc limit {top}"""


TELEMETRY_SQL = """
    with m as (select timestamp as t, record:metric:name::string as name,
                      coalesce(record_attributes:state::string, record_attributes:direction::string) as k,
                      record_attributes:cpu::string as cpu, record_attributes:device::string as dev, value::float as v
               from SNOWFLAKE.TELEMETRY.EVENTS_VIEW
               where record_type = 'METRIC' and resource_attributes['instance_id'] = '{instance}'
                 and timestamp > dateadd(minute, -{minutes}, sysdate())
                 and record:metric:name::string in ('system.cpu.time', 'system.network.io', 'postgres_locked_transactions',
                                                    'postgres_connections')),
    d as (select *, v - lag(v) over (partition by name, k, cpu, dev order by t) as delta from m
          where dev is null or dev = 'eth0')
    select to_char(convert_timezone('UTC', 'America/New_York', time_slice(t::timestamp_ntz, {every}, 'MINUTE')), 'MM-DD HH24:MI') as at,
           name, iff(name in ('system.cpu.time', 'system.network.io'), k, null) as key,
           sum(iff(name in ('system.cpu.time', 'system.network.io') and delta >= 0, delta, null)) as total,
           avg(iff(name like 'postgres%', v, null)) as mean, max(iff(name like 'postgres%', v, null)) as top,
           count(distinct cpu) as cpus
    from d group by 1, 2, 3 order by 1"""
MACHINE_SQL = """
    select resource_attributes['host.type']::string as machine, resource_attributes['cloud.region']::string as region
    from SNOWFLAKE.TELEMETRY.EVENTS_VIEW
    where record_type = 'METRIC' and resource_attributes['instance_id'] = '{instance}'
      and timestamp > dateadd(minute, -{minutes}, sysdate())
    group by 1, 2"""


CPU_STATES = ("user", "system", "wait", "steal", "idle")  # shown first, in this order; any other state after them


def telemetry_rows(raw: list[dict], every: int) -> list[dict]:
    """One row an interval: CPU by state as a share of the CPU seconds the interval's readings cover, the bytes received and sent
    as KB a second of those seconds, the mean transactions waiting on locks and the most connections. The first and last
    intervals of a window are partly read, so each is measured by what its readings cover, not by `every`. A counter's delta
    that goes back (a restart) is dropped."""
    covered: dict[str, tuple[float, int]] = {}
    for r in raw:
        if r["NAME"] == "system.cpu.time" and r["TOTAL"] is not None:
            total, cpus = covered.get(r["AT"], (0.0, 1))
            covered[r["AT"]] = (total + r["TOTAL"], max(cpus, r["CPUS"] or 1))
    found = {}
    for r in raw:
        row = found.setdefault(r["AT"], {"at_et": r["AT"]})
        cpu_seconds, cpus = covered.get(r["AT"], (every * 60.0, 1))
        seconds = cpu_seconds / cpus or every * 60.0
        if r["NAME"] == "system.cpu.time" and r["TOTAL"] is not None:
            row[f"cpu_{r['KEY']}_pct"] = round(100 * r["TOTAL"] / cpu_seconds, 1) if cpu_seconds else None
        elif r["NAME"] == "system.network.io" and r["TOTAL"] is not None:
            row[f"{r['KEY']}_kb_s"] = round(r["TOTAL"] / seconds / 1024, 1)
        elif r["NAME"] == "postgres_locked_transactions":
            row["waiting_on_locks_mean"] = r["MEAN"]
        elif r["NAME"] == "postgres_connections":
            row["connections_top"] = r["TOP"]
    order = ["at_et", *(f"cpu_{state}_pct" for state in CPU_STATES), "receive_kb_s", "transmit_kb_s", "waiting_on_locks_mean",
             "connections_top"]
    return [{key: row[key] for key in sorted(row, key=lambda k: order.index(k) if k in order else len(order))}
            for row in found.values()]


def log_connection() -> str:
    """The SnowCLI connection whose role reads only the event table; an administrator role is refused."""
    connection = os.environ.get("MONITOR_SNOWFLAKE_CONNECTION")
    if not connection:
        sys.exit("MONITOR_SNOWFLAKE_CONNECTION is not set: name the SnowCLI connection whose role reads only the event table")
    role = snow(connection, "select current_role() as role")[0]["ROLE"]
    if role.upper() in ADMIN_ROLES:
        sys.exit("the connection runs as an administrator role: use the read-only log role (see the skill, Postgres logs)")
    return connection


def telemetry(minutes: int, every: int) -> list[dict]:
    connection, instance = log_connection(), instance_id()
    machines = snow(connection, MACHINE_SQL.format(instance=instance, minutes=int(minutes)))
    rows_ = telemetry_rows(snow(connection, TELEMETRY_SQL.format(instance=instance, minutes=int(minutes), every=int(every))),
                           int(every))
    return [{"machine": m["MACHINE"], "region": m["REGION"]} for m in machines] + rows_


def upload(cursor, clock=None, sends: int = 8, mb: int = 4, seconds: float = 60.0) -> dict:
    """One connection's round trip (median of ten `select 1`), a download of `mb` MB, and up to `sends` uploads of `mb` MB each,
    in MB a second. No send starts once the uploads have taken `seconds`; one that fails ends them, and those before it show."""
    import time

    clock = clock or time.perf_counter
    trips = []
    for _ in range(10):
        began = clock()
        cursor.execute("select 1")
        cursor.fetchone()
        trips.append((clock() - began) * 1000)
    found = {"round_trip_ms": round(sorted(trips)[len(trips) // 2], 1)}
    began = clock()
    try:
        cursor.execute("select repeat('x', 1024) from generate_series(1, %s)", [mb * 1024])
        got = sum(len(row[0]) for row in cursor.fetchall())
        found["download_mb_s"] = round(got / 2**20 / (clock() - began), 2)
    except Exception as stopped:  # its message names no value: the rows are only `x`
        found["download_stopped"] = type(stopped).__name__
    payload, rates, spent = "x" * (mb * 2**20), [], 0.0
    for sent in range(1, sends + 1):
        if spent >= seconds:
            found["upload_stopped"] = f"{sent - 1} sends took {spent:.0f} s: no more were started"
            break
        began = clock()
        try:
            cursor.execute("select length(%s)", [payload])
            cursor.fetchone()
        except Exception as stopped:  # its message names no value: the payload is only `x`
            found["upload_stopped"] = (f"the statement timeout ended send {sent}" if "timeout" in str(stopped).lower()
                                       else f"send {sent} failed: {type(stopped).__name__}")
            break
        took = clock() - began
        spent += took
        rates.append(round(mb / took, 2))
    found["upload_mb_s"] = rates
    found["upload_mb_s_overall"] = round(mb * len(rates) / spent, 2) if spent else None
    return found


def scrub(text: str | None) -> str:
    """A log message without addresses, quoted literals or the values of a key."""
    text = re.sub(r"remote host: \S*", "remote host: <ip>", text or "")  # a line cut short can leave half an address
    text = re.sub(r"\b\d{1,3}(?:\.\d{0,3}){1,3}\b", "<ip>", text)
    text = re.sub(r"'(?:[^']|'')*'", "?", text)
    text = re.sub(r"\(([^()]*)\)=\(([^()]*)\)", "(?)=(?)", text)
    return " ".join(text.split())


def instance_id() -> str:
    """The instance's id: the first part of the diagnostic login's host name. Never printed."""
    host = (url(None).split("@", 1) + [""])[1]
    found = re.match(r"([a-z0-9]+)[.:/]", host)
    if not found:
        sys.exit("the reader file names no instance: source the stores folder's reader.env")
    return found.group(1)


def snow(connection: str, sql: str) -> list[dict]:
    done = subprocess.run(["snow", "sql", "-c", connection, "--format", "json", "-q", sql], capture_output=True, text=True,
                          check=False)
    if done.returncode:  # its message can quote the account
        sys.exit("the Snowflake read failed (check MONITOR_SNOWFLAKE_CONNECTION and its role)")
    return json.loads(done.stdout or "[]")


def logs(minutes: int, top: int = 20) -> list[dict]:
    connection = log_connection()
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


def breaches(now: dict, limits: dict, spent: float | None) -> list[str]:
    """What a reading says is over a limit, in plain words; a limit left out is not checked."""
    found = []
    if limits.get("connections_pct") and now["max_connections"] and \
            100 * now["connections"] / now["max_connections"] >= limits["connections_pct"]:
        found.append(f"connections {now['connections']} of {now['max_connections']}")
    for key, label in (("longest_transaction_s", "longest transaction"), ("longest_idle_in_transaction_s", "idle in transaction"),
                       ("size_mb", "stores' size MB"), ("temp_mb", "spilled MB since start"), ("waiting_on_locks", "waiting on locks")):
        if limits.get(key) and now[key] >= limits[key]:
            found.append(f"{label} {now[key]} (limit {limits[key]})")
    if limits.get("budget") and spent is not None and spent >= limits["budget"]:
        found.append(f"estimated spend {spent:.2f} (budget {limits['budget']})")
    return found


def budget(conn, history: str, limits: dict, rate: float | None) -> list[str]:
    """A poor man's resource monitor: one reading of the pressure and size, one line appended to a local history,
    and the limits it is over. The clock is the history's first line, so spend is the hours since then times --rate."""
    from datetime import datetime, timezone
    from pathlib import Path

    now = {**rows(conn, "summary")[0], **rows(conn, "size")[0]}
    now = {key: float(value) if value is not None else 0 for key, value in now.items()}
    path = Path(history)
    stamp = datetime.now(timezone.utc)
    first = stamp
    if path.exists() and path.stat().st_size:
        first = datetime.fromisoformat(path.read_text().splitlines()[0].split('"at": "')[1].split('"')[0])
    spent = (stamp - first).total_seconds() / 3600 * rate if rate else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({"at": stamp.isoformat(), **now, "spent": spent}) + "\n")
    path.chmod(0o600)
    return breaches(now, limits, spent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["summary", "locks", "sessions", "statements", "tables", "memory", "databases", "logs",
                                            "telemetry", "upload", "budget", "all"])
    parser.add_argument("--database", help="a database of the instance (the statements and tables are per database)")
    parser.add_argument("--min-seconds", type=int, default=30, help="sessions: only those running at least this long")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--by", choices=sorted(ORDER), default="total", help="statements: order")
    parser.add_argument("--minutes", type=int, default=60, help="logs and telemetry: how far back to read")
    parser.add_argument("--every", type=int, default=5, help="telemetry: the minutes of one interval")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--history", default="db-monitor-history.jsonl", help="budget: the local file each reading is appended to")
    parser.add_argument("--rate", type=float, help="budget: the instance's cost per hour, to estimate spend from the history's age")
    for name in ("budget", "connections-pct", "longest-transaction-s", "longest-idle-in-transaction-s", "size-mb", "temp-mb",
                 "waiting-on-locks"):
        parser.add_argument(f"--limit-{name}", type=float, help="budget: report when a reading reaches this")
    args = parser.parse_args(argv)
    if args.command == "telemetry":
        show("telemetry", telemetry(args.minutes, args.every), args.json)
        return 0
    conn = connect(args.database)
    options = {"sessions": {"min_seconds": args.min_seconds}, "statements": {"top": args.top, "by": args.by},
               "tables": {"top": args.top}}
    try:
        if args.command == "upload":
            with conn.cursor() as cursor:
                show("upload", [upload(cursor)], args.json)
            return 0
        if args.command == "budget":
            limits = {k[6:]: v for k, v in vars(args).items() if k.startswith("limit_") and v is not None}
            over = budget(conn, args.history, limits, args.rate)
            for line in over:
                print("OVER: " + line)
            print("budget: " + ("over a limit" if over else "within every limit"))
            return 1 if over else 0
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
