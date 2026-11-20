"""Real PG16: `rdm.code_context` and `edgar-warehouse context <code_set>` (profiling ticket 05, RDM part).

The view's migration (002) upgrades a populated RDM database. A code comes
back named, with its meaning, its place in the hierarchy, the code sets it
maps to and the version's pin; search finds labels and synonyms (full-text
first, then the words as typed); a code set keeps one version, so --as-of checks a code's own
dates and --as-at is refused; every answer is at most 8 KB, and an error names the
command that would work.
"""

from __future__ import annotations

import argparse
import json
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
    """RDM holding published versions."""
    out = tmp_path_factory.mktemp("published")
    with server() as engine:
        owner, runtime = engine("rdm"), engine("rdm", "rdm_runtime")
        store = RDM(runtime)
        assert sorted(database.migrate(owner, runtime_role="rdm_runtime")) == ["001-published-code.sql", "002-one-version.sql", "schema.sql"]
        if True:
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
            store.draft({"code_set": "test-sector"}, "2",
                        [{"code": "F", "label": "Finance and insurance"},
                         {"code": "F1", "label": "Depository institutions", "parent_code": "F"},
                         {"code": "F11", "label": "State commercial banks", "parent_code": "F1"},
                         {"code": "F12", "label": "Savings institutions (10% reserve)", "parent_code": "F1",
                          "valid_to": date.today() - timedelta(days=1)}],
                        created_by="test", supersedes="1")
            store.approve("test-sector", "2", **OPERATOR)
            store.publish("test-sector", "2", out=out)
            store.draft({"code_set": "test-retired", "name": "A retired set"}, "1", [{"code": "A", "label": "Aye"}], created_by="test")
            store.approve("test-retired", "1", **OPERATOR)
            store.publish("test-retired", "1", out=out)
            store.retire("test-retired", "1")
        assert sorted(database.migrate(owner, runtime_role="rdm_runtime", existing_only=True)) == ["001-published-code.sql", "002-one-version.sql", "schema.sql"]
        yield runtime, first


def test_the_view_has_every_published_code_with_comments(published):
    engine, *_ = published
    with engine.connect() as conn:
        counts = dict(conn.execute(text(
            "SELECT code_set || ' ' || version, count(*) FROM rdm.code_context GROUP BY 1")).all())
        uncommented = conn.scalars(text(
            "SELECT a.attname FROM pg_attribute a WHERE a.attrelid = 'rdm.code_context'::regclass AND a.attnum > 0 "
            "AND col_description(a.attrelid, a.attnum) IS NULL")).all()
    assert counts == {"sec-place-codes 1": 309, "test-sector 2": 4}  # a code set keeps one version
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


def test_a_code_set_keeps_one_version_so_as_at_is_refused_and_as_of_checks_the_codes_own_dates(published):
    engine, *_ = published
    assert ask(engine, "test-sector", "F11")["trust"]["version"] == "2"
    assert ask(engine, "test-sector", "F11", as_of="2026-01-01T00:00:00+00:00")["trust"]["version"] == "2"
    with pytest.raises(ContextError, match="keeps one version"):
        ask(engine, "test-sector", "F11", as_at="2026-01-01T00:00:00+00:00")
    assert ask(engine, "test-sector", "F12")["code_valid_to"] is not None
    with pytest.raises(ContextError, match="was not valid on"):  # the code's own business dates
        ask(engine, "test-sector", "F12", as_of=_now(engine).isoformat())
    with pytest.raises(ContextError, match="no published version now"):  # a retired code set keeps none
        ask(engine, "test-retired", "A")


def test_search_finds_labels_then_words_as_typed(published):
    engine, *_ = published
    found = ask(engine, "sec-place-codes", search="delaware")
    assert found["matches"][0] == {"name": "DELAWARE", "code": "DE", "path": "DELAWARE", "matched_by": "label"}
    assert found["trust"]["sha256"] and found["trust"]["approved_by"] == "operator"
    assert ask(engine, "sec-place-codes", search="elawa")["matches"][0]["matched_by"] == "label contains"
    assert ask(engine, "test-sector", search="chartered")["matches"] == []  # the synonym is version 1's only
    assert [m["code"] for m in ask(engine, "test-sector", search="10%")["matches"]] == ["F12"]
    assert ask(engine, "sec-place-codes", search="%")["matches"] == []  # % matches itself, not everything
    missed = ask(engine, "test-sector", search="zebra")
    assert missed["matches"] == [] and "Try fewer words" in missed["next_step"]


def test_a_code_set_id_never_takes_a_kind_name(published):
    engine, *_ = published
    with pytest.raises(Blocked, match="names a master kind"):
        RDM(engine).draft({"code_set": "company", "name": "No"}, "1", [], created_by="test")


def test_the_command_reads_a_code_set_from_rdm_and_never_prints_the_address(published, monkeypatch, capsys):
    engine, *_ = published
    monkeypatch.setenv("DATA_URL", engine.url.render_as_string(hide_password=False))
    assert context._handle(args("sec-place-codes", "DE")) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["name"] == "DELAWARE" and "test@" not in out
    assert context._handle(args("no-such-set", "X")) == 2
    assert json.loads(capsys.readouterr().out)["try"] == "edgar-warehouse rdm list"
    monkeypatch.delenv("DATA_URL")
    assert context._handle(args("compnay", "X")) == 2
    error = json.loads(capsys.readouterr().out)["error"]
    assert "is not a master kind (branch, company" in error and "DATA_URL is not set" in error
