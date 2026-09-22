"""Native archive boundary: evidence is usable only after complete verification."""

import hashlib
import io
import json
import zipfile

import pytest

from edgar_warehouse.mdm.clean.gleif_source import inspect_archive
from edgar_warehouse.mdm.clean.store import Conflict


def archive_bytes(raw, name="source.json"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, raw)
    return output.getvalue()


def metadata(count=1, **changes):
    return {
        "format": "json.zip",
        "cdf_version": "LEI_3.1",
        "content_date": "2026-09-11T16:00:00+00:00",
        "file_content": "GLEIF_FULL_PUBLISHED",
        "delta_start": None,
        "record_count": count,
        **changes,
    }


def test_native_json_archive_yields_exact_records_and_checks_metadata():
    record = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "Entity": {"EntityCategory": {"$": "GENERAL"}},
    }
    raw = archive_bytes(json.dumps({"records": [record]}).encode())
    seen = []
    report = inspect_archive(
        io.BytesIO(raw),
        member="level1",
        metadata=metadata(),
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        on_record=lambda row, ordinal: seen.append((ordinal, row)),
    )
    assert seen == [(0, record)]
    assert report["record_count"] == 1
    assert report["compressed_bytes"] == len(raw)
    assert report["canonical_source_hash"] != report["raw_evidence_hash"]


def test_xml_source_header_must_match_pinned_metadata():
    xml = b"""<LEIData xmlns="http://www.gleif.org/data/schema/leidata/2016">
      <LEIHeader><ContentDate>2026-09-11T16:00:00Z</ContentDate>
      <FileContent>GLEIF_FULL_PUBLISHED</FileContent><RecordCount>1</RecordCount></LEIHeader>
      <LEIRecords><LEIRecord><LEI>HWUPKR0MPOU8FGXBT394</LEI></LEIRecord></LEIRecords></LEIData>"""
    raw = archive_bytes(xml, "irrelevant-filename.xml")
    rows = []
    report = inspect_archive(
        io.BytesIO(raw),
        member="level1",
        metadata=metadata(format="xml.zip"),
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        on_record=lambda row, _: rows.append(row),
    )
    assert rows == [{"LEI": {"$": "HWUPKR0MPOU8FGXBT394"}}]
    assert report["record_count"] == 1
    with pytest.raises(Conflict, match="header"):
        inspect_archive(
            io.BytesIO(raw),
            member="level1",
            metadata=metadata(format="xml.zip", content_date="2026-09-12T16:00:00Z"),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"records":[{"LEI":"one","LEI":"two"}]}',
        b'{"records":[{}],"records":[]}',
        b'{"records":[{}]} {}',
        b'{"records":[{}',
        b'{"records":[NaN]}',
    ],
)
def test_malformed_native_json_is_never_verified(payload):
    raw = archive_bytes(payload)
    with pytest.raises(Conflict):
        inspect_archive(
            io.BytesIO(raw),
            member="level1",
            metadata=metadata(),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )


def test_native_company_fields_use_governed_mapping_and_other_kinds_retain_evidence():
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    record = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "Entity": {
            "EntityCategory": {"$": "GENERAL"},
            "LegalJurisdiction": {"$": "US-CA"},
        },
        "Registration": {
            "LastUpdateDate": {"$": "2026-09-10T00:00:00Z"},
            "RegistrationStatus": {"$": "LAPSED"},
        },
    }
    kwargs = {
        "member": "level1",
        "contract": dataset_contract("level1"),
        "source_code": "gleif.lei.v1",
        "eligible_leis": {"HWUPKR0MPOU8FGXBT394"},
        "publication": {
            "publication_key": "p1",
            "revision": 1,
            "artifact_sha256": "a" * 64,
            "member": "level1",
        },
        "ordinal": 0,
    }
    kind, evidence = record_evidence(record, **kwargs)
    assert kind == "assertion"
    assert evidence["fields"]["gleif_legal_jurisdiction"]["value"] == "US-CA"
    assert evidence["fields"]["gleif_registration_status"]["value"] == "LAPSED"
    assert "name" not in evidence["fields"]
    record["Entity"]["EntityCategory"]["$"] = "BRANCH"
    kind, evidence = record_evidence(record, **kwargs)
    assert kind == "deferred"
    assert evidence["raw_record"] == record
    assert evidence["reason"] == "unsupported_identity_kind"


@pytest.mark.parametrize("bound", ["max_compressed", "max_expanded", "max_record"])
def test_archive_limits_fail_closed(bound):
    raw = archive_bytes(b'{"records":[{"large":"' + b"x" * 1000 + b'"}]}')
    with pytest.raises(Conflict, match="bound"):
        inspect_archive(
            io.BytesIO(raw),
            member="level1",
            metadata=metadata(),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            **{bound: 10},
        )


