"""Stable digest primitives for cross-store (DuckDB vs. Snowflake) row
comparison.

Deliberately not reused from ``edgar_warehouse/mdm/resolvers/base.py``'s
``content_hash`` (that module pulls in ``mdm.database``/``mdm.match``/
``mdm.rules``/``mdm.survivorship`` at import time -- heavy, MDM-specific
dependencies this general reconciliation tool has no other reason to carry)
or from ``edgar_warehouse/reconcile.py``'s ``_hash_value``/``_normalize_scalar``
(private to that module's own per-CIK SEC-live-refetch comparison shape).
Both follow the same proven pattern this module also uses: normalize types,
``json.dumps(..., sort_keys=True, default=str)``, SHA-256. A future pass
could extract one shared primitive all three converge on (noted for
whoever next touches this area) -- not done here to avoid widening this
ticket's diff into modules it doesn't otherwise need to change.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def normalize_scalar(value: Any) -> Any:
    """Collapse cross-store representation differences that are not real
    content differences: datetime-like objects to ISO 8601, Decimal/other
    numeric wrappers pass through to json.dumps's ``default=str`` fallback.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def normalize_row(row: dict[str, Any], *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    return {
        key: normalize_scalar(value)
        for key, value in row.items()
        if key.lower() not in exclude
    }


def sha256_of(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sort_key(value: Any) -> tuple[bool, str]:
    """Total ordering across mixed/None values for sort purposes only --
    never used for the digest payload itself, so collapsing everything to
    its string form here does not affect content-equality sensitivity.
    """
    return (value is None, "" if value is None else str(value))


def sorted_key_set_digest(keys: list[tuple[Any, ...]]) -> str:
    """SHA-256 over the sorted set of key-tuples -- proves the same set of
    rows exists, independent of any column content.
    """
    normalized = [[normalize_scalar(v) for v in key] for key in keys]
    normalized.sort(key=lambda key: [_sort_key(v) for v in key])
    return sha256_of(normalized)


def sorted_semantic_row_digest(
    rows: list[dict[str, Any]],
    *,
    key_columns: tuple[str, ...],
    exclude_columns: frozenset[str],
) -> str:
    """SHA-256 over rows normalized and sorted by their declared key --
    order-independent, column-set-independent (columns are named in each
    row's dict, so a differently-ordered SELECT still hashes identically).
    """
    exclude = frozenset(c.lower() for c in exclude_columns)
    normalized_rows = [normalize_row(row, exclude=exclude) for row in rows]
    normalized_rows.sort(key=lambda row: [_sort_key(row.get(col)) for col in key_columns])
    return sha256_of(normalized_rows)
