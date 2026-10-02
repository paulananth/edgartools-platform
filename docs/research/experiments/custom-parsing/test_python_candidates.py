"""Compare experimental configuration with current source-specific code.

Passing counterexample tests prove DIFFERENCE, not successful replacement.
All candidate rules stay local; no registration or runtime source is changed.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from edgar_warehouse.loaders.bronze_submission_extractors import (
    OWNERSHIP_FORMS, is_individual_filer, stage_company_loader,
    stage_recent_filing_loader,
)
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.mdm.clean.classification import fired
from edgar_warehouse.mdm.clean.company_source import CONTRACT, business_address
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, inspect_archive, record_evidence
from edgar_warehouse.mdm.clean.primitives import UnknownPrimitive, call
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files

CONFIG = files.load(Path(__file__).with_name("python-candidates.yaml"))
OURS = "HWUPKR0MPOU8FGXBT394"
OTHER = "5493001KJTIIGC8Y1R12"
PUBLICATION = {
    "publication_key": "pinned-research-fixture", "revision": 1,
    "artifact_sha256": "a" * 64, "member": "native-fixture",
    "effective_at": "2026-09-10T00:00:00+00:00",
}


@pytest.mark.parametrize("payload", [
    {"name": "Example Inc.", "entityType": "operating", "sic": "7372"},
    {},
    {"name": "", "sic": "   ", "description": None},
    {"name": "Éxample & Co", "sic": 0, "ein": 1234, "category": False},
], ids=["normal", "missing", "blank", "scalar-types"])
def test_sec_scalar_lookup_projection_is_exact(payload):
    """Current path lookup can replace ten literal field selections, with glue."""
    context = dict(cik=320193, sync_run_id="fixture-run", raw_object_id="raw", load_mode="bootstrap")
    reference = stage_company_loader(payload, **context)[0]
    projected = {name: adapters.value(payload, path)
                 for name, path in CONFIG["sec_company_fields"].items()}
    assert {**projected, **context} == reference


def test_mdm_field_mapping_is_not_a_drop_in_silver_projection():
    payload = {"name": "   "}
    reference = stage_company_loader(payload, 1, "run", "raw", "bootstrap")[0]
    assert reference["entity_name"] == "   "
    assert adapters.mapped_field(payload, "entity_name", "name") is None


def level1():
    return {
        "LEI": {"$": OURS},
        "Entity": {"EntityCategory": {"$": "GENERAL"},
                   "LegalName": {"$": "Example Inc."},
                   "LegalJurisdiction": {"$": "US-CA"}},
        "Registration": {"LastUpdateDate": {"$": PUBLICATION["effective_at"]}},
    }


def native(row, member="level1", eligible=None):
    return record_evidence(
        row, member=member, contract=dataset_contract(member),
        source_code=f"gleif.{member}.v1", eligible_leis=eligible if eligible is not None else {OURS, OTHER},
        publication=PUBLICATION, ordinal=0,
    )


def direct(row, member="level1"):
    contract = deepcopy(dataset_contract(member))
    if member == "relationships":
        contract["adapter"] = CONFIG["gleif_relationship_adapter"]
    # Shared provenance wrapper and pinned effective time are still caller work.
    return adapters.normalize(
        {**row, "_native": row}, source_code=f"gleif.{member}.v1",
        contract=contract, publication=PUBLICATION,
    )


@pytest.mark.parametrize("address", [None, {
    "FirstAddressLine": {"$": "One Main Street"},
    "AdditionalAddressLine": [{"$": "Building A"}, {"$": "Suite 700"}],
    "City": {"$": "Cupertino"}, "Region": {"$": "US-CA"},
    "PostalCode": {"$": "95014"}, "Country": {"$": "US"},
}], ids=["optional-missing", "address-and-repeated-lines"])
def test_gleif_level1_direct_mapping_matches_complete_assertion(address):
    row = level1()
    if address:
        row["Entity"]["LegalAddress"] = address
    kind, reference = native(row)
    assert kind == "assertion"
    assert direct(row) == reference  # Includes assertion_id and provenance.


@pytest.mark.parametrize("defect,reason", [
    ("outside-scope", "outside_approved_company_scope"),
    ("deletion", "gleif_deletion_flag"),
], ids=["scope-is-lost", "deletion-is-lost"])
def test_gleif_level1_mapping_does_not_replace_source_gates(defect, reason):
    row = level1()
    scope = set() if defect == "outside-scope" else {OURS}
    if defect == "deletion":
        row["Extension"] = {"gleif:Deletion": "true"}
    kind, reference = native(row, eligible=scope)
    assert (kind, reference["reason"]) == ("deferred", reason)
    assert direct(row)["kind"] == "company"  # Unsafe admission, not equivalence.


def test_gleif_invalid_category_changes_the_failure_contract():
    row = level1()
    row["Entity"]["EntityCategory"]["$"] = "UNKNOWN_FUTURE_CATEGORY"
    kind, reference = native(row)
    assert (kind, reference["reason"]) == ("deferred", "invalid_identity_kind")
    with pytest.raises(adapters.UnsupportedRecord) as found:
        direct(row)
    assert found.value.reason == "unsupported_identity_kind"


def test_gleif_invalid_lei_validation_is_already_shared():
    row = level1()
    row["LEI"]["$"] = OURS[:-1] + "5"
    _, reference = native(row)
    with pytest.raises(adapters.UnsupportedRecord) as found:
        direct(row)
    assert reference["reason"] == found.value.reason == "invalid_lei_checksum"


def relationship():
    return {"RelationshipRecord": {
        "Relationship": {
            "StartNode": {"NodeID": {"$": OURS}, "NodeIDType": {"$": "LEI"}},
            "EndNode": {"NodeID": {"$": OTHER}, "NodeIDType": {"$": "LEI"}},
            "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
            "RelationshipStatus": {"$": "ACTIVE"},
            "RelationshipPeriods": {"RelationshipPeriod": {
                "PeriodType": {"$": "RELATIONSHIP_PERIOD"},
                "StartDate": {"$": "2025-01-01T00:00:00+00:00"},
            }},
        },
        "Registration": {"LastUpdateDate": {"$": PUBLICATION["effective_at"]},
                         "RegistrationStatus": {"$": "PUBLISHED"}},
    }}


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE"])
def test_relationship_scalar_projection_can_match_complete_assertion(status):
    row = relationship()
    rel = row["RelationshipRecord"]["Relationship"]
    rel["RelationshipStatus"]["$"] = status
    if status == "INACTIVE":
        rel["RelationshipPeriods"]["RelationshipPeriod"]["EndDate"] = {
            "$": "2026-01-01T00:00:00+00:00"}
    kind, reference = native(row, "relationships")
    assert kind == "assertion"
    assert direct(row, "relationships") == reference


@pytest.mark.parametrize("defect,reason", [
    ("endpoint-type", "unsupported_relationship_endpoint"),
    ("outside-scope", "outside_approved_company_scope"),
    ("deletion", "gleif_deletion_flag"),
    ("multiple-periods", "ambiguous_relationship_period"),
    ("inactive-no-end", "invalid_relationship_status_interval"),
    ("reversed-interval", "invalid_relationship_interval"),
])
def test_relationship_direct_mapping_loses_rejection_contract(defect, reason):
    row = relationship()
    raw = row["RelationshipRecord"]
    rel = raw["Relationship"]
    scope = {OURS, OTHER}
    period = rel["RelationshipPeriods"]["RelationshipPeriod"]
    if defect == "endpoint-type":
        rel["StartNode"]["NodeIDType"]["$"] = "OTHER"
    elif defect == "outside-scope":
        scope = {OURS}
    elif defect == "deletion":
        raw["Extension"] = {"gleif:Deletion": "true"}
    elif defect == "multiple-periods":
        rel["RelationshipPeriods"]["RelationshipPeriod"] = [period, deepcopy(period)]
    elif defect == "inactive-no-end":
        rel["RelationshipStatus"]["$"] = "INACTIVE"
    elif defect == "reversed-interval":
        period["EndDate"] = {"$": "2024-01-01T00:00:00+00:00"}
    kind, reference = native(row, "relationships", eligible=scope)
    assert (kind, reference["reason"]) == ("deferred", reason)
    assert direct(row, "relationships")["kind"] == "company"


@pytest.mark.parametrize("defect", ["singleton-list", "offset-date"])
def test_relationship_mapping_also_differs_on_valid_native_inputs(defect):
    row = relationship()
    periods = row["RelationshipRecord"]["Relationship"]["RelationshipPeriods"]
    if defect == "singleton-list":
        periods["RelationshipPeriod"] = [periods["RelationshipPeriod"]]
    else:
        periods["RelationshipPeriod"]["StartDate"]["$"] = "2025-01-01T01:00:00+01:00"
    kind, reference = native(row, "relationships")
    assert kind == "assertion"
    candidate = direct(row, "relationships")
    assert candidate["relationships"] != reference["relationships"]
    assert candidate["assertion_id"] != reference["assertion_id"]


@pytest.mark.parametrize("state,country", [("CA", None), (None, "X0"), ("P7", None)])
def test_sec_raw_address_mapping_cannot_replace_country_and_region_conversion(state, country):
    row = dict(street1="One Main", street2=None, city="Town", zip_code="12345",
               state_or_country=state, country_code=country)
    reference = adapters.mapped_field({"business_address": business_address(row)},
                                     "address", CONTRACT["adapter"]["fields"]["address"])
    candidate = adapters.mapped_field(row, "address", CONFIG["sec_address"])
    assert candidate != reference
    assert candidate.get("country") != reference["country"]


@pytest.mark.parametrize("forms", [["4"], ["4", "5/A"], ["4", "10-K"], [], ["20-F"]])
def test_individual_overlap_rule_matches_bounded_known_forms(forms):
    row = {"entityType": "other", "sic": None, "tickers": [], "filings": {"recent": {"form": forms}}}
    verdict, _ = fired(CONFIG["individual_candidate"], row, {})
    assert (verdict == "person") == is_individual_filer(row)


def test_individual_overlap_rule_fails_for_an_unlisted_form():
    row = {"entityType": "other", "filings": {"recent": {"form": ["4", "UNKNOWN_NEW_FORM"]}}}
    assert "UNKNOWN_NEW_FORM" not in OWNERSHIP_FORMS
    assert not is_individual_filer(row)
    assert fired(CONFIG["individual_candidate"], row, {})[0] == "person"
    with pytest.raises(UnknownPrimitive, match="unknown primitive"):
        call("values_subset@1", {}, row, {})


def test_existing_path_mapping_does_not_expand_parallel_filing_arrays():
    row = {"filings": {"recent": {"accessionNumber": ["a", "b"], "form": ["10-K"]}}}
    reference = stage_recent_filing_loader(row, 1, "run", "raw", "bootstrap")
    assert [(r["accession_number"], r["form"]) for r in reference] == [("a", "10-K"), ("b", None)]
    assert adapters.value(row, "filings.recent.form.0") is None
    with pytest.raises(adapters.UnsupportedRecord, match="invalid_field_mapping"):
        adapters.mapped_field(row, "filings", {"each": "filings.recent.accessionNumber"})


def test_existing_mapping_has_no_grouping_sorting_or_distinct_operator():
    with pytest.raises(adapters.UnsupportedRecord, match="invalid_field_mapping"):
        adapters.mapped_field({"tickers": ["Z", "A", "Z"]}, "tickers",
                              {"group_by": "cik", "distinct": "ticker", "sort": "source_rank"})


def rust_xml():
    return (Path(__file__).parent / "rust" / "gleif-two-records.xml").read_text()


def python_xml_rows(xml):
    """Authenticate the SAME XML fixture and mutations used by Rust probes."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fixture.xml", xml)
    raw = stream.getvalue()
    rows = []
    inspect_archive(
        io.BytesIO(raw), member="level1",
        metadata={"format": "xml.zip", "cdf_version": "LEI_3.1",
                  "content_date": "2026-10-01T00:00:00+00:00",
                  "file_content": "GLEIF_FULL_PUBLISHED", "delta_start": None,
                  "record_count": 2},
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        on_record=lambda row, _: rows.append(row),
    )
    return rows


