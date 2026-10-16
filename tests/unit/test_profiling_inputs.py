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


def test_a_tsv_is_read_as_csv_and_declared_tsv_for_its_contract(con, tmp_path):
    f = tmp_path / "item.tsv"
    f.write_text("id\tcode\n1\tA1\n2\tB2\n")
    part, = inputs.register(con, "item", str(f), tmp_path / "w")
    assert rows(con, "item") == [(1, "A1"), (2, "B2")]
    assert part.finding(2)["format"] == "tsv"  # the engine reads it as `format: tsv`


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


def test_keyed_records_become_rows_with_keys_and_nested_fact_links(con, tmp_path):
    # Invented concepts: nested data keys must not become part/column names.
    data = {f"Metric{i}": {"label": f"Label {i}", "units": {"ABC": [
        {"period": "2024-12-31", "amount": i}, {"period": "2025-12-31", "amount": i + 1}]}}
        for i in range(8)}
    path = tmp_path / "facts.json"
    path.write_text(json.dumps([{"company_id": "invented-1", "facts": {"taxonomy": data}},
                                {"company_id": "invented-2", "facts": {"taxonomy": data}}]))
    parts = {p.name: p for p in inputs.register(con, "source", str(path), tmp_path / "work")}
    assert set(parts) == {"source", "source.facts.taxonomy", "source.facts.taxonomy._value.units.ABC"}
    assert parts["source.facts.taxonomy"].parent == "source"
    assert parts["source.facts.taxonomy._value.units.ABC"].parent == "source.facts.taxonomy"
    actual = con.execute('SELECT _parent_row, _position, _key, "_value.label" '
                         'FROM "source.facts.taxonomy" ORDER BY _row').fetchall()
    assert actual == [(parent, i, f"Metric{i}", f"Label {i}") for parent in range(2) for i in range(8)]
    assert con.execute('SELECT count(*), count(DISTINCT _parent_row) '
                       'FROM "source.facts.taxonomy._value.units.ABC"').fetchone() == (32, 16)
    assert not any("Metric" in c[0] for c in con.execute('DESCRIBE "source.facts.taxonomy"').fetchall())


def test_top_level_keyed_records_preserve_reserved_fields(con, tmp_path):
    path = tmp_path / "keyed.json"
    path.write_text(json.dumps({f"item-{i}": {"_key": "original", "_row": 90 + i} for i in range(8)}))
    parts = {p.name: p for p in inputs.register(con, "source", str(path), tmp_path / "work")}
    assert set(parts) == {"source", "source._entries"}
    assert parts["source._entries"].parent == "source"
    assert con.execute('SELECT _row, _parent_row, _key, "_value._key", "_value._row" '
                       'FROM "source._entries" ORDER BY _row').fetchall() == [
        (i, 0, f"item-{i}", "original", 90 + i) for i in range(8)]


@pytest.mark.parametrize("kind", ["small", "different_fields", "different_types", "empty", "scalar"])
def test_ordinary_or_ambiguous_objects_keep_their_columns(con, tmp_path, kind):
    count = 7 if kind == "small" else 8
    values = {f"field{i}": {"label": "invented"} for i in range(count)}
    if kind == "different_fields":
        values["field0"] = {"other": "invented"}
    elif kind == "different_types":
        values["field0"] = {"label": 1}
    elif kind == "empty":
        values = {key: {} for key in values}
    elif kind == "scalar":
        values["field0"] = "invented"
    path = tmp_path / "ordinary.json"
    path.write_text(json.dumps({"properties": values}))
    assert [p.name for p in inputs.register(con, "source", str(path), tmp_path / "work")] == ["source"]


