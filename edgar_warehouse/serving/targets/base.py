"""Serving target contracts for gold export delivery."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ServingTarget(Protocol):
    """Provider-neutral interface for writing gold outputs to a serving target."""

    provider_name: str

    def write_gold(
        self,
        tables: dict[str, Any],
        export_root: Any,
        *,
        run_id: str,
        business_date: str,
    ) -> dict[str, int]:
        """Write gold tables and return exported row counts keyed by serving table path."""

    def write_ticker_reference(
        self,
        table: Any,
        export_root: Any,
        *,
        run_id: str,
        business_date: str,
    ) -> int:
        """Write ticker reference rows and return the exported row count."""
