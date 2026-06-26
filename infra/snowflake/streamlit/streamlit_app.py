"""EdgarTools warehouse dashboard (Streamlit-in-Snowflake).

Reads gold tables from EDGARTOOLS_GOLD via the active Snowpark session.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="EdgarTools Warehouse", layout="wide")

GOLD_SCHEMA = "EDGARTOOLS_GOLD"
SOURCE_SCHEMA = "EDGARTOOLS_SOURCE"


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
    except Exception as exc:
        st.warning(f"{label} is not available: {exc}")
        return None


def _show_dataframe(df, columns: list[str] | None = None):
    if df is None or df.empty:
        st.info("No rows to display.")
        return
    if columns is not None:
        visible = [column for column in columns if column in df.columns]
        if visible:
            df = df[visible]
    st.dataframe(df, use_container_width=True, hide_index=True)


def _metric_text(value, fmt: str) -> str:
    if value is None or value != value:
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


def render_summary():
    st.header("Summary")
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
        order by c.entity_name
        limit 25
        """,
        params=[pattern, pattern],
    )


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


def render_details():
    st.header("Company Details")
    query = st.text_input("Search by ticker or company name", placeholder="e.g. AAPL or Apple")

    if not query:
        st.info("Enter a ticker symbol or part of a company name to start.")
        return

    matches = _lookup_companies(query.strip())
    if matches is None or matches.empty:
        st.warning(f"No companies matched '{query}'.")
        return

    matches = matches.copy()
    matches["label"] = matches.apply(
        lambda r: f"{r['ENTITY_NAME']} — CIK {int(r['CIK'])}", axis=1
    )
    label = st.selectbox("Matches", matches["label"].tolist())
    selected = matches.loc[matches["label"] == label].iloc[0]
    company_key = int(selected["COMPANY_KEY"])

    meta = _company_metadata(company_key)
    if meta.empty:
        st.error("Selected company not found.")
        return
    row = meta.iloc[0]
    cik = int(row["CIK"])

    st.subheader(row["ENTITY_NAME"])
    col1, col2, col3 = st.columns(3)
    col1.metric("CIK", cik)
    col2.metric("Tickers", row["TICKERS"] or "—")
    col3.metric("Entity type", row["ENTITY_TYPE"] or "—")

    with st.expander("Metadata", expanded=True):
        st.write(
            {
                "SIC": row["SIC"],
                "SIC description": row["SIC_DESCRIPTION"],
                "State of incorporation": row["STATE_OF_INCORPORATION"],
                "Fiscal year end": row["FISCAL_YEAR_END"],
            }
        )

    st.subheader("Financial factors")
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


summary_tab, details_tab, pipeline_tab = st.tabs(["Summary", "Company Details", "Pipeline"])
with summary_tab:
    render_summary()
with details_tab:
    render_details()
with pipeline_tab:
    render_pipeline()
