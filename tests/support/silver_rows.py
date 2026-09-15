"""Test helper for the landing-only silver writers.

Every silver writer records its rows to a `LandingExportBuffer`
(silver-merge-engine-migration); `open_landing_db` returns a
`SilverLandingStore` with one attached, readable back as `db.landing_export`.
"""

from __future__ import annotations

from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_landing_store import SilverLandingStore


def open_landing_db() -> SilverLandingStore:
    return SilverLandingStore(landing_export=LandingExportBuffer())
