"""Bounded existing-source capture through real Rules/Bookkeeping CLI on PG16.

Proof/approval logins and acquisition coverage are sandbox fixtures. This
qualifies immutable artifact capture/recovery, not provider fetching, native
parsing within Bookkeeping, MDM ingest or production deployment.
"""
import hashlib
import io
import json
from pathlib import Path
from runpy import run_path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from edgar_warehouse.bookkeeping.clean import capabilities
from edgar_warehouse.bookkeeping.clean.config import digest
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.runner import Authority
from edgar_warehouse.cli import main
from edgar_warehouse.mdm.clean.gleif_source import inspect_archive
from edgar_warehouse.mdm.clean.store import migrate
from edgar_warehouse.rules.files import load
from tests.integration.test_configured_bookkeeping_postgres import databases, expire
from tests.mdm.test_clean_gleif_source import archive_bytes, metadata

ROOT = Path(__file__).resolve().parents[2]
resolve_feed = run_path(str(ROOT / "skills/bookkeeping/scripts/resolve_feed.py"))["resolve_feed"]
PAIRS = [
    ("sec.submissions.company", "submissions", "sec.submissions.company.v1"),
    ("gleif", "level1", "gleif.level1.v1"),
    ("gleif", "relationships", "gleif.relationships.v1"),
    ("gleif", "reporting_exceptions", "gleif.reporting_exceptions.v1"),
]


def captured_sample(tmp_path, feed):
    fixture = json.loads((ROOT / "tests/fixtures/clean_mdm/native_company_v1.json").read_text())
    if feed == "submissions":
        row = fixture["sec"]
        path = tmp_path / "company.parquet"
        pq.write_table(pa.Table.from_pylist([{"cik": row["cik"], "entity_name": row["sec_entity_name"],
                                             "entity_type": row["sec_entity_type"]}]), path)
        return path.read_bytes()
    records = {
        "level1": ("records", fixture["gleif"], "LEI_3.1"),
        "relationships": ("relations", {"RelationshipRecord": {"LEI": fixture["gleif"]["LEI"]}}, "RR_2.1"),
        "reporting_exceptions": ("exceptions", {"LEI": fixture["gleif"]["LEI"]}, "REPEX_2.1"),
    }
    wrapper, row, cdf = records[feed]
    raw = archive_bytes(json.dumps({wrapper: [row]}).encode())
    report = inspect_archive(io.BytesIO(raw), member=feed, metadata=metadata(cdf_version=cdf),
                             expected_sha256=hashlib.sha256(raw).hexdigest())
    assert report["record_count"] == 1
    return raw


