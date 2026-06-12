"""Gold layer builders and Parquet export helpers for the warehouse."""

from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta
from typing import Any

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyArrow is required for the gold layer. "
        "Install with: pip install 'edgartools[warehouse]'"
    ) from exc

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.silver_store import SilverDatabase
from edgar_warehouse.silver_support.access import get_connection

_TXN_CODE_DESCRIPTIONS = {
    "A": "grant, award, or other acquisition",
    "C": "conversion of derivative security",
    "D": "sale or disposition to issuer",
    "F": "payment by delivering or withholding securities",
    "G": "gift",
    "M": "exercise or conversion of derivative security",
    "P": "open market or private purchase",
    "S": "open market or private sale",
    "X": "exercise of in-the-money derivative security",
}


def _det_key(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _form_family(form: str | None) -> str:
    if not form:
        return "other"
    if form.startswith("10-K"):
        return "10-K"
    if form.startswith("10-Q"):
        return "10-Q"
    if form.startswith("8-K"):
        return "8-K"
    if form in {"3", "3/A", "4", "4/A", "5", "5/A"}:
        return "ownership"
    if form.startswith("ADV"):
        return "adv"
    if form.startswith("DEF 14") or form.startswith("PRE 14"):
        return "proxy"
    return "other"


_DIM_COMPANY_SCHEMA = pa.schema(
    [
        pa.field("company_key", pa.int64()),
        pa.field("cik", pa.int64()),
        pa.field("entity_name", pa.string()),
        pa.field("entity_type", pa.string()),
        pa.field("sic", pa.string()),
        pa.field("sic_description", pa.string()),
        pa.field("state_of_incorporation", pa.string()),
        pa.field("fiscal_year_end", pa.string()),
        pa.field("last_sync_run_id", pa.string()),
    ]
)
_DIM_TICKER_REFERENCE_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.int64()),
        pa.field("ticker", pa.string()),
        pa.field("exchange", pa.string()),
        pa.field("last_sync_run_id", pa.string()),
    ]
)
_DIM_FORM_SCHEMA = pa.schema(
    [
        pa.field("form_key", pa.int64()),
        pa.field("form", pa.string()),
        pa.field("form_family", pa.string()),
    ]
)
_DIM_DATE_SCHEMA = pa.schema(
    [
        pa.field("date_key", pa.int32()),
        pa.field("full_date", pa.date32()),
        pa.field("year", pa.int32()),
        pa.field("month", pa.int32()),
        pa.field("day", pa.int32()),
        pa.field("quarter", pa.int32()),
        pa.field("day_of_week", pa.int32()),
        pa.field("is_weekend", pa.bool_()),
    ]
)
_DIM_FILING_SCHEMA = pa.schema(
    [
        pa.field("filing_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("cik", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("form", pa.string()),
        pa.field("form_key", pa.int64()),
        pa.field("filing_date", pa.date32()),
        pa.field("date_key", pa.int32()),
        pa.field("report_date", pa.date32()),
        pa.field("is_xbrl", pa.bool_()),
        pa.field("size", pa.int64()),
    ]
)
_FACT_FILING_ACTIVITY_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("filing_key", pa.int64()),
        pa.field("date_key", pa.int32()),
        pa.field("form_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("cik", pa.int64()),
        pa.field("form", pa.string()),
        pa.field("filing_date", pa.date32()),
        pa.field("report_date", pa.date32()),
        pa.field("is_xbrl", pa.bool_()),
    ]
)
_DIM_PARTY_SCHEMA = pa.schema(
    [
        pa.field("party_key", pa.int64()),
        pa.field("party_natural_key", pa.string()),
        pa.field("party_name", pa.string()),
        pa.field("party_cik", pa.int64()),
    ]
)
_DIM_SECURITY_SCHEMA = pa.schema(
    [
        pa.field("security_key", pa.int64()),
        pa.field("security_natural_key", pa.string()),
        pa.field("security_title", pa.string()),
        pa.field("issuer_cik", pa.int64()),
    ]
)
_DIM_OWNERSHIP_TXN_TYPE_SCHEMA = pa.schema(
    [
        pa.field("ownership_txn_type_key", pa.int64()),
        pa.field("transaction_code", pa.string()),
        pa.field("description", pa.string()),
    ]
)
_DIM_GEOGRAPHY_SCHEMA = pa.schema(
    [
        pa.field("geography_key", pa.int64()),
        pa.field("state_or_country", pa.string()),
        pa.field("country", pa.string()),
    ]
)
_DIM_DISCLOSURE_CATEGORY_SCHEMA = pa.schema(
    [
        pa.field("disclosure_category_key", pa.int64()),
        pa.field("disclosure_category", pa.string()),
    ]
)
_DIM_PRIVATE_FUND_SCHEMA = pa.schema(
    [
        pa.field("private_fund_key", pa.int64()),
        pa.field("private_fund_natural_key", pa.string()),
        pa.field("fund_name", pa.string()),
        pa.field("fund_type", pa.string()),
        pa.field("jurisdiction", pa.string()),
    ]
)
_FACT_OWNERSHIP_TRANSACTION_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("date_key", pa.int32()),
        pa.field("form_key", pa.int64()),
        pa.field("party_key", pa.int64()),
        pa.field("security_key", pa.int64()),
        pa.field("ownership_txn_type_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("owner_index", pa.int16()),
        pa.field("txn_index", pa.int16()),
        pa.field("transaction_code", pa.string()),
        pa.field("transaction_shares", pa.float64()),
        pa.field("transaction_price", pa.float64()),
        pa.field("shares_owned_after", pa.float64()),
        pa.field("is_derivative", pa.bool_()),
    ]
)
_FACT_OWNERSHIP_HOLDING_SNAPSHOT_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("date_key", pa.int32()),
        pa.field("party_key", pa.int64()),
        pa.field("security_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("owner_index", pa.int16()),
        pa.field("shares_owned_after", pa.float64()),
        pa.field("ownership_direct_indirect", pa.string()),
    ]
)
_FACT_ADV_OFFICE_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("date_key", pa.int32()),
        pa.field("geography_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("office_index", pa.int16()),
        pa.field("office_name", pa.string()),
        pa.field("is_headquarters", pa.bool_()),
    ]
)
_FACT_ADV_DISCLOSURE_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("date_key", pa.int32()),
        pa.field("disclosure_category_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("event_index", pa.int16()),
        pa.field("is_reported", pa.bool_()),
    ]
)
_FACT_ADV_PRIVATE_FUND_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64()),
        pa.field("company_key", pa.int64()),
        pa.field("date_key", pa.int32()),
        pa.field("private_fund_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("fund_index", pa.int16()),
        pa.field("aum_amount", pa.float64()),
    ]
)

