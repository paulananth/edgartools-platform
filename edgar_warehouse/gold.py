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

from edgar_warehouse.silver import SilverDatabase
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


def _empty(schema: pa.Schema) -> pa.Table:
    return pa.table({field.name: pa.array([], type=field.type) for field in schema}, schema=schema)


def _arrow(result: Any) -> pa.Table:
    table = result.arrow()
    if hasattr(table, "read_all"):
        return table.read_all()
    return table


def _fetch_rows(conn: Any, query: str) -> list[dict[str, Any]]:
    try:
        result = conn.execute(query).fetchall()
    except Exception:
        return []
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
    try:
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
    except Exception:
        return _empty(_DIM_COMPANY_SCHEMA)
    return _empty(_DIM_COMPANY_SCHEMA) if table.num_rows == 0 else table.cast(_DIM_COMPANY_SCHEMA)


def _build_dim_form(conn: Any) -> pa.Table:
    try:
        base = _arrow(conn.execute("SELECT DISTINCT form FROM sec_company_filing WHERE form IS NOT NULL ORDER BY form"))
    except Exception:
        return _empty(_DIM_FORM_SCHEMA)
    forms = base.column("form").to_pylist() if base.num_rows else []
    return pa.table(
        {
            "form_key": pa.array([_det_key(form) for form in forms], type=pa.int64()),
            "form": pa.array(forms, type=pa.string()),
            "form_family": pa.array([_form_family(form) for form in forms], type=pa.string()),
        },
        schema=_DIM_FORM_SCHEMA,
    )


def _build_dim_date(conn: Any) -> pa.Table:
    try:
        row = conn.execute("SELECT MIN(filing_date), MAX(filing_date) FROM sec_company_filing").fetchone()
    except Exception:
        row = None
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
    try:
        table = _arrow(
            conn.execute(
                """
                SELECT accession_number, cik, form, filing_date, report_date, is_xbrl, size
                FROM sec_company_filing
                ORDER BY filing_date, accession_number
                """
            )
        )
    except Exception:
        return _empty(_DIM_FILING_SCHEMA)
    if table.num_rows == 0:
        return _empty(_DIM_FILING_SCHEMA)
    accessions = table.column("accession_number").to_pylist()
    ciks = table.column("cik").to_pylist()
    forms = table.column("form").to_pylist()
    filing_dates = table.column("filing_date").to_pylist()
    report_dates = table.column("report_date").to_pylist()
    return pa.table(
        {
            "filing_key": pa.array([_det_key(accession) for accession in accessions], type=pa.int64()),
            "accession_number": pa.array(accessions, type=pa.string()),
            "cik": pa.array(ciks, type=pa.int64()),
            "company_key": pa.array(ciks, type=pa.int64()),
            "form": pa.array(forms, type=pa.string()),
            "form_key": pa.array([_det_key(form) if form else 0 for form in forms], type=pa.int64()),
            "filing_date": pa.array(filing_dates, type=pa.date32()),
            "date_key": pa.array([_filing_date_to_int(item) for item in filing_dates], type=pa.int32()),
            "report_date": pa.array(report_dates, type=pa.date32()),
            "is_xbrl": table.column("is_xbrl").cast(pa.bool_()),
            "size": table.column("size").cast(pa.int64()),
        },
        schema=_DIM_FILING_SCHEMA,
    )


