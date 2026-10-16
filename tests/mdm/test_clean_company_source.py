"""Native Company evidence and bounded immutable input preparation."""

import copy
from datetime import UTC, datetime

import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord
from edgar_warehouse.mdm.clean.adapters import normalize as _normalize
from edgar_warehouse.mdm.clean.sec_company import (
    CONTRACT,
    POLICY,
    SOURCE_CODE,
)

from tests.support.retired_company_address import business_address
from tests.mdm.test_clean_activation import proof
from tests.support.name_census_inputs import gleif_archive, gleif_reading  # noqa: F401

# Field and identity tests need an active rule; this synthetic proof belongs
# only to the fixture. The standard POLICY deliberately stays inactive.
TEST_POLICY = copy.deepcopy(POLICY)
TEST_POLICY["automatic_rules"] = [
    {
        "kind": "company",
        "family": "classification",
        "rule_id": "sec-company-candidate",
        "rule_version": "2026-09-25.13",
        "verdict": "company",
        "activation": "measured",
        "proof": proof(),
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


def address_row(cik, **changes):
    return {
        "cik": cik,
        "address_type": "business",
        "street1": "1 Main Street",
        "street2": None,
        "city": "Cupertino",
        "state_or_country": "CA",
        "zip_code": "95014",
        "country": "CA",
        "last_sync_run_id": "capture-1",
        "last_synced_at": datetime(2026, 1, 1, tzinfo=UTC),
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
            {**row, "entity_type": "other"},
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication=publication,
        )


def test_step_ten_requires_the_landing_filer_category():
    publication = {
        "publication_key": "capture-1/company",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "records.jsonl",
    }
    row = source_row(
        1306965,
        entity_name="Shell plc",
        entity_type="other",
        sic="1311",
        category="",
    )
    row["last_synced_at"] = row["last_synced_at"].isoformat()
    for missing in ("", None):
        with pytest.raises(
            UnsupportedRecord, match="classification_deferred"
        ) as caught:
            normalize(
                {**row, "category": missing},
                source_code=SOURCE_CODE,
                contract=CONTRACT,
                publication=publication,
            )
        assert caught.value.detail["classification"]["step"] == "11"
    body = normalize(
        {**row, "category": "Large accelerated filer"},
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
    )
    assert body["provenance"]["classification"]["step"] == "10"


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
        from edgar_warehouse.mdm.clean import sec_company
        from edgar_warehouse.rules import files

        file = files.ROOT / "merge" / "kinds" / "company.yaml"
        # Other kinds may sit beside it (platform validation 05a).
        assert "company" in sec_company.POLICY["kinds"]
        assert sec_company.POLICY["kinds"]["company"] == files.load(file)
        assert sec_company.POLICY["kinds"]["company"]["defaults"]["sources"] == [
            "sec.submissions.company.v1",
            "gleif.level1.v1",
            "gleif.relationships.v1",
            "iapd.adv.filings.v1",
            "iapd.adv.custodians.v1",
            "sec.nport.registrant.v1",
        ]


def test_the_record_carries_its_matching_evidence_in_provenance():
    row = source_row(320193, entity_name="APPLE INC")
    row["last_synced_at"] = row["last_synced_at"].isoformat()
    row["business_address"] = {"postal_code": "95014", "country": "US"}
    row["name_census"] = {"census": "c" * 64, "key": "APPLE INC"}
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
        "name_census": {"census": "c" * 64, "key": "APPLE INC"},
        # The quality rule's standard address, a matching copy (ticket 22).
        "address": {"postcode": "95014", "country": "US"},
    }
    # Matching evidence grants no field a value.
    assert "business_postal_code" not in body["fields"]
    assert body["fields"]["address"] == {
        "op": "value",
        "value": {"postcode": "95014", "country": "US"},
    }




def test_a_foreign_business_address_has_a_country_and_no_region():
    """Ticket 18, finding 5: SEC writes a country in `stateOrCountry` ("P7",
    the Netherlands); it is the country, not a region."""
    foreign = business_address(address_row(937966, state_or_country="P7", city="Veldhoven",
                                           zip_code="5504 DR", country=None))
    assert foreign["region"] is None and foreign["country"] == "NL"
    domestic = business_address(address_row(320193))
    assert domestic["region"] == "CA" and domestic["country"] == "US"
    ontario = business_address(address_row(1, state_or_country="A6", country=None))
    assert ontario["region"] == "A6" and ontario["country"] == "CA"
    # X1: the United States with no state.
    unstated = business_address(address_row(2, state_or_country="X1", country=None))
    assert unstated["region"] is None and unstated["country"] == "US"
