"""The normal Silver registration and delivery caller; invented data only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.silver_writer.database import migrate, register
from edgar_warehouse.silver_writer.context import TableContext
from edgar_warehouse.silver_writer.relational import DatabaseSink
from edgar_warehouse.silver_writer.tables import data_table
from edgar_warehouse.silver_writer.writer import land, refresh_ids
from tests.unit.test_silver_writer import a_spec


@pytest.fixture
def silver(database_factory):
    with database_factory() as (owner, runtime, role):
        with pytest.raises(Blocked, match="not initialized"):
            migrate(owner, runtime_role=role, existing_only=True)
        installed = migrate(owner, runtime_role=role)
        assert migrate(owner, runtime_role=role, existing_only=True) == installed
        yield owner, runtime, role


def spec(**values):
    return a_spec(table="delivery_" + uuid4().hex[:10], links=[], **values)


def rows():
    return [{"visit_id": 1, "member_id": "invented-a", "amount": "1.50", "visited_on": "2026-10-01", "tags": ["x"]},
            {"visit_id": 2, "member_id": "invented-b", "amount": None, "visited_on": None, "tags": None}]


def stored(runtime, config):
    with runtime.connect() as conn:
        table = data_table(config, runtime.dialect.name)
        return [dict(r) for r in conn.execute(select(*(c for c in table.c if not c.name.startswith("_silver_"))).order_by(table.c.visit_id)).mappings()]


@pytest.mark.parametrize("mode", ["append", "upsert", "snapshot"])
def test_normal_modes_repeat_and_populated_migration(silver, mode):
    owner, runtime, role = silver
    config = spec(load_mode=mode)
    assert register(owner, config, runtime_role=role)["created"]
    assert not register(owner, config, runtime_role=role)["created"]
    sink = DatabaseSink(runtime)
    first = land(sink, config["table"], rows())
    assert (first["inserted"], first["changed"], first["deleted"]) == (2, 0, 0)
    before = stored(runtime, config)
    again = land(sink, config["table"], rows())
    assert (again["inserted"], again["changed"], again["deleted"]) == (0, 0, 0)
    assert stored(runtime, config) == before
    changed = [{**r, "amount": "4"} if r["visit_id"] == 1 else r for r in rows()]
    if mode == "append":
        with pytest.raises(Blocked, match="append only"): land(sink, config["table"], changed)
        assert stored(runtime, config) == before
    else:
        assert land(sink, config["table"], changed)["changed"] == 1
        after = stored(runtime, config)
        assert str(after[0]["amount"]) == "4.00" and after[1] == before[1]
    if mode == "snapshot":
        assert land(sink, config["table"], changed[:1])["deleted"] == 1
        with pytest.raises(Blocked, match="empty delivery"): land(sink, config["table"], [])
    assert migrate(owner, runtime_role=role, existing_only=True)
    assert land(sink, config["table"], changed[:1] if mode == "snapshot" else rows())["inserted"] == 0


@pytest.mark.parametrize("bad,pattern", [("type", "not its column's type"), ("null", "is empty"),
                                        ("duplicate", "key more than once"), ("nested", "not a nested value")])
def test_bad_delivery_is_atomic(silver, bad, pattern):
    owner, runtime, role = silver
    config = spec()
    register(owner, config, runtime_role=role)
    delivery = rows()
    if bad == "type": delivery[1]["visited_on"] = "not-a-date"
    if bad == "null": delivery[1]["visit_id"] = None
    if bad == "duplicate": delivery[1]["visit_id"] = 1
    if bad == "nested": delivery[1]["amount"] = {"unexpected": 1}
    with pytest.raises(Blocked, match=pattern): land(DatabaseSink(runtime), config["table"], delivery)
    assert stored(runtime, config) == []


def test_context_rights_and_changed_registration(silver):
    owner, runtime, role = silver
    config = spec()
    register(owner, config, runtime_role=role)
    with pytest.raises(Blocked, match="registered as a new table"):
        register(owner, {**config, "load_mode": "upsert"}, runtime_role=role)
    with pytest.raises(Blocked, match="Separate schema owner"):
        register(runtime, config, runtime_role=role)
    context = TableContext(runtime).table(config["table"])
    assert context["key"] == ["visit_id"] and context["load_mode"] == "append"
    assert TableContext(runtime).table(None)[0]["table_name"] == config["table"]
    with runtime.connect() as conn:
        assert conn.exec_driver_sql(context["next_step"]).all() == []
    target = "silver.table_spec" if runtime.dialect.name == "postgresql" else "table_spec"
    with pytest.raises(DBAPIError):
        with runtime.begin() as conn: conn.execute(text("DELETE FROM " + target))


def test_quality_and_configured_master_links(silver):
    owner, runtime, role = silver
    link = {"columns": ["member_id"], "kind": "invented-kind", "source_code": "invented-source",
            "source_key": "member_id", "mdm_id_column": "linked_id"}
    config = a_spec(table="linked_" + uuid4().hex[:10], links=[link], checks=[{
        "id": "allowed", "check": "in_set", "column": "member_id", "values": ["invented-a"],
        "on_fail": "flag", "why": "Invented quality policy"}])
    register(owner, config, runtime_role=role)
    seen = []
    def ids(source, kind, keys):
        seen.append((source, kind))
        return {key: "identity-one" for key in keys}
    sink = DatabaseSink(runtime)
    first = land(sink, config["table"], rows(), ids)
    assert first["quality"]["rows_flagged"] == 1
    assert seen == [("invented-source", "invented-kind")]
    before = stored(runtime, config)
    assert [r["quality"] for r in before] == [None, ["allowed"]]
    changed = refresh_ids(sink, config["table"], lambda *args: {"invented-a": "identity-two"})
    assert changed["rows_updated"] == {"linked_id": 2}
    after = stored(runtime, config)
    assert [r["loaded_at"] for r in after] == [r["loaded_at"] for r in before]
    assert [r["linked_id"] for r in after] == ["identity-two", None]


def test_exact_types_and_structural_json_replay(silver):
    from datetime import date, time, timedelta, timezone
    from decimal import Decimal
    owner, runtime, role = silver
    types = {"visit_id": "BIGINT", "wide": "HUGEINT", "unsigned": "UBIGINT", "money": "DECIMAL(30,8)",
             "instant": "TIMESTAMP WITH TIME ZONE", "local_time": "TIME", "local_stamp": "TIMESTAMP",
             "day": "DATE", "duration": "INTERVAL", "document": "JSON", "binary": "BLOB",
             "identity": "UUID", "flag": "BOOLEAN", "floating": "DOUBLE", "words": "VARCHAR"}
    config = spec(columns=[{"name": name, "type": logical, "nullable": name != "visit_id"}
                           for name, logical in types.items()], partition=[],
                  time={"as_of": None, "as_at": "loaded_at", "event_time": None})
    register(owner, config, runtime_role=role)
    delivered = {"visit_id": 1, "wide": 10**38, "unsigned": 2**64-1, "money": "12345678901234567890.12345678",
        "instant": datetime(2026, 10, 1, 1, 2, 3, 456789, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        "local_time": time(1, 2, 3, 456789), "local_stamp": datetime(2026, 10, 1, 1, 2, 3, 456789),
        "day": date(2026, 10, 1), "duration": timedelta(days=-2, microseconds=123456),
        "document": {"large": 10**60, "nested": [None, "Ω 😀"], "other": True},
        "binary": b"\x00\xff", "identity": "12345678-1234-5678-1234-567812345678", "flag": True,
        "floating": 1.25, "words": "Ω 😀 \t\n"}
    sink = DatabaseSink(runtime)
    assert land(sink, config["table"], [delivered])["inserted"] == 1
    with runtime.connect() as conn:
        table = data_table(config, runtime.dialect.name)
        result = dict(conn.execute(select(*(c for c in table.c if not c.name.startswith("_silver_")))).mappings().one())
    for key in delivered:
        expected = Decimal(delivered[key]) if key == "money" else delivered[key]
        assert result[key] == expected, key
    again = {**delivered, "document": dict(reversed(list(delivered["document"].items())))}
    assert land(sink, config["table"], [again])["changed"] == 0


def test_long_exact_text_keys_and_derived_refresh_do_not_alias(silver):
    owner, runtime, role = silver
    config = spec(columns=[{"name": "visit_id", "type": "VARCHAR", "nullable": False},
                           {"name": "member_id", "type": "VARCHAR", "nullable": True}], partition=[],
                  time={"as_of": None, "as_at": "loaded_at", "event_time": None})
    register(owner, config, runtime_role=role)
    keys = ["prefix" * 1000 + suffix for suffix in ("a", "b", "A", "a ")]
    sink = DatabaseSink(runtime)
    values = [{"visit_id": key, "member_id": key} for key in keys]
    assert land(sink, config["table"], values)["inserted"] == 4
    assert land(sink, config["table"], values)["changed"] == 0
    assert sink.link_keys(config, {"source_key": "member_id"}) == set(keys)


def test_concurrent_deliveries_serialize_and_replay(silver):
    owner, runtime, role = silver
    config = spec(load_mode="upsert")
    register(owner, config, runtime_role=role)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(land, DatabaseSink(runtime), config["table"], rows()) for _ in range(2)]
        results = [job.result(timeout=20) for job in jobs]
    assert sorted(r["inserted"] for r in results) == [0, 2]
    assert all(r["changed"] == 0 for r in results)
    assert len(stored(runtime, config)) == 2


def test_structurally_equal_json_numbers_do_not_change_append_rows(silver):
    owner, runtime, role = silver
    config = spec()
    register(owner, config, runtime_role=role)
    sink = DatabaseSink(runtime)
    first = [{**r, "tags": {"x": 1, "zero": 0}} for r in rows()]
    second = [{**r, "tags": {"zero": -0.0, "x": 1.0}} for r in rows()]
    land(sink, config["table"], first)
    assert land(sink, config["table"], second)["changed"] == 0


def test_binary_keys_land_and_repeat_exactly(silver):
    owner, runtime, role = silver
    config = spec(columns=[{"name": "visit_id", "type": "BLOB", "nullable": False}], partition=[],
                  time={"as_of": None, "as_at": "loaded_at", "event_time": None})
    register(owner, config, runtime_role=role)
    values = [{"visit_id": b"\x00\xff"}, {"visit_id": b"\x00\x00"}]
    sink = DatabaseSink(runtime)
    assert land(sink, config["table"], values)["inserted"] == 2
    assert land(sink, config["table"], values)["inserted"] == 0


def test_exact_text_refresh_preserves_case_accents_and_spaces(silver):
    owner, runtime, role = silver
    link = {"columns": ["member_id"], "kind": "invented-kind", "source_code": "invented-source",
            "source_key": "member_id", "mdm_id_column": "linked_id"}
    config = a_spec(table="exact_" + uuid4().hex[:10], links=[link])
    register(owner, config, runtime_role=role)
    keys = ["a", "A", "á", "a "]
    values = [{"visit_id": n, "member_id": key} for n, key in enumerate(keys)]
    sink = DatabaseSink(runtime)
    land(sink, config["table"], values, lambda *args: {})
    found = {key: "invented-id-" + str(n) for n, key in enumerate(keys)}
    assert sink.link_keys(config, link) == set(keys)
    assert sink.set_ids(config, link, found) == 4
    assert [row["linked_id"] for row in stored(runtime, config)] == list(found.values())
    assert sink.set_ids(config, link, found) == 0


def test_out_of_range_delivery_never_commits(silver):
    owner, runtime, role = silver
    config = spec()
    register(owner, config, runtime_role=role)
    bad = rows()
    bad[1]["visit_id"] = 2**63
    with pytest.raises(Blocked, match="not its column's type"):
        land(DatabaseSink(runtime), config["table"], bad)
    assert stored(runtime, config) == []


def test_normal_cli_reads_configured_connection(silver, tmp_path, monkeypatch, capsys):
    import json
    from edgar_warehouse.cli import main
    owner, runtime, role = silver
    config = spec()
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(config))
    delivered = tmp_path / "rows.jsonl"
    delivered.write_text("\n".join(json.dumps(row) for row in rows()))
    monkeypatch.setenv("SILVER_MIGRATION_DATABASE_URL", owner.url.render_as_string(hide_password=False))
    monkeypatch.setenv("SILVER_DATABASE_URL", runtime.url.render_as_string(hide_password=False))
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    assert main(["silver", "register", str(path), "--runtime-role", role]) == 0
    assert json.loads(capsys.readouterr().out)["created"]
    assert main(["silver", "land", config["table"], str(delivered)]) == 0
    assert json.loads(capsys.readouterr().out)["inserted"] == 2
    assert main(["silver", "describe", config["table"]]) == 0
    assert json.loads(capsys.readouterr().out)["key"] == ["visit_id"]


def test_key_lookup_uses_destination_unique_index(silver):
    import json
    from sqlalchemy import LargeBinary, cast, func, literal
    owner, runtime, role = silver
    config = spec()
    register(owner, config, runtime_role=role)
    land(DatabaseSink(runtime), config["table"], rows())
    table = data_table(config, runtime.dialect.name)
    query = select(table.c.visit_id).where(table.c.visit_id == 1)
    with owner.begin() as conn:
        if conn.dialect.name == "mysql":
            query = query.where(table.c._silver_key == func.sha2(cast(func.json_array(literal(1)), LargeBinary), 256))
        else:
            conn.execute(text("SET LOCAL enable_seqscan=off"))
        sql = str(query.compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True}))
        if conn.dialect.name == "mysql":
            plan = conn.execute(text("EXPLAIN " + sql)).mappings().one()
            assert plan["key"] == "silver_key" and plan["type"] in {"const", "ref"}
        else:
            plan = conn.scalar(text("EXPLAIN (FORMAT JSON) " + sql))
            assert "Index" in json.dumps(plan)


def test_structural_json_keys_and_signed_zero_are_unique(silver):
    owner, runtime, role = silver
    for logical, first, same in [("JSON", {"x": 1}, {"x": 1.0}), ("DOUBLE", -0.0, 0.0)]:
        config = spec(columns=[{"name": "visit_id", "type": logical, "nullable": False}], partition=[],
                      time={"as_of": None, "as_at": "loaded_at", "event_time": None})
        register(owner, config, runtime_role=role)
        sink = DatabaseSink(runtime)
        assert land(sink, config["table"], [{"visit_id": first}])["inserted"] == 1
        assert land(sink, config["table"], [{"visit_id": same}])["inserted"] == 0
        with pytest.raises(Blocked, match="key more than once"):
            land(sink, config["table"], [{"visit_id": first}, {"visit_id": same}])


def test_raw_json_decimal_transport_does_not_pass_through_float(silver):
    import json
    from decimal import Decimal
    from sqlalchemy import Text, cast
    owner, runtime, role = silver
    config = spec()
    register(owner, config, runtime_role=role)
    raw = '{"large":9007199254740993.0,"fraction":0.123456789012345678901234567890123,"tiny":1e-600}'
    sink = DatabaseSink(runtime)
    delivered = [{**row, "tags": raw} for row in rows()]
    assert land(sink, config["table"], delivered)["inserted"] == 2
    with runtime.connect() as conn:
        table = data_table(config, runtime.dialect.name)
        found = conn.scalar(select(cast(table.c.tags, Text)).where(table.c.visit_id == 1))
    assert json.loads(found, parse_float=Decimal) == json.loads(raw, parse_float=Decimal)
    assert land(sink, config["table"], delivered)["changed"] == 0


def test_text_transport_is_identical_for_native_scalar_inputs(silver):
    from datetime import date
    from decimal import Decimal
    owner, runtime, role = silver
    config = spec(columns=[{"name": "visit_id", "type": "BIGINT", "nullable": False},
                           {"name": "words", "type": "VARCHAR", "nullable": True}], partition=[],
                  time={"as_of": None, "as_at": "loaded_at", "event_time": None})
    register(owner, config, runtime_role=role)
    inputs = [True, False, b"\x00\xff", date(2026, 10, 1), datetime(2026, 10, 1, 1, 2), Decimal("1.50"), 1.25]
    values = [{"visit_id": n, "words": value} for n, value in enumerate(inputs)]
    sink = DatabaseSink(runtime)
    assert land(sink, config["table"], values)["inserted"] == 7
    assert [row["words"] for row in stored(runtime, config)] == ["true", "false", "\\x00ff", "2026-10-01",
                                                               "2026-10-01T01:02:00", "1.50", "1.25"]
    assert land(sink, config["table"], values)["changed"] == 0
