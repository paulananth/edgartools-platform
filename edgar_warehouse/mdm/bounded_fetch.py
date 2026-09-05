"""Shared growing-window LIMIT helper for bounded MDM source queries.

Extracted from `MDMPipeline._bounded_relationship_sql` (fundamentals-daily-
integration map, Ticket 06) so `adv_bulk.py`'s free functions can reuse the
exact same plateau fix already proven for relationship derivation and
`run_companies` (release-readiness Tickets 94/100), rather than duplicating
it a third time. `adv_bulk.py` cannot import `MDMPipeline` directly --
`pipeline.py` already imports `adv_bulk.py` via a local (deferred, in-
function) import specifically to avoid a module-level circular import, and
this module has no dependency on either side of that cycle.
"""
from __future__ import annotations

from typing import Optional

_RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER = 50
_RELATIONSHIP_SOURCE_LIMIT_MINIMUM = 100


def bounded_source_sql(sql: str, remaining: Optional[int], existing: int = 0) -> str:
    """Append a LIMIT that grows with `existing` so the source window keeps
    advancing past already-converted rows on repeat runs.

    Without `existing` in the limit, every run re-reads the same leading
    slice of the (unordered-by-default) source query: rows already turned
    into relationships/entities come back as already-resolved and the run
    never reaches fresh rows further down the table -- repeat invocations
    with the same `remaining` plateau at whatever the first run produced.
    Growing the window by `existing` guarantees it always extends past the
    previously converted prefix into unconverted territory, given a stable
    ORDER BY.
    """
    if remaining is None:
        return sql
    source_limit = int(existing) + max(
        int(remaining) * _RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER,
        _RELATIONSHIP_SOURCE_LIMIT_MINIMUM,
    )
    return f"{sql.rstrip()} LIMIT {source_limit}"