def test_rust_fixture_scalar_projection_matches_python_decoder():
    rows = python_xml_rows(rust_xml())
    expected = json.loads(Path(__file__).with_name("rust_scalar_expected.json").read_text())
    paths = {"lei": "LEI.$", "name": "Entity.LegalName.$",
             "category": "Entity.EntityCategory.$", "country": "Entity.LegalAddress.Country.$",
             "postal_code": "Entity.LegalAddress.PostalCode.$"}
    projected = [{"ordinal": ordinal, **{key: adapters.value(row, path) for key, path in paths.items()}}
                 for ordinal, row in enumerate(rows, 1)]
    assert projected == expected
    # Namespace-qualified attribute representation remains different from Rust.
    assert rows[0]["Entity"]["LegalName"]["@{http://www.w3.org/XML/1998/namespace}lang"] == "en"


def test_python_decoder_preserves_cdata_that_rust_loses():
    xml = rust_xml().replace("<lei:LegalName>Example Limited</lei:LegalName>",
                            "<lei:LegalName><![CDATA[Café Limited]]></lei:LegalName>")
    assert python_xml_rows(xml)[1]["Entity"]["LegalName"]["$"] == "Café Limited"


@pytest.mark.parametrize("defect", ["wrong-root", "malformed", "wrong-namespace",
                                   "dtd", "missing-header", "wrong-count", "duplicate-count"])
def test_python_rejects_rust_fixture_mutations_that_rust_does_not_fail_closed(defect):
    xml = rust_xml()
    if defect == "wrong-root":
        xml = xml.replace("lei:LEIData", "lei:OtherData")
    elif defect == "malformed":
        xml = "<LEIData><LEIRecords></LEIData>"
    elif defect == "wrong-namespace":
        xml = xml.replace("http://www.gleif.org/data/schema/leidata/2016", "urn:wrong")
    elif defect == "dtd":
        xml = xml.replace('<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE LEIData []>')
    elif defect == "missing-header":
        start = xml.index("  <lei:LEIHeader>")
        end = xml.index("  </lei:LEIHeader>") + len("  </lei:LEIHeader>")
        xml = xml[:start] + xml[end:]
    elif defect == "wrong-count":
        xml = xml.replace("<lei:RecordCount>2</lei:RecordCount>", "<lei:RecordCount>999</lei:RecordCount>")
    elif defect == "duplicate-count":
        xml = xml.replace("<lei:RecordCount>2</lei:RecordCount>",
                          "<lei:RecordCount>2</lei:RecordCount><lei:RecordCount>2</lei:RecordCount>")
    with pytest.raises(Conflict):
        python_xml_rows(xml)
