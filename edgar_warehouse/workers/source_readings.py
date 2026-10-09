"""Authenticate inline or partitioned readings within the consumer's budget.

Partitions are storage boundaries, not new source identities or MDM batches.
The consumer receives the same ordered tables for each original captured
artifact and keeps its existing byte and row limits.
"""
from __future__ import annotations

import copy
import re

from edgar_warehouse.bookkeeping.clean.artifacts import json_value
from edgar_warehouse.control_contract import reference

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
PART_BYTES = 8 * 1024**2
INDEX_BYTES = 32 * 1024**2


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def table_names(names):
    if (not isinstance(names, list) or len(names) > 64
            or any(not isinstance(name, str) or not NAME.fullmatch(name) for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Streamed reading declares at most 64 distinct table names")
    return names


def _index(ref, artifacts, max_bytes, allow_lookup_receipts):
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
    return body, size


def _partition_chunks(body, artifacts, *, size, max_bytes, max_rows):
    """Yield authenticated chunks; exhaustion is required before publication."""
    rows = 0
    for index, artifact in enumerate(body["artifacts"]):
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
        ordinal = 1
        # Validate complete range accounting before exposing a prefix. Content
        # authentication still proceeds one bounded partition at a time.
        for part in artifact["partitions"]:
            if (not isinstance(part, dict) or set(part) != {"receipt", "first_ordinal", "record_count", "bytes"}
                    or not _integer(part["first_ordinal"], 1, 10_000_000)
                    or part["first_ordinal"] != ordinal
                    or not _integer(part["record_count"], 1, 100_000)
                    or not _integer(part["bytes"], 1, PART_BYTES)):
                raise ValueError("Partition source ranges must be bounded and contiguous")
            reference(part["receipt"])
            ordinal += part["record_count"]
        if ordinal - 1 != artifact["record_count"]:
            raise ValueError("Partition record accounting differs from source EOF receipt")
        if not artifact["partitions"]:
            yield index, {**artifact, "tables": {name: [] for name in names}, "deferred": []}, size, None
        for part in artifact["partitions"]:
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
            rows += len(chunk["deferred"])
            if rows > max_rows:
                raise ValueError("Partitioned reading exceeds consumer row budget")
            yield index, {**artifact, "tables": chunk["tables"], "deferred": chunk["deferred"]}, size, part


def _event(body, ref, index, chunk, size, part=None):
    # The original reading receipt binds the complete authenticated index.
    # Returning that receipt and only the current range avoids copying every
    # future partition for every yielded chunk, without exposing private state.
    header = {"version": body["version"], "reading": copy.deepcopy(ref)}
    if "contract" in body:
        header["contract"] = copy.deepcopy(body["contract"])
    metadata = {name: copy.deepcopy(value) for name, value in chunk.items()
                if name not in ("partitions", "tables", "deferred")}
    if body["version"] == 2:
        metadata["partition"] = copy.deepcopy(part)
    return header, index, {**metadata, "tables": chunk["tables"], "deferred": chunk["deferred"]}, size


def iter_load(ref, artifacts, *, max_bytes, max_rows, allow_lookup_receipts=False):
    """Yield (reading header, artifact index, chunk, cumulative bytes).

    Tables in a chunk contain only that partition's rows. Original input,
    context and lookup receipts stay attached. The header's original reading
    receipt binds the complete index; each chunk carries only its current
    partition range/receipt (None for an empty source). A partition never
    becomes a new source identity. All byte/row budgets are aggregate.
    A yielded prefix is provisional: exhaust this iterator successfully before
    publishing any reduction. Stopping early proves no complete reading.
    """
    if (type(max_bytes) is not int or max_bytes < 1
            or type(max_rows) is not int or max_rows < 0):
        raise ValueError("Reading iteration requires explicit byte and row budgets")
    private_ref = copy.deepcopy(ref)
    body, size = _index(private_ref, artifacts, min(max_bytes, INDEX_BYTES), allow_lookup_receipts)
    if "contract" in body:
        reference(body["contract"])
    if body["version"] == 2:
        for index, chunk, size, part in _partition_chunks(
                body, artifacts, size=size, max_bytes=max_bytes, max_rows=max_rows):
            yield _event(body, private_ref, index, chunk, size, part)
        return
    # Inline readings retain their small authenticated document boundary.
    if not isinstance(body.get("artifacts"), list) or not 1 <= len(body["artifacts"]) <= 2:
        raise ValueError("Incremental inline reading requires one or two original artifacts")
    rows = 0
    for index, artifact in enumerate(body["artifacts"]):
        if (not isinstance(artifact, dict) or not isinstance(artifact.get("tables"), dict)
                or not isinstance(artifact.get("deferred"), list)
                or any(not isinstance(row, dict) for row in artifact["deferred"])):
            raise ValueError("Inline artifact requires tables and deferred object rows")
        reference(artifact.get("input"))
        for evidence in ("context", "lookups"):
            if evidence in artifact:
                reference(artifact[evidence])
        table_names(list(artifact["tables"]))
        for values in artifact["tables"].values():
            if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
                raise ValueError("Inline tables contain object rows")
            rows += len(values)
        rows += len(artifact["deferred"])
        if rows > max_rows:
            raise ValueError("Inline reading exceeds consumer row budget")
        # Inline rows also come from private index data; isolate them together
        # with the small evidence so editing this event cannot change the next.
        yield _event(body, private_ref, index, copy.deepcopy(artifact), size)


def load(ref, artifacts, *, max_bytes, max_rows, allow_lookup_receipts=False):
    """Return normalized version-1 tables and total authenticated bytes read."""
    body, size = _index(ref, artifacts, max_bytes, allow_lookup_receipts)
    if body["version"] == 1:
        return body, size
    normalized = []
    for index, chunk, size, _ in _partition_chunks(
            body, artifacts, size=size, max_bytes=max_bytes, max_rows=max_rows):
        if index == len(normalized):
            normalized.append({**chunk, "tables": {name: [] for name in chunk["tables"]}, "deferred": []})
        for name, values in chunk["tables"].items():
            normalized[index]["tables"][name].extend(values)
        normalized[index]["deferred"].extend(chunk["deferred"])
    return {**body, "version": 1, "artifacts": normalized}, size