# ── Branch B Fundamentals — PR-1 ─────────────────────────────────────────
# Passthrough schemas (Q1-C / Q2-A): 1:1 with silver, composite natural keys.
# PK columns marked nullable=False per Q5-C (prevents NULL MERGE-key surprises
# that would lead to duplicate INSERTs).

_SEC_FINANCIAL_FACT_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.int64(), nullable=False),
        pa.field("accession_number", pa.string(), nullable=False),
        pa.field("concept", pa.string(), nullable=False),
        pa.field("fiscal_period", pa.string(), nullable=False),
        pa.field("segment", pa.string(), nullable=False),
        pa.field("fiscal_year", pa.int32()),
        pa.field("period_end", pa.date32()),
        pa.field("period_start", pa.date32(), nullable=False),
        pa.field("form_type", pa.string()),
        pa.field("value", pa.float64()),
        pa.field("unit", pa.string()),
        pa.field("decimals", pa.int32()),
        pa.field("parser_version", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

_SEC_THIRTEENF_HOLDING_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.int64(), nullable=False),
        pa.field("accession_number", pa.string(), nullable=False),
        pa.field("holding_index", pa.int64(), nullable=False),
        pa.field("period_of_report", pa.date32()),
        pa.field("cusip", pa.string()),
        pa.field("issuer_name", pa.string()),
        pa.field("security_title", pa.string()),
        pa.field("shares_held", pa.float64()),
        pa.field("market_value", pa.float64()),
        pa.field("security_class", pa.string()),
        pa.field("put_call", pa.string()),
        pa.field("discretion_type", pa.string()),
        pa.field("voting_auth_sole", pa.float64()),
        pa.field("voting_auth_shared", pa.float64()),
        pa.field("voting_auth_none", pa.float64()),
        pa.field("parser_version", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

_SEC_FINANCIAL_DERIVED_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.int64(), nullable=False),
        pa.field("accession_number", pa.string(), nullable=False),
        pa.field("fiscal_period", pa.string(), nullable=False),
        pa.field("fiscal_year", pa.int32()),
        pa.field("period_end", pa.date32()),
        pa.field("form_type", pa.string()),
        pa.field("revenue", pa.float64()),
        pa.field("gross_profit", pa.float64()),
        pa.field("ebitda", pa.float64()),
        pa.field("ebit", pa.float64()),
        pa.field("net_income", pa.float64()),
        pa.field("eps_diluted", pa.float64()),
        pa.field("total_assets", pa.float64()),
        pa.field("total_liabilities", pa.float64()),
        pa.field("total_equity", pa.float64()),
        pa.field("cash_and_equivalents", pa.float64()),
        pa.field("total_debt", pa.float64()),
        pa.field("operating_cash_flow", pa.float64()),
        pa.field("capex", pa.float64()),
        pa.field("free_cash_flow", pa.float64()),
        pa.field("gross_margin", pa.float64()),
        pa.field("ebitda_margin", pa.float64()),
        pa.field("net_margin", pa.float64()),
        pa.field("roic", pa.float64()),
        pa.field("roe", pa.float64()),
        pa.field("roa", pa.float64()),
        pa.field("parser_version", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

# Dimensional schemas (Q3-D): surrogate fact_key (NOT NULL per Q5-C) + dim FKs.

_FACT_EARNINGS_RELEASE_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64(), nullable=False),
        pa.field("company_key", pa.int64()),
        pa.field("filing_date_key", pa.int32()),
        pa.field("period_end_date_key", pa.int32()),
        pa.field("form_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("cik", pa.int64()),
        pa.field("filing_date", pa.date32()),
        pa.field("fiscal_year", pa.int32()),
        pa.field("fiscal_quarter", pa.int32()),
        pa.field("period_end", pa.date32()),
        pa.field("revenue_gaap", pa.float64()),
        pa.field("net_income_gaap", pa.float64()),
        pa.field("eps_gaap_diluted", pa.float64()),
        pa.field("has_non_gaap", pa.bool_()),
        pa.field("has_guidance", pa.bool_()),
        pa.field("parser_version", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

_FACT_EXECUTIVE_RECORD_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64(), nullable=False),
        pa.field("company_key", pa.int64()),
        pa.field("fiscal_year_date_key", pa.int32()),
        pa.field("accession_number", pa.string()),
        pa.field("cik", pa.int64()),
        pa.field("fiscal_year", pa.int32()),
        pa.field("exec_name", pa.string()),
        pa.field("exec_role", pa.string()),
        pa.field("total_comp", pa.float64()),
        pa.field("base_salary", pa.float64()),
        pa.field("bonus", pa.float64()),
        pa.field("stock_awards", pa.float64()),
        pa.field("option_awards", pa.float64()),
        pa.field("non_equity_incentive", pa.float64()),
        pa.field("parser_version", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

_FACT_ACCOUNTING_FLAG_SCHEMA = pa.schema(
    [
        pa.field("fact_key", pa.int64(), nullable=False),
        pa.field("company_key", pa.int64()),
        pa.field("fiscal_year_date_key", pa.int32()),
        pa.field("form_key", pa.int64()),
        pa.field("accession_number", pa.string()),
        pa.field("cik", pa.int64()),
        pa.field("fiscal_year", pa.int32()),
        pa.field("period_end", pa.date32()),
        pa.field("form_type", pa.string()),
        pa.field("auditor_name", pa.string()),
        pa.field("auditor_pcaob_id", pa.string()),
        pa.field("auditor_location", pa.string()),
        pa.field("icfr_attestation", pa.bool_()),
        pa.field("auditor_changed", pa.bool_()),
        pa.field("beneish_m_score", pa.float64()),
        pa.field("altman_z_score", pa.float64()),
        pa.field("piotroski_f_score", pa.int32()),
        pa.field("parser_version", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)


def _empty(schema: pa.Schema) -> pa.Table:
    return pa.table({field.name: pa.array([], type=field.type) for field in schema}, schema=schema)


def _arrow(result: Any) -> pa.Table:
    table = result.arrow()
    if hasattr(table, "read_all"):
        return table.read_all()
    return table


def _fetch_rows(conn: Any, query: str) -> list[dict[str, Any]]:
    result = conn.execute(query).fetchall()
    columns = [desc[0] for desc in conn.description]
    return [dict(zip(columns, row)) for row in result]


def _table_from_records(schema: pa.Schema, records: list[dict[str, Any]]) -> pa.Table:
    if not records:
        return _empty(schema)
    return pa.table(
        {
            field.name: pa.array([record.get(field.name) for record in records], type=field.type)
            for field in schema
        },
        schema=schema,
    )


def _date_to_int(day: date) -> int:
    return day.year * 10000 + day.month * 100 + day.day


def _filing_date_to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, date):
        return _date_to_int(value)
    try:
        return _date_to_int(date.fromisoformat(str(value)))
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def _normalized_text(value: Any) -> str:
    return (_clean_text(value) or "").lower()


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _party_natural_key(party_name: Any, party_cik: Any) -> str | None:
    cik = _coerce_int(party_cik)
    if cik is not None:
        return f"cik:{cik}"
    name = _normalized_text(party_name)
    if name:
        return f"name:{name}"
    return None


def _security_natural_key(issuer_cik: Any, security_title: Any) -> str | None:
    title = _normalized_text(security_title)
    if not title:
        return None
    issuer = _coerce_int(issuer_cik)
    return f"{issuer or 0}|{title}"


def _geography_natural_key(state_or_country: Any, country: Any) -> str | None:
    state = _normalized_text(state_or_country)
    country_value = _normalized_text(country)
    if not state and not country_value:
        return None
    return f"{state}|{country_value}"


def _private_fund_natural_key(cik: Any, fund_name: Any, fund_type: Any, jurisdiction: Any) -> str | None:
    issuer = _coerce_int(cik)
    name = _normalized_text(fund_name)
    fund_type_value = _normalized_text(fund_type)
    jurisdiction_value = _normalized_text(jurisdiction)
    if not any((issuer is not None, name, fund_type_value, jurisdiction_value)):
        return None
    return f"{issuer or 0}|{name}|{fund_type_value}|{jurisdiction_value}"


def _build_dim_company(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                cik AS company_key,
                cik,
                entity_name,
                entity_type,
                sic,
                sic_description,
                state_of_incorporation,
                fiscal_year_end,
                last_sync_run_id
            FROM sec_company
            ORDER BY cik
            """
        )
    )
    return _empty(_DIM_COMPANY_SCHEMA) if table.num_rows == 0 else table.cast(_DIM_COMPANY_SCHEMA)


def _build_dim_form(conn: Any) -> pa.Table:
    # form_family computed in Python (466 rows — negligible); form_key uses DuckDB hash
    # to stay consistent with the hash used in _build_dim_filing / _build_fact_filing_activity.
    base = _arrow(conn.execute(
        "SELECT DISTINCT form, (hash(form) & 9223372036854775807)::BIGINT AS form_key"
        " FROM sec_company_filing WHERE form IS NOT NULL ORDER BY form"
    ))
    if base.num_rows == 0:
        return _empty(_DIM_FORM_SCHEMA)
    forms = base.column("form").to_pylist()
    return pa.table(
        {
            "form_key": base.column("form_key").cast(pa.int64()),
            "form": pa.array(forms, type=pa.string()),
            "form_family": pa.array([_form_family(form) for form in forms], type=pa.string()),
        },
        schema=_DIM_FORM_SCHEMA,
    )


def _build_dim_date(conn: Any) -> pa.Table:
    row = conn.execute("SELECT MIN(filing_date), MAX(filing_date) FROM sec_company_filing").fetchone()
    if row is None or row[0] is None:
        return _empty(_DIM_DATE_SCHEMA)
    start = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
    end = row[1] if isinstance(row[1], date) else date.fromisoformat(str(row[1]))
    values: list[date] = []
    current = start
    while current <= end:
        values.append(current)
        current += timedelta(days=1)
    return pa.table(
        {
            "date_key": pa.array([_date_to_int(day) for day in values], type=pa.int32()),
            "full_date": pa.array(values, type=pa.date32()),
            "year": pa.array([day.year for day in values], type=pa.int32()),
            "month": pa.array([day.month for day in values], type=pa.int32()),
            "day": pa.array([day.day for day in values], type=pa.int32()),
            "quarter": pa.array([math.ceil(day.month / 3) for day in values], type=pa.int32()),
            "day_of_week": pa.array([day.weekday() for day in values], type=pa.int32()),
            "is_weekend": pa.array([day.weekday() >= 5 for day in values], type=pa.bool_()),
        },
        schema=_DIM_DATE_SCHEMA,
    )


def _build_dim_filing(conn: Any) -> pa.Table:
    # All key columns computed in DuckDB — eliminates 3 × 2.7M Python-level calls.
    table = _arrow(
        conn.execute(
            """
            SELECT
                (hash(accession_number) & 9223372036854775807)::BIGINT AS filing_key,
                accession_number,
                cik::BIGINT                                              AS cik,
                cik::BIGINT                                              AS company_key,
                form,
                COALESCE((hash(form) & 9223372036854775807)::BIGINT, 0) AS form_key,
                filing_date,
                (year(filing_date)*10000 + month(filing_date)*100
                 + day(filing_date))::INTEGER                            AS date_key,
                report_date,
                is_xbrl::BOOLEAN                                        AS is_xbrl,
                size::BIGINT                                             AS size
            FROM sec_company_filing
            ORDER BY filing_date, accession_number
            """
        )
    )
    return _empty(_DIM_FILING_SCHEMA) if table.num_rows == 0 else table.cast(_DIM_FILING_SCHEMA)


def _build_fact_filing_activity(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                (hash(accession_number) & 9223372036854775807)::BIGINT AS fact_key,
                cik::BIGINT                                              AS company_key,
                (hash(accession_number) & 9223372036854775807)::BIGINT AS filing_key,
                (year(filing_date)*10000 + month(filing_date)*100
                 + day(filing_date))::INTEGER                            AS date_key,
                COALESCE((hash(form) & 9223372036854775807)::BIGINT, 0) AS form_key,
                accession_number,
                cik::BIGINT                                              AS cik,
                form,
                filing_date,
                report_date,
                is_xbrl::BOOLEAN                                        AS is_xbrl
            FROM sec_company_filing
            ORDER BY filing_date, accession_number
            """
        )
    )
    return _empty(_FACT_FILING_ACTIVITY_SCHEMA) if table.num_rows == 0 else table.cast(_FACT_FILING_ACTIVITY_SCHEMA)


def _build_dim_party(conn: Any) -> pa.Table:
    dimension_rows: dict[str, dict[str, Any]] = {}
    for row in _fetch_rows(
        conn,
        """
        SELECT owner_cik AS party_cik, owner_name AS party_name
        FROM sec_ownership_reporting_owner
        """,
    ):
        natural_key = _party_natural_key(row.get("party_name"), row.get("party_cik"))
        if natural_key is None:
            continue
        dimension_rows[natural_key] = {
            "party_key": _det_key(natural_key),
            "party_natural_key": natural_key,
            "party_name": _clean_text(row.get("party_name")) or dimension_rows.get(natural_key, {}).get("party_name"),
            "party_cik": _coerce_int(row.get("party_cik")),
        }
    for row in _fetch_rows(
        conn,
        """
        SELECT cik AS party_cik, adviser_name AS party_name
        FROM sec_adv_filing
        """,
    ):
        natural_key = _party_natural_key(row.get("party_name"), row.get("party_cik"))
        if natural_key is None:
            continue
        existing = dimension_rows.get(natural_key, {})
        dimension_rows[natural_key] = {
            "party_key": _det_key(natural_key),
            "party_natural_key": natural_key,
            "party_name": existing.get("party_name") or _clean_text(row.get("party_name")),
            "party_cik": existing.get("party_cik") if existing.get("party_cik") is not None else _coerce_int(row.get("party_cik")),
        }
    records = [dimension_rows[key] for key in sorted(dimension_rows)]
    return _table_from_records(_DIM_PARTY_SCHEMA, records)


def _build_dim_security(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT f.cik AS issuer_cik, t.security_title
        FROM sec_ownership_non_derivative_txn t
        JOIN sec_company_filing f ON f.accession_number = t.accession_number
        UNION ALL
        SELECT f.cik AS issuer_cik, t.security_title
        FROM sec_ownership_derivative_txn t
        JOIN sec_company_filing f ON f.accession_number = t.accession_number
        UNION ALL
        SELECT f.cik AS issuer_cik, t.underlying_security_title AS security_title
        FROM sec_ownership_derivative_txn t
        JOIN sec_company_filing f ON f.accession_number = t.accession_number
        """
    )
    records_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        natural_key = _security_natural_key(row.get("issuer_cik"), row.get("security_title"))
        if natural_key is None:
            continue
        records_by_key[natural_key] = {
            "security_key": _det_key(natural_key),
            "security_natural_key": natural_key,
            "security_title": _clean_text(row.get("security_title")),
            "issuer_cik": _coerce_int(row.get("issuer_cik")),
        }
    records = [records_by_key[key] for key in sorted(records_by_key)]
    return _table_from_records(_DIM_SECURITY_SCHEMA, records)


def _build_dim_ownership_txn_type(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT DISTINCT transaction_code
        FROM (
            SELECT transaction_code FROM sec_ownership_non_derivative_txn
            UNION
            SELECT transaction_code FROM sec_ownership_derivative_txn
        )
        WHERE transaction_code IS NOT NULL
        ORDER BY transaction_code
        """
    )
    records = [
        {
            "ownership_txn_type_key": _det_key(str(row["transaction_code"])),
            "transaction_code": row["transaction_code"],
            "description": _TXN_CODE_DESCRIPTIONS.get(str(row["transaction_code"]), f"transaction code {row['transaction_code']}"),
        }
        for row in rows
    ]
    return _table_from_records(_DIM_OWNERSHIP_TXN_TYPE_SCHEMA, records)


def _build_dim_geography(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT state_or_country, country FROM sec_company_address
        UNION ALL
        SELECT state_or_country, country FROM sec_adv_office
        """
    )
    records_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        natural_key = _geography_natural_key(row.get("state_or_country"), row.get("country"))
        if natural_key is None:
            continue
        records_by_key[natural_key] = {
            "geography_key": _det_key(natural_key),
            "state_or_country": _clean_text(row.get("state_or_country")),
            "country": _clean_text(row.get("country")),
        }
    records = [records_by_key[key] for key in sorted(records_by_key)]
    return _table_from_records(_DIM_GEOGRAPHY_SCHEMA, records)


def _build_dim_disclosure_category(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT DISTINCT disclosure_category
        FROM sec_adv_disclosure_event
        WHERE disclosure_category IS NOT NULL
        ORDER BY disclosure_category
        """
    )
    records = [
        {
            "disclosure_category_key": _det_key(_normalized_text(row["disclosure_category"])),
            "disclosure_category": _clean_text(row["disclosure_category"]),
        }
        for row in rows
    ]
    return _table_from_records(_DIM_DISCLOSURE_CATEGORY_SCHEMA, records)


def _build_dim_private_fund(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT f.cik, p.fund_name, p.fund_type, p.jurisdiction
        FROM sec_adv_private_fund p
        LEFT JOIN sec_adv_filing f ON f.accession_number = p.accession_number
        """
    )
    records_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        natural_key = _private_fund_natural_key(
            row.get("cik"),
            row.get("fund_name"),
            row.get("fund_type"),
            row.get("jurisdiction"),
        )
        if natural_key is None:
            continue
        records_by_key[natural_key] = {
            "private_fund_key": _det_key(natural_key),
            "private_fund_natural_key": natural_key,
            "fund_name": _clean_text(row.get("fund_name")),
            "fund_type": _clean_text(row.get("fund_type")),
            "jurisdiction": _clean_text(row.get("jurisdiction")),
        }
    records = [records_by_key[key] for key in sorted(records_by_key)]
    return _table_from_records(_DIM_PRIVATE_FUND_SCHEMA, records)


def _ownership_fact_source_rows(conn: Any) -> list[dict[str, Any]]:
    return _fetch_rows(
        conn,
        """
        SELECT
            f.accession_number,
            f.cik,
            f.form,
            f.filing_date,
            o.owner_index,
            o.owner_cik,
            o.owner_name,
            t.txn_index,
            t.security_title,
            t.transaction_code,
            t.transaction_shares,
            t.transaction_price,
            t.shares_owned_after,
            t.ownership_direct_indirect,
            FALSE AS is_derivative
        FROM sec_ownership_non_derivative_txn t
        JOIN sec_company_filing f ON f.accession_number = t.accession_number
        LEFT JOIN sec_ownership_reporting_owner o
            ON o.accession_number = t.accession_number
           AND o.owner_index = t.owner_index
        UNION ALL
        SELECT
            f.accession_number,
            f.cik,
            f.form,
            f.filing_date,
            o.owner_index,
            o.owner_cik,
            o.owner_name,
            t.txn_index,
            t.security_title,
            t.transaction_code,
            t.transaction_shares,
            t.transaction_price,
            t.shares_owned_after,
            t.ownership_direct_indirect,
            TRUE AS is_derivative
        FROM sec_ownership_derivative_txn t
        JOIN sec_company_filing f ON f.accession_number = t.accession_number
        LEFT JOIN sec_ownership_reporting_owner o
            ON o.accession_number = t.accession_number
           AND o.owner_index = t.owner_index
        """
    )


def _build_fact_ownership_transaction(conn: Any) -> pa.Table:
    # All key and natural-key derivations pushed into DuckDB SQL.
    # Eliminates Python loop + 5× _det_key() calls per row across 37K ownership rows.
    table = _arrow(conn.execute("""
        WITH src AS (
            SELECT f.accession_number, f.cik::BIGINT AS cik, f.form, f.filing_date,
                   o.owner_index, o.owner_cik, o.owner_name,
                   t.txn_index, t.security_title, t.transaction_code,
                   t.transaction_shares, t.transaction_price, t.shares_owned_after,
                   t.ownership_direct_indirect, FALSE AS is_derivative
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_company_filing f ON f.accession_number = t.accession_number
            LEFT JOIN sec_ownership_reporting_owner o
                ON o.accession_number = t.accession_number AND o.owner_index = t.owner_index
            UNION ALL
            SELECT f.accession_number, f.cik::BIGINT AS cik, f.form, f.filing_date,
                   o.owner_index, o.owner_cik, o.owner_name,
                   t.txn_index, t.security_title, t.transaction_code,
                   t.transaction_shares, t.transaction_price, t.shares_owned_after,
                   t.ownership_direct_indirect, TRUE AS is_derivative
            FROM sec_ownership_derivative_txn t
            JOIN sec_company_filing f ON f.accession_number = t.accession_number
            LEFT JOIN sec_ownership_reporting_owner o
                ON o.accession_number = t.accession_number AND o.owner_index = t.owner_index
        ),
        keyed AS (
            SELECT *,
                -- party_natural_key: prefer CIK, fall back to normalized name
                CASE
                    WHEN owner_cik IS NOT NULL
                        THEN 'cik:' || CAST(CAST(owner_cik AS BIGINT) AS VARCHAR)
                    WHEN NULLIF(trim(regexp_replace(COALESCE(owner_name,''),'\s+',' ','g')),'') IS NOT NULL
                        THEN 'name:' || lower(trim(regexp_replace(owner_name,'\s+',' ','g')))
                    ELSE NULL
                END AS party_nk,
                -- security_natural_key: cik|normalized_title (NULL if no title)
                CASE
                    WHEN NULLIF(trim(regexp_replace(COALESCE(security_title,''),'\s+',' ','g')),'') IS NULL THEN NULL
                    ELSE CAST(COALESCE(cik,0) AS VARCHAR) || '|' ||
                         lower(trim(regexp_replace(security_title,'\s+',' ','g')))
                END AS security_nk,
                -- clean transaction_code
                NULLIF(trim(regexp_replace(COALESCE(transaction_code,''),'\s+',' ','g')),'') AS txn_code_clean
            FROM src
        )
        SELECT
            (hash(accession_number || '|' ||
                  COALESCE(CAST(owner_index AS VARCHAR),'None') || '|' ||
                  COALESCE(CAST(txn_index AS VARCHAR),'None') || '|' ||
                  CASE WHEN is_derivative THEN 'D' ELSE 'N' END
            ) & 9223372036854775807)::BIGINT                                        AS fact_key,
            cik                                                                      AS company_key,
            (year(filing_date)*10000 + month(filing_date)*100
             + day(filing_date))::INTEGER                                            AS date_key,
            CASE WHEN form IS NOT NULL
                THEN (hash(form) & 9223372036854775807)::BIGINT END                 AS form_key,
            CASE WHEN party_nk IS NOT NULL
                THEN (hash(party_nk) & 9223372036854775807)::BIGINT END             AS party_key,
            CASE WHEN security_nk IS NOT NULL
                THEN (hash(security_nk) & 9223372036854775807)::BIGINT END          AS security_key,
            CASE WHEN txn_code_clean IS NOT NULL
                THEN (hash(txn_code_clean) & 9223372036854775807)::BIGINT END       AS ownership_txn_type_key,
            accession_number,
            owner_index::INTEGER                                                     AS owner_index,
            txn_index::INTEGER                                                       AS txn_index,
            txn_code_clean                                                           AS transaction_code,
            TRY_CAST(transaction_shares AS DOUBLE)                                  AS transaction_shares,
            TRY_CAST(transaction_price AS DOUBLE)                                   AS transaction_price,
            TRY_CAST(shares_owned_after AS DOUBLE)                                  AS shares_owned_after,
            is_derivative::BOOLEAN                                                   AS is_derivative
        FROM keyed
        ORDER BY accession_number, owner_index, txn_index
    """))
    return _empty(_FACT_OWNERSHIP_TRANSACTION_SCHEMA) if table.num_rows == 0 else table.cast(_FACT_OWNERSHIP_TRANSACTION_SCHEMA)


def _build_fact_ownership_holding_snapshot(conn: Any) -> pa.Table:
    # Same SQL rewrite pattern as _build_fact_ownership_transaction.
    # "Last transaction per holding group" implemented with QUALIFY ROW_NUMBER()
    # instead of a Python groupby loop.
    table = _arrow(conn.execute("""
        WITH src AS (
            SELECT f.accession_number, f.cik::BIGINT AS cik, f.filing_date,
                   o.owner_index, o.owner_cik, o.owner_name,
                   t.txn_index, t.security_title,
                   t.shares_owned_after, t.ownership_direct_indirect,
                   FALSE AS is_derivative
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_company_filing f ON f.accession_number = t.accession_number
            LEFT JOIN sec_ownership_reporting_owner o
                ON o.accession_number = t.accession_number AND o.owner_index = t.owner_index
            UNION ALL
            SELECT f.accession_number, f.cik::BIGINT AS cik, f.filing_date,
                   o.owner_index, o.owner_cik, o.owner_name,
                   t.txn_index, t.security_title,
                   t.shares_owned_after, t.ownership_direct_indirect,
                   TRUE AS is_derivative
            FROM sec_ownership_derivative_txn t
            JOIN sec_company_filing f ON f.accession_number = t.accession_number
            LEFT JOIN sec_ownership_reporting_owner o
                ON o.accession_number = t.accession_number AND o.owner_index = t.owner_index
        ),
        keyed AS (
            SELECT *,
                CASE
                    WHEN owner_cik IS NOT NULL
                        THEN 'cik:' || CAST(CAST(owner_cik AS BIGINT) AS VARCHAR)
                    WHEN NULLIF(trim(regexp_replace(COALESCE(owner_name,''),'\s+',' ','g')),'') IS NOT NULL
                        THEN 'name:' || lower(trim(regexp_replace(owner_name,'\s+',' ','g')))
                    ELSE NULL
                END AS party_nk,
                CASE
                    WHEN NULLIF(trim(regexp_replace(COALESCE(security_title,''),'\s+',' ','g')),'') IS NULL THEN NULL
                    ELSE CAST(COALESCE(cik,0) AS VARCHAR) || '|' ||
                         lower(trim(regexp_replace(security_title,'\s+',' ','g')))
                END AS security_nk,
                NULLIF(trim(regexp_replace(COALESCE(ownership_direct_indirect,''),'\s+',' ','g')),'')
                    AS di_clean
            FROM src
            WHERE NULLIF(trim(regexp_replace(COALESCE(security_title,''),'\s+',' ','g')),'') IS NOT NULL
              AND shares_owned_after IS NOT NULL
              AND CAST(shares_owned_after AS VARCHAR) != ''
        )
        SELECT
            (hash(accession_number || '|' ||
                  COALESCE(CAST(owner_index AS VARCHAR),'None') || '|' ||
                  security_nk || '|' ||
                  COALESCE(di_clean,'')
            ) & 9223372036854775807)::BIGINT                                        AS fact_key,
            cik                                                                      AS company_key,
            (year(filing_date)*10000 + month(filing_date)*100
             + day(filing_date))::INTEGER                                            AS date_key,
            CASE WHEN party_nk IS NOT NULL
                THEN (hash(party_nk) & 9223372036854775807)::BIGINT END             AS party_key,
            (hash(security_nk) & 9223372036854775807)::BIGINT                       AS security_key,
            accession_number,
            owner_index::INTEGER                                                     AS owner_index,
            TRY_CAST(shares_owned_after AS DOUBLE)                                  AS shares_owned_after,
            di_clean                                                                 AS ownership_direct_indirect
        FROM keyed
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY accession_number, owner_index, security_nk, di_clean
            ORDER BY COALESCE(txn_index,0) DESC, CASE WHEN is_derivative THEN 1 ELSE 0 END DESC
        ) = 1
        ORDER BY accession_number, owner_index, security_nk, di_clean
    """))
    return _empty(_FACT_OWNERSHIP_HOLDING_SNAPSHOT_SCHEMA) if table.num_rows == 0 else table.cast(_FACT_OWNERSHIP_HOLDING_SNAPSHOT_SCHEMA)


def _build_fact_adv_office(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT
            o.accession_number,
            o.office_index,
            o.office_name,
            o.state_or_country,
            o.country,
            o.is_headquarters,
            COALESCE(f.cik, c.cik) AS cik,
            COALESCE(c.filing_date, f.effective_date) AS fact_date
        FROM sec_adv_office o
        LEFT JOIN sec_adv_filing f ON f.accession_number = o.accession_number
        LEFT JOIN sec_company_filing c ON c.accession_number = o.accession_number
        """
    )
    records = []
    for row in rows:
        geography_natural_key = _geography_natural_key(row.get("state_or_country"), row.get("country"))
        records.append(
            {
                "fact_key": _det_key(f"{row['accession_number']}|office|{row['office_index']}"),
                "company_key": _coerce_int(row.get("cik")),
                "date_key": _filing_date_to_int(row.get("fact_date")),
                "geography_key": _det_key(geography_natural_key) if geography_natural_key else None,
                "accession_number": row.get("accession_number"),
                "office_index": _coerce_int(row.get("office_index")),
                "office_name": _clean_text(row.get("office_name")),
                "is_headquarters": bool(row.get("is_headquarters")) if row.get("is_headquarters") is not None else None,
            }
        )
    records.sort(key=lambda record: (record["accession_number"] or "", record["office_index"] or 0))
    return _table_from_records(_FACT_ADV_OFFICE_SCHEMA, records)


def _build_fact_adv_disclosure(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT
            d.accession_number,
            d.event_index,
            d.disclosure_category,
            d.is_reported,
            COALESCE(f.cik, c.cik) AS cik,
            COALESCE(c.filing_date, f.effective_date) AS fact_date
        FROM sec_adv_disclosure_event d
        LEFT JOIN sec_adv_filing f ON f.accession_number = d.accession_number
        LEFT JOIN sec_company_filing c ON c.accession_number = d.accession_number
        """
    )
    records = []
    for row in rows:
        category = _clean_text(row.get("disclosure_category"))
        normalized_category = _normalized_text(category)
        records.append(
            {
                "fact_key": _det_key(f"{row['accession_number']}|disclosure|{row['event_index']}"),
                "company_key": _coerce_int(row.get("cik")),
                "date_key": _filing_date_to_int(row.get("fact_date")),
                "disclosure_category_key": _det_key(normalized_category) if normalized_category else None,
                "accession_number": row.get("accession_number"),
                "event_index": _coerce_int(row.get("event_index")),
                "is_reported": bool(row.get("is_reported")) if row.get("is_reported") is not None else None,
            }
        )
    records.sort(key=lambda record: (record["accession_number"] or "", record["event_index"] or 0))
    return _table_from_records(_FACT_ADV_DISCLOSURE_SCHEMA, records)


def _build_fact_adv_private_fund(conn: Any) -> pa.Table:
    rows = _fetch_rows(
        conn,
        """
        SELECT
            p.accession_number,
            p.fund_index,
            p.fund_name,
            p.fund_type,
            p.jurisdiction,
            p.aum_amount,
            COALESCE(f.cik, c.cik) AS cik,
            COALESCE(c.filing_date, f.effective_date) AS fact_date
        FROM sec_adv_private_fund p
        LEFT JOIN sec_adv_filing f ON f.accession_number = p.accession_number
        LEFT JOIN sec_company_filing c ON c.accession_number = p.accession_number
        """
    )
    records = []
    for row in rows:
        fund_natural_key = _private_fund_natural_key(
            row.get("cik"),
            row.get("fund_name"),
            row.get("fund_type"),
            row.get("jurisdiction"),
        )
        records.append(
            {
                "fact_key": _det_key(f"{row['accession_number']}|fund|{row['fund_index']}"),
                "company_key": _coerce_int(row.get("cik")),
                "date_key": _filing_date_to_int(row.get("fact_date")),
                "private_fund_key": _det_key(fund_natural_key) if fund_natural_key else None,
                "accession_number": row.get("accession_number"),
                "fund_index": _coerce_int(row.get("fund_index")),
                "aum_amount": _coerce_float(row.get("aum_amount")),
            }
        )
    records.sort(key=lambda record: (record["accession_number"] or "", record["fund_index"] or 0))
    return _table_from_records(_FACT_ADV_PRIVATE_FUND_SCHEMA, records)


# ── Branch B Fundamentals builders — PR-1 ────────────────────────────────
# Passthrough builders SELECT columns in PyArrow schema order (Q1-C, Q2-A).
# Column order matters for PyArrow's table.cast() — silver-table column order
# differs from our PK-first ordering, so an explicit SELECT list is required.

def _build_sec_financial_fact(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                cik::BIGINT          AS cik,
                accession_number,
                concept,
                fiscal_period,
                segment,
                fiscal_year::INTEGER AS fiscal_year,
                period_end,
                period_start,
                form_type,
                value,
                unit,
                decimals::INTEGER    AS decimals,
                parser_version,
                ingested_at
            FROM sec_financial_fact
            ORDER BY cik, accession_number, concept, fiscal_period, segment, period_end, period_start
            """
        )
    )
    return _empty(_SEC_FINANCIAL_FACT_SCHEMA) if table.num_rows == 0 else table.cast(_SEC_FINANCIAL_FACT_SCHEMA)


