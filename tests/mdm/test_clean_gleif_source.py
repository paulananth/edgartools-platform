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
            "LegalName": {"$": "Example Inc."},
            "LegalJurisdiction": {"$": "US-CA"},
            "LegalAddress": {
                "FirstAddressLine": {"$": "One Main Street"},
                "AdditionalAddressLine": [{"$": "Building A"}, {"$": "Suite 700"}],
                "City": {"$": "Cupertino"},
                "Region": {"$": "US-CA"},
                "PostalCode": {"$": "95014"},
                "Country": {"$": "US"},
            },
        },
        "Registration": {
            "LastUpdateDate": {"$": "2026-09-10T00:00:00Z"},
            "RegistrationStatus": {"$": "LAPSED"},
        },
    }
    kwargs = {
        "member": "level1",
        "contract": dataset_contract("level1"),
        "source_code": "gleif.level1.v1",
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
    assert evidence["fields"]["jurisdiction"]["value"] == "US-CA"
    assert evidence["fields"]["address"]["value"] == {
        "street": "One Main Street",
        "street2": "Building A\nSuite 700",
        "city": "Cupertino",
        "region": "US-CA",
        "postcode": "95014",
        "country": "US",
    }
    assert evidence["fields"]["gleif_registration_status"]["value"] == "LAPSED"
    # GLEIF's legal name now fills the shared `name` field, SEC first where both
    # supply one (operator, 2026-09-24; supersedes keeping GLEIF names apart).
    # A record with none is a data quality exception (ticket 22).
    assert evidence["fields"]["name"] == {"op": "value", "value": "Example Inc."}
    record["Entity"]["EntityCategory"]["$"] = "BRANCH"
    kind, evidence = record_evidence(record, **kwargs)
    assert kind == "deferred"
    assert evidence["raw_record"] == record
    assert evidence["reason"] == "unsupported_identity_kind"
    # It waits in the Stage as what it probably is (CONTEXT.md, Probable Kind).
    assert evidence["probable_kind"] == "branch"


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
    "reason,valid",
    [
        ([{"$": "NON_CONSOLIDATING"}], True),
        ({"$": "NON_PUBLIC"}, True),
        (42, False),
        ({"bogus": "x"}, False),
        ([{"$": "NOT_A_GLEIF_REASON"}], False),
        ([{"$": ""}], False),
    ],
)
def test_reporting_exception_is_retained_and_not_a_parent_edge(reason, valid):
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    row = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "ExceptionCategory": {"$": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT"},
        "ExceptionReason": reason,
    }
    kind, result = record_evidence(
        row,
        member="reporting_exceptions",
        contract=dataset_contract("reporting_exceptions"),
        source_code="gleif.reporting_exceptions.v1",
        eligible_leis={"HWUPKR0MPOU8FGXBT394"},
        ordinal=0,
        publication={
            "publication_key": "p1",
            "revision": 1,
            "artifact_sha256": "a" * 64,
            "member": "reporting_exceptions",
        },
    )
    assert kind == "deferred"
    assert result["reason"] == (
        "reported_parent_exception" if valid else "invalid_exception_reason"
    )
    assert result["raw_record"] == row


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


def test_a_corrected_reading_of_one_gleif_publication_is_a_second_assertion():
    """Company mastering ticket 01, through the real native GLEIF contract."""
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    record = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "Entity": {
            "EntityCategory": {"$": "GENERAL"},
            "LegalName": {"$": "Example Inc."},
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
    _, first = record_evidence(record, **kwargs)
    _, corrected = record_evidence(record, **kwargs, mapping_version=2)
    assert "mapping_version" not in first
    assert corrected["mapping_version"] == 2
    assert corrected["assertion_id"] != first["assertion_id"]
    assert corrected["subject"] == first["subject"]


@pytest.mark.parametrize(
    ("category", "probable"),
    [
        ("FUND", "fund_structure"),
        ("BRANCH", "branch"),
        ("RESIDENT_GOVERNMENT_ENTITY", "government"),
        ("INTERNATIONAL_ORGANIZATION", "international_organization"),
        ("SOLE_PROPRIETOR", None),
    ],
)
def test_a_waiting_gleif_record_carries_the_kind_its_category_names(category, probable):
    """GLEIF's own category sorts the Stage; a sole proprietor is not settled."""
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    record = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "Entity": {"EntityCategory": {"$": category}},
        "Registration": {"LastUpdateDate": {"$": "2026-09-10T00:00:00Z"}},
    }
    kind, evidence = record_evidence(
        record,
        member="level1",
        contract=dataset_contract("level1"),
        source_code="gleif.lei.v1",
        eligible_leis={"HWUPKR0MPOU8FGXBT394"},
        publication={
            "publication_key": "p1",
            "revision": 1,
            "artifact_sha256": "a" * 64,
            "member": "level1",
        },
        ordinal=0,
    )
    assert kind == "deferred"
    assert evidence.get("probable_kind") == probable


