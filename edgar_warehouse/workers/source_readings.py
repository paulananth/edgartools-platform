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
from typing import Any

from edgar_warehouse.rules import files

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
# Keep lookup-document and derived-producer accounting distinct from the
# consumer's table budgets, as in the source.read worker.
RECEIPT_BYTES = 64 * 1024**2
LOOKUP_AGGREGATE_BYTES = 16 * 1024**3
DERIVED_INPUT_BYTES = 16 * 1024**3
DERIVED_INPUT_ROWS = 100_000_000
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
    yield from _iter_loaded(body, private_ref, artifacts, size=size, max_bytes=max_bytes, max_rows=max_rows)


def _iter_loaded(body: Any, private_ref, artifacts, *, size, max_bytes, max_rows):
    """Traverse a private authenticated index without reopening it."""
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
        input_ref: Any = artifact.get("input")
        reference(input_ref)
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


def lookup_sets(input_ref, lookup_ref, artifacts, contract):
    """Authenticate the contract's bounded lookup sets against their original input.

    Worker-manifest validation belongs to the worker. Reading consumers supply
    original evidence directly; derived producers are exhausted before return.
    """
    reference(input_ref)
    reference(lookup_ref)
    declared = contract["read"].get("lookup_sets", {})
    bound = json_value(artifacts.verified(lookup_ref, max_bytes=RECEIPT_BYTES))
    if (not isinstance(bound, dict) or set(bound) != {"version", "input", "sets"}
            or type(bound["version"]) is not int or bound["version"] not in (1, 2)
            or bound["input"] != input_ref or not isinstance(bound["sets"], dict)
            or set(bound["sets"]) != set(declared)):
        raise ValueError("Lookup document binds exactly declared sets to the input receipt")
    sets = (bound["sets"] if bound["version"] == 1
            else _derived_sets(bound["sets"], declared, artifacts))
    total = 0
    checked = {}
    for name, values in sets.items():
        spec = declared[name]
        pairs = bool(spec.get("pairs"))
        if not isinstance(values, list) or len(values) > spec["max_values"]:
            raise ValueError("Lookup raw values exceed their declared count or list shape")
        if pairs:  # each item a key and its value; JSON gives a list, the engine takes a tuple
            if not all(isinstance(item, (list, tuple)) and len(item) == 2 for item in values):
                raise ValueError("A pair set's items are a key and a value")
            values = [tuple(item) for item in values]
        checked[name] = values
        size = 0
        for item in values:
            for value in (item if pairs else (item,)):
                if not isinstance(value, str):
                    raise ValueError("Lookup values require exact text")
                length = len(value.encode("utf-8"))
                if length > spec["max_value_bytes"]:
                    raise ValueError("Lookup value exceeds its declared UTF-8 bound")
                size += length
            if size > spec["max_bytes"]:
                raise ValueError("Lookup raw values exceed their declared UTF-8 byte bound")
        total += size
        if total > LOOKUP_AGGREGATE_BYTES:
            raise ValueError("Lookup sets exceed the aggregate UTF-8 byte bound")
    return checked