def _build_sec_thirteenf_holding(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                cik::BIGINT          AS cik,
                accession_number,
                holding_index::BIGINT AS holding_index,
                period_of_report,
                cusip,
                issuer_name,
                security_title,
                shares_held,
                market_value,
                security_class,
                put_call,
                discretion_type,
                voting_auth_sole,
                voting_auth_shared,
                voting_auth_none,
                parser_version,
                ingested_at
            FROM sec_thirteenf_holding
            ORDER BY cik, accession_number, holding_index
            """
        )
    )
    return _empty(_SEC_THIRTEENF_HOLDING_SCHEMA) if table.num_rows == 0 else table.cast(_SEC_THIRTEENF_HOLDING_SCHEMA)


def _build_sec_financial_derived(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                cik::BIGINT          AS cik,
                accession_number,
                fiscal_period,
                fiscal_year::INTEGER AS fiscal_year,
                period_end,
                form_type,
                revenue,
                gross_profit,
                ebitda,
                ebit,
                net_income,
                eps_diluted,
                total_assets,
                total_liabilities,
                total_equity,
                cash_and_equivalents,
                total_debt,
                operating_cash_flow,
                capex,
                free_cash_flow,
                gross_margin,
                ebitda_margin,
                net_margin,
                roic,
                roe,
                roa,
                parser_version,
                ingested_at
            FROM sec_financial_derived
            ORDER BY cik, accession_number, fiscal_period
            """
        )
    )
    return _empty(_SEC_FINANCIAL_DERIVED_SCHEMA) if table.num_rows == 0 else table.cast(_SEC_FINANCIAL_DERIVED_SCHEMA)