@pytest.mark.parametrize("fmt", ["jsonl", "streamed_json"])
def test_keyed_objects_in_other_record_streams(con, tmp_path, monkeypatch, fmt):
    records = [{"values": {f"item-{i}": {"amount": i} for i in range(8)}} for _ in range(2)]
    path = tmp_path / ("input.jsonl" if fmt == "jsonl" else "input.json")
    if fmt == "jsonl":
        path.write_text("\n".join(json.dumps(record) for record in records))
    else:
        monkeypatch.setattr(inputs, "WHOLE", 10)
        path.write_text(json.dumps(records))
    inputs.register(con, "source", str(path), tmp_path / "work")
    assert con.execute('SELECT count(*), count(DISTINCT _parent_row) FROM "source.values"').fetchone() == (16, 2)


def test_mixed_numeric_shapes_keep_large_integer_exact(con, tmp_path):
    values = {f"item{i}": {"amount": 0.5} for i in range(8)}
    values["item0"]["amount"] = 9007199254740993
    path = tmp_path / "numbers.json"
    path.write_text(json.dumps({"values": values}))
    inputs.register(con, "source", str(path), tmp_path / "work")
    assert con.execute('SELECT "values.item0.amount", typeof("values.item0.amount") FROM source').fetchone() == (
        9007199254740993, "BIGINT")


@pytest.mark.parametrize("reverse,nested", [(False, False), (True, False), (False, True), (True, True)])
def test_combining_keyed_documents_refuses_lossy_numeric_column(con, tmp_path, reverse, nested):
    def record(number):
        value = {"observations": [{"amount": number}]} if nested else {"amount": number}
        return {"values": {f"item{i}": value for i in range(8)}}

    data = [record(9007199254740993), record(0.5)]
    path = tmp_path / "numbers.json"
    path.write_text(json.dumps(data[::-1] if reverse else data))
    with pytest.raises(ValueError, match="explicit exact-number reading"):
        inputs.register(con, "source", str(path), tmp_path / "work")
    assert not con.execute("SHOW TABLES").fetchall()  # no rounded table is published


def test_homogeneous_large_integer_entries_are_exact(con, tmp_path):
    path = tmp_path / "numbers.json"
    path.write_text(json.dumps({"values": {f"item{i}": {"amount": 9007199254740993 + i} for i in range(8)}}))
    inputs.register(con, "source", str(path), tmp_path / "work")
    assert con.execute('SELECT "_value.amount" FROM "source.values" ORDER BY _position').fetchall() == [
        (9007199254740993 + i,) for i in range(8)]


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


def test_sibling_lists_of_records_stay_separate_parts(con, tmp_path):
    # Two equally long lists of objects are two child parts, never one table zipped by position;
    # a single item written as an object joins its list.
    f = tmp_path / "d.json"
    f.write_text(json.dumps([
        {"id": 1, "table": {"tx": [{"a": 1}, {"a": 2}], "hold": [{"b": 1}, {"b": 2}]}},
        {"id": 2, "table": {"tx": {"a": 3}}},
    ]))
    parts = {p.name: p for p in inputs.register(con, "d", str(f), tmp_path / "w")}
    assert "d.table" not in parts
    assert parts["d.table.tx"].parent == parts["d.table.hold"].parent == "d"
    assert con.execute('SELECT _parent_row, a FROM "d.table.tx" ORDER BY 1, 2').fetchall() == [(0, 1), (0, 2), (1, 3)]
    assert con.execute('SELECT _parent_row, b FROM "d.table.hold" ORDER BY 1, 2').fetchall() == [(0, 1), (0, 2)]


def test_lists_of_plain_values_of_one_length_are_a_table_stored_by_column(con, tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps([{"id": 1, "m": {"x": [1, 2], "y": ["p", "q"]}}]))
    parts = {p.name for p in inputs.register(con, "c", str(f), tmp_path / "w")}
    assert "c.m" in parts
    assert con.execute('SELECT x, y FROM "c.m" ORDER BY 1').fetchall() == [(1, "p"), (2, "q")]


