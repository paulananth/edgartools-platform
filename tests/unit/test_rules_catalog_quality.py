"""Business catalog metadata preserves engine meaning and native API encoding."""
import pytest
from edgar_warehouse.rules import catalog

@pytest.mark.parametrize("expected, actual, matches", [
    ("a `field`", "a &#96;field&#96;", True),
    ("literal &#96;", "literal &amp;#96;", True),
    ("literal &#96;", "literal &#96;", False),
    ("a & b", "a &amp; b", True),
    ("original", "changed", False),
])
def test_markdown_comparison_decodes_only_the_native_transport_layer(expected, actual, matches):
    assert catalog._description_equal(expected, actual) == matches


def test_incomplete_verified_quality_counts_publish_as_aborted():
    body = catalog._result_body({"table": "sample_source.v1", "check": "record_name_present",
        "rows_checked": 8, "rows_failed": 1, "on_fail": "exception", "status": "unknown",
        "rows_unknown": 2, "units_unknown": 1, "rule_version": "source-quality-v1",
        "at": "2026-11-13T20:00:00+00:00"})

    assert body["testCaseStatus"] == "Aborted"
    assert body["passedRows"] == 7
    assert body["failedRows"] == 1
    assert "Incomplete/unknown" in body["result"]
    assert "source-quality-v1" in body["result"]
    assert body["testResultValue"] == [
        {"name": "rowsChecked", "value": "8"}, {"name": "rowsFailed", "value": "1"}]
