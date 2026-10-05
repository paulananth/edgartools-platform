"""Historical finite-audit oracle, copied before runtime parser retirement.

Source: silver_landing_store.py at e76fb929. Never imported by shipped modules.
"""
from typing import Any

def parse_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse company_tickers_exchange/company_tickers style payloads into rows."""
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return rows

    fields = payload.get("fields")
    data = payload.get("data")
    if isinstance(fields, list) and isinstance(data, list):
        field_names = [str(field) for field in fields]
        for record in data:
            if not isinstance(record, list):
                continue
            item = dict(zip(field_names, record))
            cik = item.get("cik") or item.get("cik_str")
            ticker = item.get("ticker")
            if cik is None or not ticker:
                continue
            rows.append(
                {
                    "cik": int(cik),
                    "ticker": str(ticker),
                    "exchange": str(item.get("exchange")) if item.get("exchange") else None,
                }
            )
        return rows

    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        cik = entry.get("cik_str")
        ticker = entry.get("ticker", "")
        if cik is None:
            continue
        rows.append(
            {
                "cik": int(cik),
                "ticker": str(ticker),
                "exchange": str(entry.get("exchange")) if entry.get("exchange") else None,
            }
        )
    return rows
