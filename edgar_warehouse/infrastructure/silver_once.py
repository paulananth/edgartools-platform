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
    bookkeeping: Any,
    *,
    accession_number: str,
    parser_name: str,
    parser_version: str,
) -> bool:
    """True when silver has a succeeded parse_run for this accession at parser_version.

    Falls back to ownership reporting-owner rows with matching parser_version when
    parse_run history is missing (older silver).

    Returns False (do not skip) when a probe cannot answer -- prefer network
    over a hard crash on incomplete test/adapter surfaces.

    DuckDB Retirement Cutover Ticket 15: sec_parse_run moved to the
    bookkeeping store, so the primary check goes through
    BookkeepingStore.has_successful_parse_run(...) instead of raw SQL on
    `db`. The fallback query stays on `db` -- sec_ownership_reporting_owner
    is a DuckDB content table, unaffected by that move.
    """
    accession = str(accession_number or "").strip()
    if not accession:
        return False
    has_successful_parse_run = getattr(bookkeeping, "has_successful_parse_run", None)
    if has_successful_parse_run is not None and has_successful_parse_run(
        accession_number=accession, parser_name=parser_name, parser_version=parser_version
    ):
        return True
    # Fallback for silver populated before parse_run was consistently written
    fetch = getattr(db, "fetch", None)
    if fetch is None:
        return False
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


_ENTITY_FACTS_QUALIFYING_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")


def get_ciks_with_new_qualifying_filing(db: Any, *, cik_list: list[int]) -> set[int]:
    """CIKs with a 10-K/10-K-A/10-Q/10-Q-A filing newer than their entity-facts
    refresh watermark (or no watermark at all -- first touch).

    Ticket 03 (fundamentals-daily-integration map): composes with (does not
    replace) has_companyfacts_at_version's existing one-time-per-parser-
    version gate above -- see run_bootstrap_entity_facts. A single bulk
    query for the whole cik_list, not one query per CIK.
    """
    fetch = getattr(db, "fetch", None)
    if fetch is None or not cik_list:
        return set()
    placeholders = ", ".join("?" * len(cik_list))
    forms_sql = ", ".join(f"'{f}'" for f in _ENTITY_FACTS_QUALIFYING_FORMS)
    rows = fetch(
        f"""
        SELECT f.cik AS cik
        FROM (
            SELECT cik, MAX(filing_date) AS latest_qualifying_filing_date
            FROM sec_company_filing
            WHERE cik IN ({placeholders})
              AND form IN ({forms_sql})
            GROUP BY cik
        ) f
        LEFT JOIN sec_entity_facts_refresh_watermark w ON w.cik = f.cik
        WHERE w.entity_facts_refreshed_at IS NULL
           OR f.latest_qualifying_filing_date > w.entity_facts_refreshed_at
        """,
        [int(c) for c in cik_list],
    )
    return {int(row["cik"]) for row in rows}


def daily_index_is_finalized(bookkeeping: Any, *, business_date: str) -> bool:
    """True when daily index checkpoint is succeeded/finalized for the date.

    DuckDB Retirement Cutover Ticket 15: sec_daily_index_checkpoint moved to
    the bookkeeping store.
    """
    existing = bookkeeping.get_daily_index_checkpoint(business_date)
    if not existing:
        return False
    return str(existing.get("status") or "") == "succeeded"
