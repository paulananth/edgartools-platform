"""journal.record: record in the Change Journal each file a run processed.

The last step of a source's target, after its merge is verified (ticket 22).
Its input names the files and their processing identity
(`changed_files.record_input`); it appends one `file.processed` event per
file, dated by the run's own time so a retry appends the same events, and
writes their receipts. The verifier reads every event back. An
identical retry returns the original receipts; the journal refuses another
body under the same key.
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


def execute(envelope: dict, artifacts) -> dict:
    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"journal.record verifies {CHECK} only")
    body = json.loads(artifacts.verified(envelope["input"], max_bytes=MAX_INPUT))
    journal = _journal()
    receipts = [journal.append(value) for value in _events(envelope, body)]
    return artifacts.put_bytes(envelope["output"], json.dumps(
        {"version": 1, "receipts": receipts}, sort_keys=True, separators=(",", ":")).encode())


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    body = json.loads(artifacts.verified(envelope["input"], max_bytes=MAX_INPUT))
    expected = _events(envelope, body)
    receipts = json.loads(artifacts.verified(envelope["candidate"], max_bytes=MAX_INPUT))["receipts"]
    if len(receipts) != len(expected):
        raise ValueError("The receipts do not name every file")
    journal = _journal()
    for receipt, value in zip(receipts, expected, strict=True):
        journal.verify(receipt, expected=value)
    return {CHECK: True}, []
