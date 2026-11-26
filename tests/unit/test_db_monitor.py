"""The database monitor reads as a read-only login: its statements only select, it refuses a superuser, it shows no literal."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "database-monitoring" / "scripts" / "db_monitor.py"
spec = importlib.util.spec_from_file_location("db_monitor", SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)

WRITES = re.compile(r"\b(insert|update|delete|truncate|drop|alter|create|grant|revoke|vacuum|analyze|copy|"
                    r"pg_terminate_backend|pg_cancel_backend|set)\b", re.I)


@pytest.mark.parametrize("name", sorted(monitor.SQL))
def test_every_reading_is_one_select_that_writes_nothing(name):
    sql = monitor.SQL[name].strip()
    assert sql.lower().startswith("select")
    assert not WRITES.search(re.sub(r"'[^']*'", "''", sql)), name
    assert ";" not in sql


def test_a_statement_shows_no_literal_and_is_cut():
    shown = monitor.plain("select * from t where name = 'Acme Corp' and cik = 12345 and x = 'it''s'", width=200)
    assert shown == "select * from t where name = ? and cik = ? and x = ?"
    assert monitor.plain("select " + "a, " * 100, width=20).endswith("…") and len(monitor.plain("select " + "a, " * 100, width=20)) == 20


def test_without_the_login_variable_it_stops_and_prints_no_address(monkeypatch, capsys):
    monkeypatch.delenv("DATA_URL", raising=False)
    with pytest.raises(SystemExit) as stop:
        monitor.main(["summary"])
    assert "DATA_URL" in str(stop.value) and "postgresql" not in str(stop.value)


def test_the_database_name_replaces_the_one_in_the_url(monkeypatch):
    monkeypatch.setenv("DATA_URL", "postgresql+psycopg2://reader:x@host:5432/data?sslmode=require")
    assert monitor.url("control") == "postgresql://reader:x@host:5432/control?sslmode=require"
    assert monitor.url(None) == "postgresql://reader:x@host:5432/postgres?sslmode=require"


class Cursor:
    def __init__(self, superuser):
        self.superuser = superuser

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return (self.superuser,)


class Connection:
    def __init__(self, superuser):
        self.superuser, self.session = superuser, None

    def set_session(self, **kwargs):
        self.session = kwargs

    def cursor(self):
        return Cursor(self.superuser)


def test_the_connection_is_a_read_only_session_and_a_superuser_is_refused(monkeypatch):
    import psycopg2

    monkeypatch.setenv("DATA_URL", "postgresql://reader:x@host:5432/data")
    ordinary = Connection(False)
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: ordinary)
    assert monitor.connect() is ordinary and ordinary.session == {"readonly": True, "autocommit": True}
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: Connection(True))
    with pytest.raises(SystemExit, match="superuser"):
        monitor.connect()


def test_a_log_message_loses_its_addresses_literals_and_key_values():
    shown = monitor.scrub("FATAL:  no entry for host \"10.20.30.40\", user 'bob' Key (cik)=(0001234) is bad")
    assert "10.20.30.40" not in shown and "bob" not in shown and "0001234" not in shown
    assert "<ip>" in shown and "(?)=(?)" in shown


def test_the_log_reading_selects_only_and_names_every_memory_phrase():
    sql = monitor.LOG_SQL.format(instance="abc123", minutes=60, top=5, level=monitor.LEVEL, level_word="x",
                                 memory="|".join(f".*{p}.*" for p in monitor.MEMORY),
                                 is_memory=" or ".join(f"m ilike '%{p}%'" for p in monitor.MEMORY))
    assert sql.strip().lower().startswith("with") and not WRITES.search(re.sub(r"'[^']*'", "''", sql))
    assert "out of memory" in sql and "terminated by signal 9" in sql and "abc123" in sql
    assert "dateadd(minute, -60, sysdate())" in sql  # the event table's times are UTC without a zone, as sysdate() is
    assert "DETAIL" not in sql and "STATEMENT" not in sql  # those lines quote data and are never selected


def test_the_instance_id_is_the_first_part_of_the_host(monkeypatch):
    monkeypatch.setenv("DATA_URL", "postgresql://reader:x@abc123def.region.example:5432/data")
    assert monitor.instance_id() == "abc123def"


@pytest.mark.parametrize("role", ["ACCOUNTADMIN", "sysadmin"])
def test_the_log_reading_refuses_an_administrator_role(monkeypatch, role):
    monkeypatch.setenv("MONITOR_SNOWFLAKE_CONNECTION", "c")
    monkeypatch.setattr(monitor, "snow", lambda connection, sql: [{"ROLE": role}])
    with pytest.raises(SystemExit, match="administrator role"):
        monitor.logs(60)


def test_the_log_reading_needs_its_connection_named(monkeypatch):
    monkeypatch.delenv("MONITOR_SNOWFLAKE_CONNECTION", raising=False)
    with pytest.raises(SystemExit, match="MONITOR_SNOWFLAKE_CONNECTION"):
        monitor.logs(60)


def test_a_read_only_role_reads_the_log_and_the_messages_are_scrubbed(monkeypatch):
    monkeypatch.setenv("MONITOR_SNOWFLAKE_CONNECTION", "c")
    monkeypatch.setenv("DATA_URL", "postgresql://reader:x@abc123.region.example:5432/data")
    answers = [[{"ROLE": "LOG_READER"}],
               [{"KIND": "memory", "MESSAGE": "ERROR:  out of memory", "N": 2, "FIRST_AT": "a", "LAST_AT": "b"},
                {"KIND": "fatal", "MESSAGE": "FATAL:  rejected host 1.2.3.4", "N": 1, "FIRST_AT": "a", "LAST_AT": "b"}]]
    monkeypatch.setattr(monitor, "snow", lambda connection, sql: answers.pop(0))
    found = monitor.logs(60)
    assert [(r["kind"], r["n"]) for r in found] == [("memory", 2), ("fatal", 1)]
    assert found[1]["message"] == "FATAL: rejected host <ip>"


def test_a_half_cut_address_is_replaced_too():
    assert monitor.scrub("authentication failed (user: u database: d remote host: 73.89.1") == "authentication failed (user: u database: d remote host: <ip>"
    assert "106.13" not in monitor.scrub("rejected for host 106.13.180.")


def test_a_reading_over_a_limit_is_named_and_one_under_is_not():
    now = {"connections": 90, "max_connections": 100, "longest_transaction_s": 10, "waiting_on_locks": 0,
           "longest_idle_in_transaction_s": 0, "size_mb": 500, "temp_mb": 0}
    assert monitor.breaches(now, {"connections_pct": 80, "size_mb": 1000}, None) == ["connections 90 of 100"]
    assert monitor.breaches(now, {}, None) == []
    assert monitor.breaches(now, {"budget": 5}, 5.5) == ["estimated spend 5.50 (budget 5)"]


def test_budget_appends_a_private_history_and_estimates_spend_from_its_first_line(tmp_path, monkeypatch):
    reading = {"summary": [{"connections": 1, "max_connections": 100, "active": 1, "idle_in_transaction": 0,
                            "waiting_on_locks": 0, "longest_transaction_s": 0, "longest_idle_in_transaction_s": 0}],
               "size": [{"size_mb": 165, "temp_mb": None}]}
    monkeypatch.setattr(monitor, "rows", lambda conn, name, **_: reading[name])
    history = tmp_path / "h.jsonl"
    history.write_text('{"at": "2020-01-01T00:00:00+00:00"}\n')
    over = monitor.budget(None, str(history), {"budget": 1}, 0.01)
    assert over and over[0].startswith("estimated spend") and len(history.read_text().splitlines()) == 2
    assert history.stat().st_mode & 0o777 == 0o600


def test_the_telemetry_reading_selects_only_this_instances_metrics():
    sql = monitor.TELEMETRY_SQL.format(instance="abc123", minutes=90, every=5)
    assert sql.strip().lower().startswith("with") and not WRITES.search(re.sub(r"'[^']*'", "''", sql))
    assert "resource_attributes['instance_id'] = 'abc123'" in sql and "dateadd(minute, -90, sysdate())" in sql


def test_telemetry_turns_counter_deltas_into_shares_and_rates_per_interval():
    raw = [{"AT": "11-26 02:40", "NAME": "system.cpu.time", "KEY": "user", "TOTAL": 120.0, "MEAN": None, "TOP": None, "CPUS": 1},
           {"AT": "11-26 02:40", "NAME": "system.cpu.time", "KEY": "idle", "TOTAL": 180.0, "MEAN": None, "TOP": None, "CPUS": 1},
           {"AT": "11-26 02:40", "NAME": "system.network.io", "KEY": "receive", "TOTAL": 614400.0, "MEAN": None, "TOP": None, "CPUS": 0},
           {"AT": "11-26 02:40", "NAME": "system.network.io", "KEY": "transmit", "TOTAL": 30720.0, "MEAN": None, "TOP": None, "CPUS": 0},
           {"AT": "11-26 02:40", "NAME": "postgres_locked_transactions", "KEY": None, "TOTAL": None, "MEAN": 1.5, "TOP": 3.0, "CPUS": 0},
           {"AT": "11-26 02:40", "NAME": "postgres_connections", "KEY": None, "TOTAL": None, "MEAN": 9.0, "TOP": 12.0, "CPUS": 0}]
    [row] = monitor.telemetry_rows(raw, every=5)
    assert list(row) == ["at_et", "cpu_user_pct", "cpu_idle_pct", "receive_kb_s", "transmit_kb_s", "waiting_on_locks_mean",
                         "connections_top"]
    assert row == {"at_et": "11-26 02:40", "cpu_user_pct": 40.0, "cpu_idle_pct": 60.0, "receive_kb_s": 2.0, "transmit_kb_s": 0.1,
                   "waiting_on_locks_mean": 1.5, "connections_top": 12.0}


def test_a_partly_read_interval_is_measured_by_what_its_readings_cover():
    raw = [{"AT": "11-26 15:10", "NAME": "system.cpu.time", "KEY": "user", "TOTAL": 12.0, "MEAN": None, "TOP": None, "CPUS": 1},
           {"AT": "11-26 15:10", "NAME": "system.cpu.time", "KEY": "idle", "TOTAL": 18.0, "MEAN": None, "TOP": None, "CPUS": 1},
           {"AT": "11-26 15:10", "NAME": "system.network.io", "KEY": "receive", "TOTAL": 61440.0, "MEAN": None, "TOP": None, "CPUS": 0}]
    [row] = monitor.telemetry_rows(raw, every=5)  # 30 s of a 5-minute interval were read
    assert (row["cpu_user_pct"], row["cpu_idle_pct"], row["receive_kb_s"]) == (40.0, 60.0, 2.0)


class TimedCursor:
    """A cursor whose clock moves by the bytes it is sent or asked for, at the rates given."""

    def __init__(self, clock, up_mb_s, down_mb_s, fail_after=None):
        self.clock, self.up, self.down, self.sent, self.fail_after = clock, up_mb_s, down_mb_s, 0, fail_after
        self.result = None

    def execute(self, sql, params=None):
        if "length(%s)" in sql:
            self.sent += 1
            if self.fail_after is not None and self.sent > self.fail_after:
                raise TimeoutError("canceling statement due to statement timeout")
            self.clock[0] += len(params[0]) / 2**20 / self.up
            self.result = [(len(params[0]),)]
        elif "repeat(" in sql:  # one row of 1 KB a row asked for
            self.clock[0] += params[0] / 1024 / self.down
            self.result = [("x" * 1024,)] * params[0]
        else:
            self.clock[0] += 0.1
            self.result = [(1,)]

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result


def test_one_connections_upload_and_download_are_timed_in_mb_a_second():
    clock = [0.0]
    found = monitor.upload(TimedCursor(clock, up_mb_s=0.5, down_mb_s=25.0), clock=lambda: clock[0], sends=3, mb=4)
    assert found["round_trip_ms"] == 100.0
    assert found["download_mb_s"] == 25.0
    assert found["upload_mb_s"] == [0.5] * 3 and found["upload_mb_s_overall"] == 0.5


def test_an_upload_cut_off_by_the_statement_timeout_is_named_and_the_rest_still_shown():
    clock = [0.0]
    found = monitor.upload(TimedCursor(clock, up_mb_s=0.5, down_mb_s=25.0, fail_after=2), clock=lambda: clock[0], sends=3, mb=4)
    assert found["upload_mb_s"] == [0.5] * 2
    assert "statement timeout" in found["upload_stopped"]


def test_no_upload_starts_once_the_uploads_have_taken_their_time():
    clock = [0.0]
    found = monitor.upload(TimedCursor(clock, up_mb_s=0.05, down_mb_s=25.0), clock=lambda: clock[0], sends=8, mb=4, seconds=60)
    assert found["upload_mb_s"] == [0.05]  # one send of 4 MB took 80 s: the second never starts
    assert "no more were started" in found["upload_stopped"]


def test_cpu_shares_of_a_two_cpu_instance_use_both_cpus_seconds():
    raw = [{"AT": "a", "NAME": "system.cpu.time", "KEY": "user", "TOTAL": 150.0, "MEAN": None, "TOP": None, "CPUS": 2},
           {"AT": "a", "NAME": "system.cpu.time", "KEY": "idle", "TOTAL": 450.0, "MEAN": None, "TOP": None, "CPUS": 2},
           {"AT": "a", "NAME": "system.network.io", "KEY": "receive", "TOTAL": 307200.0, "MEAN": None, "TOP": None, "CPUS": 0}]
    [row] = monitor.telemetry_rows(raw, every=5)  # 600 CPU seconds over 2 CPUs: 300 s of wall time
    assert (row["cpu_user_pct"], row["cpu_idle_pct"], row["receive_kb_s"]) == (25.0, 75.0, 1.0)
