"""Ownership parser adapter for Forms 3, 4, and 5 — backed by edgartools."""

from __future__ import annotations

from typing import Any

from edgar.ownership import Ownership

PARSER_NAME = "ownership_v1"
PARSER_VERSION = "2"


def parse_ownership(accession_number: str, content: str, form_type: str) -> dict[str, list[dict[str, Any]]]:
    parsed = Ownership.from_xml(content)
    owner_rows: list[dict[str, Any]] = []
    non_derivative_rows: list[dict[str, Any]] = []
    derivative_rows: list[dict[str, Any]] = []

    issuer_cik = _parse_cik(getattr(parsed.issuer, "cik", None))

    for owner_index, owner in enumerate(parsed.reporting_owners.owners, start=1):
        owner_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": owner_index,
                "owner_cik": _parse_cik(getattr(owner, "cik", None)),
                "owner_name": str(getattr(owner, "name", None) or ""),
                "is_director": bool(getattr(owner, "is_director", False)),
                "is_officer": bool(getattr(owner, "is_officer", False)),
                "is_ten_percent_owner": bool(getattr(owner, "is_ten_pct_owner", False)),
                "is_other": bool(getattr(owner, "is_other", False)),
                "officer_title": getattr(owner, "officer_title", None) or None,
                "issuer_cik": issuer_cik,
                "parser_version": PARSER_VERSION,
            }
        )

    for txn_index, txn in enumerate(
        getattr(parsed.non_derivative_table, "transactions", []) or [], start=1
    ):
        non_derivative_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": 1,
                "txn_index": txn_index,
                "security_title": str(getattr(txn, "security", None) or ""),
                "transaction_date": _to_str(getattr(txn, "date", None)),
                "transaction_code": str(getattr(txn, "transaction_code", None) or ""),
                "transaction_shares": _to_float(getattr(txn, "shares", None)),
                "transaction_price": _to_float(getattr(txn, "price", None)),
                "acquired_disposed_code": str(getattr(txn, "acquired_disposed", None) or ""),
                "shares_owned_after": _to_float(getattr(txn, "remaining", None)),
                "ownership_direct_indirect": str(getattr(txn, "direct_indirect", None) or ""),
                "parser_version": PARSER_VERSION,
            }
        )

    for txn_index, txn in enumerate(
        getattr(parsed.derivative_table, "transactions", []) or [], start=1
    ):
        derivative_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": 1,
                "txn_index": txn_index,
                "security_title": str(getattr(txn, "security", None) or ""),
                "transaction_date": _to_str(getattr(txn, "date", None)),
                "transaction_code": str(getattr(txn, "transaction_code", None) or ""),
                "transaction_shares": _to_float(getattr(txn, "shares", None)),
                "transaction_price": _to_float(getattr(txn, "price", None)),
                "acquired_disposed_code": str(getattr(txn, "acquired_disposed", None) or ""),
                "shares_owned_after": _to_float(getattr(txn, "remaining", None)),
                "ownership_direct_indirect": str(getattr(txn, "direct_indirect", None) or ""),
                "conversion_or_exercise_price": _to_float(getattr(txn, "exercise_price", None)),
                "exercise_date": _to_str(getattr(txn, "exercise_date", None)),
                "expiration_date": _to_str(getattr(txn, "expiration_date", None)),
                "underlying_security_title": str(getattr(txn, "underlying_security", None) or ""),
                "underlying_security_shares": _to_float(getattr(txn, "underlying_shares", None)),
                "parser_version": PARSER_VERSION,
            }
        )

    return {
        "sec_ownership_reporting_owner": owner_rows,
        "sec_ownership_non_derivative_txn": non_derivative_rows,
        "sec_ownership_derivative_txn": derivative_rows,
    }


def _parse_cik(value: Any) -> int | None:
    try:
        return int(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s if s else None