def _derived_sets(specs, declared, artifacts):
    """Exhaust authenticated producer readings before making indexed scopes.

    Values stay raw until the existing count/UTF-8 bounds validate them;
    duplicate rows therefore cannot evade those limits through deduplication.
    """
    result = {}
    named = lambda value: isinstance(value, str) and NAME.fullmatch(value) is not None
    for name, spec in specs.items():
        # A pair set names its value column beside its key column.
        required = {"readings", "table", "column", "max_input_bytes", "max_input_rows",
                    *(("value_column",) if declared[name].get("pairs") else ())}
        if (not isinstance(spec, dict) or set(spec) != required
                or not isinstance(spec["readings"], list) or not 1 <= len(spec["readings"]) <= 256
                or not named(spec["table"]) or not named(spec["column"])
                or ("value_column" in spec and not named(spec["value_column"]))
                or type(spec["max_input_bytes"]) is not int or not 1 <= spec["max_input_bytes"] <= DERIVED_INPUT_BYTES
                or type(spec["max_input_rows"]) is not int or not 1 <= spec["max_input_rows"] <= DERIVED_INPUT_ROWS):
            raise ValueError("Derived lookup requires complete readings, named table/column and explicit bounds")
        for ref in spec["readings"]:
            reference(ref)
        values, consumed, rows, size = [], 0, 0, 0
        bounds = declared[name]
        for ref in spec["readings"]:
            used = 0
            for _, _, chunk, used in iter_load(
                    ref, artifacts, max_bytes=spec["max_input_bytes"] - consumed,
                    max_rows=spec["max_input_rows"] - rows, allow_lookup_receipts=True):
                if chunk["deferred"] or spec["table"] not in chunk["tables"]:
                    raise ValueError("Derived lookup requires resolved records and its declared table")
                rows += sum(len(table) for table in chunk["tables"].values())
                for row in chunk["tables"][spec["table"]]:
                    item = tuple(row.get(c) for c in (spec["column"], spec.get("value_column")) if c)
                    if not all(isinstance(value, str) for value in item):
                        raise ValueError("Derived lookup columns require present exact text")
                    lengths = [len(value.encode("utf-8")) for value in item]
                    if (len(values) >= bounds["max_values"] or max(lengths) > bounds["max_value_bytes"]
                            or size + sum(lengths) > bounds["max_bytes"]):
                        raise ValueError("Derived lookup exceeds declared raw value bounds")
                    values.append(item if len(item) == 2 else item[0])
                    size += sum(lengths)
            consumed += used
        result[name] = values
    return result


class OpenedExtract:
    """Authenticated evidence and one provisional, bounded table traversal.

    Only the index and requested evidence are held privately. Partitions are
    authenticated as consumed; opening or stopping early proves no complete
    extract. Consumers publish only after successful exhaustion of chunks().
    """

    def __init__(self, ref, artifacts, *, max_bytes, max_rows, max_contract_bytes,
                 allow_lookup_receipts=False):
        if (type(max_bytes) is not int or max_bytes < 1
                or type(max_rows) is not int or max_rows < 0):
            raise ValueError("Reading iteration requires explicit byte and row budgets")
        if type(max_contract_bytes) is not int or max_contract_bytes < 1:
            raise ValueError("Source Extract requires an explicit contract byte bound")
        self._ref = copy.deepcopy(ref)
        self._store = artifacts
        self._body, self._size = _index(self._ref, artifacts, min(max_bytes, INDEX_BYTES), allow_lookup_receipts)
        self._contract = None
        if "contract" in self._body:
            reference(self._body["contract"])
            self._contract = files.loads(artifacts.verified(
                self._body["contract"], max_bytes=max_contract_bytes).decode("utf-8"))
        self._max_bytes, self._max_rows = max_bytes, max_rows
        self._started = False
        self._lookups = {}

    @property
    def reading(self):
        """The original receipt, isolated from the private traversal identity."""
        return copy.deepcopy(self._ref)

    @property
    def contract(self):
        return copy.deepcopy(self._contract)

    @property
    def artifacts(self):
        return [copy.deepcopy({k: v for k, v in entry.items()
                               if k not in {"tables", "deferred", "partitions"}})
                for entry in self._body["artifacts"]]

    def lookup_sets(self, index):
        """Return isolated authenticated values for one original artifact."""
        if type(index) is not int or not 0 <= index < len(self._body["artifacts"]):
            raise ValueError("Lookup sets name an original artifact index")
        if index not in self._lookups:
            entry = self._body["artifacts"][index]
            # A lookup-bearing input has the original input/context evidence;
            # this validates references, not the contents of the context.
            reference(entry["context"])
            if self._contract is None:
                raise ValueError("Lookup authentication requires contract evidence")
            self._lookups[index] = lookup_sets(entry["input"], entry["lookups"], self._store, self._contract)
        return copy.deepcopy(self._lookups[index])

    def chunks(self):
        """One forward traversal; exhaustion is the consumer's publication gate."""
        if self._started:
            raise ValueError("An opened Source Extract permits one traversal")
        self._started = True
        return _iter_loaded(self._body, self._ref, self._store, size=self._size,
                            max_bytes=self._max_bytes, max_rows=self._max_rows)


def _whole(body, artifacts, *, size, max_bytes, max_rows):
    """A reading in pieces, one whole artifact (with its cumulative bytes) at a time."""
    current: Any = None
    at = None
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
