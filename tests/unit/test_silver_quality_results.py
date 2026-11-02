"""A silver load leaves its checks' results in a file for the catalog."""

from edgar_warehouse.silver_writer import checks, results


def _spec():
    return {"checks": [{"id": "non_blank", "check": "in_set", "column": "a", "values": ["x"], "on_fail": "flag"}]}


def test_the_report_counts_the_rows_it_checked():
    rows = [{"a": "x"}, {"a": "y"}, {"a": "z"}]
    _, report = checks.run(_spec(), rows)
    assert report["rows_checked"] == 3 and report["checks"]["non_blank"]["rows_failed"] == 2


def test_the_results_file_keeps_the_latest_report_of_each_check(tmp_path):
    path = tmp_path / "results.json"
    _, report = checks.run(_spec(), [{"a": None}, {"a": "x"}])
    results.record(path, "visits", report)
    _, later = checks.run(_spec(), [{"a": "x"}] * 4)
    results.record(path, "visits", later)
    kept = results.load(path)
    assert list(kept) == ["visits.non_blank"]
    assert (kept["visits.non_blank"]["rows_checked"], kept["visits.non_blank"]["rows_failed"]) == (4, 0)


def test_no_file_means_no_results(tmp_path):
    assert results.load(tmp_path / "none.json") == {}


def test_a_corrupt_results_file_is_named_not_a_key_error(tmp_path):
    import pytest

    path = tmp_path / "results.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not a quality results file"):
        results.load(path)