def test_a_zip_of_csv_tables_gives_one_part_per_member(con, tmp_path):
    with zipfile.ZipFile(tmp_path / "bulk.zip", "w") as archive:
        archive.writestr("one.csv", "a,b\n1,x\n2,y\n")
        archive.writestr("sub/two.csv", "c,d,e\n1,2,3\n")
    parts = inputs.register(con, "bulk", str(tmp_path / "bulk.zip"), tmp_path / "w")
    assert sorted(p.name for p in parts) == ["one", "two"]
    assert rows(con, "one") == [(1, "x"), (2, "y")]
    assert {p.location for p in parts} == {f"{tmp_path / 'bulk.zip'}#one.csv", f"{tmp_path / 'bulk.zip'}#sub/two.csv"}


def test_a_zip_of_tables_with_its_documentation_reads_the_tables_and_lists_the_rest(con, tmp_path):
    # A bulk data set ships its tables beside a readme and a metadata file: the tables are
    # read, and each other member is listed as not read, with its reason, never dropped.
    with zipfile.ZipFile(tmp_path / "set.zip", "w") as archive:
        archive.writestr("A.tsv", "k\tv\n1\tx\n2\ty\n")
        archive.writestr("B.tsv", "k\tw\n1\t9\n")
        archive.writestr("readme.htm", "<html>about</html>")
        archive.writestr("meta.json", '{"tables": []}')
    parts = {p.name: p for p in inputs.register(con, "set", str(tmp_path / "set.zip"), tmp_path / "w")}
    assert sorted(parts) == ["A", "B", "meta", "readme"]
    assert rows(con, "A") == [(1, "x"), (2, "y")]
    assert parts["A"].not_read is None and parts["B"].not_read is None
    for name, fmt in (("readme", "htm"), ("meta", "json")):
        assert parts[name].not_read.startswith(f"not a table ({fmt})")
        assert parts[name].location == f"{tmp_path / 'set.zip'}#{name}.{fmt}"


def test_a_readme_does_not_split_tables_of_one_header(con, tmp_path):
    with zipfile.ZipFile(tmp_path / "q.zip", "w") as archive:
        archive.writestr("q1.csv", "k,v\n1,a\n")
        archive.writestr("q2.csv", "k,v\n2,b\n")
        archive.writestr("readme.htm", "<p>about</p>")
    parts = inputs.register(con, "q", str(tmp_path / "q.zip"), tmp_path / "w")
    assert sorted((p.name, p.not_read is None) for p in parts) == [("q", True), ("readme", False)]
    assert sorted(rows(con, "q")) == [(1, "a"), (2, "b")]


def test_records_beside_tables_are_named_as_records_not_documents(con, tmp_path):
    with zipfile.ZipFile(tmp_path / "m.zip", "w") as archive:
        archive.writestr("a.csv", "k\n1\n")
        archive.writestr("r.jsonl", '{"id": 1}\n')
    parts = {p.name: p for p in inputs.register(con, "m", str(tmp_path / "m.zip"), tmp_path / "w")}
    assert parts["r"].not_read == "not a table (jsonl); records beside the tables; profile this file as its own input to read it"
    assert not (tmp_path / "w" / "members" / "1").exists()  # a member not read is not copied out


def test_a_zip_holding_records_is_still_read_as_records(con, tmp_path):
    with zipfile.ZipFile(tmp_path / "r.zip", "w") as archive:
        archive.writestr("r.jsonl", '{"id": 1}\n{"id": 2}\n')
    assert [p.name for p in inputs.register(con, "r", str(tmp_path / "r.zip"), tmp_path / "w")] == ["r"]
    assert rows(con, "r")[0][-1] == 1


