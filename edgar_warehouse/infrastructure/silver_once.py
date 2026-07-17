"""Silver-once skip helpers (tickets 03–05).

Skip keys (ADR 0002):
- ownership: accession + form-family + parser_version
- companyfacts: CIK + facts_parser_version
- daily index: business date finalized checkpoint
"""

from __future__ import annotations

from typing import Any


def has_successful_ownership_parse(
    db: Any,
    *,
    accession_number: str,
    parser_name: str,
    parser_version: str,
) -> bool:
    """True when silver has a succeeded parse_run for this accession at parser_version.

    Falls back to ownership reporting-owner rows with matching parser_version when
    parse_run history is missing (older silver).

    Returns False (do not skip) when the db cannot answer SQL probes — prefer
    network over a hard crash on incomplete test/adapter surfaces.
    """
    accession = str(accession_number or "").strip()
    if not accession:
        return False
    fetch = getattr(db, "fetch", None)
    if fetch is None:
        return False
    rows = fetch(
        """
        SELECT 1 AS ok
        FROM sec_parse_run
        WHERE accession_number = ?
          AND parser_name = ?
          AND parser_version = ?
          AND status = 'succeeded'
        LIMIT 1
        """,
        [accession, parser_name, parser_version],
    )
    if rows:
        return True
    # Fallback for silver populated before parse_run was consistently written
    owners = fetch(
        """
        SELECT 1 AS ok
        FROM sec_ownership_reporting_owner
        WHERE accession_number = ?
          AND parser_version = ?
        LIMIT 1
        """,
        [accession, parser_version],
    )
    return bool(owners)


def has_companyfacts_at_version(db: Any, *, cik: int, facts_parser_version: str) -> bool:
    """True when sec_financial_fact has rows for CIK at facts_parser_version."""
    fetch = getattr(db, "fetch", None)
    if fetch is None:
        return False
    rows = fetch(
        """
        SELECT 1 AS ok
        FROM sec_financial_fact
        WHERE cik = ?
          AND parser_version = ?
        LIMIT 1
        """,
        [int(cik), str(facts_parser_version)],
    )
    return bool(rows)


def daily_index_is_finalized(db: Any, *, business_date: str) -> bool:
    """True when daily index checkpoint is succeeded/finalized for the date."""
    existing = db.get_daily_index_checkpoint(business_date)
    if not existing:
        return False
    return str(existing.get("status") or "") == "succeeded"
