"""mdm.publish: deliver one committed MDM batch to one consumer (mastering to-do 20e).

The unit's keys name the batch and the consumer. The worker claims that
outbox row through MDM's own publication fence, in the consumer's generation
order (`mdm.claim_outbox_input`, fenced by the envelope's live
lease), delivers it, reads it back, and marks it verified. The `journal`
consumer becomes a Change Journal event under the envelope's run and the
Rules document's source and feed; any other consumer is written to its
contract folder beside the unit's output. The receipt is what MDM records:
the batch, consumer and payload hash of a verified row. The verifier, with
its own MDM login, reads the row and the delivery back and reports
`mdm.published`.

A batch whose earlier generation for the same consumer is undelivered is not
claimable yet; the attempt fails and Bookkeeping retries it.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlparse


from .mdm_merge import _store

CHECK = "mdm.published"


def runtime_files() -> list[Path]:
    from edgar_warehouse.mdm.clean import journal_delivery, payloads, publication, store

    from edgar_warehouse.mdm.clean import execution
    return [Path(m.__file__) for m in (journal_delivery, payloads, publication, store)] + execution.runtime_files()


def _keys(envelope: dict) -> tuple[str, str]:
    keys = envelope["keys"]
    if not keys.get("batch_id") or not keys.get("consumer"):
        raise ValueError("mdm.publish needs the unit's batch_id and consumer")
    return keys["batch_id"], keys["consumer"]


def _publisher(envelope: dict, artifacts, store, consumer: str):
    if consumer == "journal":
        from edgar_warehouse.change_journal.store import ChangeJournal, get_engine
        from edgar_warehouse.mdm.clean.journal_delivery import JournalPublisher

        body = artifacts.json(envelope["rules"])["body"]
        source = body.get("source") or body.get("pipeline")
        feed = envelope["keys"].get("feed") or (body.get("bronze") or {}).get("family") or source
        origin = {"run_id": envelope["claim"]["run_id"], "source": source, "feed": feed}
        return JournalPublisher(ChangeJournal(get_engine()), store.engine, origin)
    from edgar_warehouse.mdm.clean.publication import LocalContractSink

    location = urlparse(envelope["output"])
    if location.scheme != "file":
        raise ValueError("A contract consumer is written to a local folder only")
    return LocalContractSink(Path(unquote(location.path)).parent / consumer)


def receipt(store, batch_id: str, consumer: str) -> bytes:
    from edgar_warehouse.mdm.clean.prepared_publication import receipt as prepared_receipt
    return prepared_receipt(store, batch_id, consumer)


def execute(envelope: dict, artifacts) -> dict:
    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"mdm.publish verifies {CHECK} only")
    batch_id, consumer = _keys(envelope)
    store = _store(restricted=True, envelope=envelope)
    try:
        found = receipt_if_unchanged(store, batch_id, consumer)
        if (found is not None):
            store.deliver_one(consumer, envelope["claim"]["attempt"], None, batch_id=batch_id)
        if found is None:
            publisher = _publisher(envelope, artifacts, store, consumer)
            # False when it is already delivered (a lost acknowledgement) or not
            # claimable yet; the receipt below says which.
            store.deliver_one(consumer, envelope["claim"]["attempt"], publisher, batch_id=batch_id)
            found = receipt(store, batch_id, consumer)
        return artifacts.put_bytes(envelope["output"], found)
    finally:
        store.engine.dispose()


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    batch_id, consumer = _keys(envelope)
    store = _store(restricted=False)
    try:
        expected = receipt(store, batch_id, consumer)
        if json.loads(expected).get("unchanged"):
            return _same(envelope, artifacts, expected)
        from edgar_warehouse.mdm.clean.prepared_publication import retained
        _, row = retained(store, batch_id, consumer)
        payload = json.loads(bytes(row["payload"]))
        publisher = _publisher(envelope, artifacts, store, consumer)
        publisher.verify(f"{consumer}/{batch_id}", payload, json.loads(expected)["payload_hash"])
    finally:
        store.engine.dispose()
    return _same(envelope, artifacts, expected)


def receipt_if_unchanged(store, batch_id: str, consumer: str) -> bytes | None:
    """The receipt of a batch that changed nothing, else None (there is work to deliver)."""
    try:
        found = receipt(store, batch_id, consumer)
    except ValueError:
        return None
    return found if json.loads(found).get("unchanged") else None


def _same(envelope: dict, artifacts, expected: bytes) -> tuple[dict, list]:
    if artifacts.verified(envelope["candidate"], max_bytes=1024**2) != expected:
        raise ValueError("The receipt differs from what MDM holds")
    return {CHECK: True}, []
