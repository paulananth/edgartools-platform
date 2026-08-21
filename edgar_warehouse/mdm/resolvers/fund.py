"""Fund field schema for MDM resolution.

`FundResolver`, the original per-row resolver class this module used to
define, was deleted (mdm-resolver-skip-unchanged map, Ticket 03,
2026-08-21): `run_funds()` has resolved private funds via
`edgar_warehouse.mdm.adv_bulk.resolve_funds_bulk`'s batched rewrite for
some time, the same rewrite that superseded `AdviserResolver` (see
`edgar_warehouse/mdm/resolvers/adviser.py`'s module docstring for the
shared rationale). `FundResolver.resolve_one` had zero callers left in
production or in the test suite; confirmed via a repo-wide audit before
deletion. `FUND_FIELDS` is the one piece of the original module still
live -- `adv_bulk.py` imports it directly to know which fields to stage.
"""
from __future__ import annotations

FUND_FIELDS = ["canonical_name", "fund_type", "jurisdiction", "aum_amount", "aum_as_of_date"]
