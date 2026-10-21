"""Normal reference caller on each currently selected engine; invented inputs only."""
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError
from uuid import uuid4
import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rdm.database import migrate
from edgar_warehouse.rdm.storage import scope
from edgar_warehouse.rdm.store import RDM, read_published


@pytest.fixture(scope="module")
def reference(database_factory):
    with database_factory() as (owner, runtime, role):
        arguments = {"runtime_role": role, "database_name": owner.url.database}
        with pytest.raises(Blocked, match="not initialized"):
            migrate(owner, existing_only=True, **arguments)
        installed = migrate(owner, **arguments)
        assert migrate(owner, existing_only=True, **arguments) == installed
        yield RDM(runtime, reserved_subjects=()), owner, arguments


def draft(store, *, name=None, version="1", supersedes=None, codes=None, **kwargs):
    name = name or "catalog-" + uuid4().hex
    store.draft({"code_set": name, "name": "Invented reference values"}, version,
        codes if codes is not None else [{"code": "a", "label": "First"},
            {"code": "b", "label": "Second", "parent_code": "a"}],
        created_by="drafter", supersedes=supersedes, **kwargs)
    return name


def approve(store, name, version="1"):
    return store.approve(name, version, by="operator", words="Approve this invented version")


def test_normal_lifecycle_and_pinned_artifacts(reference, tmp_path):
    store, *_ = reference
    name = draft(store, levels=[{"depth": 1, "name": "Root"}, {"depth": 2, "name": "Leaf"}],
        evidence={"count": 10**60, "note": "Ω 😀"},
        crosswalk=[{"from_code": "b", "to_set": "outside-standard", "to_version": "outside",
                    "to_code": "alternate", "match_type": "exact"}],
        hints=[{"kind": "meaning", "text": "Invented hierarchy"}],
        usage=[{"store": "silver", "object": "arbitrary_rows", "field": "reference_key"}])
    assert store.version(name, "1")["evidence"]["count"] == 10**60
    with pytest.raises(Blocked, match="not an approved"):
        store.publish(name, "1", out=tmp_path)
    with pytest.raises(DBAPIError, match="own draft"):
        store.approve(name, "1", by="drafter", words="approve")
    with pytest.raises(DBAPIError, match="exact words"):
        store.approve(name, "1", by="operator", words=" ")
    assert approve(store, name)["approved_at"] is not None
    published = store.publish(name, "1", out=tmp_path)
    assert published["codes"] == 2 and store.verify(name, "1")["matches"]
    rows = read_published(tmp_path, name, "1", published["sha256"])
    assert [row["level"] for row in rows] == ["Root", "Leaf"]
    assert rows[1]["crosswalk"] == [["outside-standard", "outside", "alternate", "exact"]]
    described = store.describe(name)
    assert described["counts"] == {"codes": 2, "invalid": 0, "with_parent": 1}
    assert described["hints"] == {"meaning": ["Invented hierarchy"]}
    listed = {row["code_set"]: row for row in store.code_sets()}
    assert listed[name]["published_version"] == "1"


def test_namespace_is_injected_without_importing_a_master_catalog(reference):
    store, *_ = reference
    other = RDM(store.engine, reserved_subjects={"arbitrary-kind"})
    with pytest.raises(Blocked, match="names a master kind"):
        draft(other, name="arbitrary-kind")
    assert draft(store, name="arbitrary-kind") == "arbitrary-kind"


def test_supersession_retirement_and_history(reference, tmp_path):
    store, *_ = reference
    name = draft(store)
    approve(store, name)
    first = store.publish(name, "1", out=tmp_path)
    draft(store, name=name, version="2", supersedes="1")
    approve(store, name, "2")
    assert store.publish(name, "2", out=tmp_path)["superseded"] == "1"
    assert store.version(name, "1")["valid_to"] == store.version(name, "2")["valid_from"]
    assert store.verify(name, "1")["matches"] and read_published(tmp_path, name, "1", first["sha256"])
    store.retire(name, "2")
    assert store.version(name, "2")["valid_to"] is not None
    draft(store, name=name, version="3", supersedes="2")
    approve(store, name, "3")
    assert store.publish(name, "3", out=tmp_path)["superseded"] is None


def test_content_and_approval_are_immutable_after_approval(reference):
    store, *_ = reference
    name = draft(store)
    approve(store, name)
    table = store.tables["code"]
    with pytest.raises(DBAPIError, match="Only a draft"):
        with store.engine.begin() as conn:
            conn.execute(table.update().where(scope(conn, table, code_set=name, version="1")).values(label="Changed"))
    version = store.tables["code_set_version"]
    with pytest.raises(DBAPIError, match="Approval is recorded once"):
        with store.engine.begin() as conn:
            conn.execute(version.update().where(scope(conn, version, code_set=name, version="1")).values(approved_words="Changed"))


