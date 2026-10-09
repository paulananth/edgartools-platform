"""Bounded Parquet framing for configured reading; no domain transformations.

The physical receipt stays the source identity. Arrow dates become ISO text at
this JSON boundary, matching persisted source records; unsupported scalars refuse.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import io
import json

import pyarrow.parquet as pq
import pyarrow._parquet as parquet_codec
from pathlib import Path


def runtime_files():
    return [Path(pq.__file__), Path(parquet_codec.__file__)]


def json_scalar(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported source scalar: {type(value).__name__}")


def engine_contract(contract):
    body = deepcopy(contract)
    body["read"]["format"] = "json"
    body["read"].pop("parquet", None)
    return body


def document(data, contract):
    settings = contract["read"].get("parquet", {})
    if not isinstance(settings, dict) or set(settings) - {
        "columns",
        "distinct",
        "take",
    }:
        raise ValueError("Parquet framing declares columns, distinct and take only")
    columns = settings.get("columns")
    if columns is not None and (
        not isinstance(columns, list)
        or not 1 <= len(columns) <= 128
        or any(not isinstance(name, str) or not name for name in columns)
        or len(set(columns)) != len(columns)
    ):
        raise ValueError("Parquet columns are 1..128 distinct names")
    if "distinct" in settings and type(settings["distinct"]) is not bool:
        raise ValueError("Parquet distinct must be boolean")
    take = settings.get("take")
    if take is not None and (type(take) is not int or not 1 <= take <= 1000):
        raise ValueError("Parquet take is 1..1000 or omitted")
    parquet = pq.ParquetFile(io.BytesIO(data))
    # A take is a bounded sample of the authenticated physical file. Without
    # take, consume every projected row, including after the distinct set fills.
    maximum = contract["read"]["limits"]["max_records"]
    buffer = io.BytesIO()
    buffer.write(b'{"rows":[')
    encoder = json.JSONEncoder(
        default=json_scalar,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    budget = contract["read"]["limits"]["max_bytes"]
    seen, count, visited = set(), 0, 0
    for batch in parquet.iter_batches(batch_size=1000, columns=columns):
        for row in batch.to_pylist():
            if take is not None and visited >= take:
                break
            visited += 1
            encoded = encoder.encode(row).encode()
            if settings.get("distinct", False):
                if encoded in seen:
                    continue
                seen.add(encoded)
            count += 1
            if count > maximum or buffer.tell() + len(encoded) + 3 > budget:
                raise ValueError("Parquet framing exceeds declared row/byte budget")
            if count > 1:
                buffer.write(b",")
            buffer.write(encoded)
        if take is not None and visited >= take:
            break
    buffer.write(b"]}")
    return buffer.getvalue()
