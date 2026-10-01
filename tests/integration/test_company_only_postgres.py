"""Local PG16 Company route: bounded main/page capture through MDM publication."""
from __future__ import annotations

import hashlib
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.company import (
    prepare_company, register_company_expansion, register_company_silver,
    register_company_mdm_preparation,
)
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.mdm_capabilities import register_mdm
from edgar_warehouse.bookkeeping.clean.runner import run
from edgar_warehouse.change_journal.capture import register_capture
from edgar_warehouse.change_journal.publication import JournalPublisher
from edgar_warehouse.change_journal.source_evidence import register_source_evidence
from edgar_warehouse.infrastructure.sec_client import ConditionalSecResponse
from edgar_warehouse.mdm.clean.name_census import (
    VERSION, SEC_NORMALIZER, GLEIF_NORMALIZER, sec_legal_form_key,
)
from edgar_warehouse.mdm.clean.publication import LocalContractSink
from edgar_warehouse.mdm.clean.store import migrate as migrate_mdm, register_policy
from edgar_warehouse.rules import files
from tests.integration.test_configured_bookkeeping_postgres import databases
from tests.support.rules_approval import approve


def _main(cik: int, name: str, pages: list[str]) -> bytes:
    payload = {"cik": cik, "name": name, "entityType": "operating", "sic": "3571",
        "addresses": {"business": {"street1": "1 Main St", "city": "Boston",
                                    "stateOrCountry": "MA", "zipCode": "02101"}},
        "formerNames": [],
        "filings": {"recent": {"accessionNumber": [f"{cik:010d}-20-000001"],
                               "form": ["10-K"], "filingDate": ["2020-01-01"]},
                    "files": [{"name": page} for page in pages]}}
    return canonical(payload).encode()


def _support(artifacts: Artifacts, root, company: list[tuple[str, str]]) -> dict:
    landing = root / "landing"
    ticker_rows = [{"cik": int(cik), "ticker": f"T{index}", "source_rank": 1,
                    "last_sync_run_id": "ticker-fixture"}
                   for index, (cik, _) in enumerate(company)]
    stream = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist(ticker_rows), stream)
    member = artifacts.put_bytes((landing / "support" / "tickers.parquet").as_uri(),
                                 stream.getvalue().to_pybytes())
    ticker = artifacts.put_bytes((landing / "support" / "manifest.json").as_uri(),
        canonical({"schema_version": 1, "target": "silver_landing", "run_id": "ticker-fixture",
                   "tables": [{"table_name": "sec_company_ticker", "file_count": 1,
                               "row_count": len(ticker_rows), "relative_path": "support/tickers.parquet",
                               "sha256": member["sha256"]}]}).encode())
    censuses = {}
    bindings = {}
    for cik, name in company:
        key = sec_legal_form_key(name)
        census = {"version": VERSION,
            "normalizers": {"sec": SEC_NORMALIZER, "gleif": GLEIF_NORMALIZER},
            "sec": {"capture_run_id": "pending", "company_member_sha256": "0" * 64,
                    "former_name_member_sha256": "0" * 64, "filers": 1},
            "gleif": {"archive_sha256": "0" * 64, "content_date": "2026-09-29",
                      "file_content": "GLEIF_FULL_PUBLISHED", "record_count": 0},
            "entries": {key: {"ciks": [cik], "cik_count": 1, "leis": [],
                              "lei_count": 0, "other_name_holders": 0}}}
        censuses[cik] = artifacts.put(root.as_uri() + "/fixtures/census", census)
        bindings[cik] = artifacts.put(root.as_uri() + "/fixtures/bindings",
            {"version": 1, "cik": cik, "entity_id": str(uuid4()), "actor": "local-fixture-reviewer",
             "reason": "reviewed bounded Company fixture", "at": "2026-09-29T00:00:00Z"})
    return artifacts.put(root.as_uri() + "/fixtures/support",
                         {"version": 1, "ticker_manifest": ticker, "name_census": censuses,
                          "bindings": bindings, "as_of": "2026-09-29T00:00:00Z"})