def test_cycles_and_artifact_failure_publish_nothing(reference, tmp_path, monkeypatch):
    store, *_ = reference
    name = draft(store, codes=[{"code": "a", "label": "First", "parent_code": "b"},
                              {"code": "b", "label": "Second", "parent_code": "a"}])
    approve(store, name)
    with pytest.raises(Blocked, match="cycle"):
        store.publish(name, "1", out=tmp_path)
    assert store.version(name, "1")["status"] == "approved"
    name = draft(store)
    approve(store, name)
    def fail(*args):
        raise OSError("Invented artifact failure")
    monkeypatch.setattr(store, "_write", fail)
    with pytest.raises(OSError, match="artifact failure"):
        store.publish(name, "1", out=tmp_path)
    assert store.version(name, "1")["status"] == "approved"
    table = store.tables["code_path"]
    with store.engine.connect() as conn:
        assert not conn.execute(select(table.c.code).where(scope(conn, table, code_set=name, version="1"))).all()


def test_exact_unbounded_keys_and_rollback(reference):
    store, *_ = reference
    keys = ["A", "a", "a ", "Ω😀" * 1200, "p" * 1200 + "b", "p" * 1200 + "a"]
    name = draft(store, codes=[{"code": value, "label": "Invented label"} for value in keys])
    assert [row["code"] for row in store.codes(name, "1")] == sorted(keys)
    assert [row["code"] for row in store.describe(name, samples=len(keys))["sample_codes"]][:3] == sorted(keys)[:3]
    duplicate = "catalog-" + uuid4().hex
    with pytest.raises(DBAPIError):
        draft(store, name=duplicate, codes=[{"code": "a", "label": "First"}, {"code": "a", "label": "Second"}])
    assert duplicate not in {row["code_set"] for row in store.code_sets()}


def test_competing_publications_choose_one_successor(reference, tmp_path):
    store, *_ = reference
    name = draft(store)
    draft(store, name=name, version="2")
    approve(store, name)
    approve(store, name, "2")
    def publish(version):
        try:
            store.publish(name, version, out=tmp_path)
            return "published"
        except Blocked:
            return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(publish, ("1", "2")))
    assert sorted(outcomes) == ["published", "refused"]


def test_runtime_cannot_mutate_catalog_or_migration_history(reference):
    store, owner, _ = reference
    name = draft(store)
    table = store.tables["code_set"]
    with pytest.raises(DBAPIError):
        with store.engine.begin() as conn:
            conn.execute(table.update().where(scope(conn, table, code_set=name)).values(name="Changed"))
    if owner.dialect.name == "mysql":
        with pytest.raises(DBAPIError):
            with store.engine.begin() as conn:
                conn.execute(text("UPDATE rdm_migrations SET complete=0"))


def test_long_common_prefix_crosswalks_stay_distinct(reference):
    store, *_ = reference
    versions = ["v" * 1300 + "a", "v" * 1300 + "b"]
    name = draft(store, crosswalk=[{"from_code": "a", "to_set": "outside-standard", "to_version": version,
                                   "to_code": "alternate", "match_type": "exact"} for version in versions])
    answer = store.describe(name, samples=0)
    # The public answer is bounded; these two complete rows fit together.
    assert [(r["to_version"], r["rows"]) for r in answer["maps_to"]] == [(v, 1) for v in versions]


def test_context_reads_published_values_and_history(reference, tmp_path):
    from argparse import Namespace
    from edgar_warehouse.rdm.context import CodeContext

    store, *_ = reference
    name = draft(store, labels=[{"code": "a", "label": "Alternate Ω", "kind": "synonym"}])
    approve(store, name)
    store.publish(name, "1", out=tmp_path)
    args = Namespace(subject=name, key="a", as_of=None, as_at=None, hops=1, relationship_type=None,
                     search=None, detail="full", page=None, limit=5)
    answer = CodeContext(store.engine).answer(args)
    assert answer["synonyms"] == ["Alternate Ω"] and answer["trust"]["version"] == "1"
    assert answer["trust"]["valid_from"].endswith("+00:00")


def test_indexed_exact_code_lookup(reference):
    store, owner, _ = reference
    name = draft(store)
    table = store.tables["code"]
    with owner.begin() as conn:
        query = select(table.c.label).where(scope(conn, table, code_set=name, version="1", code="a"))
        compiled = query.compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True})
        if owner.dialect.name == "mysql":
            plans = conn.execute(text("EXPLAIN " + str(compiled))).mappings().all()
            assert any(row["key"] == "PRIMARY" and row["type"] in {"const", "ref", "eq_ref"} for row in plans)
        else:
            conn.execute(text("SET LOCAL enable_seqscan=off"))
            plans = conn.execute(text("EXPLAIN " + str(compiled))).scalars().all()
            assert any("Index" in row and "code_pkey" in row for row in plans)


