"""Compatibility shim for the warehouse silver-store public surface."""

from __future__ import annotations

from edgar_warehouse.silver_store import SilverDatabase, _parse_company_ticker_rows

__all__ = ["SilverDatabase", "_parse_company_ticker_rows"]