def _build_fact_filing_activity(conn: Any) -> pa.Table:
    try:
        table = _arrow(
            conn.execute(
                """
                SELECT accession_number, cik, form, filing_date, report_date, is_xbrl
                FROM sec_company_filing
                ORDER BY filing_date, accession_number
                """
            )
        )
    except Exception:
        return _empty(_FACT_FILING_ACTIVITY_SCHEMA)
    if table.num_rows == 0:
        return _empty(_FACT_FILING_ACTIVITY_SCHEMA)
    accessions = table.column("accession_number").to_pylist()
    ciks = table.column("cik").to_pylist()
    forms = table.column("form").to_pylist()
    filing_dates = table.column("filing_date").to_pylist()
    report_dates = table.column("report_date").to_pylist()
    filing_keys = [_det_key(accession) for accession in accessions]
    return pa.table(
        {
            "fact_key": pa.array(filing_keys, type=pa.int64()),
            "company_key": pa.array(ciks, type=pa.int64()),
            "filing_key": pa.array(filing_keys, type=pa.int64()),
            "date_key": pa.array([_filing_date_to_int(item) for item in filing_dates], type=pa.int32()),
            "form_key": pa.array([_det_key(form) if form else 0 for form in forms], type=pa.int64()),
            "accession_number": pa.array(accessions, type=pa.string()),
            "cik": pa.array(ciks, type=pa.int64()),
            "form": pa.array(forms, type=pa.string()),
            "filing_date": pa.array(filing_dates, type=pa.date32()),
            "report_date": pa.array(report_dates, type=pa.date32()),
            "is_xbrl": table.column("is_xbrl").cast(pa.bool_()),
        },
        schema=_FACT_FILING_ACTIVITY_SCHEMA,
    )


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
    records: list[dict[str, Any]] = []
    for row in _ownership_fact_source_rows(conn):
        party_natural_key = _party_natural_key(row.get("owner_name"), row.get("owner_cik"))
        security_natural_key = _security_natural_key(row.get("cik"), row.get("security_title"))
        transaction_code = _clean_text(row.get("transaction_code"))
        fact_key_value = _det_key(
            f"{row['accession_number']}|{row['owner_index']}|{row['txn_index']}|{'D' if row.get('is_derivative') else 'N'}"
        )
        records.append(
            {
                "fact_key": fact_key_value,
                "company_key": _coerce_int(row.get("cik")),
                "date_key": _filing_date_to_int(row.get("filing_date")),
                "form_key": _det_key(str(row["form"])) if row.get("form") else None,
                "party_key": _det_key(party_natural_key) if party_natural_key else None,
                "security_key": _det_key(security_natural_key) if security_natural_key else None,
                "ownership_txn_type_key": _det_key(transaction_code) if transaction_code else None,
                "accession_number": row.get("accession_number"),
                "owner_index": _coerce_int(row.get("owner_index")),
                "txn_index": _coerce_int(row.get("txn_index")),
                "transaction_code": transaction_code,
                "transaction_shares": _coerce_float(row.get("transaction_shares")),
                "transaction_price": _coerce_float(row.get("transaction_price")),
                "shares_owned_after": _coerce_float(row.get("shares_owned_after")),
                "is_derivative": bool(row.get("is_derivative")) if row.get("is_derivative") is not None else None,
            }
        )
    records.sort(key=lambda record: (record["accession_number"] or "", record["owner_index"] or 0, record["txn_index"] or 0))
    return _table_from_records(_FACT_OWNERSHIP_TRANSACTION_SCHEMA, records)