@pytest.mark.parametrize(
    ("category", "probable"),
    [
        ("GENERAL", "company"),
        ("FUND", "fund_structure"),
        ("SOLE_PROPRIETOR", None),
        (None, None),
    ],
)
def test_a_gleif_record_outside_the_company_scope_still_carries_its_kind(
    category, probable
):
    """Scope decides whether it waits, not what it probably is."""
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    record = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "Entity": {"EntityCategory": {"$": category}} if category else {},
        "Registration": {"LastUpdateDate": {"$": "2026-09-10T00:00:00Z"}},
    }
    kind, evidence = record_evidence(
        record,
        member="level1",
        contract=dataset_contract("level1"),
        source_code="gleif.lei.v1",
        eligible_leis=set(),
        publication={
            "publication_key": "p1",
            "revision": 1,
            "artifact_sha256": "a" * 64,
            "member": "level1",
        },
        ordinal=0,
    )
    assert kind == "deferred"
    assert evidence["reason"] == "outside_approved_company_scope"
    assert evidence.get("probable_kind") == probable


def test_an_agent_legal_address_is_withheld_and_the_headquarters_address_is_kept():
    """Ticket 22: GLEIF gives two addresses. The legal one is often a registered
    agent's; the headquarters one is then the company's own, fit to match on."""
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
    from edgar_warehouse.mdm.clean.matching import _read

    record = {
        "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
        "Entity": {
            "EntityCategory": {"$": "GENERAL"},
            "LegalName": {"$": "Example Inc."},
            "LegalAddress": {
                "FirstAddressLine": {"$": "C/O The Corporation Trust Company"},
                "AdditionalAddressLine": [{"$": "1209 Orange Street"}],
                "City": {"$": "Wilmington"},
                "PostalCode": {"$": "19801"},
                "Country": {"$": "US"},
            },
            "HeadquartersAddress": {
                "FirstAddressLine": {"$": "One Main Street"},
                "AdditionalAddressLine": [{"$": "Suite 700"}],
                "City": {"$": "Cupertino"},
                "PostalCode": {"$": "95014-2083"},
                "Country": {"$": "US"},
            },
        },
        "Registration": {"LastUpdateDate": {"$": "2026-09-10T00:00:00Z"}},
    }
    kind, evidence = record_evidence(
        record, member="level1", contract=dataset_contract("level1"), source_code="gleif.level1.v1",
        eligible_leis={"HWUPKR0MPOU8FGXBT394"}, ordinal=0,
        publication={"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64, "member": "level1"},
    )
    assert kind == "assertion"
    assert evidence["fields"]["address"]["value"]["street"] == "C/O The Corporation Trust Company"
    assert _read(evidence, "matching.address") is None
    assert _read(evidence, "matching.headquarters_address") == {
        "street": "ONE MAIN ST", "city": "CUPERTINO", "postcode": "95014", "country": "US",
    }
    assert evidence["provenance"]["matching"]["headquarters_postal_code"] == "95014-2083"


def _repex(lei="HWUPKR0MPOU8FGXBT394", **extra):
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    row = {
        "LEI": {"$": lei},
        "ExceptionCategory": {"$": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT"},
        "ExceptionReason": [{"$": "NATURAL_PERSONS"}],
        **extra,
    }
    contract = dataset_contract("reporting_exceptions")
    kind, result = record_evidence(
        row,
        member="reporting_exceptions",
        contract=contract,
        source_code="gleif.reporting_exceptions.v1",
        eligible_leis={"HWUPKR0MPOU8FGXBT394"},
        ordinal=0,
        publication={"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64,
                     "member": "reporting_exceptions"},
    )
    return kind, result, contract


def test_an_invalid_lei_never_blocks_a_run():
    """Ticket 18, finding 3: an LEI that fails its check digit can never be
    one of our Companies (the Company scope is checked when the release is
    validated), so it is set aside without blocking."""
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract

    _, result, _ = _repex(lei="HWUPKR0MPOU8FGXBT395")
    assert result["reason"] == "invalid_lei_checksum"
    for member in ("level1", "relationships", "reporting_exceptions"):
        reasons = dataset_contract(member)["nonblocking_deferred_reasons"]
        assert {"invalid_lei", "invalid_lei_checksum"} <= set(reasons), member


def test_an_empty_deletion_field_in_a_full_file_is_read_as_usual():
    """Ticket 18, finding 1: 257,509 reporting exceptions in the 2026-09-11
    full file carry `gleif:Deletion` as null. GLEIF flags deletions in delta
    files only; a record in the full file is current."""
    _, result, _ = _repex(Extension={"gleif:Deletion": None})
    assert result["reason"] == "reported_parent_exception"


def test_a_deletion_flag_with_a_value_is_refused_and_blocks():
    """A delta file's deletion of one of our Companies' records is never read
    as a live record."""
    _, result, contract = _repex(Extension={"gleif:Deletion": "true"})
    assert result["reason"] == "gleif_deletion_flag"
    assert "gleif_deletion_flag" not in contract["nonblocking_deferred_reasons"]
    # An Extension that is not an object fails closed, never crashes.
    _, result, _ = _repex(Extension="unexpected")
    assert result["reason"] == "gleif_deletion_flag"


def test_a_deletion_outside_our_companies_stays_out_of_scope():
    """A delta deletes records of every LEI; only ours may block."""
    _, result, _ = _repex(lei="5493001KJTIIGC8Y1R12", Extension={"gleif:Deletion": "true"})
    assert result["reason"] == "outside_approved_company_scope"


@pytest.mark.parametrize("in_scope", [True, False])
def test_a_deletion_flag_on_level1_and_relationships(in_scope):
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

    ours, other = "HWUPKR0MPOU8FGXBT394", "5493001KJTIIGC8Y1R12"
    scope = {ours, other} if in_scope else {"529900T8BM49AURSDO55"}
    publication = {"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64}
    level1 = {"LEI": {"$": ours}, "Entity": {"EntityCategory": {"$": "GENERAL"}},
              "Extension": {"gleif:Deletion": "true"}}
    relationship = {"RelationshipRecord": {
        "Relationship": {"StartNode": {"NodeID": {"$": ours}, "NodeIDType": {"$": "LEI"}},
                         "EndNode": {"NodeID": {"$": other}, "NodeIDType": {"$": "LEI"}}},
        "Extension": {"gleif:Deletion": "true"}}}
    expected = "gleif_deletion_flag" if in_scope else "outside_approved_company_scope"
    for member, row in (("level1", level1), ("relationships", relationship)):
        _, result = record_evidence(
            row, member=member, contract=dataset_contract(member), source_code=f"gleif.{member}.v1",
            eligible_leis=scope, ordinal=0, publication={**publication, "member": member})
        assert result["reason"] == expected, member


@pytest.mark.parametrize("member,cdf,wrapper", [
    ("level1", "LEI_3.1", "records"),
    ("relationships", "RR_2.1", "relations"),
    ("reporting_exceptions", "REPEX_2.1", "exceptions"),
])
@pytest.mark.parametrize("empty", [False, True])
def test_configured_json_preserves_full_source_attestation(member, cdf, wrapper, empty):
    from edgar_warehouse.mdm.clean.gleif_source import VERSION
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
