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
    monkeypatch.delenv("DB_URL", raising=False)
    with pytest.raises(SystemExit) as stop:
        monitor.main(["summary"])
    assert "DB_URL" in str(stop.value) and "postgresql" not in str(stop.value)


def test_the_database_name_replaces_the_one_in_the_url(monkeypatch):
    monkeypatch.setenv("DB_URL", "postgresql+psycopg2://reader:x@host:5432?sslmode=require")
    assert monitor.url("silver") == "postgresql://reader:x@host:5432/silver?sslmode=require"
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

    monkeypatch.setenv("DB_URL", "postgresql://reader:x@host:5432/mdm")
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
    assert "DETAIL" not in sql and "STATEMENT" not in sql  # those lines quote data and are never selected


def test_the_instance_id_is_the_first_part_of_the_host(monkeypatch):
    monkeypatch.setenv("DB_URL", "postgresql://reader:x@abc123def.region.example:5432/mdm")
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
    monkeypatch.setenv("DB_URL", "postgresql://reader:x@abc123.region.example:5432/mdm")
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