def test_archive_hash_and_exact_count_are_required():
    raw = archive_bytes(b'{"records":[{}]}')
    for sha, count in [("0" * 64, 1), (hashlib.sha256(raw).hexdigest(), 2)]:
        with pytest.raises(Conflict):
            inspect_archive(
                io.BytesIO(raw),
                member="level1",
                metadata=metadata(count),
                expected_sha256=sha,
            )


def test_xml_external_entities_are_rejected():
    raw = archive_bytes(
        b'<!DOCTYPE LEIData [<!ENTITY secret SYSTEM "file:///etc/passwd">]><LEIData xmlns="http://www.gleif.org/data/schema/leidata/2016">&secret;</LEIData>'
    )
    with pytest.raises(Conflict):
        inspect_archive(
            io.BytesIO(raw),
            member="level1",
            metadata=metadata(format="xml.zip"),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )


@pytest.mark.parametrize("member,namespace,root,container,record,cdf,wrapper", [
    ("relationships", "rr", "RelationshipData", "RelationshipRecords", "RelationshipRecord", "RR_2.1", "relations"),
    ("reporting_exceptions", "repex", "ReportingExceptionData", "ReportingExceptions", "Exception", "REPEX_2.1", "exceptions"),
])
def test_rr_and_repex_xml_and_json_have_the_same_simple_record(member, namespace, root, container, record, cdf, wrapper):
    xml = f'<{root} xmlns="http://www.gleif.org/data/schema/{namespace}/2016"><Header><ContentDate>2026-09-11T16:00:00Z</ContentDate><FileContent>GLEIF_FULL_PUBLISHED</FileContent><RecordCount>1</RecordCount></Header><{container}><{record}><LEI>HWUPKR0MPOU8FGXBT394</LEI></{record}></{container}></{root}>'.encode()
    row = {"LEI": {"$": "HWUPKR0MPOU8FGXBT394"}}
    if member == "relationships":
        row = {"RelationshipRecord": row}
    hashes = []
    for fmt, payload in [("xml.zip", xml), ("json.zip", json.dumps({wrapper: [row]}).encode())]:
        raw = archive_bytes(payload)
        report = inspect_archive(io.BytesIO(raw), member=member, metadata=metadata(format=fmt, cdf_version=cdf), expected_sha256=hashlib.sha256(raw).hexdigest())
        hashes.append(report["canonical_source_hash"])
    assert hashes[0] == hashes[1]


def test_reporting_exception_is_retained_and_not_a_parent_edge():
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
    row = {"LEI": {"$": "HWUPKR0MPOU8FGXBT394"}, "ExceptionCategory": {"$": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT"}, "ExceptionReason": [{"$": "NON_CONSOLIDATING"}]}
    kind, result = record_evidence(row, member="reporting_exceptions", contract=dataset_contract("reporting_exceptions"),
        source_code="gleif.reporting_exceptions.v1", eligible_leis={"HWUPKR0MPOU8FGXBT394"}, ordinal=0,
        publication={"publication_key": "p1", "revision": 1, "artifact_sha256": "a"*64, "member": "reporting_exceptions"})
    assert kind == "assertion"
    assert result["relationships"] == []
    assert result["provenance"]["source"]["native_record"] == row


@pytest.mark.parametrize(
    "kind", ["IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"]
)
def test_native_accounting_relationships_are_typed_and_cycles_suppressed(kind):
    from types import SimpleNamespace

    from edgar_warehouse.mdm.clean.relationships import project

    state = SimpleNamespace(
        bindings={"a": "a", "b": "b"}, canonical={"a": "a", "b": "b"}
    )
    entities = {
        k: {"kind": "company", "status": "accepted", "profiles": []} for k in ("a", "b")
    }
    claims = {
        "a": {
            "assertion_id": "1",
            "relationships": [
                {
                    "type": kind,
                    "target_subject": "b",
                    "valid_from": "2020-01-01T00:00:00Z",
                }
            ],
        }
    }
    edges, reviews = project(claims, state, entities, "2026-01-01T00:00:00Z")
    assert not reviews
    assert any(e["type"] == kind and e["derived"] is False for e in edges)
    claims["b"] = {
        "assertion_id": "2",
        "relationships": [
            {"type": kind, "target_subject": "a", "valid_from": "2020-01-01T00:00:00Z"}
        ],
    }
    edges, reviews = project(claims, state, entities, "2026-01-01T00:00:00Z")
    assert not edges
    assert any(r["reason"] == "hierarchy_cycle" for r in reviews)