def test_preparation_pins_bounded_revision_without_a_provider_or_run(tmp_path):
    artifacts = Artifacts()
    company = [("0000000001", "One Example Corp")]
    support = _support(artifacts, tmp_path, company)
    prior = artifacts.put(tmp_path.as_uri() + "/fixtures/revisions",
                          {"kind": "source.revision", "body": {"position": 3}})
    scope = artifacts.put(tmp_path.as_uri() + "/fixtures/scopes",
                          {"version": 1, "ciks": [company[0][0]], "prior": {},
                           "revisions": {company[0][0]: {"revision": 4, "position": 3,
                                                           "prior": prior}}})
    manifest_ref = prepare_company(scope_ref=scope, support_ref=support,
                                   output_root=tmp_path.as_uri(), artifacts=artifacts)
    manifest = artifacts.json(manifest_ref)
    revision = manifest["steps"]["revision"][0]
    assert revision["cursor"]["resource_checkpoint"]["revision"] == 4
    assert revision["cursor"]["resource_checkpoint"]["position"] == 3
    assert revision["cursor"]["prior_revision"] == prior
    assert manifest["steps"]["prepare_mdm"][0]["cursor"]["publication_revision"] == 4
    assert manifest["steps"]["capture_main"][0]["keys"]["candidate_id"].split("/")[1] == scope["sha256"]
    duplicated = artifacts.put(tmp_path.as_uri() + "/fixtures/scopes",
        {"version": 1, "ciks": [company[0][0], company[0][0]], "prior": {}})
    with pytest.raises(Blocked, match="distinct zero-padded CIKs"):
        prepare_company(scope_ref=duplicated, support_ref=support,
                        output_root=tmp_path.as_uri(), artifacts=artifacts)


