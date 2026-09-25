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
