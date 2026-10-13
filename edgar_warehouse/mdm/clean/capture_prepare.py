"""A captured source's `mastering` input manifest: read, records, merge.

For any source whose reading keeps each captured document whole: its `read`
block has one table with one column holding the record (SEC Person reads each
filer's submissions document this way). A bundle is up to the source's `max_artifacts` documents of one
receipt-bound raw capture. This writer checks them against the receipts and
freezes every unit's input; Bookkeeping runs the source's `mastering` target
(`rules run --source <source> --target mastering`) and the registered workers
do the work:

- `read`: the documents read by the source's own reading, cut into units of
  at most 8 MiB of documents;
- `records`: every reading of the bundle as one publication (`mdm.prepare`);
- `merge`: that manifest through the Merge Stage (`mdm.merge`).

The records input is composed: Bookkeeping fills it with the verified readings
it names. Nothing here names a source or a kind.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files as rules_files
from . import raw_capture
from .evidence import instant
from .raw_capture import read_bounded
from .store import digest

TARGET = "mastering"
DOCUMENTS_BYTES = 1024**2
READ_BYTES = 8 * 1024**2  # a read unit's documents
# One records unit reads the whole bundle, inside mdm.prepare's 32 MiB of
# readings; a reading kept whole is about its documents' size.
BUNDLE_BYTES = 24 * 1024**2


def record_shape(source: dict) -> tuple[str, str]:
    """The reading's one table and its one column, which holds each document whole."""
    tables = (source.get("read") or {}).get("tables") or {}
    if len(tables) == 1:
        ((table, body),) = tables.items()
        columns = body.get("columns") or {}
        if len(columns) == 1:
            ((column, spec),) = columns.items()
            if spec == {"value": {"path": "."}}:
                return table, column
    raise ValueError("The source's reading must keep each document whole: one table with one column "
                     "whose value is the whole document (`value: {path: .}`)")


def write_capture_manifest(
    *,
    source: str,
    capture: str,
    documents: str,
    capture_run: str,
    output: str,
    as_of: str,
    revision: int,
) -> dict:
    """The source's `mastering` input manifest for one bundle of captured documents.

    `documents` lists the bundle's documents by receipt key (at most the
    source's `execution.max_artifacts`, and at most 24 MiB). `capture_run` is
    the caller's approved run ID of the capture. Returns the report: the
    manifest's reference and the publication."""
    if type(revision) is not int or revision < 0:
        raise ValueError("Require a nonnegative explicit publication revision")
    instant(as_of)
    if source not in {p.name for p in (rules_files.ROOT / "sources").iterdir() if p.is_dir()}:
        raise ValueError(f"No source named {source!r} under rules/sources")
    reading = rules_files.source(source)
    table, column = record_shape(reading)
    datasets = list((reading.get("mdm") or {}))
    if len(datasets) != 1:
        raise ValueError("The source must declare exactly one MDM dataset")
    (dataset,) = datasets
    if TARGET not in ((reading.get("bookkeeping") or {}).get("targets") or {}):
        raise ValueError(f"The source declares no `{TARGET}` target")
    limit = reading["execution"]["max_artifacts"]
    folder = Path(capture).resolve()
    receipts_raw, receipts = raw_capture.receipts(folder)
    documents_raw = read_bounded(Path(documents).resolve(), DOCUMENTS_BYTES)
    keys = json.loads(documents_raw)
    if (not isinstance(keys, list) or not 1 <= len(keys) <= limit
            or len(set(keys)) != len(keys) or any(not isinstance(key, str) for key in keys)):
        raise ValueError(f"A bundle names 1..{limit} distinct documents")
    keys = sorted(keys)  # a bundle is its documents, in key order, however they are listed
    # Each document equal to its receipt before it is frozen; its size cuts the read units.
    sized = [(key, len(raw_capture.document_bytes(folder, receipts, key))) for key in keys]
    if sum(size for _, size in sized) > BUNDLE_BYTES:
        raise ValueError(f"A bundle's documents exceed {BUNDLE_BYTES} bytes; name fewer")
    # The publication is the documents themselves (key and receipt), not the
    # list file's bytes: the same documents are one publication.
    documents_hash = digest([[key, receipts[key]] for key in keys])
    publication_key = f"{capture_run}:{source}:{documents_hash}"
    policy = digest(rules_files.policy())
    # The consumer and batch ids name what shapes the records (the reading, the
    # contract with its quality rule, the policy): a rerun under other rules or
    # another time is a new consumer, not a reused batch key. The steps do not.
    bundle = digest([publication_key, revision, as_of, reading["read"], reading["mdm"], policy])
    publication = {"publication_key": publication_key, "revision": revision, "as_of": as_of,
                   "consumer": f"{dataset}/{bundle}", "batch_id": f"{source}:{bundle}"}
    store = Artifacts()
    root = Path(output).resolve().as_uri()
    inputs = root + "/inputs"
    contract = store.put(inputs, rules_files.load(rules_files.ROOT / "sources" / source / "source.yaml"))
    read, start = [], 0
    for unit in raw_capture.slices(sized, READ_BYTES, limit):
        artifacts = [raw_capture.document(folder, receipts, key) for key in unit]
        read.append(_unit(f"{root}/read/{start}.reading.json", {"unit": f"read-{start}"},
                          store.put(inputs, {"version": 1, "contract": contract, "artifacts": artifacts})))
        start += len(unit)
    records = _unit(f"{root}/records/manifest.json", {
        "unit": "records", "table": table, "record_column": column, "dataset": dataset, "policy": policy,
        "consumer": publication["consumer"], "batch_id": publication["batch_id"], "as_of": as_of,
        "publication_key": publication_key, "revision": str(revision)}, {"compose": {
            "document": {"version": 1, "readings": {"slot": "read"}},
            "slots": {"read": [{"step": "read", "key": unit["keys"]["unit"]} for unit in read]}}})
    merge = {"keys": {"batch_id": publication["batch_id"], "consumer": publication["consumer"]},
             "input": {"from": {"step": "records", "key": "records"}}, "output": f"{root}/merge.json", "cursor": {}}
    manifest = store.put(root, {"version": 2, "steps": {"read": read, "records": [records], "merge": [merge]}})
    return {
        "source": source,
        "source_code": dataset,
        "target": TARGET,
        "manifest": manifest,
        "publication": publication,
        "policy_digest": policy,
        "scope": {"documents": len(keys), "receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
                  "capture_run_id": capture_run},
    }


def _unit(output: str, keys: dict, source: dict) -> dict:
    return {"keys": {**keys, "destination": output}, "input": source, "output": output, "cursor": {}}
