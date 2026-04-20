# EdgarTools Universe Dashboard

A six-section Streamlit explorer over the Snowflake gold layer built by
[`infra/snowflake/dbt/edgartools_gold`](../../infra/snowflake/dbt/edgartools_gold/).

![Sections](https://img.shields.io/badge/sections-6-blue) ![Stack](https://img.shields.io/badge/stack-Streamlit%20%2B%20Plotly-orange)

## Sections

| | Section | What it shows |
|---|---|---|
| 📊 | Overview | Universe KPIs (companies, filings, insider txns, funds, tickers, latest filing), gold freshness, top industries, entity-type mix |
| 🗺️ | World & US Map | Choropleth of companies by country / US state of incorporation, top-20 countries, top-15 US states |
| 🏭 | Industry & Entity | Top 25 SIC industries, entity-type pie, industry × entity heatmap |
| 📈 | Filing Activity | Monthly filing volume (5y), top 20 forms, top 15 filers, XBRL adoption rate over time |
| 💼 | Ownership & Funds | Top 20 insider-active companies, private fund AUM distribution, top 15 advisers, recent 90-day insider transactions |
| 🔎 | Company Lookup | Ticker / name search → detail card with CIK, tickers, exchanges, resolved state-of-incorporation, filings-by-form, timeline, recent filings table |

## Prerequisites

- Python 3.11+
- A Snowflake role with `SELECT` on `EDGARTOOLS_DEV.EDGARTOOLS_GOLD.*` and `USAGE` on a warehouse that can query dynamic tables.
- `~/.snowflake/config.toml` with a connection block. Minimal example:

```toml
default_connection_name = "edgartools"

[connections.edgartools]
account    = "<your-account>"
user       = "<your-user>"
password   = "<your-password>"          # or authenticator / private_key_path
role       = "<role-with-read-access>"
warehouse  = "<warehouse>"
database   = "EDGARTOOLS_DEV"
schema     = "EDGARTOOLS_GOLD"
```

`database` and `schema` are optional — defaults are `EDGARTOOLS_DEV` / `EDGARTOOLS_GOLD`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r examples/dashboard/requirements.txt
```

## Run

```bash
streamlit run examples/dashboard/edgar_universe_dashboard.py
```

The app opens on <http://localhost:8501>. Use the sidebar to switch sections.

## Caveats

- **State of incorporation ≠ headquarters.** Delaware will dominate the US map because ~60 % of US public companies are incorporated there. The app shows a banner reminder on the map section.
- **No lat/lon in the gold layer.** The maps aggregate at country / US-state granularity using SEC place codes (embedded in the dashboard file — no EdgarTools import required).
- **Adviser office geography is not plotted.** `ADVISER_OFFICES.geography_key` is an unresolved surrogate in the current gold schema; a GEOGRAPHY dimension does not exist. When that dimension lands, a "📍 Adviser Offices" section can be added.
- **All queries are cached for 1 hour.** Clear with ⟳ in the Streamlit menu (or restart) if the gold tables have just refreshed and you want to see new rows.

## Related

- [`infra/snowflake/streamlit/streamlit_app.py`](../../infra/snowflake/streamlit/streamlit_app.py) — minimal 2-tab Streamlit-in-Snowflake app (Summary / Company Details). Lives inside Snowflake and uses `get_active_session()`. Complements this example.
- [`infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml`](../../infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml) — authoritative gold-table documentation.
