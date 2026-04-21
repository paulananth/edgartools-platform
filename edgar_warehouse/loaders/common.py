"""Shared loader helpers."""

from __future__ import annotations

from datetime import date
from typing import Any


def parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def safe_str(values: list, idx: int) -> str | None:
    if idx < len(values):
        value = values[idx]
        return str(value) if value is not None and value != "" else None
    return None


def safe_int(values: list, idx: int) -> int | None:
    if idx < len(values):
        value = values[idx]
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None
    return None
