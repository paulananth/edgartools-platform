"""Native Company evidence and bounded immutable input preparation."""

import copy
from datetime import UTC, datetime

import pytest

from edgar_warehouse.mdm.adapters import UnsupportedRecord
from edgar_warehouse.mdm.adapters import normalize as _normalize
from edgar_warehouse.mdm.sec_company import (
    CONTRACT,
    POLICY,
    SOURCE_CODE,
)

# Field and identity tests run with only the classification rule on.
TEST_POLICY = copy.deepcopy(POLICY)
TEST_POLICY["automatic_rules"] = [
    {
        "kind": "company",
        "family": "classification",
        "rule_id": "sec-company-candidate",
        "rule_version": "2026-11-27.operating-investment-and-legal-form-filers",
        "verdict": "company",
    }
]


def normalize(row, **kwargs):
    return _normalize(row, policy=TEST_POLICY, **kwargs)


def source_row(cik, **changes):
    return {
        "cik": cik,
        "entity_name": f"Synthetic Company {cik}",
        "entity_type": "operating",
        "sic": "1234",
        "tickers": ["SYN"],
        "forms": ["10-K"],
        "last_sync_run_id": "capture-1",
        "last_synced_at": datetime(2026, 1, 1, tzinfo=UTC),
        "raw_object_id": f"raw-{cik}",
        **changes,
    }


def test_native_company_kind_identifiers_and_unknown_effective_time():
    publication = {
        "publication_key": "capture-1/company",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "records.jsonl",
    }
    row = source_row(123)
    row["last_synced_at"] = row["last_synced_at"].isoformat()
    a = normalize(
        row, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication
    )
    b = normalize(
        {**row, "cik": "0000000123"},
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
    )
    assert a == b
    assert a["record_key"] == "0000000123" and a["identifiers"] == {"cik": "0000000123"}
    assert a["effective_at"] is None
    assert a["profiles"] == []
    assert a["provenance"]["source"]["observed_at"] == row["last_synced_at"]
    with pytest.raises(UnsupportedRecord, match="classification_deferred"):
        normalize(
            {**row, "entity_type": "other", "entity_name": "Jane Example"},
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication=publication,
        )


def test_phase_2_masters_every_company_filer_and_sets_aside_the_rest_with_its_probable_kind():
    """Company phase 2 (operator, 2026-11-27, decisions 2 to 6 and 8): a filer is mastered with or without a ticker. An investment filer is a
    company; an operating filer is one unless fund-named; a filer SEC types other is one by a 20-F or 40-F, by a new
    listing's registration (with a ticker, operator, 2026-11-17), or by a legal-form word in its name, unless it is
    person-suffixed, fund-named or files Form D alone. Asset-backed issuers, commodity pools and governments stay aside."""
    publication = {
        "publication_key": "capture-1/company",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "records.jsonl",
    }

    def row(name="Example Works", **changes):
        made = source_row(1000001, **{"entity_name": name, "sic": "1311", "tickers": [], **changes})
        made["last_synced_at"] = made["last_synced_at"].isoformat()
        return made

    def step(made):
        try:
            found = normalize(made, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication)
        except UnsupportedRecord as held:
            assert str(held.reason) == "classification_deferred"
            return "aside", held.detail["classification"]["step"], held.probable_kind
        return "company", found["provenance"]["classification"]["step"], None

    cases = [
        (row(entity_type="operating"), ("company", "8", None)),
        (row(entity_type="operating", tickers=["EXA"]), ("company", "8", None)),
        (row("Example Income Fund", entity_type="operating"), ("aside", "5", "fund_structure")),
        (row("Example Income Fund", entity_type="investment"), ("company", "4", None)),
        (row(entity_type="operating", sic="6189"), ("aside", "1", None)),
        (row(entity_type="investment", sic="6221"), ("aside", "2", "fund_structure")),
        (row(entity_type="other", sic="8888"), ("aside", "3", "government")),
        (row("Example Works Inc", entity_type="other"), ("company", "14", None)),
        (row("Example Works Inc", entity_type="other", forms=["10-K", "D"]), ("company", "14", None)),
        (row("Example Works Inc", entity_type="other", forms=["D", "D/A"]), ("aside", "13", None)),
        (row("Example Works LP", entity_type="other", forms=["D"]), ("aside", "13", None)),
        (row("Example Partners Fund LP", entity_type="other"), ("aside", "12", "fund_structure")),
        (row("Jane Example CPA", entity_type="other"), ("aside", "9", "person")),
        (row("Jane Example", entity_type="other"), ("aside", "15", None)),
        (row("Example Works", entity_type="other", forms=["6-K", "20-F"]), ("company", "10", None)),
        (row("Example Works", entity_type="other", forms=["40-F"]), ("company", "10", None)),
        *[(row("Example Works", entity_type="other", forms=["8-A12B", form], tickers=["EXA"]), ("company", "10a", None))
          for form in ("S-1", "F-1", "S-11", "424B1", "424B4")],
        (row("Example Works Inc", entity_type=""), ("aside", "15", None)),
        (row("Example Works", entity_type="other", forms=["S-1"]), ("aside", "15", None)),
    ]
    assert [step(made) for made, _ in cases] == [verdict for _, verdict in cases]


