"""The first quality checks of the company-facts silver tables (ticket 169),
run on invented rows through the real check engine."""
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import checks


def spec(name):
    return files.load(files.ROOT / "sources" / "sec.company-facts" / f"silver-company-{name}.yaml")


def test_a_measure_over_an_unknown_window_is_flagged():
    rows = [{"window_years": w} for w in (1, 3, 5, 10, 7)]
    _, report = checks.run(spec("measure"), rows)
    assert report["checks"]["window_years_known"]["rows_failed"] == 1
    assert report["rows_checked"] == 5


def test_facts_of_one_filing_must_agree_on_what_the_filing_is():
    same = {"accession_number": "A-1", "form": "10-K", "filed": "2026-02-01", "fiscal_year_filed": 2025, "fiscal_period_filed": "FY"}
    rows = [dict(same), dict(same), dict(same), {**same, "form": "10-Q"}, {**same, "accession_number": "A-2"}]
    _, report = checks.run(spec("fact"), rows)
    failed = {check: item["rows_failed"] for check, item in report["checks"].items()}
    assert failed == {"one_form_per_filing": 1, "one_filed_per_filing": 0,
                      "one_fiscal_year_filed_per_filing": 0, "one_fiscal_period_filed_per_filing": 0}


def test_every_check_has_a_reason_and_flags_rather_than_refuses():
    for item in spec("fact")["checks"]:
        assert item["on_fail"] == "flag" and item["why"]