def test_approval_waits_for_an_admitted_content_edit(reference):
    store, *_ = reference
    name = draft(store)
    table = store.tables["code"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.engine.begin() as conn:
            conn.execute(table.update().where(scope(conn, table, code_set=name, version="1", code="a")).values(
                label="Changed while still a draft"))
            approval = pool.submit(approve, store, name)
            with pytest.raises(TimeoutError):
                approval.result(timeout=0.2)
        assert approval.result(timeout=10)["status"] == "approved"
    assert store.codes(name, "1")[0]["label"] == "Changed while still a draft"
    with pytest.raises(DBAPIError, match="Only a draft"):
        with store.engine.begin() as conn:
            conn.execute(table.update().where(scope(conn, table, code_set=name, version="1", code="a")).values(label="Too late"))


def test_normal_cli_and_read_only_context_use_the_selected_connection(reference, tmp_path, monkeypatch, capsys):
    from argparse import Namespace
    from edgar_warehouse import context
    from edgar_warehouse.rdm import cli

    store, *_ = reference
    name = draft(store)
    approve(store, name)
    store.publish(name, "1", out=tmp_path)
    monkeypatch.setenv("RDM_DATABASE_URL", store.engine.url.render_as_string(hide_password=False))
    assert cli._handle(Namespace(rdm_command="list")) == 0
    listed = json.loads(capsys.readouterr().out)
    assert name in {row["code_set"] for row in listed}
    args = Namespace(subject=name, key="a", as_of=None, as_at=None, hops=1, relationship_type=None,
                     search=None, detail="full", page=None, limit=5)
    assert context._handle(args) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["trust"]["version"] == "1"
    assert store.engine.url.render_as_string(hide_password=False) not in output


def test_instants_remain_utc_in_another_session_timezone(reference, tmp_path):
    store, *_ = reference
    with store.engine.begin() as conn:
        conn.execute(text("SET time_zone='+05:30'" if conn.dialect.name == "mysql" else "SET TIME ZONE 'Asia/Kolkata'"))
    name = draft(store)
    approved = approve(store, name)
    store.publish(name, "1", out=tmp_path)
    version = store.version(name, "1")
    assert approved["approved_at"].utcoffset().total_seconds() == 0
    assert version["created_at"].utcoffset().total_seconds() == 0
    assert version["valid_from"].utcoffset().total_seconds() == 0


@pytest.mark.parametrize("words,expected,method", [
    ("first", ["a"], "label"), ("FIRST", ["a"], "label"), ("irst", ["a"], "label contains"),
    ("alternative", ["a"], "synonym"), ("%", [], None), ("_", [], None),
    ("first reference", ["a"], "label"), ('"first reference"', ["a"], "label"),
    ("first OR second", ["a", "b"], None), ("reference -second", ["a"], "label"),
    ("chartered", ["c"], "synonym"), ("notfound", [], None),
])
def test_context_search_words_phrases_and_literal_fallback(reference, tmp_path, words, expected, method):
    from argparse import Namespace
    from edgar_warehouse.rdm.context import CodeContext

    store, *_ = reference
    name = draft(store, codes=[{"code": "a", "label": "First reference"},
                              {"code": "b", "label": "Second reference"},
                              {"code": "c", "label": "Alpha catalogue"}],
        labels=[{"code": "a", "label": "Alternative reference", "kind": "synonym"},
                {"code": "c", "label": "Chartered code", "kind": "synonym"}])
    approve(store, name)
    store.publish(name, "1", out=tmp_path)
    args = Namespace(subject=name, key=None, as_of=None, as_at=None, hops=1, relationship_type=None,
                     search=words, detail="brief", page=None, limit=5)
    found = CodeContext(store.engine).answer(args)["matches"]
    assert sorted(row["code"] for row in found) == expected
    if method:
        assert all(row["matched_by"] == method for row in found)


@pytest.mark.parametrize("words,label,expected", [
    ("first", "first", 0.1), ("first", "first first", 0.2),
    ("first second", "first second", 0.1), ("first second", "first ignored second", 0.05),
    ("first OR second", "first second", 0.2), ("first -second", "first", 0.1),
    ('"first second"', "first ignored second", 0.0),
    ("first second", "first second first second", 0.3),
])
def test_native_search_density_matches_the_postgres_reference(reference, words, label, expected):
    import edgar_control

    store, owner, _ = reference
    found = json.loads(edgar_control.prepare_reference_search(json.dumps({
        "words": words, "position_weight": 0.1, "synonym_weight": 0.9, "limit": 5,
        "rows": [{"code": "a", "label": label, "label_path": label, "search_text": label,
                  "matched_by": "label", "rank": 0}]})))[0]["rank"]
    assert found == pytest.approx(expected, abs=1e-7)
    if owner.dialect.name == "postgresql":
        with store.engine.connect() as conn:
            original = conn.scalar(text("SELECT ts_rank_cd(to_tsvector('simple',:label),websearch_to_tsquery('simple',:words))"),
                                   {"label": label, "words": words})
        assert found == pytest.approx(original, abs=1e-7)
