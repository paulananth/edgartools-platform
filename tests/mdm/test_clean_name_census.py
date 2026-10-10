"""The Name Census: every SEC filer and every GLEIF legal entity carrying a name.

Company mastering ticket 08.
"""

import hashlib
import io
import json
import zipfile

import pytest

from edgar_warehouse.mdm.clean.name_census import VERSION, build, entry
from edgar_warehouse.mdm.clean.store import Conflict, digest


def gleif(lei, legal, *, other=(), category="GENERAL", updated="2026-09-01T00:00:00Z"):
    entity = {"LegalName": {"$": legal}, "EntityCategory": {"$": category}}
    if other:
        entity["OtherEntityNames"] = {
            "OtherEntityName": [
                {"$": name, "@type": "PREVIOUS_LEGAL_NAME"} for name in other
            ]
        }
    return {
        "LEI": {"$": lei},
        "Entity": entity,
        "Registration": {"LastUpdateDate": {"$": updated}},
    }


def archive(records):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("golden.json", json.dumps({"records": records}))
    return raw.getvalue()


def metadata(count, **changes):
    return {
        "format": "json.zip",
        "cdf_version": "LEI_3.1",
        "content_date": "2026-09-11T16:00:00+00:00",
        "file_content": "GLEIF_FULL_PUBLISHED",
        "delta_start": None,
        "record_count": count,
        **changes,
    }


def census(filers, records, **meta):
    raw = archive(records)
    return build(
        filers=filers,
        sec_population={"capture_run_id": "run-1", "filers": len(filers)},
        gleif_archive=io.BytesIO(raw),
        gleif_metadata=metadata(len(records), **meta),
        gleif_sha256=hashlib.sha256(raw).hexdigest(),
    )


APPLE = ("0000320193", "APPLE INC", [])
WAYFAIR = ("0001616707", "Wayfair Inc.", [])


