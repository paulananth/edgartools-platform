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
                      "one_fiscal_year_filed_per_filing": 0, "one_fiscal_period_filed_per_filing": 0,
                      "period_start_not_after_end": 0}


def test_every_check_has_a_reason_and_flags_rather_than_refuses():
    for item in spec("fact")["checks"]:
        assert item["on_fail"] == "flag" and item["why"]


def test_a_period_that_starts_after_it_ends_is_flagged_on_a_fact_and_a_line_item():
    rows = [{"period_start": "2025-01-01", "period_end": "2025-12-31"}, {"period_start": "2025-12-31", "period_end": "2025-01-01"},
            {"period_start": None, "period_end": "2025-12-31"}]
    for table in ("fact", "line-item"):
        _, report = checks.run(spec(table), rows)
        assert report["checks"]["period_start_not_after_end"]["rows_failed"] == 1


def test_a_line_item_or_measure_has_an_empty_value_exactly_when_it_states_why():
    rows = [{"value": "1.5", "null_reason": None}, {"value": None, "null_reason": "no concept filed"},
            {"value": None, "null_reason": None}, {"value": "2", "null_reason": "denominator zero"}]
    for table in ("line-item", "measure"):
        kept, report = checks.run(spec(table), rows)
        assert report["checks"]["empty_value_has_reason"]["rows_failed"] == 2
        assert [bool(r["quality"]) for r in kept] == [False, False, True, True]
