"""Frozen Company preparation oracle from main 67e24723; test-only.

Only the Name Census evidence a Company record carries survives: the landed
preparation it belonged to was retired with `company_source.py` (Issue 20 L4)."""
from __future__ import annotations

from edgar_warehouse.mdm.clean.name_census import entry as census_entry


def _census_evidence(census: dict, row: dict, census_hash: str) -> dict | None:
    """What the census says of one SEC record: its name's entry and, when
    the census ran the cascade (ticket 21), the answer for its CIK. Both are
    one pinned document, so the record carries them as one value."""
    from edgar_warehouse.mdm.clean import cascade

    found = census_entry(census, row["entity_name"], census_digest=census_hash)
    if "cascade" not in census:
        return found
    answer = cascade.entry(census, f"{int(row['cik']):010d}", census_digest=census_hash)
    if answer is None:
        return found  # no answer for this CIK: the record is as before
    return {**(found or {}), "cascade": answer}
