"""mdm.prepare: a configured reading into an MDM input manifest (mastering to-do 21).

The unit's input is a `source.read` output (normally `from` the run's read
step); its keys say what to take from it, so nothing feed-specific runs:

- `table`: the reading's table whose rows become MDM records;
- optional `record_column`: an object-valued column holding the complete source record;
- optional `distinct_on`: 1 to 8 columns of the table row (not of the
  `record_column` object); of the artifact's rows with equal
  values in them (a missing column reads as null) only the first, in file
  order, becomes a record, so an entity named in many rows of one file is one
  record of it. The rows themselves stay in the reading;
- optional `effective_column`: a column holding the artifact's effective time,
  an ISO 8601 instant with a timezone, the same in every row (normally from
  the reading's context: when the file was published). Each of the artifact's
  publications states it, so MDM dates the records, and a link without a
  stated start starts then. Without it a publication states no time;
- `dataset`: the MDM source code whose registered contract reads them;
- `policy`: the Mastering Policy digest the batches pin;
- `consumer`: the MDM consumer the batches advance, from checkpoint 0, so a
  unit's consumer is its own;
- `batch_id`: the prefix of the batch ids;
- `as_of`: the instant the batches are mastered as of.

Each artifact's rows of that table become records files of at most 1,000
rows beside the output, one batch each, keyed by the artifact's digest. The
records a check set aside stay in the reading itself. The output is the
manifest `mdm.merge` takes. Everything is a function of the reading and the
keys, so the verifier rebuilds it and compares bytes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
import edgar_warehouse.control_contract as control_contract
from edgar_warehouse.control_contract import reference
from edgar_warehouse.mdm.clean import limits
from . import source_readings

CHECK = "mdm.prepared"
KEYS = {"table", "dataset", "policy", "consumer", "batch_id", "as_of"}
# Bounds, not budgets (ticket 83): the input is read one input file at a time
# and each batch's records file written as it fills, so memory holds one input
# file's rows and one batch.
INPUT_BYTES = 16 * 1024**3
INPUT_ROWS = 100_000_000


def runtime_files():
    return [Path(artifact_store.__file__), Path(control_contract.__file__), Path(source_readings.__file__),
            Path(limits.__file__)]


def _lines(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False).encode() + b"\n" for r in rows)


READINGS = 256  # as many as a composed input lists


def _artifacts(envelope: dict, artifacts):
    """Each input file of the unit's readings, whole, in order: one source.read
    output, or a readings list `{"version": 1, "readings": [ref, ...]}` (a
    composed input naming many). A reading written in pieces is gathered one
    file at a time; the byte and row bounds are spent across all of them."""
    refs = [envelope["input"]]
    try:  # a readings list is small; a larger input is a reading, read below
        document = artifacts.json(envelope["input"])
    except artifact_store.Blocked:
        document = {}
    if set(document) == {"version", "readings"}:
        if (document["version"] != 1 or not isinstance(document["readings"], list)
                or not 1 <= len(document["readings"]) <= READINGS):
            raise ValueError(f"mdm.prepare reads a readings list of 1 to {READINGS} readings (version 1)")
        refs = [reference(ref) for ref in document["readings"]]
    consumed = rows = 0
    for ref in refs:
        used = 0
        for artifact, used in source_readings.iter_artifacts(
                ref, artifacts, max_bytes=INPUT_BYTES - consumed, max_rows=INPUT_ROWS - rows):
            rows += sum(len(t) for t in artifact["tables"].values() if isinstance(t, list))
            if rows > INPUT_ROWS:
                raise ValueError("mdm.prepare readings exceed their row budget")
            yield artifact
        consumed += used


def _artifact_rows(artifact: dict, keys: dict) -> tuple[str, list[dict], dict]:
    """One artifact's records, checked: its source digest, its rows and its publication facts."""
    record_column = _optional_text(keys, "record_column")
    effective_column = _optional_text(keys, "effective_column")
    distinct_on = _distinct_columns(keys)
    rows = artifact["tables"].get(keys["table"])
    if rows is None:
        raise ValueError(f"The reading has no table {keys['table']}")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("mdm.prepare table rows must be objects")
    # Every row is checked before duplicates are dropped, so a dropped
    # row cannot hide a bad time or shape.
    publication = {}
    if effective_column is not None and rows:
        publication["effective_at"] = _effective_at(rows, effective_column, keys["as_of"])
    if record_column is not None and any(not isinstance(row.get(record_column), dict) for row in rows):
        raise ValueError("mdm.prepare record_column must hold an object in every row")
    if distinct_on is not None:
        rows = _first_of_each(rows, distinct_on)
    if record_column is not None:
        rows = [row[record_column] for row in rows]
    source = artifact["input"]["sha256"]
    if "context" in artifact:
        reference(artifact["context"])
        # One captured document may be read under distinct approved caller
        # facts. Keep their records, batches and publications independent.
        source = hashlib.sha256(f"{source}:{artifact['context']['sha256']}".encode()).hexdigest()
    return source, rows, publication


def _published(keys: dict) -> dict | None:
    """Optional `publication_key` and `revision`: the caller's one publication for every row of the unit."""
    if "publication_key" not in keys and "revision" not in keys:
        return None
    revision = keys.get("revision")  # unit keys are text: the revision is written in decimal digits
    if (not isinstance(keys.get("publication_key"), str) or not keys["publication_key"]
            or not isinstance(revision, str) or not revision.isascii() or not revision.isdigit()
            or revision != str(int(revision))):
        raise ValueError("mdm.prepare publication_key and revision come together: text and a nonnegative integer")
    if "effective_column" in keys:
        raise ValueError("mdm.prepare states one publication's time; effective_column states one per artifact")
    return {"publication_key": keys["publication_key"], "revision": int(revision), "effective_at": None}


