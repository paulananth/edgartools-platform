"""The Name Census: every SEC filer and every GLEIF legal entity carrying a name.

Company mastering ticket 08.
"""

import hashlib
import io
import json
import zipfile


from edgar_warehouse.mdm.clean import name_census
from edgar_warehouse.mdm.clean.name_census import VERSION, entry
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_stream

COMPLETE_READING = files.ROOT / "sources/gleif/census-complete-stream.yaml"


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


def configured(filers, records, *, cascade=None, recipe=None, population=None, archive_sha256=None):
    """The census `mdm name-census` writes: the Golden Copy through its configured
    complete reading (`census-complete-stream.yaml`), folded, then `document`.
    `cascade` is {"spec", "filers"}: the passes and every SEC filer as the cascade reads it."""
    held, wanted = name_census._sec_population(filers)
    spec, engine, _ = source_stream.stream_policy(recipe or files.load(COMPLETE_READING))
    found = []
    engine.stream_json_array(
        io.BytesIO(json.dumps({"records": records}).encode()), wrapper=spec["wrapper"],
        lookups={"wanted": sorted(wanted)}, context={"publication_count": len(records)},
        ordinal_context=spec["ordinal_context"], on_reading=lambda reading, _ordinal: found.append(reading.tables),
        **{k: spec[k] for k in ("max_bytes", "max_record", "max_records", "max_depth", "min_integer", "record_encoding")})
    return name_census.census(
        sec_population=population or {"capture_run_id": "run-1", "filers": len(filers)},
        gleif={"archive_sha256": archive_sha256 or hashlib.sha256(archive(records)).hexdigest(),
               "content_date": metadata(0)["content_date"], "file_content": "GLEIF_FULL_PUBLISHED",
               "record_count": len(records)},
        held=held, wanted=wanted, readings=found, cascade=cascade)


def census(filers, records):
    return configured(filers, records)


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

        filer = cascade.Filer(cik="0000320193", key="APPLE INC",
                              place=cascade.place({"street": "1 APPLE PARK WAY", "city": "CUPERTINO",
                                                   "postcode": "95014", "country": "US"}),
                              incorporated="US-CA", business_country="US")
        return configured([APPLE], records, cascade={"spec": cascade.spec(POLICY), "filers": [filer]})

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
