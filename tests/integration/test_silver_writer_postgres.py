"""Real PG16: the silver writer (profiling ticket 06).

The silver schema migrates from zero with the owner and a restricted runtime
apart; a spec becomes a table with a comment on every column; the same spec
again changes nothing and a changed spec is refused; each load mode reruns
without change; a link's MDM id is read from a real MDM database, and a record
MDM has not mastered keeps an empty id until a later landing fills it.

CI starts PG16 in Docker, like every PG16 test here. PG16_ADMIN_URL points the
module at an existing PG16 server instead (a superuser URL).
"""

from __future__ import annotations

import contextlib
import os
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land, refresh_ids
from tests.integration import test_clean_entity_context_postgres as entity_context
from tests.integration import test_clean_mdm_postgres as core
from tests.support import pg16
from tests.unit.test_silver_writer import a_spec

RUNTIME = "silver_runtime"


@pytest.fixture(scope="module")
def postgres():
    if url := os.environ.get("PG16_ADMIN_URL"):  # a server kept between runs
        yield from _servers(url)
        return
    # Docker in CI; PG16_SERVER=pgserver runs on a local PostgreSQL 16 (tests/support/pg16.py).
    with pg16.server() as found:
        yield from _servers(found.url())


def _servers(url):
    admin = create_engine(url)
    deadline = time.monotonic() + 30
    while True:
        try:
            with admin.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except DBAPIError:
            if time.monotonic() > deadline:
                pytest.fail("PostgreSQL did not become ready")
            time.sleep(0.1)
    with admin.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
        # A server kept between runs still holds the MDM template an earlier run made.
        conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {core.TEMPLATE} WITH (FORCE)")
        if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='clean_application'")):
            conn.execute(text("CREATE ROLE clean_application LOGIN PASSWORD 'test' "
                              "NOSUPERUSER NOCREATEDB NOCREATEROLE"))
    app = create_engine(admin.url.set(username="clean_application", password="test"))
    yield admin, app
    app.dispose()
    admin.dispose()
    core._templates.pop(core.server_key(admin), None)


