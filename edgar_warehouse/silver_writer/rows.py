"""Flat records from a file: JSON Lines, CSV or Parquet, one record per row.

The writer reads parts already flat. A nested JSON or XML part is exported
flat by profiling first (its child lists become their own parts), so a record's
fields are the spec's column names.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterator

from edgar_warehouse.control_contract import Blocked

FORMATS = (".jsonl", ".ndjson", ".csv", ".parquet")


def records(path: Path) -> Iterator[dict]:
    path = Path(path)
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        for batch in pq.ParquetFile(path).iter_batches(batch_size=10_000):
            yield from batch.to_pylist()
    elif path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            # An empty CSV cell is an empty value, as profiling read it.
            for row in csv.DictReader(handle):
                yield {k: (None if v == "" else v) for k, v in row.items()}
    elif path.suffix in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise Blocked(f"{path.name} line {number} is not a JSON object")
                yield record
    else:
        raise Blocked(f"Rows are read from {', '.join(FORMATS)} files: {path.name}")
