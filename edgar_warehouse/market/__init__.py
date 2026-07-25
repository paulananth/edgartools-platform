"""Market data utilities for edgartools-platform.

Optional dependency group: ``pip install edgartools-platform[market]``
(or ``uv sync --extra market``).

Modules
-------
- ``price_provider`` — Yahoo / FRED / Damodaran facade (``PriceProvider``)
- ``wacc`` — CAPM WACC from gold debt/tax + market Ke inputs
- ``eod_join`` — ERDP-07 Explore join helpers (CIK→ticker, EOD snapshot, EV)

**Grade:** all market outputs are **Explore-only**.  Do not inject into pure-SEC
Decision Features / ``subject_features`` (ADR 0001 / ERDP-06).
"""

from edgar_warehouse.market.eod_join import (
    SOURCE_SYSTEM_YAHOO,
    EodSnapshot,
    batch_eod_snapshots,
    enterprise_value,
    eod_snapshot,
    eod_snapshot_for_cik,
    normalize_cik,
    pick_primary_ticker,
)
from edgar_warehouse.market.price_provider import PriceProvider
from edgar_warehouse.market.wacc import WaccInputs, WaccResult, compute_wacc

__all__ = [
    "SOURCE_SYSTEM_YAHOO",
    "EodSnapshot",
    "PriceProvider",
    "WaccInputs",
    "WaccResult",
    "batch_eod_snapshots",
    "compute_wacc",
    "enterprise_value",
    "eod_snapshot",
    "eod_snapshot_for_cik",
    "normalize_cik",
    "pick_primary_ticker",
]