@contextlib.contextmanager
def silver_database(admin):
    """An empty database for the silver schema, its owner and its restricted runtime login."""
    name = f"silver_{uuid4().hex[:10]}"
    server = admin.execution_options(isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:r"), {"r": RUNTIME}):
            conn.exec_driver_sql(f"CREATE ROLE {RUNTIME} LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    owner = create_engine(admin.url.set(database=name))
    runtime = create_engine(admin.url.set(database=name, username=RUNTIME, password="test"))
    try:
        yield owner, runtime
    finally:
        owner.dispose()
        runtime.dispose()
        with server.connect() as conn:
            conn.exec_driver_sql(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def stores(postgres, database):
    """A migrated silver database beside a real MDM database holding mastered records a, b and c."""
    admin, _ = postgres
    mastered = entity_context.load_group(database)
    with silver_database(admin) as (owner, runtime):
        with pytest.raises(Blocked, match="not initialized"):
            silver.migrate(owner, runtime_role=RUNTIME, existing_only=True)
        first = silver.migrate(owner, runtime_role=RUNTIME)
        assert silver.migrate(owner, runtime_role=RUNTIME, existing_only=True) == first  # installs nothing
        yield owner, runtime, MdmIds(database.application), mastered


def visit_spec(**more):
    link = {"columns": ["member_id"], "kind": "company", "source_code": "fixture.primary", "to_part": "member",
            "source_key": "member_id", "mdm_id_column": "member_id_mdm_id", "inclusion": 1.0}
    return a_spec(links=[link], **more)


def visits(*changes):
    base = [{"visit_id": 1, "member_id": "a", "amount": "10.50", "visited_on": "2026-10-01", "tags": ["x"]},
            {"visit_id": 2, "member_id": "b", "amount": "3", "visited_on": "2026-10-02", "tags": None},
            {"visit_id": 3, "member_id": "z", "amount": None, "visited_on": "2026-10-03", "tags": []}]
    for number, field, value in changes:
        base[number - 1] = {**base[number - 1], field: value}
    return base


def table(runtime, name="visit"):
    with runtime.connect() as conn:
        return {r["visit_id"]: dict(r) for r in conn.execute(
            text(f'SELECT * FROM silver."{name}" ORDER BY visit_id')).mappings()}


def test_the_runtime_reads_specs_and_writes_rows_but_cannot_register_or_create(stores):
    owner, runtime, _, _ = stores
    with runtime.connect() as conn:
        assert not conn.scalar(text("SELECT has_schema_privilege('silver','CREATE')"))
        assert not conn.scalar(text("SELECT has_table_privilege('silver.table_spec','INSERT')"))
    with pytest.raises(Blocked, match="Separate schema owner"):
        silver.register(runtime, visit_spec(), runtime_role=RUNTIME)


def test_a_spec_becomes_a_table_with_comments_and_a_changed_spec_is_refused(stores):
    owner, runtime, _, _ = stores
    assert silver.register(owner, visit_spec(), runtime_role=RUNTIME)["created"] is True
    assert silver.register(owner, visit_spec(), runtime_role=RUNTIME)["created"] is False
    with pytest.raises(Blocked, match="registered as a new table"):
        silver.register(owner, visit_spec(load_mode="upsert"), runtime_role=RUNTIME)
    with owner.connect() as conn:
        types = dict(conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='silver' AND table_name='visit'")).all())
        comments = conn.execute(text(
            "SELECT count(*) FROM information_schema.columns c WHERE table_schema='silver' AND table_name='visit' "
            "AND col_description('silver.visit'::regclass, c.ordinal_position) IS NULL")).scalar()
        context = conn.execute(text("SELECT * FROM silver.table_context WHERE table_name='visit'")).mappings().one()
    assert types == {"visit_id": "bigint", "member_id": "text", "amount": "numeric", "visited_on": "date",
                     "tags": "jsonb", "member_id_mdm_id": "text", "loaded_at": "timestamp with time zone"}
    assert comments == 0  # every column says what it holds
    assert context["links"] == [{"columns": ["member_id"], "kind": "company", "source_code": "fixture.primary",
                                 "source_key": "member_id", "mdm_id_column": "member_id_mdm_id", "inclusion": 1.0}]
    assert context["key"] == ["visit_id"] and context["load_mode"] == "append"


def test_append_lands_typed_rows_with_mdm_ids_reruns_unchanged_and_refuses_a_changed_row(stores, database):
    owner, runtime, ids, mastered = stores
    silver.register(owner, visit_spec(), runtime_role=RUNTIME)
    sink = PostgresSink(runtime)
    first = land(sink, "visit", visits(), ids)
    assert (first["inserted"], first["changed"], first["mdm_keys_found"]) == (3, 0, 2)
    rows = table(runtime)
    assert rows[1]["member_id_mdm_id"] == mastered["a"] and rows[2]["member_id_mdm_id"] == mastered["b"]
    assert rows[3]["member_id"] == "z" and rows[3]["member_id_mdm_id"] is None  # not mastered: empty id
    assert str(rows[1]["amount"]) == "10.50" and rows[1]["tags"] == ["x"] and rows[3]["tags"] == []
    again = land(sink, "visit", visits(), ids)
    assert (again["inserted"], again["changed"], again["deleted"], again["mdm_ids_updated"]) == (0, 0, 0, 0)
    assert table(runtime) == rows
    with pytest.raises(Blocked, match="append only"):
        land(sink, "visit", visits((2, "amount", "4")), ids)
    assert table(runtime) == rows  # nothing written
    # Mastering z later: the next landing fills its id and changes nothing else.
    z = entity_context.company("z")
    identity, binding = core.identity_and_binding(z, published_at="2026-01-02T00:00:00+00:00")
    core.apply(database, 2, assertions=[z], identities=[identity], decisions=[binding])
    filled = land(sink, "visit", visits(), ids)
    assert (filled["inserted"], filled["changed"], filled["mdm_ids_updated"]) == (0, 0, 1)
    assert table(runtime)[3]["member_id_mdm_id"] == identity["entity_id"]
    # Migrating again over the populated schema installs nothing and keeps the runtime's rights.
    assert silver.migrate(owner, runtime_role=RUNTIME, existing_only=True)
    assert land(sink, "visit", visits(), ids)["inserted"] == 0


def test_a_flagged_row_lands_with_its_failed_checks_and_a_refused_row_does_not(stores, database):
    owner, runtime, ids, _ = stores
    checks = [{"id": "known_member", "check": "in_set", "column": "member_id", "values": ["a", "b"],
               "on_fail": "flag", "why": "members are a or b"},
              {"id": "has_day", "check": "one_value", "column": "member_id", "per": "visited_on",
               "on_fail": "exception", "why": "one member a day"}]
    silver.register(owner, visit_spec(table="checked_visit", checks=checks), runtime_role=RUNTIME)
    with owner.connect() as conn:
        assert "known_member: members are a or b" in conn.scalar(text(
            "SELECT col_description('silver.checked_visit'::regclass, attnum) FROM pg_attribute "
            "WHERE attrelid = 'silver.checked_visit'::regclass AND attname = 'quality'"))
    sink = PostgresSink(runtime)
    delivered = visits() + [{"visit_id": 4, "member_id": "a", "amount": None, "visited_on": "2026-10-09", "tags": None},
                            {"visit_id": 5, "member_id": "b", "amount": None, "visited_on": "2026-10-09", "tags": None}]
    first = land(sink, "checked_visit", delivered, ids)
    assert first["inserted"] == 3 and (first["quality"]["rows_flagged"], first["quality"]["rows_refused"]) == (1, 2)
    rows = table(runtime, "checked_visit")
    assert {k: r["quality"] for k, r in rows.items()} == {1: None, 2: None, 3: ["known_member"]}  # jsonb, read back
    again = land(sink, "checked_visit", delivered, ids)
    assert (again["inserted"], again["changed"], again["quality_updated"]) == (0, 0, 0)
    assert table(runtime, "checked_visit") == rows
    # One member a day, flagged: delivered together, rows 1 and 2 tie on their day and are both flagged;
    # row 1 delivered alone passes. An append table takes the moved flag, and nothing else changes.
    day = [{"id": "one_member_a_day", "check": "one_value", "column": "member_id", "per": "visited_on",
            "on_fail": "flag", "why": "one member a day"}]
    silver.register(owner, visit_spec(table="daily_visit", checks=day), runtime_role=RUNTIME)
    same_day = [{**v, "visited_on": "2026-10-01"} for v in visits()[:2]]
    land(sink, "daily_visit", same_day, ids)
    assert {k: r["quality"] for k, r in table(runtime, "daily_visit").items()} == {
        1: ["one_member_a_day"], 2: ["one_member_a_day"]}
    alone = land(sink, "daily_visit", same_day[:1], ids)
    assert (alone["changed"], alone["quality_updated"]) == (0, 1)
    assert table(runtime, "daily_visit")[1]["quality"] is None


def test_refresh_fills_ids_of_rows_already_landed_and_follows_a_merge(stores, database):
    owner, runtime, ids, mastered = stores
    silver.register(owner, visit_spec(), runtime_role=RUNTIME)
    sink = PostgresSink(runtime)
    land(sink, "visit", visits(), ids)
    # z is mastered after its row landed; the row is never delivered again.
    z = entity_context.company("z")
    identity, binding = core.identity_and_binding(z, published_at="2026-01-02T00:00:00+00:00")
    core.apply(database, 2, assertions=[z], identities=[identity], decisions=[binding])
    assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 1}
    assert table(runtime)[3]["member_id_mdm_id"] == identity["entity_id"]
    assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 0}
    # p and q (no identifiers, so nothing refuses the merge) land apart, then are merged:
    # both rows then point at the survivor.
    p_, q_ = (core.source(key, fields={"name": f"Company {key}"}, identifiers={}) for key in ("p", "q"))
    pairs = [core.identity_and_binding(r, published_at="2026-01-03T00:00:00+00:00") for r in (p_, q_)]
    core.apply(database, 3, assertions=[p_, q_], identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    left, right = (i["entity_id"] for i, _ in pairs)
    more = [{"visit_id": 4, "member_id": "p"}, {"visit_id": 5, "member_id": "q"}]
    land(sink, "visit", more, ids)
    assert table(runtime)[4]["member_id_mdm_id"] == left and table(runtime)[5]["member_id_mdm_id"] == right
    loaded = {k: r["loaded_at"] for k, r in table(runtime).items()}
    core.apply(database, 4, decisions=[core.decision(
        "merge", actor="steward", reason="same company", at="2026-01-04T00:00:00+00:00", left=left, right=right)])
    canonical = {key: body["canonical_id"] for key, body in core.documents(database, "entity").items()
                 if key in {left, right}}
    survivor = canonical[left] or left
    assert survivor == (canonical[right] or right)
    assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 1}
    rows = table(runtime)
    assert rows[4]["member_id_mdm_id"] == rows[5]["member_id_mdm_id"] == survivor
    assert rows[1]["member_id_mdm_id"] == mastered["a"]  # unmerged rows keep their id
    assert {k: r["loaded_at"] for k, r in rows.items()} == loaded  # an id is not a delivered value


def test_a_name_with_symbols_is_quoted_everywhere(stores):
    owner, runtime, ids, _ = stores
    odd = a_spec(table="Odd % : Table", columns=[
        {"name": "Line No.", "type": "BIGINT", "nullable": False},
        {"name": "Price ($) 100%", "type": "DOUBLE", "nullable": True}],
        key=["Line No."], links=[], time={"as_of": None, "as_at": "loaded_at", "event_time": None}, partition=[])
    silver.register(owner, odd, runtime_role=RUNTIME)
    assert land(PostgresSink(runtime), "Odd % : Table", [{"Line No.": 1, "Price ($) 100%": 2.5}])["inserted"] == 1
    with runtime.connect() as conn:  # the table and its columns carry the names exactly as the spec writes them
        names = conn.execute(text("SELECT column_name FROM information_schema.columns "
                                  "WHERE table_schema='silver' AND table_name=:t ORDER BY ordinal_position"),
                             {"t": "Odd % : Table"}).scalars().all()
    assert names == ["Line No.", "Price ($) 100%", "loaded_at"]


def test_an_agent_reads_a_table_spec_through_context(stores):
    import json

    from edgar_warehouse.context import LIMIT_BYTES, ContextError, store_for
    from edgar_warehouse.silver_writer.context import TableContext

    owner, runtime, _, _ = stores
    silver.register(owner, visit_spec(), runtime_role=RUNTIME)
    assert store_for("silver").variable == "SILVER_DATABASE_URL"
    answer = TableContext(runtime).answer(entity_context.args("silver", "visit"))
    assert len(json.dumps(answer).encode()) <= LIMIT_BYTES
    assert answer["kind"] == "silver table" and answer["key"] == ["visit_id"] and answer["load_mode"] == "append"
    assert answer["links"][0]["mdm_id_column"] == "member_id_mdm_id"
    assert answer["trust"]["spec_ref"].startswith("silver.table_spec/visit@")
    with runtime.connect() as conn:  # the next step an agent is offered runs as written
        assert conn.exec_driver_sql(answer["next_step"]).all() == []
    listed = TableContext(runtime).answer(entity_context.args("silver"))
    assert [t["table_name"] for t in listed["tables"]] == ["visit"]
    with pytest.raises(ContextError, match="No silver table"):
        TableContext(runtime).answer(entity_context.args("silver", "nope"))


def test_legacy_interval_text_transport_is_preserved(stores):
    from datetime import timedelta
    owner, runtime, _, _ = stores
    config = a_spec(links=[], columns=[{"name": "visit_id", "type": "BIGINT", "nullable": False},
        {"name": "duration", "type": "INTERVAL", "nullable": True}], partition=[],
        time={"as_of": None, "as_at": "loaded_at", "event_time": None})
    silver.register(owner, config, runtime_role=RUNTIME)
    assert land(PostgresSink(runtime), "visit", [{"visit_id": 1, "duration": "2 days 01:02:03.123456"}])["inserted"] == 1
    assert table(runtime)[1]["duration"] == timedelta(days=2, hours=1, minutes=2, seconds=3, microseconds=123456)
