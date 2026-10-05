"""The data-profiling input step: every format becomes views, lists become child parts."""

import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import inputs  # noqa: E402


@pytest.fixture
def con():
    return duckdb.connect()


def rows(con, part):
    return con.execute(f'SELECT * FROM "{part}" ORDER BY 1').fetchall()


def test_csv_is_one_view_with_full_type_scan(con, tmp_path):
    f = tmp_path / "item.csv"
    # A text value after the default sniff sample would break a sampled type guess.
    f.write_text("id,code\n" + "".join(f"{i},{i}\n" for i in range(25_000)) + "25000,X9\n")
    parts = inputs.register(con, "item", str(f), tmp_path / "w")
    assert [p.name for p in parts] == ["item"]
    assert con.execute('SELECT typeof(code) FROM item LIMIT 1').fetchone()[0] == "VARCHAR"


def test_folder_of_different_tables_gives_one_part_each(con, tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "a.csv").write_text("x\n1\n")
    (tmp_path / "d" / "b.csv").write_text("y,z\n1,2\n")
    assert sorted(p.name for p in inputs.register(con, "d", str(tmp_path / "d"), tmp_path / "w")) == ["a", "b"]


def test_folder_of_same_header_files_is_one_part(con, tmp_path):
    (tmp_path / "d").mkdir()
    for n in range(3):
        (tmp_path / "d" / f"p{n}.csv").write_text(f"x\n{n}\n")
    parts = inputs.register(con, "d", str(tmp_path / "d"), tmp_path / "w")
    assert [p.name for p in parts] == ["d"] and len(rows(con, "d")) == 3


def test_json_nested_objects_lists_and_value_wrappers(con, tmp_path):
    f = tmp_path / "e.json"
    f.write_text(json.dumps({"items": [
        {"id": {"$": "A1"}, "addr": {"city": "X", "zip": {"@lang": "en", "$": "1"}},
         "names": [{"n": "old"}, {"n": "older"}], "tags": ["t1", "t2"],
         "events": {"when": ["2020", "2021"], "what": ["a", "b"]}},
    ]}))
    parts = {p.name: p for p in inputs.register(con, "e", str(f), tmp_path / "w")}
    assert set(parts) == {"e", "e.names", "e.tags", "e.events"}
    assert parts["e"].wrapper == "items"
    top = con.execute('SELECT id, "addr.city", "addr.zip" FROM e').fetchall()
    assert top == [("A1", "X", "1")]
    assert con.execute('SELECT _parent_row, _position, "when", what FROM "e.events" ORDER BY 2').fetchall() == [
        (0, 0, "2020", "a"), (0, 1, "2021", "b")]
    assert con.execute('SELECT value FROM "e.tags" ORDER BY 1').fetchall() == [("t1",), ("t2",)]
    assert parts["e.names"].parent == "e"


def test_large_json_is_streamed_record_by_record(con, tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, "WHOLE", 10)
    f = tmp_path / "big.json"
    f.write_text('{"records":[\n' + ",\n".join(json.dumps({"k": i}) for i in range(5000)) + "\n]}")
    inputs.register(con, "big", str(f), tmp_path / "w")
    assert con.execute("SELECT count(*), count(DISTINCT k) FROM big").fetchone() == (5000, 5000)


def test_folder_of_json_files_is_one_part(con, tmp_path):
    (tmp_path / "d").mkdir()
    for i in range(3):
        (tmp_path / "d" / f"{i}.json").write_text(json.dumps({"k": i, "l": [i, i]}))
    parts = inputs.register(con, "r", str(tmp_path / "d"), tmp_path / "w")
    assert sorted(p.name for p in parts) == ["r", "r.l"]
    assert con.execute('SELECT count(*) FROM "r.l"').fetchone()[0] == 6
    # Child rows point at distinct parent rows.
    assert con.execute('SELECT count(DISTINCT _parent_row) FROM "r.l"').fetchone()[0] == 3


def test_zip_member_and_jsonl(con, tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as archive:
        archive.writestr("a.jsonl", "\n".join(json.dumps({"k": i}) for i in range(4)))
    inputs.register(con, "a", str(z), tmp_path / "w")
    assert con.execute("SELECT count(*) FROM a").fetchone()[0] == 4


def test_xml_records_with_attributes_and_repeats(con, tmp_path):
    f = tmp_path / "x.xml"
    f.write_text('<root><rec id="1"><name>A</name><alt>p</alt><alt>q</alt></rec>'
                 '<rec id="2"><name>B</name></rec></root>')
    parts = {p.name for p in inputs.register(con, "x", str(f), tmp_path / "w")}
    assert parts == {"x", "x.alt"}
    assert con.execute('SELECT "@id", name FROM x ORDER BY 1').fetchall() == [("1", "A"), ("2", "B")]
    assert con.execute('SELECT count(*) FROM "x.alt"').fetchone()[0] == 2


def test_oversized_input_is_sampled_with_a_seed_and_full_pass_is_exact(con, tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps({"k": i, "c": i % 3 or None}) for i in range(1000)))
    parts = inputs.register(con, "s", str(f), tmp_path / "w", limit=100, sample=50, seed=7)
    assert parts[0].scan == "sampled"
    assert con.execute("SELECT count(*) FROM s").fetchone()[0] == 50
    again = duckdb.connect()
    inputs.register(again, "s", str(f), tmp_path / "w2", limit=100, sample=50, seed=7)
    assert rows(con, "s") == rows(again, "s")
    read = inputs.full_values(parts[0], ["c", "k"])
    assert read["c"] == ({1, 2}, 1000, 334) and len(read["k"][0]) == 1000


