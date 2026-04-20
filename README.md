# edgartools-platform

Data platform for SEC EDGAR built on [edgartools](https://github.com/dgunning/edgartools).

Extracts SEC EDGAR filing data from source through a bronze AWS S3 layer to a gold Snowflake analytics layer.

## Architecture

```
SEC EDGAR API → edgar-warehouse (Python) → S3 (Parquet) → Snowflake source tables → dbt → Gold dynamic tables → Streamlit dashboard
```

## Quick Start

See [docs/runbook.md](docs/runbook.md) for complete end-to-end setup.

## Structure

| Directory | Purpose |
|---|---|
| `edgar_warehouse/` | Python ETL runtime — exports SEC data to S3 |
| `infra/terraform/` | AWS + Snowflake infrastructure (IaC) |
| `infra/snowflake/dbt/` | dbt project that creates Snowflake gold tables |
| `infra/snowflake/sql/bootstrap/` | Bootstrap SQL for Snowflake native S3 pull |
| `infra/snowflake/streamlit/` | Streamlit-in-Snowflake production dashboard |
| `scripts/batch/` | Batch processing scripts for individual form types |
| `examples/dashboard/` | Standalone Streamlit dashboard |

## Dependencies

This platform requires `edgartools` (the core SEC library):
```bash
pip install edgartools>=5.29.0
```

## Installation

```bash
git clone https://github.com/paulananth/edgartools-platform
cd edgartools-platform
pip install -e ".[s3,snowflake]"
```
