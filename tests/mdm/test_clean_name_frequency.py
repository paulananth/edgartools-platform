"""Name Frequency from configured readings writes the census the retired builder wrote
(`tests/support/retired_name_census.py`, the independent oracle), counting the SEC
population from the receipt-bound raw capture."""

import hashlib
import json
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean.name_census import _sec_population
from edgar_warehouse.mdm.clean.name_frequency import write_name_frequency
from edgar_warehouse.mdm.clean.store import Conflict, canonical
from tests.mdm.test_clean_company_source import gleif_archive, gleif_reading
from tests.mdm.test_clean_name_census import gleif


RECORDS = [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.", other=["Old Name Inc"]),
           gleif("5493001KJTIIGC8Y1R12", "Other LLC", other=["Apple Inc."]),
           gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.", updated="2026-09-02T00:00:00Z"),
           gleif("549300BRANCH00000001", "Apple Inc.", category="BRANCH")]
FILERS = [("0000320193", "APPLE INC", ["Old Name Inc"]), ("0000000001", "OLD NAME INC", []),
          ("0000789019", "Apple Inc.", [])]


def key(cik: int) -> str:
    return f"warehouse/bronze/submissions/sec/cik={cik}/main/2026/09/29/CIK{cik:010d}.json"


def write_capture(root: Path, documents: dict[int, dict]) -> tuple[Path, Path]:
    """A capture folder (receipts.jsonl and bronze/) and a population naming every document."""
    receipts = []
    for cik, document in documents.items():
        raw = json.dumps(document).encode()
        path = root / "bronze" / key(cik).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(cik), "sha256": hashlib.sha256(raw).hexdigest()})
    (root / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    population = root / "population.json"
    population.write_text(json.dumps([key(cik) for cik in documents]))
    return root, population


@pytest.fixture
def capture(tmp_path):
    folder, population = write_capture(tmp_path / "capture", {
        320193: {"name": "APPLE INC", "formerNames": [{"name": "Old Name Inc", "from": "2000-01-01"}, {"name": ""}]},
        1: {"name": "OLD NAME INC", "formerNames": []},
        789019: {"name": "Apple Inc."}})
    (tmp_path / "g").mkdir()
    archive, metadata, _ = gleif_archive(tmp_path / "g", RECORDS)
    return folder, population, archive, metadata, _sec_population(FILERS)[1]


def census_of(tmp_path, capture, **changes):
    folder, population, archive, metadata, wanted = capture
    if "gleif_reading" not in changes:
        changes["gleif_reading"] = gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS))
    return write_name_frequency(capture=str(folder), population=str(population), gleif_metadata=str(metadata),
                                **{"output": str(tmp_path / "x.json"), **changes})