class TestWhoCarriesAName:
    def test_one_filer_and_one_legal_entity(self):
        doc = census([APPLE], [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")])
        assert doc["entries"]["APPLE INC"] == {
            "ciks": ["0000320193"],
            "cik_count": 1,
            "leis": [["HWUPKR0MPOU8FGXBT394", "2026-09-01T00:00:00Z"]],
            "lei_count": 1,
            "other_name_holders": 0,
        }

    def test_a_different_legal_form_is_a_different_name(self):
        doc = census([WAYFAIR], [gleif("549300WAYFAIRLLC00001", "WAYFAIR LLC")])
        assert doc["entries"]["WAYFAIR INC"]["lei_count"] == 0

    def test_a_former_sec_name_counts_as_a_holder(self):
        renamed = ("0000000002", "NEW NAME INC", ["APPLE INC"])
        doc = census([APPLE, renamed], [])
        assert doc["entries"]["APPLE INC"]["cik_count"] == 2

    def test_another_gleif_entity_with_the_name_as_another_name_counts(self):
        doc = census(
            [APPLE],
            [
                gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc."),
                gleif(
                    "549300OTHER000000001", "Fruit Holdings LLC", other=["Apple Inc."]
                ),
            ],
        )
        assert doc["entries"]["APPLE INC"]["other_name_holders"] == 1

    def test_a_branch_is_not_a_legal_entity(self):
        doc = census(
            [APPLE],
            [
                gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc."),
                gleif("549300BRANCH00000001", "Apple Inc.", category="BRANCH"),
            ],
        )
        assert doc["entries"]["APPLE INC"]["lei_count"] == 1


class TestTheCensusIsBoundToItsInputs:
    def test_it_records_both_populations(self):
        doc = census([APPLE], [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")])
        assert doc["version"] == VERSION
        assert doc["sec"] == {"capture_run_id": "run-1", "filers": 1}
        assert doc["gleif"]["file_content"] == "GLEIF_FULL_PUBLISHED"
        assert doc["gleif"]["record_count"] == 1

    def test_a_delta_publication_is_refused(self):
        with pytest.raises(Conflict, match="never a delta"):
            census(
                [APPLE],
                [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")],
                file_content="GLEIF_DELTA_PUBLISHED",
                delta_start="2026-09-10T16:00:00+00:00",
            )

    def test_a_population_count_that_disagrees_is_refused(self):
        raw = archive([])
        with pytest.raises(Conflict, match="SEC population"):
            build(
                filers=[APPLE],
                sec_population={"capture_run_id": "run-1", "filers": 2},
                gleif_archive=io.BytesIO(raw),
                gleif_metadata=metadata(0),
                gleif_sha256=hashlib.sha256(raw).hexdigest(),
            )


class TestWhatARecordCarries:
    def test_its_entry_names_the_census(self):
        doc = census([APPLE], [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")])
        found = entry(doc, "APPLE INC /CA/", census_digest=digest(doc))
        assert found["census"] == digest(doc)
        assert found["key"] == "APPLE INC"
        assert found["leis"] == [["HWUPKR0MPOU8FGXBT394", "2026-09-01T00:00:00Z"]]

    def test_a_name_the_census_does_not_hold_has_no_entry(self):
        doc = census([APPLE], [])
        assert entry(doc, "SOMEONE ELSE INC", census_digest="x") is None


class TestTheCascade:
    """Ticket 21: the census runs the cascade over both whole sources."""

    def native(self, lei, legal, street, country="US", status="ACTIVE"):
        address = {"FirstAddressLine": {"$": street}, "City": {"$": "CUPERTINO"},
                   "PostalCode": {"$": "95014"}, "Country": {"$": country}}
        record = gleif(lei, legal)
        record["Entity"].update({"LegalAddress": address, "HeadquartersAddress": address,
                                 "LegalJurisdiction": {"$": "US-CA"}, "EntityStatus": {"$": status}})
        record["Registration"]["RegistrationStatus"] = {"$": "ISSUED"}
        return record

    def run(self, records):
        from edgar_warehouse.mdm.clean import cascade
        from edgar_warehouse.mdm.clean.company_source import POLICY
        from edgar_warehouse.mdm.clean.gleif_source import dataset_contract

        filer = cascade.Filer(cik="0000320193", key="APPLE INC",
                              place=cascade.place({"street": "1 APPLE PARK WAY", "city": "CUPERTINO",
                                                   "postcode": "95014", "country": "US"}),
                              incorporated="US-CA", business_country="US")
        raw = archive(records)
        return build(
            filers=[APPLE], sec_population={"capture_run_id": "run-1", "filers": 1},
            gleif_archive=io.BytesIO(raw), gleif_metadata=metadata(len(records)),
            gleif_sha256=hashlib.sha256(raw).hexdigest(),
            cascade={"spec": cascade.spec(POLICY), "filers": [filer], "gleif_contract": dataset_contract("level1")},
        )

    def test_the_entity_at_the_filers_address_binds_in_the_first_pass(self):
        found = self.run([self.native("HWUPKR0MPOU8FGXBT394", "Apple Inc.", "1 Apple Park Way"),
                          self.native("5493001KJTIIGC8Y1R12", "Apple Inc.", "1 Rue de Paris", country="FR")])
        answer = found["cascade"]["assignments"]["0000320193"]
        assert (answer["lei"], answer["pass"], answer["via"]) == ("HWUPKR0MPOU8FGXBT394", "P1", "legal name")
        assert answer["flags"] == ["name held by another candidate"]
        assert [p["pass"] for p in found["cascade"]["passes"]][:2] == ["P1", "P2"]

    def test_an_entity_the_rules_find_ineligible_never_binds(self):
        found = self.run([self.native("HWUPKR0MPOU8FGXBT394", "Apple Inc.", "1 Apple Park Way", status="INACTIVE")])
        assert found["cascade"]["assignments"] == {}

    def test_without_passes_the_census_is_as_before(self):
        assert "cascade" not in census([APPLE], [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")])


def test_a_record_carries_its_ciks_cascade_answer_inside_its_census_entry():
    from tests.support.retired_company_preparation import _census_evidence

    found = census([APPLE], [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")])
    row = {"cik": 320193, "entity_name": "APPLE INC"}
    assert "cascade" not in _census_evidence(found, row, "d")  # no passes: as before
    found["cascade"] = {"version": "sec-gleif-cascade-v1", "assignments": {"0000320193": {"lei": "L", "pass": "P1"}}}
    carried = _census_evidence(found, row, "d")
    assert carried["key"] == "APPLE INC"
    assert carried["cascade"] == {"census": "d", "version": "sec-gleif-cascade-v1", "lei": "L", "pass": "P1"}
    assert "cascade" not in _census_evidence(found, {"cik": 1, "entity_name": "APPLE INC"}, "d")


def same(left, right):
    """Equal but for the archive digest: each zip the fixture writes has its own timestamps."""
    return [{**d, "gleif": {**d["gleif"], "archive_sha256": None}} for d in (left, right)] == [
        {**right, "gleif": {**right["gleif"], "archive_sha256": None}}] * 2


class TestTheConfiguredReadingCountsTheSame:
    """The configured Golden Copy reading, folded, gives the document `build` gives."""

    def configured(self, filers, cascade_filers, records, spec):
        from collections import Counter

        from edgar_warehouse.mdm.clean import cascade, name_census
        from edgar_warehouse.rules import files
        from edgar_warehouse.workers import source_stream
        from tests.mdm.test_clean_name_census import metadata

        held, wanted = name_census._sec_population(filers)
        engine = source_stream.stream_policy(files.load(files.ROOT / "sources/gleif/census-complete-stream.yaml"))[1]
        found = []
        engine.stream_json_array(
            io.BytesIO(json.dumps({"records": records}).encode()), wrapper="records",
            lookups={"wanted": sorted(wanted)}, context={"publication_count": len(records)},
            ordinal_context="source_index", max_bytes=1048576, max_record=1048576, max_records=100000,
            on_reading=lambda reading, _ordinal: found.append(reading.tables))
        counts = cascade.count_addresses(f.place for f in cascade_filers) if spec else Counter()
        legal, other, entities = name_census.fold_reading(
            found, cascade_wanted={f.key for f in cascade_filers} - {""}, address_counts=counts)
        raw = archive(records)
        return name_census.document(
            sec_population={"capture_run_id": "run-1", "filers": len(filers)},
            gleif={"archive_sha256": hashlib.sha256(raw).hexdigest(), "content_date": metadata(0)["content_date"],
                   "file_content": "GLEIF_FULL_PUBLISHED", "record_count": len(records)},
            held=held, wanted=wanted, legal=legal, other=other,
            cascade={"spec": spec, "filers": cascade_filers} if spec else None,
            entities=entities, address_counts=counts)

    def test_names_counted_alike(self):
        records = [gleif("A", "Apple Inc.", other=["Wayfair Inc."]),
                   gleif("B", "Other LLC", other=["Apple Inc."]),
                   gleif("A", "Apple Inc.", updated="2026-09-02T00:00:00Z"),
                   gleif("C", "Apple Inc.", category="BRANCH")]
        assert same(self.configured([APPLE, WAYFAIR], [], records, None), census([APPLE, WAYFAIR], records))

    def test_cascade_answered_alike(self):
        from edgar_warehouse.mdm.clean import cascade
        from edgar_warehouse.mdm.clean.company_source import POLICY

        case = TestTheCascade()
        records = [case.native("HWUPKR0MPOU8FGXBT394", "Apple Inc.", "1 Apple Park Way"),
                   case.native("5493001KJTIIGC8Y1R12", "Apple Inc.", "1 Rue de Paris", country="FR"),
                   case.native("HWUPKR0MPOU8FGXBT394", "Apple Inc.", "1 Apple Park Way", status="INACTIVE")]
        filer = cascade.Filer(cik="0000320193", key="APPLE INC",
                              place=cascade.place({"street": "1 APPLE PARK WAY", "city": "CUPERTINO",
                                                   "postcode": "95014", "country": "US"}),
                              incorporated="US-CA", business_country="US")
        expected = case.run(records)
        assert expected["cascade"]["assignments"]
        assert same(self.configured([APPLE], [filer], records, cascade.spec(POLICY)), expected)
