"""EdgarTools warehouse dashboard (Streamlit-in-Snowflake).

Reads gold tables from EDGARTOOLS_GOLD via the active Snowpark session.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="EdgarTools Warehouse", layout="wide")

GOLD_SCHEMA = "EDGARTOOLS_GOLD"


@st.cache_resource
def _session():
    return get_active_session()


def _df(sql: str, params: list | None = None):
    session = _session()
    if params:
        return session.sql(sql, params=params).to_pandas()
    return session.sql(sql).to_pandas()


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

    st.subheader(row["ENTITY_NAME"])
    col1, col2, col3 = st.columns(3)
    col1.metric("CIK", int(row["CIK"]))
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


summary_tab, details_tab = st.tabs(["Summary", "Company Details"])
with summary_tab:
    render_summary()
with details_tab:
    render_details()