def test_it_writes_the_census_the_retired_builder_writes(tmp_path, capture):
    import io

    from tests.support import retired_name_census

    folder, population, archive, metadata, wanted = capture
    configured = tmp_path / "configured.json"
    report = census_of(tmp_path, capture, output=str(configured))
    census = json.loads(configured.read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: E731
    sec = {"receipts_sha256": sha(folder / "receipts.jsonl"), "population_sha256": sha(population), "filers": 3}
    expected = retired_name_census.build(
        filers=FILERS, sec_population=sec, gleif_archive=io.BytesIO(archive.read_bytes()),
        gleif_metadata=json.loads(metadata.read_text()), gleif_sha256=sha(archive))
    assert configured.read_bytes() == (canonical(expected) + "\n").encode()
    assert census["entries"]["APPLE INC"]["cik_count"] == 2  # two filers hold the name
    assert census["entries"]["APPLE INC"]["leis"] == [["HWUPKR0MPOU8FGXBT394", "2026-09-02T00:00:00Z"]]
    assert census["entries"]["APPLE INC"]["other_name_holders"] == 1
    assert report["entries"] == len(census["entries"])


def test_a_document_the_receipts_do_not_name_is_refused(tmp_path, capture):
    folder, population, *_ = capture
    population.write_text(json.dumps([key(320193), key(42)]))
    with pytest.raises(Conflict, match="receipts do not"):
        census_of(tmp_path, capture)


def test_a_document_that_differs_from_its_receipt_is_refused(tmp_path, capture):
    folder, *_ = capture
    (folder / "bronze" / key(1).removeprefix("warehouse/bronze/")).write_text(json.dumps({"name": "CHANGED"}))
    with pytest.raises(Exception, match="(?i)hash|sha256|differ"):
        census_of(tmp_path, capture)


def test_a_filer_counted_twice_is_refused(tmp_path, capture):
    folder, population, *_ = capture
    second = "warehouse/bronze/submissions/sec/cik=1/main/2026/09/30/CIK0000000001.json"
    raw = (folder / "bronze" / key(1).removeprefix("warehouse/bronze/")).read_bytes()
    (folder / "bronze" / second.removeprefix("warehouse/bronze/")).parent.mkdir(parents=True)
    (folder / "bronze" / second.removeprefix("warehouse/bronze/")).write_bytes(raw)
    with (folder / "receipts.jsonl").open("a") as stream:
        stream.write(json.dumps({"bytes": len(raw), "key": second, "sha256": hashlib.sha256(raw).hexdigest()}) + "\n")
    population.write_text(json.dumps([key(320193), key(1), key(789019), second]))
    with pytest.raises(Conflict, match="population twice"):
        census_of(tmp_path, capture)


def test_former_names_that_are_not_a_list_are_refused(tmp_path):
    folder, population = write_capture(tmp_path / "capture", {7: {"name": "X", "formerNames": "Y"}})
    (tmp_path / "g").mkdir()
    archive, metadata, _ = gleif_archive(tmp_path / "g", RECORDS)
    with pytest.raises(Exception, match="formerNames"):
        census_of(tmp_path, (folder, population, archive, metadata, _sec_population([("0000000007", "X", [])])[1]))


def test_a_reading_of_another_populations_names_is_refused(tmp_path, capture):
    folder, population, archive, metadata, wanted = capture
    reading = gleif_reading(tmp_path / "r", archive, wanted - {"APPLE INC"}, len(RECORDS))
    with pytest.raises(Conflict, match="another SEC population"):
        census_of(tmp_path, capture, gleif_reading=reading)


def test_a_delta_or_a_short_publication_is_refused(tmp_path, capture):
    folder, population, archive, metadata, wanted = capture
    reading = gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS))
    published = json.loads(metadata.read_text())
    for change, message in [({"file_content": "GLEIF_DELTA_PUBLISHED", "delta_start": "2026-09-10T16:00:00+00:00"}, "never a delta"),
                            ({"record_count": len(RECORDS) + 1}, "record count")]:
        metadata.write_text(json.dumps({**published, **change}))
        with pytest.raises(Conflict, match=message):
            census_of(tmp_path, capture, gleif_reading=reading)


def test_a_reading_made_by_another_recipe_is_refused(tmp_path, capture, monkeypatch):
    from edgar_warehouse.mdm.clean import name_frequency
    from edgar_warehouse.rules import files

    folder, population, archive, metadata, wanted = capture
    altered = files.load(name_frequency.GLEIF_READING)
    altered["read"]["limits"]["max_records"] = 99_999
    original = files.load
    monkeypatch.setattr(files, "load", lambda path: altered if path == name_frequency.GLEIF_READING else original(path))
    reading = gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS))
    monkeypatch.setattr(files, "load", original)
    with pytest.raises(Conflict, match="not made by census-complete-stream.yaml"):
        census_of(tmp_path, capture, gleif_reading=reading)


def test_metadata_the_publisher_would_not_have_written_is_refused(tmp_path, capture):
    folder, population, archive, metadata, wanted = capture
    reading = gleif_reading(tmp_path / "r", archive, wanted, len(RECORDS))
    published = json.loads(metadata.read_text())
    for change in ({"content_date": "yesterday"}, {"format": "csv.zip"}, {"cdf_version": "LEI_2.1"}):
        metadata.write_text(json.dumps({**published, **change}))
        with pytest.raises(Conflict):
            census_of(tmp_path, capture, gleif_reading=reading)


def test_a_switched_on_cascade_is_refused(tmp_path, capture, monkeypatch):
    # Name Frequency has no configured cascade reading yet; the cascade is off in today's policy.
    from edgar_warehouse.mdm.clean import cascade, name_frequency

    monkeypatch.setattr(name_frequency, "active_rules",
                        lambda policy: [("on", {"when": [{"primitive": cascade.TEST}]})])
    with pytest.raises(Conflict, match="cascade is switched on"):
        census_of(tmp_path, capture, gleif_reading={"uri": "file:///unused", "sha256": "0" * 64})