def test_a_csv_that_is_not_utf8_is_read_and_its_encoding_stated(con, tmp_path):
    (tmp_path / "w1252.csv").write_bytes(b"id,name,note\n1,Caf\xe9,\x93quoted\x94\n2,Beta,ok\n")
    (part,) = inputs.register(con, "w1252", str(tmp_path / "w1252.csv"), tmp_path / "w")
    assert part.encoding == {"read_as": "windows-1252", "inferred": True, "files_not_utf8": 1, "files": 1,
                             "first_invalid_byte_offset": 18, "declare": "windows-1252"}
    assert part.finding(2)["encoding"]["read_as"] == "windows-1252"
    assert rows(con, "w1252")[0][1:] == ("Café", "\u201cquoted\u201d")
    (latin,) = inputs.register(con, "latin", str(_write(tmp_path / "latin.csv", b"id,n\n1,\x81x\n")), tmp_path / "w2")
    assert latin.encoding["read_as"] == "latin-1"  # 0x81 is no Windows-1252 character
    assert latin.encoding["declare"].startswith("none")


def test_utf16_or_binary_text_is_not_read(con, tmp_path):
    (tmp_path / "u16.csv").write_bytes("id,name\n1,a\n".encode("utf-16"))
    (tmp_path / "nul.csv").write_bytes(b"id,name\n1,a\x00b\n")
    for name in ("u16", "nul"):
        (part,) = inputs.register(con, name, str(tmp_path / f"{name}.csv"), tmp_path / f"w{name}")
        assert part.not_read and part.encoding is None


@pytest.mark.parametrize("data, reason", [
    (b"a,b,c\n1,2,3\n4,5\n6,7,8,9\n", "skip"),  # the reader takes the last line as the header
    (b"id,name\n1,\"x\n2,y\n", "double quotes"),
    (b"a,b\n1,2\n3,4,5\n6,7\n", "one column"),  # the reader picks another delimiter
    (b"a,b,c\n1,2,3\n4,5,6\n7,8\n9,10,11\n", "not one way"),  # a short row: the reader again picks another delimiter
    (b"Report generated\n\nid,name\n1,a\n2,b\n", "skip"),
])
def test_a_csv_of_more_than_one_shape_is_not_read(con, tmp_path, data, reason):
    (part,) = inputs.register(con, "odd", str(_write(tmp_path / "odd.csv", data)), tmp_path / "w")
    assert part.not_read and reason in part.not_read
    assert "odd" not in {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}


def test_a_regular_csv_with_quoted_delimiters_is_read(con, tmp_path):
    (part,) = inputs.register(con, "ok", str(_write(tmp_path / "ok.csv", b'id,name,note\n1,"A, Inc","say ""hi"""\n2,B,\n')),
                              tmp_path / "w")
    assert part.not_read is None and rows(con, "ok")[0] == (1, "A, Inc", 'say "hi"')


def test_members_of_one_name_in_two_zips_stay_apart(con, tmp_path):
    (tmp_path / "d").mkdir()
    for month, header, text in (("2025-06", "id,name", b"1,Caf\xe9 June\n"), ("2025-07", "id,name", b"1,Caf\xe9 July\n")):
        with zipfile.ZipFile(tmp_path / "d" / f"{month}.zip", "w") as archive:
            archive.writestr("sched.csv", header.encode() + b"\n" + text)
    with zipfile.ZipFile(tmp_path / "d" / "2025-08.zip", "w") as archive:
        archive.writestr("sched.csv", "id,name\n1,Café August\n".encode())
    (part,) = inputs.register(con, "d", str(tmp_path / "d"), tmp_path / "w")
    assert sorted(r[1] for r in rows(con, part.name)) == ["Café August", "Café July", "Café June"]
    assert part.encoding["declare"] == ["utf-8", "windows-1252"]  # publications changed encoding
    with zipfile.ZipFile(tmp_path / "e.zip", "w") as archive:
        archive.writestr("a/s.csv", "x\n1\n")
        archive.writestr("b/s.csv", "y,z\n1,2\n")
    parts = inputs.register(con, "e", str(tmp_path / "e.zip"), tmp_path / "w2")
    assert len({p.name for p in parts}) == 2 and not any(p.not_read for p in parts)
    assert {p.location for p in parts} == {f"{tmp_path / 'e.zip'}#a/s.csv", f"{tmp_path / 'e.zip'}#b/s.csv"}


