"""Authenticate inline or partitioned readings within the consumer's budget.

Partitions are storage boundaries, not new source identities or MDM batches.
The consumer receives the same ordered tables for each original captured
artifact and keeps its existing byte and row limits.
"""
from __future__ import annotations

import copy
import json
import hashlib
import re

from edgar_warehouse.bookkeeping.clean.artifacts import json_value
from edgar_warehouse.control_contract import reference

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
PART_BYTES = 8 * 1024**2
PART_ROWS = 100_000
INDEX_BYTES = 32 * 1024**2
# One artifact's rows and bytes in a version-2 reading. No output is refused
# for its size (ticket 83): these only bound integers the index states; the
# index's own byte bound limits how many pieces it names.
ARTIFACT_ROWS = 10**12
ARTIFACT_BYTES = 2**50
MAX_ARTIFACTS = 512  # documents one reading may hold (`source.read`); byte and row budgets bound the rest


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
            or not isinstance(body["artifacts"], list) or not 1 <= len(body["artifacts"]) <= MAX_ARTIFACTS):
        raise ValueError(f"Partitioned reading requires contract and 1..{MAX_ARTIFACTS} artifacts")
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
        if (not _integer(artifact["record_count"], 0, ARTIFACT_ROWS)
                or not _integer(artifact["expanded_bytes"], 1, ARTIFACT_BYTES)
                or not isinstance(artifact["partitions"], list)):
            raise ValueError("Partitioned artifact has invalid source accounting")
        ordinal = 1
        # Validate complete range accounting before exposing a prefix. Content
        # authentication still proceeds one bounded partition at a time.
        for part in artifact["partitions"]:
            if (not isinstance(part, dict) or set(part) != {"receipt", "first_ordinal", "record_count", "bytes"}
                    or not _integer(part["first_ordinal"], 1, ARTIFACT_ROWS)
                    or part["first_ordinal"] != ordinal
                    or not _integer(part["record_count"], 1, PART_ROWS)
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
    # Inline readings retain their authenticated document boundary (at most MAX_ARTIFACTS documents).
    if not isinstance(body.get("artifacts"), list) or not 1 <= len(body["artifacts"]) <= MAX_ARTIFACTS:
        raise ValueError(f"Incremental inline reading requires 1..{MAX_ARTIFACTS} original artifacts")
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


def _whole(body, artifacts, *, size, max_bytes, max_rows):
    """A reading in pieces, one whole artifact (with its cumulative bytes) at a time."""
    current, at = None, None
    for index, chunk, size, _ in _partition_chunks(
            body, artifacts, size=size, max_bytes=max_bytes, max_rows=max_rows):
        if index != at:
            if current is not None:
                yield current, size
            current, at = {**chunk, "tables": {name: [] for name in chunk["tables"]}, "deferred": []}, index
        for name, values in chunk["tables"].items():
            current["tables"][name].extend(values)
        current["deferred"].extend(chunk["deferred"])
    if current is not None:
        yield current, size


def iter_artifacts(ref, artifacts, *, max_bytes, max_rows, allow_lookup_receipts=False):
    """Yield (one whole artifact as version 1, cumulative bytes): a whole
    reading's artifacts as written, a reading in pieces one artifact at a
    time, so memory holds one artifact (ticket 83)."""
    body, size = _index(ref, artifacts, max_bytes, allow_lookup_receipts)
    if body["version"] == 1:
        if not isinstance(body.get("artifacts"), list):
            raise ValueError("A whole reading lists its artifacts")
        for artifact in body["artifacts"]:
            yield artifact, size
        return
    yield from _whole(body, artifacts, size=size, max_bytes=max_bytes, max_rows=max_rows)


def load(ref, artifacts, *, max_bytes, max_rows, allow_lookup_receipts=False):
    """Return normalized version-1 tables and total authenticated bytes read."""
    body, size = _index(ref, artifacts, max_bytes, allow_lookup_receipts)
    if body["version"] == 1:
        return body, size
    normalized = []
    for artifact, size in _whole(body, artifacts, size=size, max_bytes=max_bytes, max_rows=max_rows):
        normalized.append(artifact)
    return {**body, "version": 1, "artifacts": normalized}, size


def _encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def publish(artifacts):
    """A piece sink that writes each piece (before the index that names it)."""
    def sink(receipt, data):
        if artifacts.put_bytes(receipt["uri"], data) != receipt:
            raise ValueError("Written partition receipt differs from its bytes")
    return sink


def check(artifacts):
    """A piece sink that compares each written piece with the one made again."""
    def sink(receipt, data):
        if artifacts.verified(receipt, max_bytes=PART_BYTES) != data:
            raise ValueError("Written partition differs from pinned inputs and configuration")
    return sink


def pieces(output_uri: str, evidence: dict, tables: dict, deferred: list, names: list[str],
           input_bytes: int, sink) -> dict:
    """One input's rows, then its deferred records, in order, cut into version-1
    chunks of at most PART_BYTES and PART_ROWS (ticket 83), each handed to
    `sink(receipt, bytes)` as it is made: the input's entry in a version-2
    index. Only one row larger than a piece is refused."""
    items = [(name, row) for name in names for row in tables.get(name, [])]
    items += [(None, item) for item in deferred]
    parts, ordinal = [], 1

    def fresh():
        return {"version": 1, "tables": {name: [] for name in names}, "deferred": []}

    def flush(pending, count):
        nonlocal ordinal
        data = _encode(pending)
        sha = hashlib.sha256(data).hexdigest()
        receipt = {"uri": f"{output_uri}.parts/{sha}.json", "sha256": sha}
        parts.append({"receipt": receipt, "first_ordinal": ordinal, "record_count": count, "bytes": len(data)})
        sink(receipt, data)
        ordinal += count

    pending, count = fresh(), 0
    empty = size = len(_encode(pending))
    for name, item in items:
        target = pending["deferred"] if name is None else pending["tables"][name]
        extra = len(_encode(item)) + (1 if target else 0)
        if count and (size + extra > PART_BYTES or count == PART_ROWS):
            flush(pending, count)
            pending, count, size = fresh(), 0, empty
            target = pending["deferred"] if name is None else pending["tables"][name]
            extra = len(_encode(item))
        if size + extra > PART_BYTES:
            raise ValueError("One source row exceeds the partition byte bound")
        target.append(item)
        size, count = size + extra, count + 1
    if count:
        flush(pending, count)
    entry = {**evidence, "record_count": ordinal - 1, "expanded_bytes": max(1, input_bytes),
             "table_names": names, "partitions": parts}
    return entry
