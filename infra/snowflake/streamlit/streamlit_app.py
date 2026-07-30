"""EdgarTools warehouse dashboard (Streamlit-in-Snowflake).

Reads gold tables from EDGARTOOLS_GOLD via the active Snowpark session.

Ticket 13 / GH-246: Agent View vs Explore mode toggle. Mode semantics are
the single authoritative policy in ``edgar_warehouse.serving.dashboard_modes``
(unit-tested) -- no local re-implementation. ``deploy.sh`` stages
``dashboard_modes.py`` flat alongside this file so the SiS runtime, which
has no ``edgar_warehouse`` package installed, imports the identical source
file rather than a hand-copied duplicate.

Company Details' "Equity research (Explore)" section surfaces the 4 ERDP
Gold Explore products (CONSENSUS_ESTIMATES / GUIDANCE_FACTS /
EARNINGS_CALENDAR / TRANSCRIPT_EVENTS, see ``docs/er-*.md``) -- Explore-only
per ADR 0001, gated the same way Financial factors is.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from snowflake.snowpark.context import get_active_session

try:
    from edgar_warehouse.serving.dashboard_modes import (
        AGENT_VIEW_ALLOWED_OBJECTS,
        AGENT_VIEW_BANNER,
        EXPLORE_BANNER,
        MODE_AGENT_VIEW,
        MODE_EXPLORE,
        SESSION_CIK_KEY,
        SESSION_MODE_KEY,
    )
    from edgar_warehouse.serving.dashboard_modes import (
        is_object_allowed as _is_object_allowed,
    )
    from edgar_warehouse.serving.dashboard_modes import (
        normalize_mode as _normalize_mode,
    )
    from edgar_warehouse.serving.dashboard_query_registry import registered_query
    from edgar_warehouse.serving.dashboard_workflows import (
        MAX_ADV_ROWS,
        MAX_COMPANY_ROWS,
        MAX_INSIDER_ROWS,
        MAX_SCREEN_ROWS,
        PERFORMANCE_BUDGET_MS,
        adv_query,
        company_query,
        fundamentals_query,
        insider_query,
        sec_filing_url,
    )
except ImportError:  # pragma: no cover -- exercised only in the SiS stage
    # SiS runtime: edgar_warehouse isn't installed as a package here (see
    # deploy.sh -- only streamlit_app.py + dashboard_modes.py are staged).
    # dashboard_modes.py is staged flat next to this file, so add the stage
    # root to sys.path and import the identical source as a top-level module.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dashboard_modes import (
        AGENT_VIEW_ALLOWED_OBJECTS,
        AGENT_VIEW_BANNER,
        EXPLORE_BANNER,
        MODE_AGENT_VIEW,
        MODE_EXPLORE,
        SESSION_CIK_KEY,
        SESSION_MODE_KEY,
    )
    from dashboard_modes import (
        is_object_allowed as _is_object_allowed,
    )
    from dashboard_modes import (
        normalize_mode as _normalize_mode,
    )
    from dashboard_query_registry import registered_query
    from dashboard_workflows import (
        MAX_ADV_ROWS,
        MAX_COMPANY_ROWS,
        MAX_INSIDER_ROWS,
        MAX_SCREEN_ROWS,
        PERFORMANCE_BUDGET_MS,
        adv_query,
        company_query,
        fundamentals_query,
        insider_query,
        sec_filing_url,
    )

st.set_page_config(page_title="EdgarTools Warehouse", layout="wide")

GOLD_SCHEMA = "EDGARTOOLS_GOLD"
SOURCE_SCHEMA = "EDGARTOOLS_SOURCE"
DECISION_SCHEMA = "EDGARTOOLS_DECISION"


def _render_mode_chrome() -> str:
    """Visible sticky mode toggle + banner. Returns resolved mode."""
    session = getattr(st, "session_state", None)
    if session is None:
        # Import/load under unit fakes without full Streamlit runtime
        return MODE_AGENT_VIEW
    prior = session.get(SESSION_MODE_KEY, MODE_AGENT_VIEW)
    labels = {
        MODE_AGENT_VIEW: "Agent View (Decision Contract)",
        MODE_EXPLORE: "Explore (labeled not-for-agent)",
    }
    sidebar = getattr(st, "sidebar", None)
    if sidebar is None:
        return _normalize_mode(str(prior))
    choice = sidebar.radio(
        "Dashboard mode",
        options=[MODE_AGENT_VIEW, MODE_EXPLORE],
        format_func=lambda m: labels[m],
        index=0 if prior == MODE_AGENT_VIEW else 1,
        key="dashboard_mode_radio",
    )
    mode = _normalize_mode(choice)
    session[SESSION_MODE_KEY] = mode
    if mode == MODE_EXPLORE:
        st.warning(EXPLORE_BANNER)
    else:
        st.info(AGENT_VIEW_BANNER)
    return mode


@st.cache_resource
def _session():
    return get_active_session()


def _df(sql: str, params: list | None = None):
    session = _session()
    if params:
        return session.sql(sql, params=params).to_pandas()
    return session.sql(sql).to_pandas()


def _safe_df(label: str, sql: str, params: list | None = None):
    try:
        return _df(sql, params=params)
    except Exception:  # noqa: BLE001 - connector exceptions share no stable base
        # Fixed, secret-safe copy: connector exceptions may contain account
        # identifiers, SQL text, stage paths, or credentials.
        st.warning(
            f"{label} is temporarily unavailable. "
            "No data was shown; contact the dashboard operator with this section name."
        )
        return None


def _registered_df(query_id: str, params: list | None = None):
    """Execute one registry-enforced Agent View query."""
    query = registered_query(query_id)
    return _safe_df(query.query_id, query.sql, params=params)


def _workflow_df(query):
    """Execute one bounded Explore workflow query."""
    return _safe_df(query.query_id, query.sql, params=list(query.params))


def _show_dataframe(df, columns: list[str] | None = None):
    if df is None or df.empty:
        st.info("No rows to display.")
        return
    if columns is not None:
        visible = [column for column in columns if column in df.columns]
        if visible:
            df = df[visible]
    st.dataframe(df, use_container_width=True, hide_index=True)


def _bounded_export(df, *, filename: str, max_rows: int) -> None:
    """Expose exactly the already-bounded result, never an unrestricted export."""
    if df is None or df.empty:
        return
    st.caption(f"Showing/exporting {len(df):,} rows (hard maximum {max_rows:,}).")
    download = getattr(st, "download_button", None)
    if download is not None:
        download(
            "Download bounded CSV",
            data=df.head(max_rows).to_csv(index=False),
            file_name=filename,
            mime="text/csv",
        )


def _metric_text(value, fmt: str) -> str:
    if value is None or value != value:  # noqa: PLR0124 - generic NaN detection
        return "—"
    return format(float(value), fmt)


def _kpi_row():
    df = _df(
        f"""
        select
          (select count(*) from {GOLD_SCHEMA}.COMPANY) as company_count,
          (select count(*) from {GOLD_SCHEMA}.FILING_ACTIVITY) as filing_count,
          (select max(filing_date) from {GOLD_SCHEMA}.FILING_ACTIVITY) as last_filing_date
        """
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Companies", f"{int(df['COMPANY_COUNT'].iloc[0]):,}")
    col2.metric("Filings", f"{int(df['FILING_COUNT'].iloc[0]):,}")
    last_date = df["LAST_FILING_DATE"].iloc[0]
    col3.metric("Latest filing", str(last_date) if last_date is not None else "—")


def _top_companies():
    df = _df(
        f"""
        select c.entity_name, count(*) as filing_count
        from {GOLD_SCHEMA}.FILING_ACTIVITY f
        join {GOLD_SCHEMA}.COMPANY c on c.company_key = f.company_key
        group by c.entity_name
        order by filing_count desc
        limit 10
        """
    )
    if df.empty:
        st.info("No filings loaded yet.")
        return
    fig = px.bar(
        df.sort_values("FILING_COUNT"),
        x="FILING_COUNT",
        y="ENTITY_NAME",
        orientation="h",
        title="Top 10 companies by filing count",
    )
    fig.update_layout(yaxis_title="", xaxis_title="Filings")
    st.plotly_chart(fig, use_container_width=True)


def _by_form_type():
    df = _df(
        f"""
        select form, count(*) as filing_count
        from {GOLD_SCHEMA}.FILING_ACTIVITY
        group by form
        order by filing_count desc
        limit 20
        """
    )
    if df.empty:
        return
    fig = px.bar(df, x="FORM", y="FILING_COUNT", title="Filings by form type (top 20)")
    fig.update_layout(xaxis_title="Form", yaxis_title="Filings")
    st.plotly_chart(fig, use_container_width=True)


def _over_time_all():
    df = _df(
        f"""
        select date_trunc('month', filing_date) as month, count(*) as filing_count
        from {GOLD_SCHEMA}.FILING_ACTIVITY
        where filing_date is not null
        group by month
        order by month
        """
    )
    if df.empty:
        return
    fig = px.line(df, x="MONTH", y="FILING_COUNT", title="Filings per month (all time)")
    fig.update_layout(xaxis_title="Month", yaxis_title="Filings")
    st.plotly_chart(fig, use_container_width=True)


def _two_year_timeline():
    df = _df(
        f"""
        select date_trunc('week', filing_date) as week, count(*) as filing_count
        from {GOLD_SCHEMA}.FILING_ACTIVITY
        where filing_date >= dateadd(year, -2, current_date)
        group by week
        order by week
        """
    )
    if df.empty:
        st.info("No filings in the past 2 years.")
        return
    fig = px.area(
        df,
        x="WEEK",
        y="FILING_COUNT",
        title="Filings per week (last 2 years)",
    )
    fig.update_layout(xaxis_title="Week", yaxis_title="Filings")
    st.plotly_chart(fig, use_container_width=True)


def _render_agent_view_company(cik: int, bundle=None) -> None:
    """Agent View: contract objects only (no free gold FINANCIAL_FACTORS joins)."""
    st.subheader("Agent View — Decision Contract")
    st.write(
        {
            "cik": cik,
            "allowed_objects": sorted(AGENT_VIEW_ALLOWED_OBJECTS),
            "note": (
                "Free gold joins (e.g. FINANCIAL_FACTORS, FILING_ACTIVITY charts) "
                "are Explore-only. Switch mode to Explore for research SQL."
            ),
        }
    )
    if bundle is None:
        bundle = _registered_df("agent.subject_bundle", params=[int(cik)])
    if bundle is None or bundle.empty:
        st.error(
            "Agent-grade evidence is unavailable because the Decision Contract "
            "is missing, stale, or not aligned with the active graph generation."
        )
        return
    row = bundle.iloc[0]
    freshness = {
        "contract_version": row.get("DECISION_CONTRACT_VERSION"),
        "decision_watermark": row.get("DECISION_WATERMARK"),
        "business_date": row.get("BUSINESS_DATE"),
        "gold_updated_at": row.get("GOLD_UPDATED_AT"),
        "graph_generation_id": row.get("GRAPH_GENERATION_ID"),
        "graph_activated_at": row.get("GRAPH_ACTIVATED_AT"),
        "coverage_state": row.get("COVERAGE_STATE"),
        "alignment_status": row.get("ALIGNMENT_STATUS"),
    }
    if freshness["alignment_status"] != "aligned":
        st.error(
            "Agent-grade evidence is unavailable because contract and graph "
            "generations are not aligned."
        )
        return
    st.caption("Published Decision Contract freshness and alignment")
    st.write(freshness)
    _show_dataframe(bundle)


def render_summary(mode: str = MODE_EXPLORE):
    st.header("Summary")
    if mode == MODE_AGENT_VIEW:
        st.caption("Agent View summary is limited to contract/status surfaces.")
        status = _registered_df("agent.contract_status")
        _show_dataframe(status)
        return
    _kpi_row()
    st.divider()
    _two_year_timeline()
    col_left, col_right = st.columns(2)
    with col_left:
        _top_companies()
    with col_right:
        _by_form_type()
    _over_time_all()


def _lookup_companies(query: str):
    if not query:
        return None
    pattern = f"%{query}%"
    return _df(
        f"""
        select distinct c.company_key, c.cik, c.entity_name, c.sic_description
        from {GOLD_SCHEMA}.COMPANY c
        left join {GOLD_SCHEMA}.TICKER_REFERENCE t on t.cik = c.cik
        where c.entity_name ilike ?
           or t.ticker ilike ?
           or to_varchar(c.cik) = ?
        order by c.entity_name
        limit 25
        """,
        params=[pattern, pattern, query],
    )


def _lookup_contract_subjects(query: str):
    if not query:
        return None
    pattern = f"%{query}%"
    return _registered_df("agent.subject_search", params=[pattern, pattern])


def _company_metadata(company_key: int):
    return _df(
        f"""
        select c.cik, c.entity_name, c.entity_type, c.sic, c.sic_description,
               c.state_of_incorporation, c.fiscal_year_end,
               listagg(distinct t.ticker, ', ') within group (order by t.ticker) as tickers
        from {GOLD_SCHEMA}.COMPANY c
        left join {GOLD_SCHEMA}.TICKER_REFERENCE t on t.cik = c.cik
        where c.company_key = ?
        group by c.cik, c.entity_name, c.entity_type, c.sic, c.sic_description,
                 c.state_of_incorporation, c.fiscal_year_end
        """,
        params=[int(company_key)],
    )


def _company_form_counts(company_key: int):
    return _df(
        f"""
        select form, count(*) as filing_count
        from {GOLD_SCHEMA}.FILING_ACTIVITY
        where company_key = ?
        group by form
        order by filing_count desc
        """,
        params=[int(company_key)],
    )


def _company_recent_filings(company_key: int, limit: int = 100):
    return _df(
        f"""
        select filing_date, form, accession_number, report_date, is_xbrl
        from {GOLD_SCHEMA}.FILING_ACTIVITY
        where company_key = ?
        order by filing_date desc nulls last
        limit {int(limit)}
        """,
        params=[int(company_key)],
    )


def _add_sec_evidence_links(
    df, cik_column: str = "CIK", *, fixed_cik: int | None = None
):
    """Return a copy with deterministic SEC archive evidence links."""
    if df is None or df.empty or "ACCESSION_NUMBER" not in df.columns:
        return df
    result = df.copy()
    if fixed_cik is not None:
        result["SEC_EVIDENCE_URL"] = result["ACCESSION_NUMBER"].apply(
            lambda accession: sec_filing_url(int(fixed_cik), str(accession))
        )
    elif cik_column in result.columns:
        result["SEC_EVIDENCE_URL"] = result.apply(
            lambda row: sec_filing_url(
                int(row[cik_column]), str(row["ACCESSION_NUMBER"])
            ),
            axis=1,
        )
    return result


def _render_company360_surfaces(cik: int) -> None:
    st.subheader("Company 360 audit surfaces (Explore)")
    st.caption(
        f"Every read is parameterized and capped at {MAX_COMPANY_ROWS} rows. "
        "Blank values remain unavailable; they are never displayed as numeric zero."
    )
    labels = [
        ("Filings", "filings"),
        ("Financials", "financials"),
        ("Insiders", "insiders"),
        ("Earnings", "earnings"),
        ("Executive pay", "executives"),
        ("Accounting flags", "accounting_flags"),
        ("Institutional holders", "institutional_holders"),
        ("Relationships", "relationships"),
    ]
    tabs = st.tabs([label for label, _surface in labels])
    for tab, (_label, surface) in zip(tabs, labels, strict=True):
        with tab:
            rows = _workflow_df(company_query(surface, cik))
            if rows is None or rows.empty:
                st.info(
                    "Coverage unavailable for this surface at the current source "
                    "dates. This is distinct from a measured numeric zero."
                )
            else:
                evidence_surfaces = {
                    "filings",
                    "financials",
                    "insiders",
                    "earnings",
                    "executives",
                    "accounting_flags",
                }
                linked = (
                    _add_sec_evidence_links(rows, fixed_cik=cik)
                    if surface in evidence_surfaces
                    else rows
                )
                _show_dataframe(linked)


def _company_financial_factors(cik: int, limit: int = 40):
    return _safe_df(
        "Financial factors",
        f"""
        select
          fiscal_year,
          fiscal_period,
          period_end,
          revenue,
          total_assets,
          current_assets,
          current_liabilities,
          working_capital,
          current_ratio,
          quick_ratio,
          receivables_to_revenue,
          inventory_to_assets,
          sga_to_revenue,
          retained_earnings_to_assets,
          asset_turnover,
          debt_to_assets,
          cash_to_assets,
          free_cash_flow_to_revenue,
          accruals_to_assets,
          asset_growth_yoy,
          shares_outstanding,
          shares_outstanding_yoy_change
        from {GOLD_SCHEMA}.FINANCIAL_FACTORS
        where cik = ?
        order by period_end desc nulls last, fiscal_year desc nulls last, fiscal_period desc
        limit {int(limit)}
        """,
        params=[int(cik)],
    )


def _company_consensus_estimates(cik: int, limit: int = 40):
    """ERDP-01: Gold Explore only (ADR 0001) -- not Decision Contract input."""
    return _safe_df(
        "Consensus estimates",
        f"""
        select
          metric, period_type, fiscal_year, fiscal_quarter, period_end,
          estimate_value, unit, currency, statistic,
          source_system, source_ref, as_of, ingested_at
        from {GOLD_SCHEMA}.CONSENSUS_ESTIMATES
        where cik = ? and is_current
        order by fiscal_year desc nulls last, fiscal_quarter desc nulls last, metric, statistic
        limit {int(limit)}
        """,
        params=[int(cik)],
    )


def _company_guidance_facts(cik: int, limit: int = 40):
    """ERDP-02: Gold Explore only (ADR 0001) -- not Decision Contract input."""
    return _safe_df(
        "Guidance facts",
        f"""
        select
          metric, period_type, fiscal_year, fiscal_quarter, period_end,
          value_low, value_mid, value_high, unit, currency, is_non_gaap,
          source_system, source_ref, as_of, accession_number
        from {GOLD_SCHEMA}.GUIDANCE_FACTS
        where cik = ? and is_current
        order by fiscal_year desc nulls last, fiscal_quarter desc nulls last, metric
        limit {int(limit)}
        """,
        params=[int(cik)],
    )


def _company_earnings_calendar(cik: int, limit: int = 20):
    """ERDP-03: Gold Explore only (ADR 0001) -- not Decision Contract input."""
    return _safe_df(
        "Earnings calendar",
        f"""
        select
          fiscal_year, fiscal_quarter, expected_date, expected_time, timezone,
          session, status, source_system, source_ref, as_of
        from {GOLD_SCHEMA}.EARNINGS_CALENDAR
        where cik = ? and is_current
        order by expected_date desc nulls last
        limit {int(limit)}
        """,
        params=[int(cik)],
    )


def _company_transcript_events(cik: int, limit: int = 20):
    """ERDP-04: Gold Explore only (ADR 0001) -- not Decision Contract input.

    No ``is_current`` filter -- unlike the other 3 ERDP products, a
    transcript pointer is revalidated in place, not versioned (see
    transcript_events.sql).
    """
    return _safe_df(
        "Transcript events",
        f"""
        select
          event_type, fiscal_year, fiscal_quarter, event_date, storage_uri,
          content_sha256 is not null as has_content, char_count, language,
          source_system, source_url, as_of
        from {GOLD_SCHEMA}.TRANSCRIPT_EVENTS
        where cik = ?
        order by event_date desc nulls last
        limit {int(limit)}
        """,
        params=[int(cik)],
    )


def _render_equity_research(mode: str, cik: int) -> None:
    """ERDP-01..04 Gold Explore products -- Explore-only, not Decision Contract input.

    Same guard pattern as the Financial factors section: this is only ever
    reached from the Explore branch of ``render_details``, but the explicit
    ``_is_object_allowed`` check is defense-in-depth against future callers.
    """
    st.subheader("Equity research (Explore)")
    if not _is_object_allowed(mode, "CONSENSUS_ESTIMATES"):
        st.error("Agent View cannot query free gold ERDP Explore tables.")
        return
    st.caption(
        "CONSENSUS_ESTIMATES / GUIDANCE_FACTS / EARNINGS_CALENDAR / TRANSCRIPT_EVENTS "
        "-- Gold Explore products (ADR 0001). Not pure-SEC Agent-Grade Decision "
        "Features and not Trading Decision input."
    )
    tabs = st.tabs(["Consensus", "Guidance", "Earnings calendar", "Transcripts"])
    with tabs[0]:
        _show_dataframe(_company_consensus_estimates(cik))
    with tabs[1]:
        _show_dataframe(_company_guidance_facts(cik))
    with tabs[2]:
        _show_dataframe(_company_earnings_calendar(cik))
    with tabs[3]:
        transcripts = _company_transcript_events(cik)
        _show_dataframe(transcripts)
        if transcripts is not None and not transcripts.empty:
            st.caption(
                "storage_uri is a pointer (ir_website) or platform-held copy "
                "(firm_manual, has_content=True) -- not rendered inline."
            )


def _company_timeline(company_key: int):
    return _df(
        f"""
        select date_trunc('month', filing_date) as month, count(*) as filing_count
        from {GOLD_SCHEMA}.FILING_ACTIVITY
        where company_key = ? and filing_date is not null
        group by month
        order by month
        """,
        params=[int(company_key)],
    )


def render_details(mode: str = MODE_EXPLORE):
    st.header("Company 360")
    st.caption(
        f"Mode: **{mode}** — same CIK can be inspected in Agent View and Explore for audit comparison."
    )
    prior_cik = getattr(st, "session_state", {}).get(SESSION_CIK_KEY, "")
    query = st.text_input(
        "Search by ticker, company name, or CIK",
        value=str(prior_cik) if prior_cik and mode == MODE_EXPLORE else "",
        placeholder="e.g. AAPL, Apple, or 320193",
    )

    if not query:
        st.info("Enter a ticker symbol or part of a company name to start.")
        return

    matches = (
        _lookup_contract_subjects(query.strip())
        if mode == MODE_AGENT_VIEW
        else _lookup_companies(query.strip())
    )
    if matches is None or matches.empty:
        st.warning(f"No companies matched '{query}'.")
        return

    matches = matches.copy()
    matches["label"] = matches.apply(
        lambda r: f"{r['ENTITY_NAME']} — CIK {int(r['CIK'])}", axis=1
    )
    label = st.selectbox("Matches", matches["label"].tolist())
    selected = matches.loc[matches["label"] == label].iloc[0]
    if mode == MODE_AGENT_VIEW:
        row = selected
        cik = int(row["CIK"])
        company_key = None
    else:
        company_key = int(selected["COMPANY_KEY"])
        meta = _company_metadata(company_key)
        if meta.empty:
            st.error("Selected company not found.")
            return
        row = meta.iloc[0]
        cik = int(row["CIK"])
    st.session_state[SESSION_CIK_KEY] = cik

    st.subheader(row["ENTITY_NAME"])
    col1, col2, col3 = st.columns(3)
    col1.metric("CIK", cik)
    col2.metric("Tickers", row["TICKERS"] or "—")
    col3.metric("Entity type", row.get("ENTITY_TYPE") or "—")

    with st.expander("Metadata", expanded=True):
        st.write(
            {
                "SIC": row.get("SIC"),
                "SIC description": row.get("SIC_DESCRIPTION"),
                "State of incorporation": row.get("STATE_OF_INCORPORATION"),
                "Fiscal year end": row.get("FISCAL_YEAR_END"),
            }
        )

    if mode == MODE_AGENT_VIEW:
        _render_agent_view_company(cik, bundle=matches.loc[matches["CIK"] == cik])
        return

    st.subheader("Financial factors")
    # Explore only — free gold FINANCIAL_FACTORS is blocked in Agent View.
    if not _is_object_allowed(mode, "FINANCIAL_FACTORS"):
        st.error("Agent View cannot query free gold FINANCIAL_FACTORS.")
        return
    factors = _company_financial_factors(cik)
    if factors is not None:
        if factors.empty:
            st.info("No financial factors loaded for this company.")
        else:
            latest_fy = factors.loc[factors["FISCAL_PERIOD"] == "FY"]
            latest = latest_fy.iloc[0] if not latest_fy.empty else factors.iloc[0]
            factor_cols = st.columns(4)
            factor_cols[0].metric(
                "Current ratio",
                _metric_text(latest["CURRENT_RATIO"], ".2f"),
            )
            factor_cols[1].metric(
                "Debt/assets",
                _metric_text(latest["DEBT_TO_ASSETS"], ".2f"),
            )
            factor_cols[2].metric(
                "FCF/revenue",
                _metric_text(latest["FREE_CASH_FLOW_TO_REVENUE"], ".2f"),
            )
            factor_cols[3].metric(
                "Shares",
                _metric_text(latest["SHARES_OUTSTANDING"], ",.0f"),
            )
            _show_dataframe(
                factors,
                [
                    "FISCAL_YEAR",
                    "FISCAL_PERIOD",
                    "PERIOD_END",
                    "REVENUE",
                    "TOTAL_ASSETS",
                    "WORKING_CAPITAL",
                    "CURRENT_RATIO",
                    "QUICK_RATIO",
                    "ASSET_TURNOVER",
                    "DEBT_TO_ASSETS",
                    "CASH_TO_ASSETS",
                    "FREE_CASH_FLOW_TO_REVENUE",
                    "ACCRUALS_TO_ASSETS",
                    "ASSET_GROWTH_YOY",
                    "SHARES_OUTSTANDING",
                    "SHARES_OUTSTANDING_YOY_CHANGE",
                ],
            )

    st.divider()
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Filings by form")
        form_counts = _company_form_counts(company_key)
        if form_counts.empty:
            st.info("No filings recorded for this company.")
        else:
            fig = px.bar(form_counts, x="FORM", y="FILING_COUNT")
            fig.update_layout(xaxis_title="Form", yaxis_title="Filings", height=350)
            st.plotly_chart(fig, use_container_width=True)
    with col_right:
        st.subheader("Filing timeline")
        timeline = _company_timeline(company_key)
        if timeline.empty:
            st.info("No dated filings.")
        else:
            fig = px.line(timeline, x="MONTH", y="FILING_COUNT")
            fig.update_layout(xaxis_title="Month", yaxis_title="Filings", height=350)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Recent filings")
    recent = _company_recent_filings(company_key, limit=250)
    if recent.empty:
        st.info("No filings to display.")
    else:
        st.dataframe(recent, use_container_width=True, hide_index=True)

    st.divider()
    _render_company360_surfaces(cik)
    st.divider()
    _render_equity_research(mode, cik)


def _parse_optional_number(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        st.warning("Numeric filters must contain a number; the invalid value was ignored.")
        return None


def render_fundamentals(mode: str) -> None:
    st.header("Fundamentals Screener")
    if mode == MODE_AGENT_VIEW:
        st.info(
            "The accounting screener is an Explore workflow. Agent View remains "
            "limited to published Decision Contract subject bundles."
        )
        return
    st.caption(
        f"Active tracked issuers only; accounting data only; maximum {MAX_SCREEN_ROWS} "
        f"rows; target p95 query budget {PERFORMANCE_BUDGET_MS:,} ms."
    )
    sic = st.text_input("SIC prefix", value="", key="fund_sic")
    period = st.selectbox("Fiscal period", ["FY", "Q1", "Q2", "Q3"], key="fund_period")
    min_revenue = _parse_optional_number(
        st.text_input("Minimum revenue", value="", key="fund_revenue")
    )
    min_growth = _parse_optional_number(
        st.text_input("Minimum 3-year revenue growth", value="", key="fund_growth")
    )
    min_liquidity = _parse_optional_number(
        st.text_input("Minimum current ratio", value="", key="fund_liquidity")
    )
    max_leverage = _parse_optional_number(
        st.text_input("Maximum debt/assets", value="", key="fund_leverage")
    )
    min_cash = _parse_optional_number(
        st.text_input("Minimum cash/assets", value="", key="fund_cash")
    )
    min_fcf = _parse_optional_number(
        st.text_input("Minimum FCF/revenue", value="", key="fund_fcf")
    )
    max_accruals = _parse_optional_number(
        st.text_input("Maximum accruals/assets", value="", key="fund_accruals")
    )
    risk = st.selectbox(
        "Beneish risk tier", ["all", "low", "medium", "high"], key="fund_risk"
    )
    query = fundamentals_query(
        sic_pattern=f"{sic.strip()}%",
        fiscal_period=period,
        min_revenue=min_revenue,
        min_growth=min_growth,
        min_current_ratio=min_liquidity,
        max_debt_to_assets=max_leverage,
        min_cash_to_assets=min_cash,
        min_fcf_to_revenue=min_fcf,
        max_accruals_to_assets=max_accruals,
        risk_tier=risk,
    )
    rows = _workflow_df(query)
    if rows is None or rows.empty:
        st.info(
            "No covered issuers matched. Missing feature history is not treated as zero."
        )
        return
    _show_dataframe(_add_sec_evidence_links(rows))
    _bounded_export(rows, filename="fundamentals-screen.csv", max_rows=MAX_SCREEN_ROWS)
    selected_cik = st.selectbox(
        "Open result in Company 360",
        rows["CIK"].astype(int).tolist(),
        key="fund_drill_cik",
    )
    st.session_state[SESSION_CIK_KEY] = int(selected_cik)
    st.caption("Selection and dashboard mode are preserved for Company 360 drill-through.")


def render_insider_watch(mode: str) -> None:
    st.header("Insider Watch")
    if mode == MODE_AGENT_VIEW:
        st.info(
            "Insider Watch is an Explore workflow. Agent View does not query "
            "free ownership tables."
        )
        return
    st.caption(
        f"Deduplicated Form 3/4/5 transactions; maximum {MAX_INSIDER_ROWS} rows. "
        "P means purchase and S means sale; missing price/notional remains unavailable."
    )
    st.caption(
        "Earnings-event comparison is shown as unavailable unless an authoritative "
        "issuer event is present; no calendar proximity is presented as evidence."
    )
    issuer = st.text_input("Issuer name", value="", key="insider_issuer")
    start_date = st.text_input(
        "Start date (YYYY-MM-DD)", value="1900-01-01", key="insider_start"
    )
    end_date = st.text_input(
        "End date (YYYY-MM-DD)", value="2999-12-31", key="insider_end"
    )
    form = st.selectbox("Form", ["%", "3%", "4%", "5%"], key="insider_form")
    owner_role = st.selectbox(
        "Owner role",
        ["all", "officer", "director", "ten_percent_owner", "unavailable"],
        key="insider_role",
    )
    code = st.selectbox("Transaction code", ["all", "P", "S"], key="insider_code")
    derivative = st.selectbox(
        "Security type",
        ["all", "non_derivative", "derivative"],
        key="insider_derivative",
    )
    min_shares = _parse_optional_number(
        st.text_input("Minimum shares", value="", key="insider_min_shares")
    )
    min_notional = _parse_optional_number(
        st.text_input("Minimum notional", value="", key="insider_min_notional")
    )
    rows = _workflow_df(
        insider_query(
            start_date=start_date,
            end_date=end_date,
            issuer_pattern=f"%{issuer.strip()}%",
            form_pattern=form,
            owner_role=owner_role,
            transaction_code=code,
            min_shares=min_shares,
            min_notional=min_notional,
            derivative=derivative,
        )
    )
    if rows is None or rows.empty:
        st.info("No covered transactions matched the current filters.")
        return
    _show_dataframe(_add_sec_evidence_links(rows))
    _bounded_export(rows, filename="insider-watch.csv", max_rows=MAX_INSIDER_ROWS)
    selected_cik = st.selectbox(
        "Open issuer in Company 360",
        rows["CIK"].astype(int).tolist(),
        key="insider_drill_cik",
    )
    st.session_state[SESSION_CIK_KEY] = int(selected_cik)


def render_adv_explorer(mode: str) -> None:
    st.header("ADV Adviser / Fund Explorer")
    if mode == MODE_AGENT_VIEW:
        st.info(
            "ADV Explorer is explicitly Explore-only and is not agent-grade "
            "Decision Contract evidence."
        )
        return
    st.caption(
        f"Read-only active adviser/fund records and active MANAGES_FUND generation; "
        f"maximum {MAX_ADV_ROWS} rows. Missing AUM remains unavailable, never zero."
    )
    search = st.text_input(
        "Adviser/fund name, CRD, SEC file number, or PFID",
        value="",
        key="adv_search",
    )
    if not search.strip():
        st.info("Enter an adviser or fund identifier to search.")
        return
    rows = _workflow_df(adv_query(f"%{search.strip()}%"))
    if rows is None or rows.empty:
        st.info(
            "No active covered adviser/fund relationship matched. The graph may "
            "be unavailable, partial, or stale; no mutation was attempted."
        )
        return
    rows = rows.copy()
    rows["IAPD_EVIDENCE_URL"] = rows["CRD_NUMBER"].apply(
        lambda value: (
            f"https://adviserinfo.sec.gov/firm/summary/{value}"
            if value is not None and str(value).strip()
            else None
        )
    )
    _show_dataframe(rows)
    _bounded_export(rows, filename="adv-explorer.csv", max_rows=MAX_ADV_ROWS)


def _render_freshness_strip(mode: str) -> None:
    st.caption("Release-bound freshness")
    if mode == MODE_AGENT_VIEW:
        status = _registered_df("agent.contract_status")
        if status is None or status.empty:
            st.warning(
                "Decision watermark / contract-generation alignment unavailable. "
                "Agent-grade evidence is fail-closed."
            )
        else:
            row = status.iloc[0]
            st.write(
                {
                    "decision_watermark": row.get("DECISION_WATERMARK"),
                    "business_date": row.get("BUSINESS_DATE"),
                    "gold_updated_at": row.get("GOLD_UPDATED_AT"),
                    "graph_generation_id": row.get("GRAPH_GENERATION_ID"),
                    "alignment_status": row.get("ALIGNMENT_STATUS"),
                }
            )
        return
    status = _safe_df(
        "Explore freshness",
        f"""
        select
          max(updated_at) as gold_source_updated_at,
          max(business_date) as source_business_date,
          (
            select active_generation_id
            from NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER
            where pointer_id = 'active'
          ) as graph_generation_id,
          'not_decision_contract_evidence' as alignment_status
        from {SOURCE_SCHEMA}.SNOWFLAKE_REFRESH_STATUS
        limit 1
        """,
    )
    if status is None or status.empty:
        st.warning("Explore source dates and graph generation are unavailable.")
    else:
        st.write(status.iloc[0].to_dict())


def _pipeline_runs():
    return _safe_df(
        "Pipeline runs",
        f"""
        with latest_manifest as (
          select
            environment,
            workflow_name,
            run_id,
            business_date,
            received_at,
            completed_at as manifest_completed_at
          from {SOURCE_SCHEMA}.SNOWFLAKE_RUN_MANIFEST_INBOX
          qualify row_number() over (
            partition by environment, workflow_name, run_id
            order by received_at desc
          ) = 1
        )
        select
          coalesce(s.environment, m.environment) as environment,
          coalesce(s.source_workflow, m.workflow_name) as workflow_name,
          coalesce(s.run_id, m.run_id) as run_id,
          m.business_date,
          m.received_at as manifest_received_at,
          m.manifest_completed_at,
          s.source_load_status,
          s.refresh_status,
          s.status,
          s.source_row_count,
          s.tables_loaded,
          s.error_message,
          s.updated_at,
          datediff('second', m.manifest_completed_at, s.updated_at) as snowflake_seconds
        from latest_manifest m
        full outer join {SOURCE_SCHEMA}.SNOWFLAKE_REFRESH_STATUS s
          on s.environment = m.environment
         and s.source_workflow = m.workflow_name
         and s.run_id = m.run_id
        order by coalesce(s.updated_at, m.received_at) desc
        limit 100
        """,
    )


def _pipeline_task_history():
    return _safe_df(
        "Manifest task history",
        """
        select *
        from table(information_schema.task_history(
          task_name => 'SNOWFLAKE_RUN_MANIFEST_TASK',
          result_limit => 50
        ))
        order by scheduled_time desc
        """,
    )


def _dynamic_table_refresh_history():
    return _safe_df(
        "Dynamic table refresh history",
        f"""
        select *
        from table(information_schema.dynamic_table_refresh_history(result_limit => 100))
        where database_name = current_database()
          and schema_name = '{GOLD_SCHEMA}'
        order by coalesce(refresh_start_time, data_timestamp) desc
        """,
    )


def _manifest_copy_history():
    return _safe_df(
        "Manifest copy history",
        f"""
        select *
        from table(information_schema.copy_history(
          table_name => '{SOURCE_SCHEMA}.SNOWFLAKE_RUN_MANIFEST_INBOX',
          start_time => dateadd(day, -7, current_timestamp())
        ))
        order by last_load_time desc
        """,
    )


def _adv_fund_count_mismatches():
    """Ticket 04: mismatched-firm detail table for the ADV fund count
    completeness cross-check (advFilingData vs Firm Roster CSV)."""
    return _safe_df(
        "ADV fund count reconciliation",
        f"""
        select
          adviser_crd_number,
          roster_dataset_period,
          filing_derived_fund_count,
          roster_fund_count,
          fund_count_delta,
          private_fund_count_7b1,
          private_fund_count_7b2
        from {GOLD_SCHEMA}.ADV_FUND_COUNT_RECONCILIATION
        where mismatch
        order by abs(fund_count_delta) desc
        """,
    )


def _adv_fund_count_reconciliation_summary():
    return _safe_df(
        "ADV fund count reconciliation summary",
        f"""
        select
          count(*) as total_firms,
          sum(case when mismatch then 1 else 0 end) as mismatched_firms
        from {GOLD_SCHEMA}.ADV_FUND_COUNT_RECONCILIATION
        """,
    )


def _adv_reconciliation_mismatch_stats(summary) -> tuple[int, int, float]:
    """Returns (mismatched_firms, total_firms, mismatch_pct), defaulting to
    zeros on missing/empty input and guarding against division by zero."""
    if summary is None or summary.empty:
        return 0, 0, 0.0
    total = int(summary["TOTAL_FIRMS"].iloc[0] or 0)
    mismatched = int(summary["MISMATCHED_FIRMS"].iloc[0] or 0)
    pct = (mismatched / total * 100) if total else 0.0
    return mismatched, total, pct


def _render_pipeline_metrics(runs):
    if runs is None or runs.empty:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Runs", "0")
        col2.metric("Succeeded", "0")
        col3.metric("Running", "0")
        col4.metric("Failed", "0")
        return

    status = runs["STATUS"].fillna("pending").str.lower()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Runs", f"{len(runs):,}")
    col2.metric("Succeeded", f"{int((status == 'succeeded').sum()):,}")
    col3.metric("Running", f"{int((status == 'running').sum()):,}")
    col4.metric("Failed", f"{int((status == 'failed').sum()):,}")


def render_pipeline():
    st.header("Pipeline")
    runs = _pipeline_runs()
    _render_pipeline_metrics(runs)

    st.subheader("Recent runs")
    _show_dataframe(
        runs,
        [
            "ENVIRONMENT",
            "WORKFLOW_NAME",
            "RUN_ID",
            "BUSINESS_DATE",
            "MANIFEST_RECEIVED_AT",
            "MANIFEST_COMPLETED_AT",
            "SOURCE_LOAD_STATUS",
            "REFRESH_STATUS",
            "STATUS",
            "SOURCE_ROW_COUNT",
            "TABLES_LOADED",
            "SNOWFLAKE_SECONDS",
            "ERROR_MESSAGE",
            "UPDATED_AT",
        ],
    )

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Manifest task")
        _show_dataframe(
            _pipeline_task_history(),
            [
                "SCHEDULED_TIME",
                "COMPLETED_TIME",
                "STATE",
                "QUERY_ID",
                "ERROR_CODE",
                "ERROR_MESSAGE",
            ],
        )
    with col_right:
        st.subheader("Manifest copy")
        _show_dataframe(
            _manifest_copy_history(),
            [
                "FILE_NAME",
                "STATUS",
                "ROW_COUNT",
                "ERROR_COUNT",
                "LAST_LOAD_TIME",
                "FIRST_ERROR_MESSAGE",
            ],
        )

    st.subheader("Gold dynamic table refresh")
    _show_dataframe(
        _dynamic_table_refresh_history(),
        [
            "NAME",
            "STATE",
            "REFRESH_TRIGGER",
            "REFRESH_ACTION",
            "REFRESH_START_TIME",
            "REFRESH_END_TIME",
            "DATA_TIMESTAMP",
            "STATE_MESSAGE",
        ],
    )

    st.subheader("ADV fund count reconciliation")
    st.caption(
        "advFilingData-derived private fund counts vs SEC's independently-published "
        "Firm Roster CSV aggregate counts. Purely additive visibility -- never gates "
        "MDM entity resolution or graph sync."
    )
    mismatched, total, pct = _adv_reconciliation_mismatch_stats(
        _adv_fund_count_reconciliation_summary()
    )
    st.metric(
        "Firms mismatched",
        f"{mismatched:,} / {total:,}",
        f"{pct:.1f}%",
    )
    _show_dataframe(
        _adv_fund_count_mismatches(),
        [
            "ADVISER_CRD_NUMBER",
            "ROSTER_DATASET_PERIOD",
            "FILING_DERIVED_FUND_COUNT",
            "ROSTER_FUND_COUNT",
            "FUND_COUNT_DELTA",
            "PRIVATE_FUND_COUNT_7B1",
            "PRIVATE_FUND_COUNT_7B2",
        ],
    )


def main() -> None:
    """App entry — only run under Streamlit (not when imported by unit tests)."""
    mode = _render_mode_chrome()
    _render_freshness_strip(mode)
    (
        summary_tab,
        details_tab,
        fundamentals_tab,
        insider_tab,
        adv_tab,
        pipeline_tab,
    ) = st.tabs(
        [
            "Summary",
            "Company 360",
            "Fundamentals Screener",
            "Insider Watch",
            "ADV Explorer",
            "Pipeline",
        ]
    )
    with summary_tab:
        render_summary(mode=mode)
    with details_tab:
        render_details(mode=mode)
    with fundamentals_tab:
        render_fundamentals(mode=mode)
    with insider_tab:
        render_insider_watch(mode=mode)
    with adv_tab:
        render_adv_explorer(mode=mode)
    with pipeline_tab:
        if mode == MODE_AGENT_VIEW:
            st.header("Pipeline")
            st.info(
                "Pipeline ops views use free SOURCE/information_schema joins — "
                "switch to **Explore** mode (labeled not-for-agent)."
            )
        else:
            render_pipeline()


# Streamlit / SiS provide session_state; unit tests inject a FakeStreamlit without it.
if hasattr(st, "session_state"):
    main()
