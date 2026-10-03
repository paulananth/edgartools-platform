"""Publish Clean MDM's committed local intent without copying business payloads."""

from __future__ import annotations

from datetime import UTC

from sqlalchemy import text

from edgar_warehouse.change_journal.store import ChangeJournal, JournalConflict, envelope


class JournalPublisher:
    """Deliver one committed `journal` outbox row as a Change Journal event.

    `origin` names the Bookkeeping run, source and feed the event belongs to;
    the `mdm.publish` worker takes them from its task envelope (mastering
    to-do 20e). Nothing here reads Bookkeeping: the batch is in scope because
    the run's frozen unit names it.
    """

    def __init__(self, journal: ChangeJournal, owner_engine, origin: dict):
        if set(origin) != {"run_id", "source", "feed"} or not all(origin.values()):
            raise ValueError("Journal publication requires its run, source and feed")
        self.journal, self.owner_engine, self.origin = journal, owner_engine, origin

    def _event(self, key: str, payload: dict, expected_hash: str) -> dict:
        consumer, separator, batch = key.partition("/")
        if consumer != "journal" or not separator or not batch:
            raise ValueError(
                "Journal publication requires its original journal/batch key"
            )
        with self.owner_engine.connect() as conn:
            row = (
                conn.execute(
                    text("""SELECT b.created_at,p.payload,p.payload_hash,
                encode(sha256(convert_to(p.payload::text,'UTF8')),'hex') AS actual_hash
                FROM mdm.outbox p JOIN mdm.batch b USING(batch_id)
                WHERE p.batch_id=:b AND p.consumer='journal'"""),
                    {"b": batch},
                )
                .mappings()
                .one()
            )
        if (
            row["payload"] != payload
            or row["payload_hash"] != expected_hash
            or row["actual_hash"] != expected_hash
        ):
            raise JournalConflict(
                "MDM publication disagrees with committed local evidence"
            )
        return envelope(
            producer="mdm",
            event_key=key,
            run_id=self.origin["run_id"],
            source=self.origin["source"],
            feed=self.origin["feed"],
            event_type="mdm.committed",
            occurred_at=row["created_at"].astimezone(UTC).isoformat(),
            scope={"batch_id": batch, "generation": str(payload["generation"])},
            evidence=[{"uri": f"mdm-outbox:///{key}", "sha256": expected_hash}],
        )

    def publish(self, key, payload, expected_hash):
        self.journal.append(self._event(key, payload, expected_hash))

    def verify(self, key, payload, expected_hash):
        event = self._event(key, payload, expected_hash)
        receipt = self.journal.get("mdm", key)
        self.journal.verify(receipt, expected=event)
        return expected_hash
