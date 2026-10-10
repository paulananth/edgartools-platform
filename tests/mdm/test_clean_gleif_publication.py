"""GLEIF publication boundary: a record is usable only after its archive is verified.

The records themselves are read by their contracts (`test_clean_gleif_*_contract.py`);
the older reader and its tests were retired with Issue 20 L6."""

import hashlib
import io
import json
import zipfile

import pytest

from edgar_warehouse.mdm.clean.gleif_publication import attest_publication as inspect_archive
from edgar_warehouse.mdm.clean.store import Conflict
from tests.support.gleif_archives import archive_bytes, metadata


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


@pytest.mark.parametrize(
    "member,namespace,root,container,record,cdf,wrapper",
    [
        (
            "relationships",
            "rr",
            "RelationshipData",
            "RelationshipRecords",
            "RelationshipRecord",
            "RR_2.1",
            "relations",
        ),
        (
            "reporting_exceptions",
            "repex",
            "ReportingExceptionData",
            "ReportingExceptions",
            "Exception",
            "REPEX_2.1",
            "exceptions",
        ),
    ],
)
def test_rr_and_repex_xml_and_json_have_the_same_simple_record(
    member, namespace, root, container, record, cdf, wrapper
):
    xml = f'<{root} xmlns="http://www.gleif.org/data/schema/{namespace}/2016"><Header><ContentDate>2026-09-11T16:00:00Z</ContentDate><FileContent>GLEIF_FULL_PUBLISHED</FileContent><RecordCount>1</RecordCount></Header><{container}><{record}><LEI>HWUPKR0MPOU8FGXBT394</LEI></{record}></{container}></{root}>'.encode()
    row = {"LEI": {"$": "HWUPKR0MPOU8FGXBT394"}}
    if member == "relationships":
        row = {"RelationshipRecord": row}
    hashes = []
    for fmt, payload in [
        ("xml.zip", xml),
        ("json.zip", json.dumps({wrapper: [row]}).encode()),
    ]:
        raw = archive_bytes(payload)
        report = inspect_archive(
            io.BytesIO(raw),
            member=member,
            metadata=metadata(format=fmt, cdf_version=cdf),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )
        hashes.append(report["canonical_source_hash"])
    assert hashes[0] == hashes[1]


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


@pytest.mark.parametrize("member,cdf,wrapper", [
    ("level1", "LEI_3.1", "records"),
    ("relationships", "RR_2.1", "relations"),
    ("reporting_exceptions", "REPEX_2.1", "exceptions"),
])
@pytest.mark.parametrize("empty", [False, True])
def test_configured_json_preserves_full_source_attestation(member, cdf, wrapper, empty):
    from edgar_warehouse.mdm.clean.gleif_publication import VERSION
    from edgar_warehouse.mdm.clean.store import canonical

    # Neither record belongs to an approved mastering cohort. Attestation still
    # covers every raw record, including unmapped fields, types and list order.
    records = [] if empty else [
        {"LEI": {"$": "outside"}, "unmapped": [False, None, -0.0, 1e-5, "é🦀"]},
        {"nested": {"z": 2**63 - 1, "a": [{"v": 1.25}]}, "number": -(2**63 - 1)},
    ]
    payload = json.dumps({wrapper: records}, ensure_ascii=False).encode()
    raw = archive_bytes(payload)
    seen = []
    report = inspect_archive(
        io.BytesIO(raw), member=member,
        metadata=metadata(len(records), cdf_version=cdf),
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        on_record=lambda row, n: seen.append((n, row)),
    )
    expected = hashlib.sha256(b"".join(canonical(row).encode() + b"\n" for row in records)).hexdigest()
    assert seen == list(enumerate(records))
    assert report == {
        "adapter_version": VERSION,
        "raw_evidence_hash": hashlib.sha256(raw).hexdigest(),
        "canonical_source_hash": expected,
        "record_count": len(records),
        "domain_content_hash": hashlib.sha256(f"{VERSION}\n{member}\n{expected}".encode()).hexdigest(),
        "compressed_bytes": len(raw),
        "expanded_bytes": len(payload),
    }


def test_configured_json_preserves_explicit_larger_record_bound():
    record = {"text": "x" * 1_100_000}
    raw = archive_bytes(json.dumps({"records": [record]}).encode())
    seen = []
    report = inspect_archive(
        io.BytesIO(raw), member="level1", metadata=metadata(),
        expected_sha256=hashlib.sha256(raw).hexdigest(), max_record=2 * 1024**2,
        on_record=lambda row, n: seen.append(row),
    )
    assert report["record_count"] == 1 and seen == [record]


@pytest.mark.parametrize("kind", ["runtime", "source_rejected", "interrupt"])
def test_configured_json_preserves_consumer_failure_identity(kind):
    raw = archive_bytes(b'{"records":[{}]}')
    from edgar_warehouse.rules.source_engine import SourceRejected
    failure = {
        "runtime": RuntimeError("consumer_unavailable"),
        "source_rejected": SourceRejected("consumer_retry", "consumer_unavailable"),
        "interrupt": KeyboardInterrupt(),
    }[kind]
    def fail(row, ordinal):
        raise failure
    with pytest.raises(type(failure)) as caught:
        inspect_archive(
            io.BytesIO(raw), member="level1", metadata=metadata(),
            expected_sha256=hashlib.sha256(raw).hexdigest(), on_record=fail,
        )
    assert caught.value is failure


def test_small_xml_record_limit_does_not_limit_authenticated_header():
    xml = b"""<LEIData xmlns="http://www.gleif.org/data/schema/leidata/2016">
      <LEIHeader><ContentDate>2026-09-11T16:00:00Z</ContentDate>
      <FileContent>GLEIF_FULL_PUBLISHED</FileContent><RecordCount>1</RecordCount></LEIHeader>
      <LEIRecords><LEIRecord/></LEIRecords></LEIData>"""
    raw = archive_bytes(xml, "source.xml")
    seen = []
    report = inspect_archive(io.BytesIO(raw), member="level1", metadata=metadata(format="xml.zip"),
        expected_sha256=hashlib.sha256(raw).hexdigest(), max_record=2,
        on_record=lambda row, ordinal: seen.append((row, ordinal)))
    assert seen == [({}, 0)]
    assert report["record_count"] == 1
    raw = archive_bytes(xml.replace(b"<LEIRecord/>", b"<LEIRecord><LEI>large</LEI></LEIRecord>"), "source.xml")
    with pytest.raises(Conflict):
        inspect_archive(io.BytesIO(raw), member="level1", metadata=metadata(format="xml.zip"),
            expected_sha256=hashlib.sha256(raw).hexdigest(), max_record=2)




def test_a_native_publication_manifest_is_refused_before_any_work(tmp_path):
    """The native GLEIF path was retired (Issue 20 L6): a manifest still naming it
    fails closed, before any database read, rather than running as a plain manifest."""
    from uuid import uuid4

    from edgar_warehouse.mdm.clean import cli

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"contract_version": 2, "native_source": {}, "batches": [
        {"batch_id": "b0", "stage": "mastering"}]}))
    with pytest.raises(Conflict, match="retired"):
        cli.execute_manifest(None, None, path=str(path), run_id=str(uuid4()), stage="mastering", limit=10)
