"""Name Frequency from configured readings writes the census `write_name_census` writes."""

import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.name_census import _sec_population
from edgar_warehouse.mdm.clean.name_frequency import GLEIF_READING, write_name_frequency
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read
from tests.mdm.test_clean_company_source import (
    address_row, filing_row, former_row, gleif_archive, landing, source_row, write_run,
)
from tests.mdm.test_clean_name_census import gleif


def gleif_reading(folder: Path, archive: Path, wanted, count: int) -> dict:
    """The Golden Copy through its configured complete reading, as the `source.read` worker writes it."""
    folder.mkdir()
    store = Artifacts()
    source = store.put_bytes((folder / archive.name).as_uri(), archive.read_bytes())
    context = store.put(folder.as_uri(), {"version": 1, "input": source, "values": {"publication_count": count}})
    lookups = store.put(folder.as_uri(), {"version": 1, "input": source, "sets": {"wanted": sorted(wanted)}})
    request = store.put(folder.as_uri(), {"version": 3, "contract": store.put(folder.as_uri(), files.load(GLEIF_READING)),
                                          "artifacts": [{"input": source, "context": context, "lookups": lookups}]})
    task = {"input": request, "output": (folder / "reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": candidate}, store) == ({"source.output": True}, [])
    return candidate


RECORDS = [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.", other=["Old Name Inc"]),
           gleif("5493001KJTIIGC8Y1R12", "Other LLC", other=["Apple Inc."]),
           gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.", updated="2026-09-02T00:00:00Z"),
           gleif("549300BRANCH00000001", "Apple Inc.", category="BRANCH")]


@pytest.fixture
def capture(tmp_path):
    args = landing(tmp_path, [source_row(320193, entity_name="APPLE INC"), source_row(1, entity_name="OLD NAME INC")],
                   former=[former_row(320193, "Old Name Inc")], gleif=RECORDS)
    root = Path(args["landing_root"])
    second = write_run(root, "capture-2", {
        "sec_company": [source_row(789019, entity_name="Apple Inc.", last_sync_run_id="capture-2")],
        "sec_company_filing": [filing_row(999, "10-K", last_sync_run_id="capture-2")],
        "sec_company_address": [address_row(999, last_sync_run_id="capture-2")],
    }, folder="two")
    (tmp_path / "g").mkdir()
    archive, metadata, _ = gleif_archive(tmp_path / "g", RECORDS)
    filers = [("0000320193", "APPLE INC", ["Old Name Inc"]), ("0000000001", "OLD NAME INC", []),
              ("0000789019", "Apple Inc.", [])]
    return root, [args["landing_manifest"], str(second)], archive, metadata, _sec_population(filers)[1]


def test_it_writes_the_census_the_original_builder_writes(tmp_path, capture):
    from edgar_warehouse.mdm.clean.company_source import write_name_census

    root, manifests, archive, metadata, wanted = capture
    original = tmp_path / "original.json"
    write_name_census(landing_root=str(root), landing_manifests=manifests, gleif_archive=str(archive),
                      gleif_metadata=str(metadata), gleif_sha256=__import__("hashlib").sha256(archive.read_bytes()).hexdigest(),
                      output=str(original))
    configured = tmp_path / "configured.json"
    report = write_name_frequency(landing_root=str(root), landing_manifests=manifests,
                                  gleif_reading=gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS)),
                                  gleif_metadata=str(metadata), output=str(configured))
    assert configured.read_bytes() == original.read_bytes()
    census = json.loads(configured.read_text())
    assert census["entries"]["APPLE INC"]["cik_count"] == 2  # both captures hold the name
    assert census["entries"]["APPLE INC"]["leis"] == [["HWUPKR0MPOU8FGXBT394", "2026-09-02T00:00:00Z"]]
    assert census["entries"]["APPLE INC"]["other_name_holders"] == 1
    assert report["entries"] == len(census["entries"])


def test_a_reading_of_another_populations_names_is_refused(tmp_path, capture):
    root, manifests, archive, metadata, wanted = capture
    reading = gleif_reading(tmp_path / "r", archive, wanted - {"APPLE INC"}, len(RECORDS))
    with pytest.raises(Conflict, match="another SEC population"):
        write_name_frequency(landing_root=str(root), landing_manifests=manifests, gleif_reading=reading,
                             gleif_metadata=str(metadata), output=str(tmp_path / "x.json"))


def test_a_delta_or_a_short_publication_is_refused(tmp_path, capture):
    root, manifests, archive, metadata, wanted = capture
    reading = gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS))
    published = json.loads(metadata.read_text())
    for change, message in [({"file_content": "GLEIF_DELTA_PUBLISHED"}, "never a delta"),
                            ({"record_count": len(RECORDS) + 1}, "record count")]:
        metadata.write_text(json.dumps({**published, **change}))
        with pytest.raises(Conflict, match=message):
            write_name_frequency(landing_root=str(root), landing_manifests=manifests, gleif_reading=reading,
                                 gleif_metadata=str(metadata), output=str(tmp_path / "x.json"))


def test_a_filer_in_two_captures_is_refused(tmp_path, capture):
    root, manifests, archive, metadata, wanted = capture
    with pytest.raises(Conflict, match="two of the census's captures"):
        write_name_frequency(landing_root=str(root), landing_manifests=[manifests[0]] * 2,
                             gleif_reading=gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS)),
                             gleif_metadata=str(metadata), output=str(tmp_path / "x.json"))
