"""mdm.prepare: a configured reading into a Clean MDM input manifest (mastering to-do 21).

The unit's input is a `source.read` output (normally `from` the run's read
step); its keys say what to take from it, so nothing feed-specific runs:

- `table`: the reading's table whose rows become MDM records;
- optional `record_column`: an object-valued column holding the complete source record;
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

from edgar_warehouse.control_contract import reference

CHECK = "mdm.prepared"
KEYS = {"table", "dataset", "policy", "consumer", "batch_id", "as_of"}
BATCH = 1000
RECORD_BYTES = 16 * 1024**2
MANIFEST_BYTES = 32 * 1024**2


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
    reading = artifacts.json(envelope["input"])
    if reading.get("version") != 1 or not isinstance(reading.get("artifacts"), list):
        raise ValueError("mdm.prepare reads a source.read output (version 1)")
    files, batches = {}, []
    for artifact in reading["artifacts"]:
        rows = artifact["tables"].get(keys["table"])
        if rows is None:
            raise ValueError(f"The reading has no table {keys['table']}")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("mdm.prepare table rows must be objects")
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
                          "publication": {"publication_key": f"{keys['dataset']}:{source}", "revision": 1}},
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