# Dimensional builders (Q3-D): generate fact_key + dim FKs.  The hash + mask
# pattern matches _build_fact_filing_activity (line 452-474) — DuckDB hash()
# is deterministic, so MERGE is idempotent across re-runs.

def _build_fact_earnings_release(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                (hash(accession_number) & 9223372036854775807)::BIGINT AS fact_key,
                cik::BIGINT                                            AS company_key,
                (year(filing_date)*10000 + month(filing_date)*100
                 + day(filing_date))::INTEGER                          AS filing_date_key,
                CASE
                    WHEN period_end IS NULL THEN NULL
                    ELSE (year(period_end)*10000 + month(period_end)*100
                          + day(period_end))::INTEGER
                END                                                    AS period_end_date_key,
                (hash('8-K') & 9223372036854775807)::BIGINT            AS form_key,
                accession_number,
                cik::BIGINT                                            AS cik,
                filing_date,
                fiscal_year::INTEGER                                   AS fiscal_year,
                fiscal_quarter::INTEGER                                AS fiscal_quarter,
                period_end,
                revenue_gaap,
                net_income_gaap,
                eps_gaap_diluted,
                has_non_gaap,
                has_guidance,
                parser_version,
                ingested_at
            FROM sec_earnings_release
            ORDER BY cik, accession_number
            """
        )
    )
    return _empty(_FACT_EARNINGS_RELEASE_SCHEMA) if table.num_rows == 0 else table.cast(_FACT_EARNINGS_RELEASE_SCHEMA)


def _build_fact_executive_record(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                (hash(accession_number, exec_name) & 9223372036854775807)::BIGINT AS fact_key,
                cik::BIGINT                                                       AS company_key,
                (fiscal_year*10000 + 1231)::INTEGER                               AS fiscal_year_date_key,
                accession_number,
                cik::BIGINT                                                       AS cik,
                fiscal_year::INTEGER                                              AS fiscal_year,
                exec_name,
                exec_role,
                total_comp,
                base_salary,
                bonus,
                stock_awards,
                option_awards,
                non_equity_incentive,
                parser_version,
                ingested_at
            FROM sec_executive_record
            ORDER BY cik, accession_number, exec_name
            """
        )
    )
    return _empty(_FACT_EXECUTIVE_RECORD_SCHEMA) if table.num_rows == 0 else table.cast(_FACT_EXECUTIVE_RECORD_SCHEMA)


