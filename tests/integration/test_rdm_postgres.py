"""Real PG16: the RDM database from zero (profiling ticket 02).

The place-code table drafts as a code set version of all 309 codes and
rebuilds exactly; approval needs the operator's name and words; publishing
writes paths, the sha256 and files a consumer reads by its pin; a published
version never changes; a hierarchy with a cycle never publishes; a new version
supersedes the current one, and the diff names what moved.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rdm import cli, store
from edgar_warehouse.rdm.database import migrate
from edgar_warehouse.rdm.store import RDM
from edgar_warehouse.rules import files

IMAGE = "postgres:16-alpine"
OPERATOR = {"by": "operator", "words": "approved"}


def docker(*args):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True).stdout.strip()


@contextlib.contextmanager
def server():
    """A PG16 server with an empty `rdm` database (and a `not_rdm` one) and the runtime login."""
    docker("image", "inspect", IMAGE)
    name = f"rdm-test-{uuid4().hex[:10]}"
    docker("run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD=test", IMAGE)
    engines = []
    try:
        port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]

        def engine(db, user="postgres"):
            value = create_engine(f"postgresql+psycopg2://{user}:test@127.0.0.1:{port}/{db}")
            engines.append(value)
            return value

        admin = engine("postgres")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with admin.connect() as conn:
                    conn.execute(text("SELECT 1"))
                break
            except DBAPIError:
                time.sleep(0.1)
        else:
            pytest.fail("PostgreSQL did not become ready")
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql("CREATE ROLE rdm_runtime LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
            conn.exec_driver_sql("CREATE DATABASE rdm")
            conn.exec_driver_sql("CREATE DATABASE not_rdm")
        yield engine
    finally:
        for value in engines:
            value.dispose()
        docker("stop", name)


@pytest.fixture(scope="module")
def rdm():
    """An empty `rdm` database on PG16, migrated from zero by its owner."""
    with server() as engine:
        owner = engine("rdm")
        with pytest.raises(Blocked, match="not initialized"):
            migrate(owner, runtime_role="rdm_runtime", existing_only=True)
        with pytest.raises(Blocked, match="its own rdm database"):
            migrate(engine("not_rdm"), runtime_role="rdm_runtime")
        with pytest.raises(Blocked, match="restricted runtime"):
            migrate(owner, runtime_role="postgres")
        installed = migrate(owner, runtime_role="rdm_runtime")
        assert migrate(owner, runtime_role="rdm_runtime", existing_only=True) == installed  # a rerun installs nothing
        yield RDM(engine("rdm", "rdm_runtime")), owner


def _import(rdm):
    """Import SEC's place-code table as version 1. Its YAML is removed (profiling
    ticket 02), so the table comes back from the published version, which equals
    it code for code."""
    from unittest import mock

    from tests.support import place_codes

    with mock.patch.object(files, "reference", lambda name, root=None: {"codes": place_codes.table()}):
        return _import_table(rdm)


def _import_table(rdm):
    return cli.import_reference(rdm, argparse.Namespace(
        name="sec-place-codes", key="codes", label="place", code_set=None, set_name="EDGAR state and country codes",
        version="1", created_by="claude/data-profiling (test)",
        crosswalk=["iso=iso-3166@outside:exact", "type=sec-place-types@1:broad"],
        definition="The codes a filer writes for its state or country of incorporation and of each address",
        used_in=["mdm:company:state_of_incorporation:upper_trimmed", "source:sec.submissions.company:stateOfIncorporation"],
        hint=["meaning=A US state reads as its postal code; X1 is the United States with no state; XX is unknown",
              "example_question=Which companies are incorporated in Delaware? (state_of_incorporation = DE)",
              "avoid_when=Comparing with a GLEIF jurisdiction: use the iso-3166 crosswalk instead"]))


def test_place_codes_import_approve_publish_and_read_by_pin(rdm, tmp_path):
    rdm, owner = rdm
    found = _import(rdm)
    assert found["codes"] == 309 and found["rebuilds_exactly"] and found["also_drafted"] == {"sec-place-types": 4}
    with pytest.raises(Blocked, match="not an approved"):
        rdm.publish("sec-place-codes", "1", out=tmp_path)
    with pytest.raises(DBAPIError, match="cannot approve its own"):
        rdm.approve("sec-place-codes", "1", by="claude/data-profiling (test)", words="approved")
    with pytest.raises(DBAPIError, match="exact words"):
        rdm.approve("sec-place-codes", "1", by="operator", words=" ")
    approved = rdm.approve("sec-place-codes", "1", **OPERATOR)
    assert approved["approved_words"] == "approved" and approved["approved_at"] is not None
    with pytest.raises(DBAPIError, match="Only a draft"):  # approved content is frozen
        with rdm.engine.begin() as conn:
            conn.execute(text("UPDATE rdm.code SET label='X' WHERE code_set='sec-place-codes' AND code='DE'"))
    published = rdm.publish("sec-place-codes", "1", out=tmp_path)
    codes = rdm.codes("sec-place-codes", "1")
    assert published["sha256"] == store.sha256(codes) and published["superseded"] is None
    assert rdm.verify("sec-place-codes", "1")["matches"]
    pin = json.loads((tmp_path / "sec-place-codes" / "1" / "pin.json").read_text())
    assert pin == {"code_set": "sec-place-codes", "version": "1", "sha256": published["sha256"]}
    rows = store.read_published(tmp_path, "sec-place-codes", "1", pin["sha256"])
    assert len(rows) == 309 and {"DE": "US-DE"} == {r["code"]: x[2] for r in rows if r["code"] == "DE"
                                                    for x in r["crosswalk"] if x[0] == "iso-3166"}
    silver = [json.loads(l) for l in (tmp_path / "sec-place-codes" / "1" / "rdm_code.jsonl").read_text().splitlines()]
    assert len(silver) == 309 and {s["path"] for s in silver if s["code"] == "DE"} == {"DE"}
    with pytest.raises(Blocked, match="differs from its pinned"):
        store.read_published(tmp_path, "sec-place-codes", "1", "0" * 64)
    with pytest.raises(DBAPIError, match="Only a draft"):  # published content never changes
        with rdm.engine.begin() as conn:
            conn.execute(text("DELETE FROM rdm.code_label WHERE code_set='sec-place-codes'"))
    with pytest.raises(DBAPIError, match="history is retained"):
        with owner.begin() as conn:  # not even the owner deletes a version
            conn.execute(text("DELETE FROM rdm.code_set_version WHERE code_set='sec-place-codes'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        with rdm.engine.begin() as conn:
            conn.execute(text("TRUNCATE rdm.code_set_version CASCADE"))
    listed = {s["code_set"]: s for s in rdm.code_sets()}
    assert listed["sec-place-codes"]["published_version"] == "1"
    assert listed["sec-place-types"]["newest_status"] == "draft" and listed["sec-place-types"]["published_version"] is None


def test_describe_gives_an_agent_the_semantic_layer_in_one_bounded_answer(rdm):
    rdm, _ = rdm
    answer = rdm.describe("sec-place-codes")
    assert answer["version"] == "1" and answer["status"] == "published" and len(answer["sha256"]) == 64
    assert {"store": "mdm", "object": "company", "field": "state_of_incorporation", "match": "upper_trimmed",
            "note": ""} in answer["used_in"]
    assert answer["hints"]["meaning"][0].startswith("A US state") and set(answer["hints"]) == {
        "meaning", "example_question", "avoid_when"}
    assert answer["counts"]["codes"] == 309 and {m["to_set"] for m in answer["maps_to"]} == {"iso-3166", "sec-place-types"}
    assert len(json.dumps(answer, default=str).encode()) <= store.DESCRIBE_LIMIT and answer["sample_codes"]
    rdm.draft({"code_set": "test-long", "name": "Long hints"}, "1", [{"code": "A", "label": "a"}], created_by="test",
              hints=[{"kind": "use_when", "text": "x" * 500} for _ in range(40)])
    long = rdm.describe("test-long")
    assert long["truncated"] and len(json.dumps(long, default=str).encode()) <= store.DESCRIBE_LIMIT
    with pytest.raises(Blocked, match="rdm list"):
        rdm.describe("no-such-set")


def _industry(rdm, version, *, supersedes=None, parent_of_c=None, label_b="Mining"):
    rdm.draft({"code_set": "test-industry", "name": "Test industry hierarchy"}, version,
              [{"code": "A", "label": "Finance"}, {"code": "B", "label": label_b},
               {"code": "A1", "label": "Depository", "parent_code": "A"},
               {"code": "C", "label": "Banks", "parent_code": parent_of_c or "A1"}],
              created_by="test", supersedes=supersedes,
              levels=[{"depth": 1, "name": "division"}, {"depth": 2, "name": "major group"}])


def test_a_hierarchy_publishes_paths_and_a_new_version_supersedes(rdm, tmp_path):
    rdm, _ = rdm
    _industry(rdm, "1")
    rdm.approve("test-industry", "1", **OPERATOR)
    first = rdm.publish("test-industry", "1", out=tmp_path)
    with rdm.engine.connect() as conn:
        found = {r.code: r for r in conn.execute(text(
            "SELECT code,path,label_path,level,depth FROM rdm.code_path WHERE code_set='test-industry' AND version='1'"))}
        subtree = conn.scalars(text("SELECT code FROM rdm.code_path WHERE code_set='test-industry' AND version='1' "
                                    "AND path LIKE 'A/%' ORDER BY code")).all()
    assert (found["C"].path, found["C"].label_path, found["C"].level, found["C"].depth) == \
        ("A/A1/C", "Finance > Depository > Banks", None, 3)
    assert found["A1"].level == "major group" and subtree == ["A1", "C"]
    _industry(rdm, "2", supersedes=None, parent_of_c="A", label_b="Mining and quarrying")
    rdm.approve("test-industry", "2", **OPERATOR)
    with pytest.raises(Blocked, match="must supersede 1"):
        rdm.publish("test-industry", "2", out=tmp_path)
    with pytest.raises(DBAPIError, match="must supersede the version it replaces"):  # the database holds it too
        with rdm.engine.begin() as conn:
            conn.execute(text("INSERT INTO rdm.code_path SELECT code_set,version,code,code,label,NULL,1 FROM rdm.code "
                              "WHERE code_set='test-industry' AND version='2'"))
            conn.execute(text("UPDATE rdm.code_set_version SET valid_to=clock_timestamp() "
                              "WHERE code_set='test-industry' AND version='1'"))
            conn.execute(text("UPDATE rdm.code_set_version SET status='published', sha256=repeat('0',64), "
                              "valid_from=clock_timestamp() WHERE code_set='test-industry' AND version='2'"))
    _industry(rdm, "3", supersedes="1", parent_of_c="A", label_b="Mining and quarrying")
    assert rdm.diff("test-industry", "1", "3") == {
        "code_set": "test-industry", "from": "1", "to": "3", "added": [], "removed": [],
        "relabelled": [{"code": "B", "from": "Mining", "to": "Mining and quarrying"}],
        "moved": [{"code": "C", "from": "A1", "to": "A"}]}
    rdm.approve("test-industry", "3", **OPERATOR)
    third = rdm.publish("test-industry", "3", out=tmp_path)
    assert third["superseded"] == "1" and third["sha256"] != first["sha256"]
    old, new = rdm.version("test-industry", "1"), rdm.version("test-industry", "3")
    assert old["valid_to"] == new["valid_from"] and new["valid_to"] is None
    retired = rdm.retire("test-industry", "3")
    assert retired["status"] == "retired" and retired["valid_to"] is not None
    _industry(rdm, "4", supersedes="3")
    rdm.approve("test-industry", "4", **OPERATOR)
    assert rdm.publish("test-industry", "4", out=tmp_path)["superseded"] is None  # it replaces the retired 3


def test_a_cycle_never_publishes(rdm, tmp_path):
    rdm, _ = rdm
    rdm.draft({"code_set": "test-cycle", "name": "A cycle"}, "1",
              [{"code": "A", "label": "a", "parent_code": "B"}, {"code": "B", "label": "b", "parent_code": "A"}],
              created_by="test")
    rdm.approve("test-cycle", "1", **OPERATOR)
    with pytest.raises(Blocked, match="cycle"):
        rdm.publish("test-cycle", "1", out=tmp_path)
    assert rdm.version("test-cycle", "1")["status"] == "approved"  # nothing half-published


def test_an_agent_drafts_from_a_file(rdm, tmp_path):
    rdm, _ = rdm
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"code_set": {"code_set": "test-file", "name": "From a file"}, "version": "1",
                                "created_by": "agent", "evidence": {"findings": "x.yaml"},
                                "codes": [{"code": "X", "label": "Ex"}],
                                "labels": [{"code": "X", "label": "Ex", "kind": "preferred"},
                                           {"code": "X", "label": "The ex", "kind": "synonym"}]}))
    assert cli.draft_file(rdm, path) == {"code_set": "test-file", "version": "1", "status": "draft", "codes": 1}
    path.write_text(json.dumps({"code_set": {"code_set": "test-file"}, "version": "2", "codes": [],
                                "created_by": "agent", "approved_by": "me"}))
    with pytest.raises(Blocked, match="only"):
        cli.draft_file(rdm, path)
    path.write_text(json.dumps({"code_set": {"code_set": "test-file"}, "version": "2", "created_by": "agent",
                                "codes": [{"code": "Y", "label": "Why", "parent": "X"}]}))
    with pytest.raises(Blocked, match="only"):  # a misspelled field is refused, never dropped
        cli.draft_file(rdm, path)
    path.write_text(json.dumps({"code_set": {"code_set": "test-file", "name": "Renamed"}, "version": "2",
                                "created_by": "agent", "codes": []}))
    with pytest.raises(Blocked, match="never change"):
        cli.draft_file(rdm, path)


def test_an_import_that_does_not_rebuild_writes_nothing(rdm, monkeypatch):
    rdm, _ = rdm
    monkeypatch.setattr(files, "reference", lambda name: {"codes": {"A": {"place": "Aye"}}})
    with pytest.raises(Blocked, match="nothing was written"):  # no iso field: it would come back as iso: null
        cli.import_reference(rdm, argparse.Namespace(
            name="test-import", key="codes", label="place", code_set=None, set_name=None, version="1",
            created_by="test", crosswalk=["iso=iso-3166@outside:exact"], definition=None, used_in=[], hint=[]))
    assert "test-import" not in {s["code_set"] for s in rdm.code_sets()}