@pytest.mark.parametrize("source,feed,code", PAIRS)
def test_existing_source_feed_capture_cli_and_lost_ack(databases, tmp_path, monkeypatch, capsys, source, feed, code):
    binding = resolve_feed(ROOT / "rules", source, feed)
    assert [d["code"] for d in binding["datasets"]] == [code]
    body = load(ROOT / "rules/sources" / source / "source.yaml")
    migrate(databases.destination_admin, application_role="clean_application")
    book = Bookkeeping(databases.runtime, capabilities.standard_registry())
    raw = captured_sample(tmp_path, feed)
    units = []
    for ordinal in range(2):
        output = (tmp_path / f"captured-{ordinal}").as_uri()
        units.append({"keys": {"artifact_id": str(ordinal), "destination": output,
                               "source": source, "feed": feed, "dataset": code},
                      "input": book.artifacts.put_bytes((tmp_path / f"input-{ordinal}").as_uri(), raw),
                      "output": output, "cursor": {"offset": ordinal}})
    inputs = book.artifacts.put(tmp_path.as_uri(), {"version": 2, "steps": {"capture": units}})
    plan = {"binding": binding, "target": "capture", "inputs": inputs,
            "expected_count": 2, "processing_versions": {"artifact.copy": "1"}}
    plan_ref = book.artifacts.put((tmp_path / "plans").as_uri(), plan)
    version = "sandbox-" + uuid4().hex
    saved = databases.rules.save("source", source, version, body)
    assert saved["digest"] == binding["rules_digest"]
    # Exact approved scope for every declared feed. These sandbox attestations
    # qualify immutable sample bytes only; they do not assert provider or MDM
    # output completeness. Activation uses Rules, never the legacy registry.
    baselines = {}
    for declared_feed, policy in body["acquisition"]["feeds"].items():
        sample = captured_sample(tmp_path, declared_feed)
        member = book.artifacts.put_bytes((tmp_path / ("baseline-" + declared_feed)).as_uri(), sample)
        assert book.artifacts.verified(member) == sample
        baseline = book.artifacts.put((tmp_path / "baselines").as_uri(), {
            "version": 1, "source": source, "feed": declared_feed, "members": [member],
        })
        baselines[declared_feed] = {
            "manifest": baseline,
            "counts": {producer: {"expected": 1, "verified": 1} for producer in policy["required_producers"]},
            "checks": {"immutable_artifact_fixture_only": True},
        }
    databases.rules.prove("source", source, version, {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True, "acquisition": baselines})
    databases.approver.approve("source", source, version, saved["digest"])
    databases.rules.activate("source", source, version, mdm_engine=databases.destination_admin)
    for key, engine in [("RULES_DATABASE_URL", databases.rules.engine),
                        ("BOOKKEEPING_CLEAN_DATABASE_URL", databases.runtime),
                        ("CHANGE_JOURNAL_DATABASE_URL", databases.ledger.engine)]:
        monkeypatch.setenv(key, engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("BOOKKEEPING_MANIFEST_ROOT", (tmp_path / "exports").as_uri())
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    command = ["rules", "run", "--source", source, "--feed", feed, "--target", "capture"]
    assert main(command + ["--input-manifest", inputs["uri"], "--input-sha256", inputs["sha256"], "--limit", "1"]) == 3
    result = json.loads(capsys.readouterr().out)
    rid = result["run"]["run_id"]
    assert result["counts"] == {"verified": 1, "pending": 1}
    assert result["run"]["state"] != "complete"
    assert book.artifacts.json(result["run"]["submission"]["inputs"])["steps"]["capture"] == units
    # Commit the second immutable artifact but lose the control acknowledgement.
    claim = book.claim(rid, "capture", "1")
    receipt = book.registry.operations["artifact.copy"].execute(book, book.item(claim), Authority(claim))
    before = (tmp_path / "captured-1").stat().st_mtime_ns
    expire(databases, claim)

    def unexpected_repeat(*args):
        pytest.fail("A committed artifact must reconcile without repeating execution")

    monkeypatch.setattr(capabilities, "_copy", unexpected_repeat)
    assert main(command + ["--resume-run-id", rid, "--limit", "2"]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["run"]["state"] == "complete"
    assert completed["run"]["expected_count"] == 2
    assert completed["counts"] == {"verified": 2}
    assert completed["pending_deliveries"] == 0
    assert all(book.check(rid).values())
    assert (tmp_path / "captured-1").stat().st_mtime_ns == before
    assert book.artifacts.verified(receipt["evidence"])
    for unit in units:
        assert book.artifacts.read(unit["output"]) == raw
    assert book.deliver(databases.ledger, rid) == 0
    validation = {"binding": binding, "plan": plan_ref, "run_id": rid,
                  "config_digest": digest(body), "inputs": inputs,
                  "processing_versions": completed["run"]["submission"]["processing_versions"],
                  "expected_count": 2, "verified_count": 2, "state": completed["run"]["state"],
                  "receipts": [item["receipt"] for item in completed["items"]],
                  "checks": book.check(rid), "pending_deliveries": 0,
                  "qualified_scope": "isolated artifact capture/recovery only"}
    book.artifacts.put((tmp_path / "validation").as_uri(), validation)
