"""Adviser field schema for MDM resolution.

`AdviserResolver`, the original per-row resolver class this module used to
define, was deleted (mdm-resolver-skip-unchanged map, Ticket 03,
2026-08-21): `run_advisers()` has resolved advisers via
`edgar_warehouse.mdm.adv_bulk.resolve_advisers_bulk`'s batched rewrite for
some time -- one-row-at-a-time resolution against Postgres doesn't scale to
ADV's hundreds of thousands of historical filing rows (see `adv_bulk.py`'s
module docstring). `AdviserResolver.resolve_one` had zero callers left in
production or in the test suite; confirmed via a repo-wide audit before
deletion. `ADVISER_FIELDS` is the one piece of the original module still
live -- `adv_bulk.py` imports it directly to know which fields to stage.
"""
from __future__ import annotations

ADVISER_FIELDS = [
    "canonical_name",
    "cik",
    "crd_number",
    "sec_file_number",
    "adviser_type",
    "hq_city",
    "hq_state",
    "aum_total",
    "fund_count",
]
