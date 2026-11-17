"""The committed IPO pipeline reading on invented SEC submissions documents: each stage filing of a company that filed
an IPO registration becomes a row with its stage, date and file number; a company that never filed one gives none.
Every name and number here is invented."""
import json
from pathlib import Path

import yaml

from edgar_warehouse.rules.source_engine import SourceEngine

CONTRACT = yaml.safe_load((Path(__file__).parents[2] / "rules/sources/sec.ipo/ipo-filings.yaml").read_text())
FILINGS = [  # (form, date, file number), newest first as the SEC lists them
    ("10-Q", "2026-08-10", "001-99999"), ("424B4", "2026-06-12", "333-999999"), ("EFFECT", "2026-06-11", "333-999999"),
    ("CERT", "2026-06-10", "001-99999"), ("8-A12B", "2026-06-10", "001-99999"), ("S-1/A", "2026-06-01", "333-999999"),
    ("S-1", "2026-05-20", "333-999999"), ("DRS/A", "2026-05-07", "377-09999"), ("DRS", "2026-03-30", "377-09999"),
    ("RW", "2026-04-01", "333-888888"), ("S-8", "2026-07-01", "333-777777")]


def document(cik: str, filings) -> bytes:
    recent = {"accessionNumber": [f"0000000009-26-{n:06d}" for n in range(len(filings))],
              "form": [f for f, _, _ in filings], "filingDate": [d for _, d, _ in filings],
              "fileNumber": [n for _, _, n in filings]}
    return json.dumps({"cik": cik, "name": "INVENTED ROCKETS INC", "filings": {"recent": recent}}).encode()


def read(doc: bytes):
    return SourceEngine(CONTRACT).read(doc, context={"observed_at": "2026-09-30T00:00:00+00:00"}).tables.get("filing", [])


def test_each_stage_filing_of_an_ipo_company_is_a_row_with_its_stage_date_and_file_number():
    rows = read(document("9999", FILINGS))
    assert [(r["form"], r["stage"], r["filing_date"], r["file_number"]) for r in rows] == [
        ("424B4", "priced", "2026-06-12", "333-999999"), ("EFFECT", "effective", "2026-06-11", "333-999999"),
        ("CERT", "listed", "2026-06-10", "001-99999"), ("8-A12B", "listed", "2026-06-10", "001-99999"),
        ("S-1/A", "amended", "2026-06-01", "333-999999"), ("S-1", "filed", "2026-05-20", "333-999999"),
        ("DRS/A", "draft", "2026-05-07", "377-09999"), ("DRS", "draft", "2026-03-30", "377-09999"),
        ("RW", "withdrawn", "2026-04-01", "333-888888")]  # the 10-Q and the S-8 mark no stage


def test_the_cik_is_the_companys_record_key_with_its_zeros_and_each_row_names_its_filing():
    rows = read(document("9999", FILINGS))
    assert {r["cik"] for r in rows} == {"0000009999"}
    assert len({r["accession_number"] for r in rows}) == len(rows)


def test_a_company_that_never_filed_an_ipo_registration_has_no_rows():
    shelf_only = [("S-3", "2026-02-01", "333-555555"), ("EFFECT", "2026-02-10", "333-555555"), ("424B5", "2026-03-01", "333-555555")]
    assert read(document("8888", shelf_only)) == []