def _batch(keys: dict, name: str, batch_id: str, chunk: list[dict], publication: dict) -> tuple[bytes, dict]:
    data = _lines(chunk)
    if len(data) > limits.RECORDS_FILE_BYTES:
        raise ValueError("mdm.prepare records exceed the verifier byte budget; partition the input")
    return data, {"batch_id": batch_id, "stage": "mastering", "consumer": keys["consumer"],
                  "input": {"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                            "record_count": len(chunk), "source_code": keys["dataset"], "publication": publication}}


def _documents(envelope: dict, artifacts, on_file) -> bytes:
    """The manifest's bytes; `on_file(name, data)` receives each records file as it is made.

    Without `publication_key` each artifact is its own publication (revision 1) and its own batches;
    with it, the unit's rows, in reading and artifact order, are one publication cut into batches once."""
    keys = envelope["keys"]
    if not KEYS <= set(keys):
        raise ValueError(f"mdm.prepare needs the unit keys {sorted(KEYS)}")
    published = _published(keys)
    batches = []
    if published is None:
        for artifact in _artifacts(envelope, artifacts):
            source, rows, publication = _artifact_rows(artifact, keys)
            for n, chunk in enumerate(limits.iter_batches(rows, lambda row: _lines([row]))):
                name = f"{source}.{n}.jsonl"
                data, batch = _batch(keys, name, f"{keys['batch_id']}:{source[:16]}:{n}", chunk,
                                     {"publication_key": f"{keys['dataset']}:{source}", "revision": 1,
                                      **publication})
                on_file(name, data)
                batches.append(batch)
    else:  # one publication: _published refused per-artifact times; its rows are cut as they come
        pooled = (row for artifact in _artifacts(envelope, artifacts) for row in _artifact_rows(artifact, keys)[1])
        for n, chunk in enumerate(limits.iter_batches(pooled, lambda row: _lines([row]))):
            name = f"records.{n}.jsonl"
            data, batch = _batch(keys, name, f"{keys['batch_id']}:{n}", chunk, published)
            on_file(name, data)
            batches.append(batch)
    if not batches:
        raise ValueError(f"The reading's {keys['table']} table holds no rows")
    for n, batch in enumerate(batches):
        batch["expected_checkpoint"], batch["checkpoint"] = n, n + 1
    manifest = {"contract_version": 2, "as_of": keys["as_of"],
                "policy_digest": keys["policy"], "batches": batches}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > limits.MANIFEST_BYTES:
        raise ValueError("mdm.prepare manifest exceeds the verifier byte budget; partition the input")
    return encoded


def _optional_text(keys: dict, name: str) -> str | None:
    value = keys.get(name)
    if name in keys and (not isinstance(value, str) or not value):
        raise ValueError(f"mdm.prepare {name} must be nonempty text")
    return value


def _distinct_columns(keys: dict) -> list[str] | None:
    """`distinct_on`: 1 to 8 distinct columns of the table row (as many as
    source.combine's `order_by` takes)."""
    columns = keys.get("distinct_on")
    if "distinct_on" in keys and (
        not isinstance(columns, list) or not 1 <= len(columns) <= 8
        or any(not isinstance(c, str) or not c for c in columns) or len(set(columns)) != len(columns)
    ):
        raise ValueError("mdm.prepare distinct_on names 1 to 8 distinct nonempty columns")
    return columns


def _first_of_each(rows: list[dict], columns: list[str]) -> list[dict]:
    """The first row, in order, of each distinct value of the columns."""
    seen, kept = set(), []
    for row in rows:
        key = json.dumps([row.get(c) for c in columns], sort_keys=True)
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def _effective_at(rows: list[dict], column: str, as_of: str) -> str:
    """The one effective time every row of an artifact states, checked.

    Compared as written: one file states its time one way. A time after the
    manifest's `as_of` is refused, since MDM would read those records as not
    yet in effect and leave them out silently. (The same test as MDM's
    `evidence.instant`, kept here so the worker's pinned runtime stays small.)
    """
    if len({json.dumps(row.get(column)) for row in rows}) != 1:
        raise ValueError(f"mdm.prepare {column} must hold one effective time per artifact")
    value = rows[0].get(column)
    try:
        moment = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        raise ValueError(f"mdm.prepare {column} must be an instant with a timezone")
    if moment > datetime.fromisoformat(as_of):
        raise ValueError(f"mdm.prepare {column} is after the manifest's as_of")
    return value


def _beside(output: str, name: str) -> str:
    return f"{output.rsplit('/', 1)[0]}/{name}"


def execute(envelope: dict, artifacts) -> dict:
    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"mdm.prepare verifies {CHECK} only")
    # Records first, each as it is made: the manifest names them.
    manifest = _documents(envelope, artifacts,
                          lambda name, data: artifacts.put_bytes(_beside(envelope["output"], name), data))
    return artifacts.put_bytes(envelope["output"], manifest)


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    def check(name, data):
        if artifacts.read(_beside(envelope["output"], name), max_bytes=limits.RECORDS_FILE_BYTES) != data:
            raise ValueError(f"The records file {name} differs from the reading")

    manifest = _documents(envelope, artifacts, check)
    if artifacts.verified(envelope["candidate"], max_bytes=limits.MANIFEST_BYTES) != manifest:
        raise ValueError("The manifest differs from the reading")
    return {CHECK: True}, []
