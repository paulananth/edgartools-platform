"""Authenticate inline or partitioned readings within the consumer's budget.

Partitions are storage boundaries, not new source identities or MDM batches.
The consumer receives the same ordered tables for each original captured
artifact and keeps its existing byte and row limits.
"""
from __future__ import annotations

import re

from edgar_warehouse.bookkeeping.clean.artifacts import json_value
from edgar_warehouse.control_contract import reference

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
PART_BYTES = 8 * 1024**2


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def table_names(names):
    if (not isinstance(names, list) or len(names) > 64
            or any(not isinstance(name, str) or not NAME.fullmatch(name) for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Streamed reading declares at most 64 distinct table names")
    return names


def load(ref, artifacts, *, max_bytes, max_rows, allow_lookup_receipts=False):
    """Return normalized version-1 tables and total authenticated bytes read."""
    data = artifacts.verified(ref, max_bytes=max_bytes)
    size = len(data)
    body = json_value(data)
    if (not isinstance(body, dict) or type(body.get("version")) is not int
            or body["version"] not in (1, 2)):
        raise ValueError("Consumer requires a version-1 or version-2 source reading")
    entries = body.get("artifacts", [])
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and "lookups" in entry:
                reference(entry["lookups"])
                if not allow_lookup_receipts:
                    raise ValueError("Consumer must explicitly bind lookup receipts into its output identity")
    if body["version"] == 1:
        return body, size
    if (set(body) != {"version", "contract", "artifacts"}
            or not isinstance(body["artifacts"], list) or not 1 <= len(body["artifacts"]) <= 2):
        raise ValueError("Partitioned reading requires contract and one or two artifacts")
    reference(body["contract"])
    normalized, rows = [], 0
    for artifact in body["artifacts"]:
        required = {"input", "record_count", "expanded_bytes", "table_names", "partitions"}
        if (not isinstance(artifact, dict) or not required <= set(artifact)
                or set(artifact) - required - {"context", "lookups"}):
            raise ValueError("Partitioned artifact has unknown or missing evidence")
        reference(artifact["input"])
        for evidence in ("context", "lookups"):
            if evidence in artifact:
                reference(artifact[evidence])
        names = table_names(artifact["table_names"])
        if (not _integer(artifact["record_count"], 0, 10_000_000)
                or not _integer(artifact["expanded_bytes"], 1, 16 * 1024**3)
                or not isinstance(artifact["partitions"], list)
                or len(artifact["partitions"]) > 4096):
            raise ValueError("Partitioned artifact has invalid source accounting")
        tables, deferred, ordinal = {name: [] for name in names}, [], 1
        for part in artifact["partitions"]:
            if (not isinstance(part, dict) or set(part) != {"receipt", "first_ordinal", "record_count", "bytes"}
                    or not _integer(part["first_ordinal"], 1, 10_000_000)
                    or part["first_ordinal"] != ordinal
                    or not _integer(part["record_count"], 1, 100_000)
                    or not _integer(part["bytes"], 1, PART_BYTES)):
                raise ValueError("Partition source ranges must be bounded and contiguous")
            if size + part["bytes"] > max_bytes:
                raise ValueError("Partitioned reading exceeds consumer byte budget")
            data = artifacts.verified(part["receipt"], max_bytes=part["bytes"])
            if len(data) != part["bytes"]:
                raise ValueError("Partition byte receipt differs from actual content")
            size += len(data)
            chunk = json_value(data)
            if (not isinstance(chunk, dict) or set(chunk) != {"version", "tables", "deferred"}
                    or type(chunk["version"]) is not int or chunk["version"] != 1
                    or not isinstance(chunk["tables"], dict) or set(chunk["tables"]) != set(names)
                    or not isinstance(chunk["deferred"], list)
                    or any(not isinstance(item, dict) for item in chunk["deferred"])):
                raise ValueError("Partition content differs from its declared table schema")
            for name, values in chunk["tables"].items():
                if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
                    raise ValueError("Partition tables contain object rows")
                rows += len(values)
                if rows > max_rows:
                    raise ValueError("Partitioned reading exceeds consumer row budget")
                tables[name].extend(values)
            rows += len(chunk["deferred"])
            if rows > max_rows:
                raise ValueError("Partitioned reading exceeds consumer row budget")
            deferred.extend(chunk["deferred"])
            ordinal += part["record_count"]
        if ordinal - 1 != artifact["record_count"]:
            raise ValueError("Partition record accounting differs from source EOF receipt")
        # Preserve all input/context/contract and partition evidence. The
        # original artifact remains the batching and publication identity.
        normalized.append({**artifact, "tables": tables, "deferred": deferred})
    return {**body, "version": 1, "artifacts": normalized}, size
