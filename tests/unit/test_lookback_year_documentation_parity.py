"""Proves docs/data-architecture.md's documented lookback-year defaults match
the real code constants, so a future change to any of these defaults can't
silently leave the documentation wrong.

Resolves .scratch/fundamentals-lookback-years/spec.md's Seam 2 testing
decision. Mirrors tests/architecture/test_task_profile_source_of_truth.py's
ethos: prove against the real thing, never a re-implementation -- every
value below is imported from the module that actually enforces it, then
compared against a small, explicit "documented defaults" mapping living in
this file, not scraped from the markdown itself.
"""

from __future__ import annotations

import inspect

from edgar_warehouse.application import adv_bulk_fetch
from edgar_warehouse.application import warehouse_orchestrator as orch

# What docs/data-architecture.md's "Artifact Loader Date-Range Reference" and
# per-category tables document today. Update this mapping in the same commit
# that changes any of these defaults in the doc.
DOCUMENTED_LOOKBACK_YEAR_DEFAULTS = {
    "ownership_lookback_years": 2,
    "item_502_lookback_years": 2,
    "filing_lookback_years": 0,
    "fundamentals_lookback_years": 2,
}

# What docs/data-architecture.md documents for fetch-adv-bulk's rolling
# window ("Rolling 13 months").
DOCUMENTED_ADV_BULK_WINDOW_MONTHS = 13


def test_documented_lookback_year_defaults_match_code_constants() -> None:
    real = {
        "ownership_lookback_years": orch.DEFAULT_OWNERSHIP_LOOKBACK_YEARS,
        "item_502_lookback_years": orch.DEFAULT_ITEM_502_LOOKBACK_YEARS,
        "filing_lookback_years": orch.DEFAULT_FILING_LOOKBACK_YEARS,
        "fundamentals_lookback_years": orch.DEFAULT_FUNDAMENTALS_LOOKBACK_YEARS,
    }
    assert real == DOCUMENTED_LOOKBACK_YEAR_DEFAULTS


def test_documented_fundamentals_family_overrides_fall_back_to_shared_default() -> None:
    # Each per-family resolver, called with nothing set anywhere, must
    # resolve to the documented shared default -- not an independent value
    # that happens to match today by coincidence.
    resolvers = (
        orch._resolve_item_202_lookback_years,
        orch._resolve_proxy_lookback_years,
        orch._resolve_thirteenf_lookback_years,
        orch._resolve_adv_lookback_years,
    )
    for resolve in resolvers:
        assert resolve() == DOCUMENTED_LOOKBACK_YEAR_DEFAULTS["fundamentals_lookback_years"]


def test_documented_adv_bulk_rolling_window_matches_code_default() -> None:
    default = inspect.signature(adv_bulk_fetch.rolling_window_periods).parameters[
        "window_months"
    ].default
    assert default == DOCUMENTED_ADV_BULK_WINDOW_MONTHS