def test_database_file_tables_become_parts(con, tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as lite:
        lite.execute("CREATE TABLE a (k INTEGER)")
        lite.execute("INSERT INTO a VALUES (1), (2)")
    try:
        parts = inputs.register(con, "t", str(db), tmp_path / "w")
    except duckdb.Error as exc:  # the sqlite extension may need a download CI cannot make
        pytest.skip(f"sqlite extension unavailable: {type(exc).__name__}")
    assert [p.name for p in parts] == ["a"] and rows(con, "a") == [(1,), (2,)]


def test_database_address_from_environment_is_never_printed(con, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PROFILE_TEST_DB", "postgresql://user:secret-pw@127.0.0.1:1/x")
    with pytest.raises(SystemExit) as stop:
        inputs.register(con, "db", "env:PROFILE_TEST_DB", tmp_path / "w")
    out = capsys.readouterr()
    assert "secret-pw" not in str(stop.value) + out.out + out.err


def test_missing_environment_variable_names_it(con, tmp_path, monkeypatch):
    monkeypatch.delenv("PROFILE_TEST_DB", raising=False)
    with pytest.raises(SystemExit, match="PROFILE_TEST_DB"):
        inputs.register(con, "db", "env:PROFILE_TEST_DB", tmp_path / "w")


def test_split_table_json_reads_as_rows(con, tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"fields": ["a", "b"], "data": [[1, "x"], [2, "y"]]}))
    inputs.register(con, "t", str(f), tmp_path / "w")
    assert con.execute("SELECT a, b FROM t ORDER BY a").fetchall() == [(1, "x"), (2, "y")]


def test_streamed_text_with_a_character_across_chunks(con, tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, "WHOLE", 10)
    f = tmp_path / "u.json"
    name = "\u00e9" * (1 << 19)  # 2 bytes each in UTF-8: the 1 MB chunk edge falls inside one
    f.write_text(json.dumps([{"n": name}, {"n": "b"}]), encoding="utf-8")
    inputs.register(con, "u", str(f), tmp_path / "w")
    assert con.execute("SELECT count(*), max(length(n)) FROM u").fetchone() == (2, 1 << 19)


def test_spill_files_are_removed_once_loaded(con, tmp_path):
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(json.dumps({"k": i}) for i in range(10)))
    inputs.register(con, "r", str(f), tmp_path / "w")
    assert not list((tmp_path / "w").glob("*.gz"))


def test_a_date_column_that_fails_to_load_is_loaded_as_text(con, tmp_path):
    # DuckDB fixes one format per date column; on a real 487,721-record file a
    # later value with milliseconds failed the load. Drive that failure here.
    f = tmp_path / "m.jsonl"
    f.write_text("\n".join(json.dumps({"k": i, "ended": "2022-03-14"}) for i in range(5)))

    class FailsFirstLoad:
        def __init__(self, inner):
            self.inner, self.failed = inner, False

        def execute(self, sql, *args):
            if sql.startswith("CREATE TABLE") and "columns=" not in sql and not self.failed:
                self.failed = True
                raise duckdb.InvalidInputException("Could not parse string according to format specifier")
            return self.inner.execute(sql, *args)

    inputs._load_json_lines(FailsFirstLoad(con), "m", f)
    assert con.execute('SELECT typeof(any_value("ended")), typeof(any_value(k)), count(*) FROM m').fetchone() == (
        "VARCHAR", "BIGINT", 5)


def test_a_list_of_one_written_as_an_object_joins_its_list(con, tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps([
        {"id": 1, "periods": {"period": [{"start": "2020", "end": "2021"}, {"start": "2022", "end": None}]}},
        {"id": 2, "periods": {"period": {"start": "2019", "end": "2020"}}},
        {"id": 3},
    ]))
    parts = {p.name for p in inputs.register(con, "x", str(f), tmp_path / "w")}
    assert "x.periods.period" in parts
    assert not [c for (c, *_) in con.execute("DESCRIBE x").fetchall() if c.startswith("periods.")]
    assert con.execute('SELECT _parent_row, _position, start FROM "x.periods.period" ORDER BY 1, 2').fetchall() == [
        (0, 0, "2020"), (0, 1, "2022"), (1, 0, "2019")]
    assert con.execute('SELECT count(DISTINCT _row) FROM "x.periods.period"').fetchone()[0] == 3


def test_a_list_inside_a_nested_object_names_its_enclosing_part(con, tmp_path):
    f = tmp_path / "n.json"
    f.write_text(json.dumps([{"id": 1, "group": {"items": [{"x": 1}, {"x": 2}]}}]))
    parts = {p.name: p for p in inputs.register(con, "n", str(f), tmp_path / "w")}
    assert parts["n.group.items"].parent == "n"
