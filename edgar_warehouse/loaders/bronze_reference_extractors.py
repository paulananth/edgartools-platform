"""Loaders for SEC reference datasets."""

from __future__ import annotations

from typing import Any


def seed_universe_loader(
    payload: dict[str, Any],
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
) -> list[dict[str, Any]]:
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
                    "exchange": str(item["exchange"]) if item.get("exchange") else None,
                    "sync_run_id": sync_run_id,
                    "raw_object_id": raw_object_id,
                    "load_mode": load_mode,
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
                "exchange": str(entry["exchange"]) if entry.get("exchange") else None,
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "load_mode": load_mode,
            }
        )
    return rows
