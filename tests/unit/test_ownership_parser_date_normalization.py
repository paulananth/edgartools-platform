"""Regression tests for edgar_warehouse.parsers.ownership date normalization.

SEC Form 3/4/5 XML legitimately attaches footnote markers (e.g. "[F2]") to
date-shaped fields. DuckDB's implicit VARCHAR->DATE cast silently truncates
such values (confirmed live), but Snowflake's COPY INTO cast is strict and
rejects them outright -- this caused LOAD_SILVER_LANDING_TASK to abort every
scheduled run and auto-suspend in prod (2026-08-29 through 2026-09-01+).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from edgar_warehouse.parsers.ownership import _to_date_str, parse_ownership


class TestToDateStr:
    def test_strips_trailing_footnote_marker(self):
        assert _to_date_str("2021-02-04 [F2]") == "2021-02-04"

    def test_strips_trailing_footnote_marker_multi_digit(self):
        assert _to_date_str("2021-02-04 [F12]") == "2021-02-04"

    def test_passes_through_clean_iso_date_unchanged(self):
        assert _to_date_str("2021-02-04") == "2021-02-04"

    def test_returns_none_for_none(self):
        assert _to_date_str(None) is None

    def test_returns_none_for_empty_string(self):
        assert _to_date_str("") is None

    def test_returns_none_for_no_date_prefix(self):
        assert _to_date_str("[F2]") is None

    def test_returns_none_for_garbage(self):
        assert _to_date_str("not a date") is None


class _FakeTxn(SimpleNamespace):
    """Mimics edgartools' DerivativeTransaction/NonDerivativeTransaction shape."""


def _fake_parsed_with_derivative_exercise_date(exercise_date_value: str):
    issuer = SimpleNamespace(cik="910001")
    owners = SimpleNamespace(owners=[])
    non_derivative_table = SimpleNamespace(transactions=[])
    derivative_txn = _FakeTxn(
        security="Option",
        date="2021-02-04 [F2]",
        transaction_code="A",
        shares="100",
        price="1.00",
        acquired_disposed="A",
        remaining="100",
        direct_indirect="D",
        exercise_price="1.00",
        exercise_date=exercise_date_value,
        expiration_date="2026-02-04 [F3]",
        underlying_security="Common Stock",
        underlying_shares="100",
    )
    derivative_table = SimpleNamespace(transactions=[derivative_txn])
    return SimpleNamespace(
        issuer=issuer,
        reporting_owners=owners,
        non_derivative_table=non_derivative_table,
        derivative_table=derivative_table,
    )


class TestParseOwnershipNormalizesDateFields:
    def test_footnote_marked_exercise_date_is_normalized(self):
        fake_parsed = _fake_parsed_with_derivative_exercise_date("2021-02-04 [F2]")
        with patch(
            "edgar_warehouse.parsers.ownership.Ownership.from_xml",
            return_value=fake_parsed,
        ):
            result = parse_ownership("0001234567-24-000001", "<xml/>", "4")

        derivative_rows = result["sec_ownership_derivative_txn"]
        assert len(derivative_rows) == 1
        assert derivative_rows[0]["exercise_date"] == "2021-02-04"
        assert derivative_rows[0]["expiration_date"] == "2026-02-04"

    def test_footnote_marked_transaction_date_is_normalized(self):
        fake_parsed = _fake_parsed_with_derivative_exercise_date("2021-02-04")
        with patch(
            "edgar_warehouse.parsers.ownership.Ownership.from_xml",
            return_value=fake_parsed,
        ):
            result = parse_ownership("0001234567-24-000002", "<xml/>", "4")

        derivative_rows = result["sec_ownership_derivative_txn"]
        assert derivative_rows[0]["transaction_date"] == "2021-02-04"

    def test_footnote_marker_never_reaches_a_date_field(self):
        fake_parsed = _fake_parsed_with_derivative_exercise_date("2021-02-04 [F2]")
        with patch(
            "edgar_warehouse.parsers.ownership.Ownership.from_xml",
            return_value=fake_parsed,
        ):
            result = parse_ownership("0001234567-24-000003", "<xml/>", "4")

        row = result["sec_ownership_derivative_txn"][0]
        for field in ("transaction_date", "exercise_date", "expiration_date"):
            assert "[" not in (row[field] or ""), (
                f"{field}={row[field]!r} still carries a footnote marker"
            )
