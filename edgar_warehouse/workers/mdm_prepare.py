"""mdm.prepare: a configured reading into a Clean MDM input manifest (mastering to-do 21).

The unit's input is a `source.read` output (normally `from` the run's read
step); its keys say what to take from it, so nothing feed-specific runs:

- `table`: the reading's table whose rows become MDM records;
- optional `record_column`: an object-valued column holding the complete source record;
- optional `distinct_on`: 1 to 8 columns; of the artifact's rows with equal
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
from . import source_readings

CHECK = "mdm.prepared"
KEYS = {"table", "dataset", "policy", "consumer", "batch_id", "as_of"}
BATCH = 1000
RECORD_BYTES = 16 * 1024**2
MANIFEST_BYTES = 32 * 1024**2
INPUT_BYTES = 32 * 1024**2
INPUT_ROWS = 100_000


def runtime_files():
    return [Path(artifact_store.__file__), Path(control_contract.__file__), Path(source_readings.__file__)]


def _lines(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False).encode() + b"\n" for r in rows)


def _documents(envelope: dict, artifacts) -> tuple[dict[str, bytes], bytes]:
    """{name: bytes} of the records files, and the manifest's bytes."""
    keys = envelope["keys"]
    if not KEYS <= set(keys):
        raise ValueError(f"mdm.prepare needs the unit keys {sorted(KEYS)}")
    record_column = keys.get("record_column")
    if "record_column" in keys and (not isinstance(record_column, str) or not record_column):
        raise ValueError("mdm.prepare record_column must be nonempty text")
    effective_column = keys.get("effective_column")
    if "effective_column" in keys and (not isinstance(effective_column, str) or not effective_column):
        raise ValueError("mdm.prepare effective_column must be nonempty text")
    distinct_on = keys.get("distinct_on")
    if "distinct_on" in keys and (
        not isinstance(distinct_on, list) or not 1 <= len(distinct_on) <= 8
        or any(not isinstance(c, str) or not c for c in distinct_on) or len(set(distinct_on)) != len(distinct_on)
    ):
        raise ValueError("mdm.prepare distinct_on names 1 to 8 distinct nonempty columns")
    reading, _ = source_readings.load(envelope["input"], artifacts,
                                      max_bytes=INPUT_BYTES, max_rows=INPUT_ROWS)
    if reading.get("version") != 1 or not isinstance(reading.get("artifacts"), list):
        raise ValueError("mdm.prepare reads a source.read output (version 1)")
    files, batches = {}, []
    for artifact in reading["artifacts"]:
        rows = artifact["tables"].get(keys["table"])
        if rows is None:
            raise ValueError(f"The reading has no table {keys['table']}")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("mdm.prepare table rows must be objects")
        if distinct_on is not None:
            rows = _first_of_each(rows, distinct_on)
        publication = {}
        if effective_column is not None and rows:
            publication["effective_at"] = _effective_at(rows, effective_column, keys["as_of"])
        if record_column is not None:
            if any(not isinstance(row.get(record_column), dict) for row in rows):
                raise ValueError("mdm.prepare record_column must hold an object in every row")
            rows = [row[record_column] for row in rows]
        source = artifact["input"]["sha256"]
        if "context" in artifact:
            reference(artifact["context"])
            # One captured document may be read under distinct approved caller
            # facts. Keep their records, batches and publications independent.
            source = hashlib.sha256(f"{source}:{artifact['context']['sha256']}".encode()).hexdigest()
        for start in range(0, len(rows), BATCH):
            chunk = rows[start:start + BATCH]
            data = _lines(chunk)
            if len(data) > RECORD_BYTES:
                raise ValueError("mdm.prepare records exceed the verifier byte budget; partition the input")
            name = f"{source}.{start // BATCH}.jsonl"
            files[name] = data
            batches.append({
                "batch_id": f"{keys['batch_id']}:{source[:16]}:{start // BATCH}",
                "stage": "mastering", "consumer": keys["consumer"],
                "input": {"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                          "record_count": len(chunk), "source_code": keys["dataset"],
                          "publication": {"publication_key": f"{keys['dataset']}:{source}", "revision": 1,
                                          **publication}},
            })
    if not batches:
        raise ValueError(f"The reading's {keys['table']} table holds no rows")
    for n, batch in enumerate(batches):
        batch["expected_checkpoint"], batch["checkpoint"] = n, n + 1
    manifest = {"contract_version": 2, "as_of": keys["as_of"],
                "policy_digest": keys["policy"], "batches": batches}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MANIFEST_BYTES:
        raise ValueError("mdm.prepare manifest exceeds the verifier byte budget; partition the input")
    return files, encoded


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
    yet in effect and leave them out silently. (The same test as Clean MDM's
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
    files, manifest = _documents(envelope, artifacts)
    for name, data in files.items():  # records first: the manifest names them
        artifacts.put_bytes(_beside(envelope["output"], name), data)
    return artifacts.put_bytes(envelope["output"], manifest)


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    files, manifest = _documents(envelope, artifacts)
    if artifacts.verified(envelope["candidate"], max_bytes=MANIFEST_BYTES) != manifest:
        raise ValueError("The manifest differs from the reading")
    for name, data in files.items():
        if artifacts.read(_beside(envelope["output"], name), max_bytes=RECORD_BYTES) != data:
            raise ValueError(f"The records file {name} differs from the reading")
    return {CHECK: True}, []
