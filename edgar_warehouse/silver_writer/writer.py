"""Land one delivery of a part into its registered silver table.

Each row keeps the source's own key for every link. A row finds its master by a join on the
kind's view in the MDM schema (`<kind>_record`, or `<kind>_identifier_holder` for an identifier
link), so no id is looked up or written here and a master merged later still resolves.

A spec's data quality checks run on the delivery first (`checks.py`): a
flagged row lands with the ids of the checks it failed in its `quality`
column, and a row an exception refuses does not land.

A delivery is held in memory (the sink copies it in bounded chunks); a part too large
for that is landed in several deliveries.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


from edgar_warehouse.control_contract import Blocked

from . import checks
from . import results as quality_results
from .sink import Sink


def land(sink: Sink, table: str, records: Iterable[dict], results: Path | None = None, *,
         record_quality_results: bool = True) -> dict:
    """Write records into a registered table: fields are the spec's columns (a field the spec
    does not name is refused). A master is found by a join on a view, so no id is looked up or written."""
    spec = sink.spec(table)
    names = {c["name"] for c in spec["columns"]}
    rows = []
    for number, record in enumerate(records, 1):
        unknown = set(record) - names
        if unknown:
            raise Blocked(f"Record {number} holds fields silver.{table} does not name: {sorted(unknown)}")
        rows.append(record)
    rows, quality = checks.run(spec, rows)
    results = (results or os.environ.get(quality_results.ENVIRONMENT)) if record_quality_results else None
    if quality and results:
        quality_results.record(Path(results), table, quality)
    result = sink.write(spec, rows)
    return {**result, **({"quality": quality} if quality else {})}
