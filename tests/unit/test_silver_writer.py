"""The silver writer without a database (profiling ticket 06): a spec is checked
before any table is made, values are written for the database to cast, and each
link's MDM id is looked up by the master's Dataset Contract, kind and key."""

from __future__ import annotations

import datetime
import json

import pytest

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.silver_writer import rows, spec as specs, writer
from edgar_warehouse.silver_writer.sink import _copy_text, _without_values


def a_spec(**more):
    base = {
        "table": "visit",
        "grain": "one row per visit_id",
        "columns": [
            {"name": "visit_id", "type": "BIGINT", "nullable": False, "definition": None,
             "source": "visit.visit_id", "sensitivity": "none"},
            {"name": "member_id", "type": "VARCHAR", "nullable": True, "definition": None,
             "source": "visit.member_id", "sensitivity": "none"},
            {"name": "amount", "type": "DECIMAL(18,2)", "nullable": True, "definition": "What was paid.",
             "source": "visit.amount", "sensitivity": "none"},
            {"name": "visited_on", "type": "DATE", "nullable": True, "definition": None,
             "source": "visit.visited_on", "sensitivity": "none"},
            {"name": "tags", "type": "VARCHAR[]", "nullable": True, "definition": None,
             "source": "visit.tags", "sensitivity": "none"},
        ],
        "key": ["visit_id"],
        "links": [{"columns": ["member_id"], "kind": "person", "source_code": "fixture.members",
                   "to_part": "member", "source_key": "member_id", "mdm_id_column": "member_id_mdm_id",
                   "inclusion": 1.0}],
        "time": {"as_of": None, "as_at": "loaded_at", "event_time": "visited_on"},
        "partition": ["visited_on"],
        "load_mode": "append",
        "why": "events are appended and never changed",
    }
    return {**base, **more}


def test_types_land_as_their_postgres_type_and_an_unknown_type_is_refused():
    assert specs.postgres_type("INTEGER") == specs.postgres_type("SMALLINT") == "bigint"  # never narrower
    assert specs.postgres_type("HUGEINT") == "numeric(39,0)"
    assert specs.postgres_type("DECIMAL(18, 2)") == "numeric(18,2)"
    assert specs.postgres_type("STRUCT(a INTEGER)") == specs.postgres_type("VARCHAR[]") == "jsonb"
    assert specs.postgres_type("TIMESTAMP WITH TIME ZONE") == "timestamp with time zone"
    with pytest.raises(Blocked, match="No silver type"):
        specs.postgres_type("GEOMETRY")


def test_a_spec_is_checked_and_the_writer_adds_its_mdm_ids_and_loaded_at():
    spec = specs.check(a_spec())
    assert specs.columns(spec) == ["visit_id", "member_id", "amount", "visited_on", "tags",
                                   "member_id_mdm_id", "loaded_at"]
    stamped_by_source = a_spec(time={"as_of": None, "as_at": "visited_on", "event_time": None})
    assert "loaded_at" not in specs.columns(specs.check(stamped_by_source))


@pytest.mark.parametrize("change, refused", [
    ({"links": [{"columns": ["member_id"], "kind": None, "source_code": None, "to_part": "member",
                 "source_key": "member_id", "mdm_id_column": "member_id_mdm_id", "inclusion": 1.0}]},
     "name the master's kind and Dataset Contract"),
    ({"links": [{"columns": ["member_id"], "kind": "person", "source_code": "x", "source_key": "member_id",
                 "mdm_id_column": "amount"}]}, "share a name"),
    ({"table": "t" * 64}, "1 to 63 bytes"),
    ({"key": ["member_id"]}, "never empty"),
    ({"key": ["nope"]}, "The key names"),
    ({"load_mode": "merge"}, "load_mode"),
    ({"time": {"as_of": None, "as_at": "recorded", "event_time": None}}, "as_at names a column"),
    ({"extra": 1}, "A silver table spec holds"),
    ({"grain": None}, "grain is plain words"),
    ({"links": [{"columns": ["member_id"], "kind": "person", "source_code": "x", "source_key": "member_id",
                 "mdm_id_column": "m", "inclusion": 1.5}]}, "inclusion is a share"),
    ({"links": [{"columns": ["member_id", "amount"], "kind": "person", "source_code": "x",
                 "source_key": "member_id", "mdm_id_column": "m"}]}, "one column of the spec"),
])
def test_a_spec_that_could_not_land_is_refused_before_any_table(change, refused):
    with pytest.raises(Blocked, match=refused):
        specs.check(a_spec(**change))


