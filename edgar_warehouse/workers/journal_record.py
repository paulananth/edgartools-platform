"""journal.record: record in the Change Journal each file a run processed.

The last step of a source's target, after its merge is verified (ticket 22).
Its input names the files and their processing identity
(`changed_files.record_input`). A file's first record stands: one
`file.processed` event per file not yet recorded under that identity, dated
by the run's own time so a retry appends the same events; a file another run
recorded first (a forced run, two runs at once) keeps that record. A forced
run also records itself once (`files.forced`). The verifier reads back, for
every file, the record under its key.
"""
from __future__ import annotations

import json

CHECK = "journal.recorded"
MAX_INPUT = 8 * 1024**2


def _events(envelope: dict, body: dict) -> list[dict]:
    from edgar_warehouse.change_journal.store import envelope as event
    from edgar_warehouse.mdm.clean import changed_files

    if body.get("version") != 1 or not isinstance(body.get("files"), list) or not body["files"]:
        raise ValueError("journal.record reads a version 1 list of files")
    return [event(producer=changed_files.PRODUCER,
                  event_key=changed_files.event_key(body["source"], body["identity"], f["key"], f["sha256"]),
                  run_id=envelope["claim"]["run_id"], source=body["source"], feed=body["feed"],
                  event_type=changed_files.EVENT_TYPE, occurred_at=body["occurred_at"],
                  scope={"file": f["key"], "identity": body["identity"], "forced": "yes" if body["forced"] else "no"},
                  evidence=[{"uri": f["uri"], "sha256": f["sha256"]}])
            for f in body["files"]]


def _journal():
    from edgar_warehouse.mdm.clean.changed_files import journal

    return journal()


def _forced(envelope: dict, body: dict) -> dict:
    """A forced run's own record: which run reprocessed which files."""
    from edgar_warehouse.change_journal.store import envelope as event
    from edgar_warehouse.mdm.clean import changed_files

    return event(producer=changed_files.PRODUCER, event_key=f"files.forced:{envelope['claim']['run_id']}",
                 run_id=envelope["claim"]["run_id"], source=body["source"], feed=body["feed"],
                 event_type="files.forced", occurred_at=body["occurred_at"],
                 scope={"identity": body["identity"], "files": str(len(body["files"]))},
                 evidence=[envelope["input"]])


def _matches(receipt: dict | None, value: dict) -> bool:
    """A record of this file under its key: the same file, hash and identity, from any run."""
    if receipt is None:
        return False
    found = receipt["event"]
    return (found["event_key"], found["evidence"], found["scope"]["identity"], found["scope"]["file"]) == (
        value["event_key"], value["evidence"], value["scope"]["identity"], value["scope"]["file"])


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.change_journal import JournalConflict
    from edgar_warehouse.mdm.clean import changed_files

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"journal.record verifies {CHECK} only")
    body = json.loads(artifacts.verified(envelope["input"], max_bytes=MAX_INPUT))
    journal, values = _journal(), _events(envelope, body)
    seen = journal.found(changed_files.PRODUCER, [v["event_key"] for v in values])
    receipts = []
    for value in values:
        receipt = journal.get(value["producer"], value["event_key"]) if value["event_key"] in seen else None
        if receipt is None:
            try:
                receipt = journal.append(value)
            except JournalConflict:  # another run recorded this file first: its record stands
                receipt = journal.get(value["producer"], value["event_key"])
        if not _matches(receipt, value):
            raise ValueError(f"The Change Journal records {value['scope']['file']} otherwise")
        receipts.append(receipt)
    if body["forced"]:
        receipts.append(journal.append(_forced(envelope, body)))
    return artifacts.put_bytes(envelope["output"], json.dumps(
        {"version": 1, "receipts": receipts}, sort_keys=True, separators=(",", ":")).encode())


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    body = json.loads(artifacts.verified(envelope["input"], max_bytes=MAX_INPUT))
    expected = _events(envelope, body)
    receipts = json.loads(artifacts.verified(envelope["candidate"], max_bytes=MAX_INPUT))["receipts"]
    journal = _journal()
    if body["forced"]:
        *receipts, forced = receipts if receipts else [None]
        journal.verify(forced, expected=_forced(envelope, body))
    if len(receipts) != len(expected):
        raise ValueError("The receipts do not name every file")
    for receipt, value in zip(receipts, expected, strict=True):
        if not _matches(journal.verify(receipt), value):
            raise ValueError(f"The Change Journal records {value['scope']['file']} otherwise")
    return {CHECK: True}, []
