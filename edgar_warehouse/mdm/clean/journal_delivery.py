"""Publish MDM's committed local intent without copying business payloads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import text

from edgar_warehouse.change_journal.store import ChangeJournal, JournalConflict, envelope

from .payloads import prepare
from .store import Conflict


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
        from .prepared_registry import installed
        origin = self.origin
        with self.owner_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            api = installed(conn)
            if api is not None:
                rows = api.read_batches([batch], outboxes=True, connection=conn)
                matches = [row for row in rows if bytes(row["consumer_bytes"]).decode() == consumer]
                if len(matches) != 1:
                    raise JournalConflict("MDM holds no unambiguous Journal publication")
                row = matches[0]
                retained = api.publication_context(batch, consumer, connection=conn)
                if retained is None:
                    raise JournalConflict("MDM publication has no retained delivery origin")
                origin = json.loads(retained)
                if set(origin) != {"run_id","source","feed"} or not all(origin.values()):
                    raise JournalConflict("MDM publication has an invalid retained delivery origin")
                committed = json.loads(bytes(row["payload"]))
                metadata = api.batch_metadata(int(row["generation"]), limit=1, connection=conn)
                if not metadata or metadata[0]["generation"] != row["generation"]:
                    raise JournalConflict("MDM publication has no original recording time")
                occurred = (datetime(1970,1,1,tzinfo=UTC)
                            + timedelta(microseconds=metadata[0]["recorded_at"])).isoformat()
            else:
                row = conn.execute(text("""SELECT * FROM mdm.outbox_input
                    WHERE batch_id=:b AND consumer='journal'"""), {"b":batch}).mappings().one()
                try:
                    committed = prepare(row)
                except Conflict as exc:
                    raise JournalConflict("MDM publication disagrees with committed local evidence") from exc
                occurred = row["created_at"].astimezone(UTC).isoformat()
        if (
            committed != payload
            or row["payload_hash"] != expected_hash
        ):
            raise JournalConflict(
                "MDM publication disagrees with committed local evidence"
            )
        return envelope(
            producer="mdm",
            event_key=key,
            run_id=origin["run_id"],
            source=origin["source"],
            feed=origin["feed"],
            event_type="mdm.committed",
            occurred_at=occurred,
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
