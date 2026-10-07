"""Real PG16: `rdm.code_context` and `edgar-warehouse context <code_set>` (profiling ticket 05, RDM part).

The view's migration (002) upgrades a populated RDM database. A code comes
back named, with its meaning, its place in the hierarchy, the code sets it
maps to and the version's pin; search finds labels and synonyms (full-text
first, then the words as typed); --as-of and --as-at read the version current
then, as it stood; every answer is at most 8 KB, and an error names the
command that would work.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from edgar_warehouse import context
from edgar_warehouse.context import LIMIT_BYTES, ContextError
from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rdm import database
from edgar_warehouse.rdm.context import CodeContext
from edgar_warehouse.rdm.store import RDM
from tests.integration.test_rdm_postgres import OPERATOR, _import, server


def args(subject, key=None, **more):
    base = dict(search=None, limit=5, as_of=None, as_at=None, hops=1, relationship_type="", detail="brief", page=None)
    return argparse.Namespace(subject=subject, key=key, **{**base, **more})


def ask(engine, subject, key=None, **more):
    answer = CodeContext(engine).answer(args(subject, key, **more))
    assert len(json.dumps(answer, ensure_ascii=False).encode()) <= LIMIT_BYTES
    return answer


def _now(engine):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT clock_timestamp()"))


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """RDM at migration 001 holding published versions, then upgraded to 002."""
    out = tmp_path_factory.mktemp("published")
    first_only = tmp_path_factory.mktemp("migrations")
    shutil.copy(database.MIGRATIONS / "001_rdm.sql", first_only)
    with server() as engine:
        owner, runtime = engine("rdm"), engine("rdm", "rdm_runtime")
        store = RDM(runtime)
        held, database.MIGRATIONS = database.MIGRATIONS, first_only
        try:
            assert list(database.migrate(owner, runtime_role="rdm_runtime")) == ["001_rdm.sql"]
        finally:
            database.MIGRATIONS = held
        _import(store)
        store.approve("sec-place-codes", "1", **OPERATOR)
        first = store.publish("sec-place-codes", "1", out=out)
        store.draft({"code_set": "test-sector", "name": "Test sectors"}, "1",
                    [{"code": "F", "label": "Finance"},
                     {"code": "F1", "label": "Depository institutions", "parent_code": "F"},
                     {"code": "F11", "label": "State commercial banks", "parent_code": "F1"},
                     {"code": "F12", "label": "Savings institutions (10% reserve)", "parent_code": "F1",
                      "valid_to": date.today() - timedelta(days=1)}],
                    created_by="test", labels=[{"code": "F11", "label": "Chartered state banks", "kind": "synonym"}],
                    levels=[{"depth": 1, "name": "division"}, {"depth": 3, "name": "industry"}],
                    usage=[{"store": "silver", "object": "filings", "field": "sector_code"}],
                    hints=[{"kind": "meaning", "text": "An industry grouping of companies"}])
        store.approve("test-sector", "1", **OPERATOR)
        store.publish("test-sector", "1", out=out)
        between = _now(runtime)
        store.draft({"code_set": "test-sector"}, "2",
                    [{"code": "F", "label": "Finance and insurance"},
                     {"code": "F1", "label": "Depository institutions", "parent_code": "F"},
                     {"code": "F11", "label": "State commercial banks", "parent_code": "F1"}],
                    created_by="test", supersedes="1")
        store.approve("test-sector", "2", **OPERATOR)
        store.publish("test-sector", "2", out=out)
        store.draft({"code_set": "test-retired", "name": "A retired set"}, "1", [{"code": "A", "label": "Aye"}], created_by="test")
        store.approve("test-retired", "1", **OPERATOR)
        store.publish("test-retired", "1", out=out)
        before_retiring = _now(runtime)
        store.retire("test-retired", "1")
        upgraded = database.migrate(owner, runtime_role="rdm_runtime", existing_only=True)
        assert list(upgraded) == ["001_rdm.sql", "002_code_context.sql"]  # 002 on a populated database
        yield runtime, first, between, before_retiring


def test_the_view_has_every_published_code_with_comments(published):
    engine, *_ = published
    with engine.connect() as conn:
        counts = dict(conn.execute(text(
            "SELECT code_set || ' ' || version, count(*) FROM rdm.code_context GROUP BY 1")).all())
        uncommented = conn.scalars(text(
            "SELECT a.attname FROM pg_attribute a WHERE a.attrelid = 'rdm.code_context'::regclass AND a.attnum > 0 "
            "AND col_description(a.attrelid, a.attnum) IS NULL")).all()
    assert counts == {"sec-place-codes 1": 309, "test-sector 1": 4, "test-sector 2": 3, "test-retired 1": 1}
    assert uncommented == []


def test_a_code_comes_back_named_with_its_path_crosswalk_and_pin(published):
    engine, first, *_ = published
    answer = ask(engine, "sec-place-codes", "DE")
    assert answer["name"] == "DELAWARE" and answer["kind"] == "code" and answer["path"] == "DELAWARE"
    assert answer["definition"] == "" and answer["code_set_definition"].startswith("The codes a filer writes")
    assert {"to_set": "iso-3166", "to_version": "outside", "to_code": "US-DE", "match_type": "exact"} in answer["crosswalk"]
    assert answer["trust"]["version"] == "1" and answer["trust"]["sha256"] == first["sha256"]
    assert answer["trust"]["status"] == "published" and answer["trust"]["approved_by"] == "operator"
    deep = ask(engine, "test-sector", "F11", detail="full")
    assert deep["path"] == "Finance and insurance > Depository institutions > State commercial banks"
    assert (deep["path_codes"], deep["level"], deep["depth"], deep["code_status"]) == ("F/F1/F11", None, 3, "valid")
    assert deep["used_in"] == [] and "used_in" not in ask(engine, "test-sector", "F11")
    with pytest.raises(ContextError, match="no code 'ZZ'") as error:
        ask(engine, "sec-place-codes", "ZZ")
    assert error.value.command == "edgar-warehouse context sec-place-codes --search ZZ"
    with pytest.raises(ContextError, match="--hops and --type are for relationships"):
        ask(engine, "sec-place-codes", "DE", hops=2)


def test_as_of_and_as_at_read_the_version_current_then_as_it_stood(published):
    engine, _, between, before_retiring = published
    then = ask(engine, "test-sector", "F11", as_at=between.isoformat())
    assert then["trust"]["version"] == "1" and then["path"].startswith("Finance >") and then["level"] == "industry"
    assert then["trust"]["valid_to"] is None and then["trust"]["status"] == "published"  # not yet replaced then
    assert then["synonyms"] == ["Chartered state banks"]
    assert ask(engine, "test-sector", "F11", as_of=between.isoformat())["trust"]["version"] == "1"
    assert ask(engine, "test-sector", "F11")["trust"]["version"] == "2"
    assert ask(engine, "test-sector", "F12", as_at=between.isoformat())["code_valid_to"] is not None
    with pytest.raises(ContextError, match="was not valid on"):  # the code's own business dates
        ask(engine, "test-sector", "F12", as_of=between.isoformat())
    assert ask(engine, "test-retired", "A", as_at=before_retiring.isoformat())["trust"]["status"] == "published"
    with pytest.raises(ContextError, match="no published version now"):
        ask(engine, "test-retired", "A")
    with pytest.raises(ContextError, match="no published version --as-of"):
        ask(engine, "test-sector", "F11", as_of="2000-01-01T00:00:00+00:00")


def test_search_finds_labels_then_words_as_typed(published):
    engine, _, between, _ = published
    found = ask(engine, "sec-place-codes", search="delaware")
    assert found["matches"][0] == {"name": "DELAWARE", "code": "DE", "path": "DELAWARE", "matched_by": "label"}
    assert found["trust"]["sha256"] and found["trust"]["approved_by"] == "operator"
    assert ask(engine, "sec-place-codes", search="elawa")["matches"][0]["matched_by"] == "label contains"
    assert ask(engine, "test-sector", search="chartered")["matches"] == []  # the synonym is version 1's only
    assert ask(engine, "test-sector", search="chartered", as_of=between.isoformat())["matches"][0]["matched_by"] == "synonym"
    assert [m["code"] for m in ask(engine, "test-sector", search="10%", as_at=between.isoformat())["matches"]] == ["F12"]
    assert ask(engine, "sec-place-codes", search="%")["matches"] == []  # % matches itself, not everything
    missed = ask(engine, "test-sector", search="zebra")
    assert missed["matches"] == [] and "Try fewer words" in missed["next_step"]


def test_a_code_set_id_never_takes_a_kind_name(published):
    engine, *_ = published
    with pytest.raises(Blocked, match="names a master kind"):
        RDM(engine).draft({"code_set": "company", "name": "No"}, "1", [], created_by="test")


def test_the_command_reads_a_code_set_from_rdm_and_never_prints_the_address(published, monkeypatch, capsys):
    engine, *_ = published
    monkeypatch.setenv("RDM_DATABASE_URL", engine.url.render_as_string(hide_password=False))
    assert context._handle(args("sec-place-codes", "DE")) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["name"] == "DELAWARE" and "test@" not in out
    assert context._handle(args("no-such-set", "X")) == 2
    assert json.loads(capsys.readouterr().out)["try"] == "edgar-warehouse rdm list"
    monkeypatch.delenv("RDM_DATABASE_URL")
    assert context._handle(args("compnay", "X")) == 2
    error = json.loads(capsys.readouterr().out)["error"]
    assert "is not a master kind (branch, company" in error and "RDM_DATABASE_URL is not set" in error