def test_values_are_written_for_the_database_to_cast():
    assert _copy_text(None, "bigint", "c") == r"\N"
    assert _copy_text(True, "boolean", "c") == "true"
    assert _copy_text(["a", "b"], "jsonb", "c") == '["a", "b"]'
    assert _copy_text(datetime.date(2026, 10, 8), "date", "c") == "2026-10-08"
    assert _copy_text("a\tb\\c\nd", "text", "c") == "a\\tb\\\\c\\nd"
    with pytest.raises(Blocked, match="not a nested value"):
        _copy_text({"a": 1}, "text", "c")
    with pytest.raises(Blocked, match="finite"):
        _copy_text(float("nan"), "double precision", "c")
    aware = datetime.datetime(2026, 10, 8, 12, tzinfo=datetime.timezone.utc)
    assert _copy_text(aware, "timestamp with time zone", "c") == "2026-10-08T12:00:00+00:00"
    with pytest.raises(Blocked, match="would lose it"):
        _copy_text(aware, "timestamp", "c")


def test_a_refused_value_is_never_shown():
    message = 'invalid input syntax for type bigint: "jane.doe@example.org"'
    assert _without_values(message) == 'invalid input syntax for type bigint: "…"'


def test_rows_come_from_json_lines_csv_and_parquet(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    (tmp_path / "a.jsonl").write_text(json.dumps({"visit_id": 1, "tags": ["x"]}) + "\n\n")
    (tmp_path / "a.csv").write_text("visit_id,member_id\n1,\n")
    pq.write_table(pa.table({"visit_id": [1]}), tmp_path / "a.parquet")
    assert list(rows.records(tmp_path / "a.jsonl")) == [{"visit_id": 1, "tags": ["x"]}]
    assert list(rows.records(tmp_path / "a.csv")) == [{"visit_id": "1", "member_id": None}]
    assert list(rows.records(tmp_path / "a.parquet")) == [{"visit_id": 1}]
    with pytest.raises(Blocked, match="Rows are read from"):
        list(rows.records(tmp_path / "a.xml"))


class FakeSink:
    def __init__(self, spec):
        self._spec, self.written = specs.check(spec), None

    def spec(self, table):
        return self._spec

    def write(self, spec, delivered):
        self.written = list(delivered)
        return {"table": spec["table"], "rows": len(self.written)}


def test_each_link_gets_its_master_mdm_id_and_an_unmastered_record_keeps_it_empty():
    sink, asked = FakeSink(a_spec()), []

    def ids(source_code, kind, keys):
        asked.append((source_code, kind, sorted(keys)))
        return {"m1": "entity-1", "m2": None}

    result = writer.land(sink, "visit", [{"visit_id": 1, "member_id": "m1"}, {"visit_id": 2, "member_id": "m2"},
                                         {"visit_id": 3, "member_id": None}], ids)
    assert asked == [("fixture.members", "person", ["m1", "m2"])]
    assert [r["member_id_mdm_id"] for r in sink.written] == ["entity-1", None, None]
    assert result["mdm_keys_found"] == 1


def test_a_field_the_spec_does_not_name_or_a_missing_mdm_database_is_refused():
    with pytest.raises(Blocked, match="does not name"):
        writer.land(FakeSink(a_spec()), "visit", [{"visit_id": 1, "member_id_mdm_id": "forged"}], lambda *a: {})
    with pytest.raises(Blocked, match="MDM_DATABASE_URL"):
        writer.land(FakeSink(a_spec()), "visit", [{"visit_id": 1}], None)


def test_a_number_read_as_a_float_matches_its_record_key():
    assert writer._key(320193.0) == "320193" and writer._key(7) == "7" and writer._key("007") == "007"
