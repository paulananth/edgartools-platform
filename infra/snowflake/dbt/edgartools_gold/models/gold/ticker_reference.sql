-- TICKER_REFERENCE: CIK-to-ticker reference mirror.
--
-- dbt-gold-silver-rewiring map, Ticket 02: unlike this batch's other five
-- models, TICKER_REFERENCE was never a silver passthrough -- the Python
-- builder (build_ticker_reference_table, edgar_warehouse/serving/gold_models.py)
-- projected it directly from seed_universe_loader's raw SEC
-- company_tickers_exchange.json parse, bypassing DuckDB silver entirely. The
-- nearest silver equivalent is sec_company_ticker
-- (edgar_warehouse.silver_store.replace_company_tickers), which parses the
-- same company_tickers_exchange.json payload into a durable table carrying
-- an explicit source_name per row ('company_tickers_exchange' vs
-- 'company_tickers', the latter ticker-less and used elsewhere only for
-- tracking-universe eligibility, not ticker data). Filtering to
-- source_name = 'company_tickers_exchange' reproduces this table's grain and
-- columns exactly: cik/ticker/exchange/last_sync_run_id, one row per
-- (cik, ticker) courtesy of sec_company_ticker's own
-- qualify row_number() ... partition by (cik, ticker, source_name) collapse.
{{ gold_model_config('TICKER_REFERENCE') }}

select
  cik,
  ticker,
  exchange,
  last_sync_run_id
from {{ ref("sec_company_ticker") }}
where source_name = 'company_tickers_exchange'
