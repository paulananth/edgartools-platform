"""Bounded, parameterized Explore workflow queries for the audit dashboard.

Agent View remains closed-world in ``dashboard_query_registry``.  These
queries are deliberately labelled Explore and expose only named columns from
the gold/MDM read surfaces.  Keeping them here makes row caps, parameters,
missing-data semantics, and drill-through state testable without Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_COMPANY_ROWS = 250
MAX_SCREEN_ROWS = 200
MAX_INSIDER_ROWS = 250
MAX_ADV_ROWS = 200
PERFORMANCE_BUDGET_MS = 5_000


@dataclass(frozen=True)
class WorkflowQuery:
    query_id: str
    sql: str
    params: tuple[Any, ...]
    max_rows: int
    explore_only: bool = True


def data_state(value: Any, *, history_available: bool = True, covered: bool = True) -> str:
    """Distinguish missing coverage/history/null from a numeric zero."""
    if not covered:
        return "coverage_unavailable"
    if not history_available:
        return "insufficient_history"
    if value is None:
        return "value_unavailable"
    return "numeric_zero" if value == 0 else "available"


def sec_filing_url(cik: int, accession_number: str) -> str:
    accession = accession_number.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession}/{accession_number}-index.html"
    )


def company_query(surface: str, cik: int, *, limit: int = MAX_COMPANY_ROWS) -> WorkflowQuery:
    limit = min(max(int(limit), 1), MAX_COMPANY_ROWS)
    surfaces = {
        "filings": """
            select filing_date, report_date, form, accession_number, is_xbrl
            from EDGARTOOLS_GOLD.FILING_ACTIVITY
            where cik = ?
            order by filing_date desc nulls last, accession_number desc
        """,
        "financials": """
            select fiscal_year, fiscal_period, period_end, accession_number,
                   revenue, net_income, total_assets, current_ratio,
                   debt_to_assets, cash_to_assets, free_cash_flow,
                   free_cash_flow_to_revenue, accruals_to_assets,
                   revenue_cagr_3y, revenue_cagr_5y, ingested_at
            from EDGARTOOLS_GOLD.FINANCIAL_FACTORS
            where cik = ?
            order by period_end desc nulls last, accession_number desc
        """,
        "insiders": """
            select f.filing_date, f.form, o.accession_number, o.owner_index,
                   o.transaction_code, o.transaction_shares, o.transaction_price,
                   o.transaction_shares * o.transaction_price as transaction_notional,
                   o.shares_owned_after, o.is_derivative
            from EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY o
            left join EDGARTOOLS_GOLD.FILING_ACTIVITY f
              on f.accession_number = o.accession_number
            where f.cik = ?
            order by f.filing_date desc nulls last, o.accession_number desc,
                     o.owner_index, o.txn_index
        """,
        "earnings": """
            select filing_date, fiscal_year, fiscal_quarter, period_end,
                   revenue_gaap, net_income_gaap, eps_gaap_diluted,
                   has_non_gaap, has_guidance, accession_number, ingested_at
            from EDGARTOOLS_GOLD.EARNINGS_RELEASES
            where cik = ?
            order by filing_date desc nulls last, accession_number desc
        """,
        "executives": """
            select fiscal_year, exec_name, exec_role, total_comp, base_salary,
                   bonus, stock_awards, option_awards, non_equity_incentive,
                   comp_rank_within_filing, comp_pct_change_yoy,
                   accession_number, ingested_at
            from EDGARTOOLS_GOLD.EXECUTIVE_RECORDS
            where cik = ?
            order by fiscal_year desc nulls last, comp_rank_within_filing
        """,
        "accounting_flags": """
            select fiscal_year, period_end, auditor_name, auditor_pcaob_id,
                   icfr_attestation, auditor_changed, beneish_m_score,
                   beneish_risk_tier, altman_z_score, altman_zone,
                   piotroski_f_score, piotroski_strength,
                   accession_number, ingested_at
            from EDGARTOOLS_GOLD.ACCOUNTING_FLAGS
            where cik = ?
            order by fiscal_year desc nulls last, accession_number desc
        """,
        "institutional_holders": """
            select cik as manager_cik, period_of_report, issuer_name, cusip,
                   security_title, shares_held, market_value, qoq_change_shares,
                   qoq_change_pct, put_call, accession_number, ingested_at
            from EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS
            where upper(issuer_name) = (
              select upper(entity_name) from EDGARTOOLS_GOLD.COMPANY
              where cik = ? qualify row_number() over (order by company_key) = 1
            )
            order by period_of_report desc nulls last, market_value desc nulls last
        """,
        "relationships": """
            select e.relationship_type, e.source_entity_type, e.target_entity_type,
                   e.source_accession, e.effective_from, e.effective_to,
                   e.generation_id
            from NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES e
            join NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER p
              on p.pointer_id = 'active'
             and p.active_generation_id = e.generation_id
            where e.sourcenodeid in (
              select nodeid from NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES
              where generation_id = p.active_generation_id
                and entity_type = 'company'
                and try_to_number(properties:cik::string) = ?
            ) or e.targetnodeid in (
              select nodeid from NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES
              where generation_id = p.active_generation_id
                and entity_type = 'company'
                and try_to_number(properties:cik::string) = ?
            )
            order by e.relationship_type, e.sourcenodeid, e.targetnodeid
        """,
    }
    if surface not in surfaces:
        raise KeyError(f"unknown Company 360 surface: {surface}")
    params: tuple[Any, ...] = (int(cik), int(cik)) if surface == "relationships" else (int(cik),)
    return WorkflowQuery(
        query_id=f"company360.{surface}",
        sql=f"{surfaces[surface].strip()}\nlimit {limit}",
        params=params,
        max_rows=limit,
    )


def fundamentals_query(
    *,
    cik: int | None = None,
    sic_pattern: str,
    fiscal_period: str,
    min_revenue: float | None,
    min_growth: float | None,
    min_current_ratio: float | None,
    max_debt_to_assets: float | None,
    min_cash_to_assets: float | None,
    min_fcf_to_revenue: float | None,
    max_accruals_to_assets: float | None,
    risk_tier: str,
    limit: int = MAX_SCREEN_ROWS,
) -> WorkflowQuery:
    limit = min(max(int(limit), 1), MAX_SCREEN_ROWS)
    return WorkflowQuery(
        query_id="fundamentals.screen",
        sql=f"""
            select c.cik, c.display_name as entity_name, c.sic, c.sic_description,
                   f.fiscal_year, f.fiscal_period, f.period_end, f.accession_number,
                   f.revenue, f.revenue_cagr_3y, f.current_ratio,
                   f.debt_to_assets, f.cash_to_assets,
                   f.free_cash_flow_to_revenue, f.accruals_to_assets,
                   a.beneish_risk_tier, a.altman_zone, a.piotroski_strength,
                   f.ingested_at as feature_as_of
            from EDGARTOOLS_GOLD.FINANCIAL_FACTORS f
            join EDGARTOOLS_GOLD.COMPANY c on c.cik = f.cik
            left join EDGARTOOLS_GOLD.ACCOUNTING_FLAGS a
              on a.cik = f.cik and a.is_most_recent
            where coalesce(c.tracking_status, 'active') = 'active'
              and (? is null or f.cik = ?)
              and c.sic ilike ?
              and f.fiscal_period = ?
              and (? is null or f.revenue >= ?)
              and (? is null or f.revenue_cagr_3y >= ?)
              and (? is null or f.current_ratio >= ?)
              and (? is null or f.debt_to_assets <= ?)
              and (? is null or f.cash_to_assets >= ?)
              and (? is null or f.free_cash_flow_to_revenue >= ?)
              and (? is null or f.accruals_to_assets <= ?)
              and (? = 'all' or a.beneish_risk_tier = ?)
            qualify row_number() over (
              partition by f.cik order by f.period_end desc nulls last,
              f.accession_number desc
            ) = 1
            order by f.revenue desc nulls last, c.cik
            limit {limit}
        """.strip(),
        params=(
            cik, cik,
            sic_pattern,
            fiscal_period,
            min_revenue, min_revenue,
            min_growth, min_growth,
            min_current_ratio, min_current_ratio,
            max_debt_to_assets, max_debt_to_assets,
            min_cash_to_assets, min_cash_to_assets,
            min_fcf_to_revenue, min_fcf_to_revenue,
            max_accruals_to_assets, max_accruals_to_assets,
            risk_tier, risk_tier,
        ),
        max_rows=limit,
    )


def insider_query(
    *,
    cik: int | None = None,
    start_date: Any,
    end_date: Any,
    issuer_pattern: str,
    form_pattern: str,
    owner_role: str,
    transaction_code: str,
    min_shares: float | None,
    min_notional: float | None,
    derivative: str,
    limit: int = MAX_INSIDER_ROWS,
) -> WorkflowQuery:
    limit = min(max(int(limit), 1), MAX_INSIDER_ROWS)
    return WorkflowQuery(
        query_id="insider_watch.screen",
        sql=f"""
            with active_people as (
              select e.source_accession as accession_number,
                     n.properties:primary_role::string as owner_role
              from NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES e
              join NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER p
                on p.pointer_id = 'active'
               and p.active_generation_id = e.generation_id
              join NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES n
                on n.nodeid = e.sourcenodeid and n.generation_id = e.generation_id
              where e.relationship_type = 'EMPLOYED_BY'
              qualify row_number() over (
                partition by e.source_accession order by e.updated_at desc nulls last
              ) = 1
            )
            select c.cik, c.display_name as entity_name, f.filing_date, f.form,
                   o.accession_number, o.owner_index, o.transaction_code,
                   p.owner_role,
                   case when o.transaction_code = 'P' then 'purchase'
                        when o.transaction_code = 'S' then 'sale'
                        else 'other_or_unavailable' end as transaction_semantics,
                   o.transaction_shares, o.transaction_price,
                   o.transaction_shares * o.transaction_price as transaction_notional,
                   o.shares_owned_after, o.is_derivative
            from EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY o
            join EDGARTOOLS_GOLD.FILING_ACTIVITY f
              on f.accession_number = o.accession_number
            join EDGARTOOLS_GOLD.COMPANY c on c.cik = f.cik
            left join active_people p on p.accession_number = o.accession_number
            where f.filing_date between ? and ?
              and (? is null or f.cik = ?)
              and c.display_name ilike ?
              and f.form ilike ?
              and (? = 'all' or lower(coalesce(p.owner_role, 'unavailable')) = ?)
              and (? = 'all' or o.transaction_code = ?)
              and (? is null or o.transaction_shares >= ?)
              and (? is null or o.transaction_shares * o.transaction_price >= ?)
              and (? = 'all' or o.is_derivative = (? = 'derivative'))
            qualify row_number() over (
              partition by o.accession_number, o.owner_index, o.txn_index
              order by f.filing_date desc
            ) = 1
            order by f.filing_date desc, o.accession_number, o.owner_index, o.txn_index
            limit {limit}
        """.strip(),
        params=(
            start_date, end_date, cik, cik, issuer_pattern, form_pattern,
            owner_role, owner_role,
            transaction_code, transaction_code,
            min_shares, min_shares, min_notional, min_notional,
            derivative, derivative,
        ),
        max_rows=limit,
    )


def adv_query(search_pattern: str, *, limit: int = MAX_ADV_ROWS) -> WorkflowQuery:
    limit = min(max(int(limit), 1), MAX_ADV_ROWS)
    return WorkflowQuery(
        query_id="adv.explorer",
        sql=f"""
            select a.entity_id as adviser_entity_id, a.canonical_name as adviser_name,
                   a.crd_number, a.sec_file_number, a.cik, a.adviser_type,
                   a.hq_city, a.hq_state, a.aum_total, a.fund_count,
                   a.valid_from as adviser_source_updated_at,
                   case when exists (
                     select 1 from EDGARTOOLS_GOLD.ADVISER_OFFICES o
                     join EDGARTOOLS_GOLD.COMPANY c on c.company_key = o.company_key
                     where c.entity_id = a.linked_company_entity_id
                   ) then 'available' else 'coverage_unavailable' end
                     as office_coverage_state,
                   case when exists (
                     select 1 from EDGARTOOLS_GOLD.ADVISER_DISCLOSURES d
                     join EDGARTOOLS_GOLD.COMPANY c on c.company_key = d.company_key
                     where c.entity_id = a.linked_company_entity_id
                   ) then 'available' else 'coverage_unavailable' end
                     as disclosure_coverage_state,
                   f.entity_id as fund_entity_id, f.private_fund_id,
                   f.canonical_name as fund_name, f.fund_type, f.jurisdiction,
                   f.aum_amount, f.aum_as_of_date,
                   f.valid_from as fund_source_updated_at, e.generation_id
            from EDGARTOOLS_GOLD.MDM_ADVISER a
            left join EDGARTOOLS_GOLD.MDM_FUND f
              on f.adviser_entity_id = a.entity_id and f.valid_to is null
            left join NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES e
              on e.relationship_type = 'MANAGES_FUND'
             and e.sourcenodeid = a.entity_id and e.targetnodeid = f.entity_id
            left join NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER p
              on p.pointer_id = 'active'
             and p.active_generation_id = e.generation_id
            where a.valid_to is null
              and (
                a.canonical_name ilike ? or a.crd_number ilike ?
                or a.sec_file_number ilike ? or f.canonical_name ilike ?
                or f.private_fund_id ilike ?
              )
              and (e.generation_id is null or p.active_generation_id is not null)
            order by a.canonical_name, f.canonical_name
            limit {limit}
        """.strip(),
        params=(search_pattern,) * 5,
        max_rows=limit,
    )