def test_a_member_has_its_own_checksum_and_no_work_path_in_a_reason(con, tmp_path):
    with zipfile.ZipFile(tmp_path / "z.zip", "w") as archive:
        archive.writestr("good.csv", "x,y\n1,2\n")
        archive.writestr("bad.csv", bytes(range(1, 256)) * 4)
    parts = {p.name: p for p in inputs.register(con, "z", str(tmp_path / "z.zip"), tmp_path / "w")}
    assert parts["good"].sha256 == __import__("hashlib").sha256(b"x,y\n1,2\n").hexdigest()
    assert parts["bad"].not_read and str(tmp_path / "w") not in parts["bad"].not_read


def _write(path, data):
    path.write_bytes(data)
    return path


def test_a_table_duckdb_cannot_read_is_reported_and_the_rest_read(con, tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "good.csv").write_text("x,y\n1,2\n")
    (tmp_path / "d" / "bad.csv").write_bytes(bytes(range(1, 256)) * 4)
    parts = {p.name: p for p in inputs.register(con, "d", str(tmp_path / "d"), tmp_path / "w")}
    assert parts["good"].not_read is None and rows(con, "good") == [(1, 2)]
    assert parts["bad"].not_read and "bad" not in {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}


def test_table_names_never_repeat_or_come_out_empty(tmp_path):
    for folder in ("a", "b", "c", "d"):
        (tmp_path / "s" / folder).mkdir(parents=True)
    (tmp_path / "s" / "a" / "t.csv").write_text("x\n1\n")
    (tmp_path / "s" / "b" / "t.csv").write_text("y\n1\n")
    (tmp_path / "s" / "t_2.csv").write_text("z\n1\n")
    (tmp_path / "s" / "c" / "@.csv").write_text("p\n1\n")
    (tmp_path / "s" / "d" / "@.csv").write_text("q\n1\n")
    tables, _ = inputs._tables(tmp_path / "s", tmp_path / "w")
    names = [t.name for t in tables]
    assert len(set(names)) == len(names) and all(names)
    assert {"a_t", "b_t", "t_2"} <= set(names)


@pytest.mark.parametrize("data", [b"a;b\nx\ny\n", b'a,b\n"x" ,1\n'])
def test_regular_files_the_shape_check_once_refused_are_read(con, tmp_path, data):
    (part,) = inputs.register(con, "ok", str(_write(tmp_path / "ok.csv", data)), tmp_path / "w")
    assert part.not_read is None


def test_mac_resource_entries_in_a_zip_are_left_out(con, tmp_path):
    with zipfile.ZipFile(tmp_path / "m.zip", "w") as archive:
        archive.writestr("t.csv", "x\n1\n")
        archive.writestr("__MACOSX/._t.csv", b"\x00\x05\x16\x07")
    assert [(p.name, p.not_read) for p in inputs.register(con, "m", str(tmp_path / "m.zip"), tmp_path / "w")] == [("m", None)]


def test_each_table_of_a_folder_keeps_its_own_hash(con, tmp_path):
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "a.csv").write_text("k\n1\n")
    (tmp_path / "f" / "b.csv").write_text("j,m\n2,3\n")
    parts = {p.name: p for p in inputs.register(con, "f", str(tmp_path / "f"), tmp_path / "w")}
    assert parts["a"].sha256 == inputs.digest(tmp_path / "f" / "a.csv") != parts["b"].sha256


def test_a_file_with_no_suffix_is_read_by_its_first_character(con, tmp_path):
    (tmp_path / "doc").write_text('<?xml version="1.0"?>\n<table><row><id>1</id></row><row><id>2</id></row></table>')
    assert inputs.format_of(tmp_path / "doc") == "xml"
    (tmp_path / "rec").write_text('[{"id": 1}]')
    assert inputs.format_of(tmp_path / "rec") == "json"
