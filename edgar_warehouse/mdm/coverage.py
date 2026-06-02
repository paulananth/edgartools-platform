"""Coverage reporting: compare silver source counts to MDM entity counts per domain.

Pure compute core — no side effects, no CLI concerns.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def compute_coverage(silver_reader: Any, session: Session) -> list[dict]:
    """Return per-domain silver_count vs mdm_count comparison.

    Predicates mirror pipeline.py loader queries exactly so gaps reflect real
    loader misses, not measurement drift.

    Each returned dict has: domain, silver_count, mdm_count, gap, reason.
    gap = silver_count - mdm_count.  Positive gap = loader missed records.
    """
    from sqlalchemy import func, select

    from edgar_warehouse.mdm.database import (
        MdmAdviser,
        MdmCompany,
        MdmFund,
        MdmPerson,
        MdmSecurity,
    )

    def _silver(sql: str) -> int:
        rows = silver_reader.fetch(sql)
        if not rows:
            return 0
        first = rows[0]
        return int(list(first.values())[0] or 0)

    def _mdm_count(model) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    # ------------------------------------------------------------------
    # Companies — active tracking_status via sec_company_sync_state join.
    # Mirrors: run_companies iterates sec_company and checks sync_state per row.
    # Inactive/dropped companies (no active sync_state) are excluded.
    # ------------------------------------------------------------------
    company_silver = _silver(
        "SELECT COUNT(DISTINCT c.cik) AS n "
        "FROM sec_company c "
        "JOIN sec_company_sync_state s ON s.cik = c.cik "
        "WHERE s.tracking_status = 'active'"
    )
    company_mdm = _mdm_count(MdmCompany)

    # ------------------------------------------------------------------
    # Persons — non-corporate reporting owners.
    # Mirrors: run_persons excludes owner_cik values present in sec_company
    # (the silver-side proxy for _company_cik_set()).
    # ------------------------------------------------------------------
    person_silver = _silver(
        "SELECT COUNT(DISTINCT o.owner_cik) AS n "
        "FROM sec_ownership_reporting_owner o "
        "JOIN sec_company_filing f ON o.accession_number = f.accession_number "
        "WHERE o.owner_name IS NOT NULL "
        "  AND (o.owner_cik IS NULL "
        "       OR o.owner_cik NOT IN (SELECT cik FROM sec_company))"
    )
    person_mdm = _mdm_count(MdmPerson)

    # ------------------------------------------------------------------
    # Securities — ownership-sourced transactions only.
    # Mirrors: run_securities UNION ALL of non-derivative + derivative txns.
    # XBRL-sourced securities (sec_financial_fact) are deferred to Phase 6.
    # ------------------------------------------------------------------
    security_silver = _silver(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT t.accession_number, t.owner_index, t.txn_index"
        "  FROM sec_ownership_non_derivative_txn t"
        "  JOIN sec_company_filing f ON t.accession_number = f.accession_number"
        "  WHERE t.security_title IS NOT NULL"
        "  UNION ALL"
        "  SELECT t.accession_number, t.owner_index, t.txn_index"
        "  FROM sec_ownership_derivative_txn t"
        "  JOIN sec_company_filing f ON t.accession_number = f.accession_number"
        "  WHERE t.security_title IS NOT NULL"
        ")"
    )
    security_mdm = _mdm_count(MdmSecurity)

    # ------------------------------------------------------------------
    # Advisers — all ADV filers.
    # Mirrors: run_advisers iterates all sec_adv_filing rows.
    # ------------------------------------------------------------------
    adviser_silver = _silver("SELECT COUNT(*) AS n FROM sec_adv_filing")
    adviser_mdm = _mdm_count(MdmAdviser)

    # ------------------------------------------------------------------
    # Funds — all private funds (zero acceptable exclusions per D-21).
    # Mirrors: run_funds iterates all sec_adv_private_fund rows.
    # ------------------------------------------------------------------
    fund_silver = _silver("SELECT COUNT(*) AS n FROM sec_adv_private_fund")
    fund_mdm = _mdm_count(MdmFund)

    return [
        {
            "domain": "companies",
            "silver_count": company_silver,
            "mdm_count": company_mdm,
            "gap": company_silver - company_mdm,
            "reason": "Inactive and dropped companies excluded (tracking_status != 'active')",
        },
        {
            "domain": "persons",
            "silver_count": person_silver,
            "mdm_count": person_mdm,
            "gap": person_silver - person_mdm,
            "reason": "Corporate owners (owner_cik in company CIK set) excluded",
        },
        {
            "domain": "securities",
            "silver_count": security_silver,
            "mdm_count": security_mdm,
            "gap": security_silver - security_mdm,
            "reason": (
                "Ownership-sourced only; XBRL-sourced securities "
                "(sec_financial_fact) deferred to Phase 6 per D-24/D-28"
            ),
        },
        {
            "domain": "advisers",
            "silver_count": adviser_silver,
            "mdm_count": adviser_mdm,
            "gap": adviser_silver - adviser_mdm,
            "reason": "All ADV filers included (no exclusions)",
        },
        {
            "domain": "funds",
            "silver_count": fund_silver,
            "mdm_count": fund_mdm,
            "gap": fund_silver - fund_mdm,
            "reason": "All private funds included (zero acceptable exclusions per D-21)",
        },
    ]