def test_a_corrected_reading_of_one_sec_publication_is_a_second_assertion():
    """Company mastering ticket 01, through the real SEC Company contract.

    A mapping correction must not re-bind the record: the subject is keyed on
    source code and record key, and neither moves.
    """
    publication = {
        "publication_key": "capture-1",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "company.parquet",
        "record_locator": "line:1",
    }
    # The bundle writer renders source scalars before the adapter sees them.
    row = source_row(
        320193, last_synced_at=datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    )
    first = normalize(
        row, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication
    )
    corrected = normalize(
        row,
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
        mapping_version=2,
    )
    assert "mapping_version" not in first
    assert corrected["mapping_version"] == 2
    assert corrected["assertion_id"] != first["assertion_id"]
    assert corrected["subject"] == first["subject"]
    assert corrected["record_key"] == first["record_key"]


class TestTheCompanyRule:
    """SEC gives state of incorporation; GLEIF gives jurisdiction (2026-09-24)."""

    def test_sec_state_of_incorporation_is_its_own_field_as_sec_writes_it(self):
        fields = normalize(
            source_row(
                1306965,
                state_of_incorporation="E9",
                last_synced_at="2026-01-01T00:00:00+00:00",
            ),
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication={
                "publication_key": "p",
                "revision": 0,
                "artifact_sha256": "a" * 64,
                "member": "m",
            },
        )["fields"]
        assert fields["state_of_incorporation"] == {"op": "value", "value": "E9"}
        assert "jurisdiction" not in fields

    def test_blank_text_is_unknown_not_a_value(self):
        fields = normalize(
            source_row(
                937966,
                state_of_incorporation="",
                description="   ",
                last_synced_at="2026-01-01T00:00:00+00:00",
            ),
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication={
                "publication_key": "p",
                "revision": 0,
                "artifact_sha256": "a" * 64,
                "member": "m",
            },
        )["fields"]
        assert fields["state_of_incorporation"] == {"op": "unknown"}
        assert fields["description"] == {"op": "unknown"}

    def test_the_company_rule_is_loaded_not_restated(self):
        from edgar_warehouse.mdm import sec_company
        from edgar_warehouse.rules import files

        file = files.ROOT / "merge" / "kinds" / "company.yaml"
        # Other kinds may sit beside it (platform validation 05a).
        assert "company" in sec_company.POLICY["kinds"]
        loaded = sec_company.POLICY["kinds"]["company"]
        assert {key: value for key, value in loaded.items() if key != "lists"} == {
            key: value for key, value in files.load(file).items() if key != "lists"}
        assert files.load(file)["lists"].items() <= loaded["lists"].items() and "entity_legal_form" in loaded["lists"]
        assert sec_company.POLICY["kinds"]["company"]["defaults"]["sources"] == [
            "sec.company.v1",
            "gleif.level1.v1",
            "gleif.relationships.v1",
            "iapd.adv.filings.v2",
            "iapd.adv.custodians.v1",
            "sec.nport.registrant.v2",
            "sec.ncen.adviser.v1",
            "sec.ncen.registrant.v1",
        ]


def test_the_record_carries_its_matching_evidence_in_provenance():
    row = source_row(320193, entity_name="APPLE INC")
    row["last_synced_at"] = row["last_synced_at"].isoformat()
    row["business_address"] = {"postal_code": "95014", "country": "US"}
    row["name_count"] = {"name_count": "c" * 64, "key": "APPLE INC"}
    body = normalize(
        row,
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication={
            "publication_key": "capture-1/company",
            "revision": 0,
            "effective_at": None,
            "artifact_sha256": "a" * 64,
            "member": "records.jsonl",
        },
    )
    assert body["provenance"]["matching"] == {
        "business_postal_code": "95014",
        "business_country": "US",
        "name_count": {"name_count": "c" * 64, "key": "APPLE INC"},
        # The quality rule's standard address, a matching copy (ticket 22).
        "address": {"postcode": "95014", "country": "US"},
    }
    # Matching evidence grants no field a value.
    assert "business_postal_code" not in body["fields"]
    assert body["fields"]["address"] == {
        "op": "value",
        "value": {"postcode": "95014", "country": "US"},
    }

