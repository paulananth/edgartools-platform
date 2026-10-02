"""Publish Clean MDM's committed local intent without copying business payloads."""

from __future__ import annotations

from datetime import UTC

from sqlalchemy import text

from edgar_warehouse.change_journal.store import ChangeJournal, JournalConflict, envelope


class JournalPublisher:
    def __init__(self, journal: ChangeJournal, owner_engine, book):
        self.journal, self.owner_engine, self.book = journal, owner_engine, book

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
        run, config, _, items = self.book._frozen(payload["run_id"])
        # Historical pending publications stay on their original stack. Only
        # batches named by a fresh root's immutable worklist may enter here.
        scoped = False
        mdm_steps = {
            step["name"]
            for step in config["steps"]
            if step["operation"].startswith("mdm.")
        }
        for item in items:
            if item["step"] not in mdm_steps:
                continue
            item = self.book._resolve_item({**item, "run_id": run["run_id"]})
            command = self.book.artifacts.json(item["unit"]["input"])
            if (
                command.get("batch_id", command.get("command", {}).get("batch_id"))
                == batch
            ):
                scoped = True
                break
        if not scoped:
            raise JournalConflict("MDM publication is outside the fresh root manifest")
        submission = run["submission"]
        document = self.book.artifacts.json(submission["rules"])["body"]
        source = document.get("source", submission["name"])
        return envelope(
            producer="mdm",
            event_key=key,
            run_id=payload["run_id"],
            source=source,
            feed=submission["scope"].get(
                "feed", document.get("bronze", {}).get("family", submission["target"])
            ),
            event_type="mdm.committed",
            occurred_at=row["created_at"].astimezone(UTC).isoformat(),
            scope={"batch_id": batch, "generation": str(payload["generation"])},
            evidence=[{"uri": f"mdm-outbox:///{key}", "sha256": expected_hash}],
        )

    def publish(self, key, payload, expected_hash):
        self.journal.append(self._event(key, payload, expected_hash))

    def validate_batch(self, batch_id):
        """Reject historical/out-of-scope intent before claiming its outbox lease."""
        with self.owner_engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT payload,payload_hash FROM mdm.outbox WHERE batch_id=:b AND consumer='journal'"
                    ),
                    {"b": batch_id},
                )
                .mappings()
                .one()
            )
        self._event(f"journal/{batch_id}", row["payload"], row["payload_hash"])

    def verify(self, key, payload, expected_hash):
        event = self._event(key, payload, expected_hash)
        receipt = self.journal.get("mdm", key)
        self.journal.verify(receipt, expected=event)
        return expected_hash