def _build_fact_accounting_flag(conn: Any) -> pa.Table:
    table = _arrow(
        conn.execute(
            """
            SELECT
                (hash(accession_number) & 9223372036854775807)::BIGINT AS fact_key,
                cik::BIGINT                                            AS company_key,
                (fiscal_year*10000 + 1231)::INTEGER                    AS fiscal_year_date_key,
                COALESCE(
                    (hash(form_type) & 9223372036854775807)::BIGINT,
                    (hash('10-K') & 9223372036854775807)::BIGINT
                )                                                      AS form_key,
                accession_number,
                cik::BIGINT                                            AS cik,
                fiscal_year::INTEGER                                   AS fiscal_year,
                period_end,
                form_type,
                auditor_name,
                auditor_pcaob_id,
                auditor_location,
                icfr_attestation,
                auditor_changed,
                beneish_m_score,
                altman_z_score,
                piotroski_f_score::INTEGER                             AS piotroski_f_score,
                parser_version,
                ingested_at
            FROM sec_accounting_flag
            ORDER BY cik, accession_number
            """
        )
    )
    return _empty(_FACT_ACCOUNTING_FLAG_SCHEMA) if table.num_rows == 0 else table.cast(_FACT_ACCOUNTING_FLAG_SCHEMA)


def build_gold(db: Any) -> dict[str, pa.Table]:
    # Accepts SilverDatabase or ShardedSilverReader via duck typing (._conn attribute).
    import json
    import sys
    from datetime import datetime, timezone

    def _timed(name: str, fn):
        t0 = datetime.now(timezone.utc)
        print(json.dumps({"event": "gold_table_started", "table": name,
                          "emitted_at": t0.isoformat().replace("+00:00", "Z")}),
              file=sys.stderr, flush=True)
        result = fn()
        duration = (datetime.now(timezone.utc) - t0).total_seconds()
        print(json.dumps({"event": "gold_table_completed", "table": name,
                          "rows": len(result), "duration_seconds": round(duration, 2),
                          "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}),
              file=sys.stderr, flush=True)
        return result

    conn = get_connection(db)
    return {
        "dim_company":                    _timed("dim_company",                    lambda: _build_dim_company(conn)),
        "dim_form":                       _timed("dim_form",                       lambda: _build_dim_form(conn)),
        "dim_date":                       _timed("dim_date",                       lambda: _build_dim_date(conn)),
        "dim_filing":                     _timed("dim_filing",                     lambda: _build_dim_filing(conn)),
        "fact_filing_activity":           _timed("fact_filing_activity",           lambda: _build_fact_filing_activity(conn)),
        "dim_party":                      _timed("dim_party",                      lambda: _build_dim_party(conn)),
        "dim_security":                   _timed("dim_security",                   lambda: _build_dim_security(conn)),
        "dim_ownership_txn_type":         _timed("dim_ownership_txn_type",         lambda: _build_dim_ownership_txn_type(conn)),
        "dim_geography":                  _timed("dim_geography",                  lambda: _build_dim_geography(conn)),
        "dim_disclosure_category":        _timed("dim_disclosure_category",        lambda: _build_dim_disclosure_category(conn)),
        "dim_private_fund":               _timed("dim_private_fund",               lambda: _build_dim_private_fund(conn)),
        "fact_ownership_transaction":     _timed("fact_ownership_transaction",     lambda: _build_fact_ownership_transaction(conn)),
        "fact_ownership_holding_snapshot":_timed("fact_ownership_holding_snapshot",lambda: _build_fact_ownership_holding_snapshot(conn)),
        "fact_adv_office":                _timed("fact_adv_office",                lambda: _build_fact_adv_office(conn)),
        "fact_adv_disclosure":            _timed("fact_adv_disclosure",            lambda: _build_fact_adv_disclosure(conn)),
        "fact_adv_private_fund":          _timed("fact_adv_private_fund",          lambda: _build_fact_adv_private_fund(conn)),
        # Branch B fundamentals — PR-1 (Q1-C hybrid passthrough+dimensional).
        # The dict KEY here is informational; the actual Snowflake target table
        # name comes from SNOWFLAKE_EXPORT_TABLES (run_manifest_builder.py),
        # which is keyed UPPER-snake by Snowflake table name.
        "sec_financial_fact":             _timed("sec_financial_fact",             lambda: _build_sec_financial_fact(conn)),
        "sec_thirteenf_holding":          _timed("sec_thirteenf_holding",          lambda: _build_sec_thirteenf_holding(conn)),
        "sec_financial_derived":          _timed("sec_financial_derived",          lambda: _build_sec_financial_derived(conn)),
        "fact_earnings_release":          _timed("fact_earnings_release",          lambda: _build_fact_earnings_release(conn)),
        "fact_executive_record":          _timed("fact_executive_record",          lambda: _build_fact_executive_record(conn)),
        "fact_accounting_flag":           _timed("fact_accounting_flag",           lambda: _build_fact_accounting_flag(conn)),
    }


def _write_parquet(table: pa.Table, storage_root: Any, relative_path: str) -> None:
    buffer = pa.BufferOutputStream()
    pq.write_table(table, buffer)
    storage_root.write_bytes(relative_path, buffer.getvalue().to_pybytes())


def write_gold_to_storage(tables: dict[str, pa.Table], storage_root: Any, run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    capture_specs = default_capture_spec_factory()
    for table_name, table in tables.items():
        output_spec = capture_specs.gold_table_output(table_name, run_id)
        _write_parquet(table, storage_root, output_spec.relative_path)
        counts[table_name] = table.num_rows
    return counts


def build_ticker_reference_table(
    universe_rows: list[dict[str, Any]], sync_run_id: str
) -> pa.Table:
    """Project seed-universe rows into the TICKER_REFERENCE gold schema."""
    records: list[dict[str, Any]] = []
    for row in universe_rows:
        cik = row.get("cik")
        ticker = row.get("ticker")
        if cik is None or not ticker:
            continue
        records.append(
            {
                "cik": int(cik),
                "ticker": str(ticker),
                "exchange": row.get("exchange"),
                "last_sync_run_id": sync_run_id,
            }
        )
    return _table_from_records(_DIM_TICKER_REFERENCE_SCHEMA, records)