def _build_fact_ownership_holding_snapshot(conn: Any) -> pa.Table:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in _ownership_fact_source_rows(conn):
        party_natural_key = _party_natural_key(row.get("owner_name"), row.get("owner_cik"))
        security_natural_key = _security_natural_key(row.get("cik"), row.get("security_title"))
        if security_natural_key is None:
            continue
        if row.get("shares_owned_after") in (None, ""):
            continue
        group_key = (
            row.get("accession_number"),
            _coerce_int(row.get("owner_index")),
            security_natural_key,
            _clean_text(row.get("ownership_direct_indirect")),
        )
        current = grouped.get(group_key)
        row_rank = (_coerce_int(row.get("txn_index")) or 0, 1 if row.get("is_derivative") else 0)
        current_rank = ((current or {}).get("_txn_rank") or (-1, -1))
        if current is not None and row_rank <= current_rank:
            continue
        grouped[group_key] = {
            "_txn_rank": row_rank,
            "fact_key": _det_key(
                f"{row['accession_number']}|{row.get('owner_index')}|{security_natural_key}|{_clean_text(row.get('ownership_direct_indirect')) or ''}"
            ),
            "company_key": _coerce_int(row.get("cik")),
            "date_key": _filing_date_to_int(row.get("filing_date")),
            "party_key": _det_key(party_natural_key) if party_natural_key else None,
            "security_key": _det_key(security_natural_key),
            "accession_number": row.get("accession_number"),
            "owner_index": _coerce_int(row.get("owner_index")),
            "shares_owned_after": _coerce_float(row.get("shares_owned_after")),
            "ownership_direct_indirect": _clean_text(row.get("ownership_direct_indirect")),
        }
    records = [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for _, record in sorted(grouped.items(), key=lambda item: ((item[0][0] or ""), item[0][1] or 0, item[0][2], item[0][3] or ""))
    ]
    return _table_from_records(_FACT_OWNERSHIP_HOLDING_SNAPSHOT_SCHEMA, records)


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


def build_gold(db: SilverDatabase) -> dict[str, pa.Table]:
    conn = get_connection(db)
    return {
        "dim_company": _build_dim_company(conn),
        "dim_form": _build_dim_form(conn),
        "dim_date": _build_dim_date(conn),
        "dim_filing": _build_dim_filing(conn),
        "fact_filing_activity": _build_fact_filing_activity(conn),
        "dim_party": _build_dim_party(conn),
        "dim_security": _build_dim_security(conn),
        "dim_ownership_txn_type": _build_dim_ownership_txn_type(conn),
        "dim_geography": _build_dim_geography(conn),
        "dim_disclosure_category": _build_dim_disclosure_category(conn),
        "dim_private_fund": _build_dim_private_fund(conn),
        "fact_ownership_transaction": _build_fact_ownership_transaction(conn),
        "fact_ownership_holding_snapshot": _build_fact_ownership_holding_snapshot(conn),
        "fact_adv_office": _build_fact_adv_office(conn),
        "fact_adv_disclosure": _build_fact_adv_disclosure(conn),
        "fact_adv_private_fund": _build_fact_adv_private_fund(conn),
    }


def _write_parquet(table: pa.Table, storage_root: Any, relative_path: str) -> None:
    buffer = pa.BufferOutputStream()
    pq.write_table(table, buffer)
    storage_root.write_bytes(relative_path, buffer.getvalue().to_pybytes())


def write_gold_to_storage(tables: dict[str, pa.Table], storage_root: Any, run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name, table in tables.items():
        relative_path = f"gold/{table_name}/run_id={run_id}/{table_name}.parquet"
        _write_parquet(table, storage_root, relative_path)
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


def write_ticker_reference_to_snowflake_export(
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> int:
    relative_path = (
        f"ticker_reference/business_date={business_date}/run_id={run_id}/ticker_reference.parquet"
    )
    _write_parquet(table, export_root, relative_path)
    return table.num_rows


def write_gold_to_snowflake_export(
    tables: dict[str, pa.Table],
    export_root: Any,
    run_id: str,
    business_date: str,
) -> dict[str, int]:
    export_map = {
        "company": "dim_company",
        "filing_activity": "fact_filing_activity",
        "ownership_activity": "fact_ownership_transaction",
        "ownership_holdings": "fact_ownership_holding_snapshot",
        "adviser_offices": "fact_adv_office",
        "adviser_disclosures": "fact_adv_disclosure",
        "private_funds": "fact_adv_private_fund",
        "filing_detail": "dim_filing",
    }
    counts: dict[str, int] = {}
    for export_name, source_name in export_map.items():
        table = tables.get(source_name)
        if table is None:
            continue
        relative_path = f"{export_name}/business_date={business_date}/run_id={run_id}/{export_name}.parquet"
        _write_parquet(table, export_root, relative_path)
        counts[export_name] = table.num_rows
    return counts
