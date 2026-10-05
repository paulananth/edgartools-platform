"""Time roles and hierarchies of the data-profiling skill, on small tables."""

import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import hierarchy, profile, timing  # noqa: E402


@pytest.fixture
def con():
    return duckdb.connect()


def test_valid_pair_needs_start_and_end_words_and_order(con):
    con.execute("""CREATE TABLE t AS SELECT i AS k, DATE '2020-01-01' + CAST(i AS INTEGER) AS valid_from,
                   CASE WHEN i % 2 = 0 THEN NULL ELSE DATE '2021-01-01' + CAST(i AS INTEGER) END AS valid_to,
                   DATE '2019-01-01' + CAST(i AS INTEGER) AS shipped_on FROM range(100) r(i)""")
    roles = timing.roles(con, "t", profile.columns(con, "t"), ["k"])
    assert roles["as_of"] == {"from": "valid_from", "to": "valid_to"}
    assert roles["event_time"] == "shipped_on"


def test_record_time_and_personal_dates(con):
    con.execute("""CREATE TABLE t AS SELECT i AS k, DATE '1980-01-01' + CAST(i AS INTEGER) AS birth_date,
                   TIMESTAMP '2025-01-01 00:00:00' + INTERVAL (i) MINUTE AS last_updated FROM range(10) r(i)""")
    roles = timing.roles(con, "t", profile.columns(con, "t"), ["k"], personal={"birth_date"})
    assert roles["as_at"] == "last_updated" and roles["event_time"] is None


def test_daily_series_with_its_step_and_gaps(con):
    con.execute("""CREATE TABLE t AS SELECT DATE '2025-01-01' + CAST(d AS INTEGER) AS day, c AS code, d * 1.5 AS rate
                   FROM range(30) a(d), (VALUES ('A'), ('B')) b(c) WHERE NOT (c = 'B' AND d = 10)""")
    s = timing.roles(con, "t", profile.columns(con, "t"), ["day", "code"])["series"]
    assert s["key"] == ["code"] and s["time"] == "day" and s["step"].startswith("1 day") and s["gaps"] == 1


def test_parent_column_depth_orphans_and_cycles(con):
    con.execute("""CREATE TABLE t (node VARCHAR, up VARCHAR);
                   INSERT INTO t VALUES ('a', NULL), ('b', 'a'), ('c', 'b'), ('d', 'a'), ('e', 'zz'),
                                        ('x', 'y'), ('y', 'x')""")
    h = hierarchy.by_parent_column(con, "t", "up", "node")
    assert h["depth"] == 3 and h["orphans"] == 1 and h["cycles"] == 2 and h["shape"] == "ragged"


def test_link_part_gives_one_hierarchy_per_role_with_one_parent(con):
    con.execute("""CREATE TABLE l (child VARCHAR, parent VARCHAR, kind VARCHAR);
                   INSERT INTO l VALUES ('b', 'a', 'owns'), ('c', 'b', 'owns'), ('d', 'a', 'owns'),
                                        ('b', 'x', 'knows'), ('b', 'y', 'knows')""")
    found = hierarchy.by_link_part(con, "l", "child", "parent", "kind")
    assert [h["role"] for h in found] == ["owns"]  # "knows" has two parents for b: a network
    assert found[0]["depth"] == 3 and found[0]["evidence_kind"] == "parent_column"