def test_company_route_locally_with_and_without_pagination(databases, tmp_path, monkeypatch):
    name = "change_journal_validation_company_" + uuid4().hex[:12]
    with databases.destination_admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    owner = create_engine(databases.destination_admin.url.set(database=name))
    application = create_engine(databases.mdm.url.set(database=name))
    try:
        migrate_mdm(owner, application_role="clean_application")
        migrate_guard(owner, runtime_role="clean_application")
        with owner.begin() as conn:
            register_policy(conn, files.policy())
        company = [("0000000001", "One Example Corp"), ("0000000002", "Two Example Corp")]
        page = "CIK0000000001-submissions-001.json"
        empty_page = "CIK0000000001-submissions-002.json"
        payloads = {f"CIK{company[0][0]}.json": _main(1, company[0][1], [page, empty_page]),
                    page: canonical({"filings": {"accessionNumber": ["0000000001-20-000002"],
                                                  "form": ["10-Q"], "filingDate": ["2020-02-01"]}}).encode(),
                    empty_page: canonical({"filings": {"accessionNumber": [], "form": []}}).encode(),
                    f"CIK{company[1][0]}.json": _main(2, company[1][1], [])}
        requested = []

        def fetch(url, identity, *, before_request, etag, last_modified, definition):
            before_request()
            requested.append((url, etag))
            if url.endswith("CIK0000000002.json"):
                return ConditionalSecResponse(True, b"", '"prior"', None)
            return ConditionalSecResponse(False, payloads[url.rsplit("/", 1)[1]],
                                          '"fixture"', "Tue, 29 Sep 2026 00:00:00 GMT")

        registry = standard_registry()
        register_capture(registry, databases.ledger, fetchers={"sec.conditional": fetch})
        register_source_evidence(registry)
        register_company_expansion(registry)
        register_company_silver(registry)
        register_company_mdm_preparation(registry)
        book = Bookkeeping(databases.runtime, registry)

        def publisher(spec):
            if spec["consumer"] == "journal":
                return JournalPublisher(databases.ledger, application, book)
            return LocalContractSink(spec["destination"].removeprefix("file://"))

        register_mdm(registry, application, publisher_factory=publisher)
        artifacts = book.artifacts
        prior_raw = artifacts.put_bytes((tmp_path / "fixtures" / "prior-main.json").as_uri(),
                                        payloads["CIK0000000002.json"])
        prior = artifacts.put(tmp_path.as_uri() + "/fixtures/prior-outcome",
            {"version": 1, "source": "sec.submissions.company", "feed": "submissions",
             "scope": {"cik": "0000000002", "file": "main"}, "outcome": "captured",
             "artifact": prior_raw, "etag": '"prior"', "last_modified": None})
        scope = artifacts.put(tmp_path.as_uri() + "/fixtures/scope",
                              {"version": 1, "ciks": [cik for cik, _ in company],
                               "prior": {"0000000002": prior}})
        support = _support(artifacts, tmp_path, company)
        inputs = prepare_company(scope_ref=scope, support_ref=support,
                                 output_root=tmp_path.as_uri(), artifacts=artifacts)
        body = files.source("sec.submissions.company")
        saved = databases.rules.save("source", "sec.submissions.company", uuid4().hex, body)
        version = saved["version"]
        proof = {"passed": True, "digest": saved["digest"], "batch_hash": inputs["sha256"],
                 "acquisition": {"submissions": {"manifest": inputs,
                     "counts": {key: {"expected": count, "verified": count} for key, count in
                                (("capture", 4), ("sec_company", 2), ("sec_company_filing", 3))},
                     "checks": {"bounded-local": True}}}}
        databases.rules.prove("source", "sec.submissions.company", version, proof)
        approve(databases.approver, "source", "sec.submissions.company", version)
        databases.rules.activate("source", "sec.submissions.company", version, mdm_engine=owner)
        rules_ref = databases.rules.resolve("source", "sec.submissions.company",
                                            root=tmp_path.as_uri() + "/rules")
        monkeypatch.setenv("EDGAR_IDENTITY", "Local fixture fixture@example.test")
        rid = book.start(rules_ref=rules_ref, inputs_ref=inputs, target="company",
                         scope={"source": "sec.submissions.company", "feed": "submissions"})
        result = run(book, rid, databases.ledger, limit=100)
        assert result["run"]["state"] == "complete"
        assert result["pending_deliveries"] == 0
        assert len(requested) == 4
        assert any(url.endswith("CIK0000000002.json") and etag == '"prior"' for url, etag in requested)
        assert result["counts"] == {"verified": 28}
        assert len(result["deliveries"]) == 32
        capture_counts = sorted(artifacts.json(item["receipt"]["evidence"])["body"]["expected"]
                                for item in result["items"] if item["step"] == "capture")
        assert capture_counts == [1, 3]
        revisions = [artifacts.json(item["receipt"]["evidence"])["body"]["domain"]
                     for item in result["items"] if item["step"] == "revision"]
        assert sorted(len(artifacts.json(ref)["pages"]) for ref in revisions) == [0, 2]
        silver_items = [item for item in result["items"] if item["step"] == "silver"]
        assert len(silver_items) == 2
        by_cik = {}
        for item in silver_items:
            manifest = artifacts.json(item["receipt"]["evidence"])
            landing_root = tmp_path / "landing"
            tables = {}
            for entry in manifest["tables"]:
                payload = (landing_root / entry["relative_path"]).read_bytes()
                assert len(payload) > 0 and entry["sha256"] == hashlib.sha256(payload).hexdigest()
                tables[entry["table_name"]] = pq.read_table(pa.BufferReader(payload)).to_pylist()
            by_cik[manifest["cik"]] = tables
        assert [row["accession_number"] for row in by_cik["0000000001"]["sec_company_filing"]] == [
            "0000000001-20-000001", "0000000001-20-000002"]
        assert [row["accession_number"] for row in by_cik["0000000002"]["sec_company_filing"]] == [
            "0000000002-20-000001"]
        assert {cik: len(tables["sec_company"]) for cik, tables in by_cik.items()} == {
            "0000000001": 1, "0000000002": 1}
        with databases.ledger_admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM journal.event WHERE run_id=CAST(:r AS uuid)"),
                               {"r": rid}) == 34
        with application.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2
            assert conn.scalar(text("SELECT count(*) FROM mdm.company WHERE valid_to IS NULL")) == 2
            assert conn.scalar(text("SELECT count(*) FROM mdm.current_entity WHERE kind='company' AND status<>'alias'")) == 2
            assert conn.scalar(text("SELECT count(*) FROM mdm.outbox WHERE verified_at IS NULL")) == 0
        with book.engine.connect() as conn:
            silver_row = dict(conn.execute(text("""SELECT * FROM bookkeeping.work_item
                WHERE run_id=CAST(:r AS uuid) AND step='silver'
                  AND unit->'keys'->>'cik'='0000000001'"""), {"r": rid}).mappings().one())
        assert registry.operations["company.silver"].execute(
            book, book._resolve_item(silver_row), None) == silver_row["receipt"]
        damaged = tmp_path / "landing" / "0000000001" / "sec_company_filing.parquet"
        damaged.write_bytes(b"wrong destination rows")
        with pytest.raises(Blocked):
            book.resume(rid)
    finally:
        application.dispose()
        owner.dispose()
