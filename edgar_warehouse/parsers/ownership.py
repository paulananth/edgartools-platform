"""Ownership parser adapter for Forms 3, 4, and 5."""

from __future__ import annotations

from typing import Any

from edgar.ownership import Ownership

PARSER_NAME = "ownership_v1"
PARSER_VERSION = "1"


def parse_ownership(accession_number: str, content: str, form_type: str) -> dict[str, list[dict[str, Any]]]:
    parsed = Ownership.from_xml(content)
    owner_rows: list[dict[str, Any]] = []
    non_derivative_rows: list[dict[str, Any]] = []
    derivative_rows: list[dict[str, Any]] = []

    for owner_index, owner in enumerate(parsed.reporting_owners.owners, start=1):
        relationship = getattr(owner, "relationship", None)
        owner_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": owner_index,
                "owner_cik": _parse_owner_cik(getattr(owner, "cik", None)),
                "owner_name": getattr(owner, "name", None),
                "is_director": getattr(relationship, "is_director", None),
                "is_officer": getattr(relationship, "is_officer", None),
                "is_ten_percent_owner": getattr(relationship, "is_ten_pct_owner", None),
                "is_other": getattr(relationship, "is_other", None),
                "officer_title": getattr(relationship, "officer_title", None),
                "parser_version": PARSER_VERSION,
            }
        )

    non_transactions = getattr(parsed.non_derivative_table, "transactions", None)
    if non_transactions is not None:
        frame = getattr(non_transactions, "data", None)
        if frame is not None:
            for txn_index, record in enumerate(frame.to_dict("records"), start=1):
                non_derivative_rows.append(
                    {
                        "accession_number": accession_number,
                        "owner_index": 1,
                        "txn_index": txn_index,
                        "security_title": record.get("Security"),
                        "transaction_date": record.get("Date"),
                        "transaction_code": record.get("Code"),
                        "transaction_shares": _to_float(record.get("Shares")),
                        "transaction_price": _to_float(record.get("Price")),
                        "acquired_disposed_code": record.get("AcquiredDisposed"),
                        "shares_owned_after": _to_float(record.get("Remaining")),
                        "ownership_nature": record.get("Nature Of Ownership"),
                        "ownership_direct_indirect": record.get("Direct Indirect"),
                        "parser_version": PARSER_VERSION,
                    }
                )

    derivative_transactions = getattr(parsed.derivative_table, "transactions", None)
    if derivative_transactions is not None:
        frame = getattr(derivative_transactions, "data", None)
        if frame is not None:
            for txn_index, record in enumerate(frame.to_dict("records"), start=1):
                derivative_rows.append(
                    {
                        "accession_number": accession_number,
                        "owner_index": 1,
                        "txn_index": txn_index,
                        "security_title": record.get("Security"),
                        "transaction_date": record.get("Date"),
                        "transaction_code": record.get("Code"),
                        "transaction_shares": _to_float(record.get("Shares")),
                        "transaction_price": _to_float(record.get("Price")),
                        "acquired_disposed_code": record.get("AcquiredDisposed"),
                        "shares_owned_after": _to_float(record.get("Remaining")),
                        "ownership_nature": record.get("Nature Of Ownership"),
                        "ownership_direct_indirect": record.get("Direct Indirect"),
                        "conversion_or_exercise_price": _to_float(record.get("Exercise Price")),
                        "exercise_date": record.get("Exercise Date"),
                        "expiration_date": record.get("Expiration Date"),
                        "underlying_security_title": record.get("Underlying Security"),
                        "underlying_security_shares": _to_float(record.get("Underlying Shares")),
                        "parser_version": PARSER_VERSION,
                    }
                )

    return {
        "sec_ownership_reporting_owner": owner_rows,
        "sec_ownership_non_derivative_txn": non_derivative_rows,
        "sec_ownership_derivative_txn": derivative_rows,
    }


def _parse_owner_cik(value: Any) -> int | None:
    try:
        return int(str(value)) if value else None
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
