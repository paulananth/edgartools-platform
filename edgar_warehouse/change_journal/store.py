"""Versioned journal receipts, on the journal's own connection only."""

from __future__ import annotations

import os
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import canonical, reference


# Keys `journal.found` takes in one call: migration 002's bound, held equal by
# `test_change_journal_postgres.py`.
FOUND_LIMIT = 10_000


class JournalConflict(ValueError):
    """An original producer key names conflicting immutable content."""


def get_engine(url: str | None = None):
    target = make_url(url or os.environ["CHANGE_JOURNAL_DATABASE_URL"])
    defaults = {"postgresql":"postgresql+psycopg2", "mysql":"mysql+pymysql", "mssql":"mssql+pymssql"}
    if target.drivername in defaults:
        target = target.set(drivername=defaults[target.drivername])
    return create_engine(target, pool_pre_ping=True, hide_parameters=True)


def envelope(
    *,
    producer: str,
    event_key: str,
    run_id: str,
    source: str,
    feed: str,
    event_type: str,
    occurred_at: str,
    evidence: list[dict],
    scope: dict | None = None,
) -> dict:
    value = {
        "version": 1,
        "producer": producer,
        "event_key": event_key,
        "run_id": str(UUID(run_id)),
        "source": source,
        "feed": feed,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "scope": {} if scope is None else scope,
        "evidence": evidence,
    }
    validate(value)
    return value


def validate(value: dict) -> None:
    """The shared native contract validates every producer, independent of storage."""
    import edgar_control
    import json
    edgar_control.prepare_journal_event(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


class ChangeJournal:
    def __init__(self, engine):
        self.engine = engine

    def append(self, value: dict) -> dict:
        import edgar_control
        import json
        from . import storage
        prepared = json.loads(edgar_control.prepare_journal_event(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",", ":"))))
        try:
            storage.record_event(self.engine, prepared["body"], prepared["canonical_hash"])
        except DBAPIError as exc:
            # Classify only the storage interface's explicit key/content conflict.
            if "journal_content_conflict" in str(exc.orig):
                raise JournalConflict("Producer event key already names different content") from None
            raise
        receipt = self.get(prepared["producer"], prepared["event_key"])
        if receipt is None:
            raise JournalConflict("Journal durable read-back mismatch")
        edgar_control.check_journal_receipt(canonical(receipt), prepared["body"])
        return receipt

    def get(self, producer: str, event_key: str) -> dict | None:
        import edgar_control
        import json
        from . import storage
        stored = storage.get_event(self.engine, producer, event_key)
        return json.loads(edgar_control.prepare_journal_receipt(canonical(stored))) if stored else None

    def get_many(self, producer: str, event_keys: list[str]) -> dict[str, dict]:
        """The receipt of each key the journal holds, in one read of up to 400 keys."""
        import edgar_control
        import json
        from . import storage
        stored = storage.get_events(self.engine, producer, event_keys)
        return {key: json.loads(edgar_control.prepare_journal_receipt(canonical(row))) for key, row in stored.items()}

    def append_many(self, values: list[dict]) -> list[dict]:
        """`append` for a file set: every event on one connection, then one read back. A content conflict
        raises `JournalConflict` (events before it may stay on MySQL); the caller settles the rest singly."""
        import edgar_control
        import json
        from . import storage
        prepared = [json.loads(edgar_control.prepare_journal_event(
            json.dumps(v, ensure_ascii=False, allow_nan=False, separators=(",", ":")))) for v in values]
        try:
            storage.record_events(self.engine, [(p["body"], p["canonical_hash"]) for p in prepared])
        except DBAPIError as exc:
            if "journal_content_conflict" in str(exc.orig):
                raise JournalConflict("Producer event key already names different content") from None
            raise
        stored = {}
        for producer in dict.fromkeys(p["producer"] for p in prepared):
            stored.update({(producer, k): r for k, r in self.get_many(
                producer, [p["event_key"] for p in prepared if p["producer"] == producer]).items()})
        receipts = []
        for p in prepared:
            receipt = stored.get((p["producer"], p["event_key"]))
            if receipt is None:
                raise JournalConflict("Journal durable read-back mismatch")
            edgar_control.check_journal_receipt(canonical(receipt), p["body"])
            receipts.append(receipt)
        return receipts

    def found(self, producer: str, event_keys: list[str]) -> set[str]:
        from . import storage
        import edgar_control
        edgar_control.prepare_journal_read(canonical({"operation":"found", "producer":producer, "keys":event_keys}))
        return storage.found_events(self.engine, producer, event_keys)

    def list(self, *, source: str | None = None, feed: str | None = None,
             run_id: str | None = None, limit: int = 100, after: int = 0) -> list[dict]:
        import edgar_control
        import json
        from . import storage
        prepared = json.loads(edgar_control.prepare_journal_read(canonical({"operation":"list", "limit":limit,"after":after,"run_id":run_id})))
        records = storage.list_events(self.engine, source=source, feed=feed, run_id=prepared["run_id"], limit=limit, after=after)
        return [json.loads(edgar_control.prepare_journal_receipt(canonical(row))) for row in records]

    def verify(self, receipt: dict, *, expected: dict | None = None) -> dict:
        import edgar_control
        import json
        try:
            prepared = json.loads(edgar_control.check_journal_receipt(canonical(receipt), canonical(expected) if expected is not None else None))
            stored = self.get(prepared["producer"], prepared["event_key"])
            edgar_control.confirm_journal_receipt(canonical(receipt), canonical(stored))
        except ValueError as error:
            if "mismatch" in str(error):
                raise JournalConflict(str(error)) from None
            raise
        return receipt

    def verify_many(self, receipts: list[dict]) -> list[dict]:
        """`verify` for a file set: each receipt checked against what the journal holds, read once."""
        import edgar_control
        import json
        try:
            checked = [json.loads(edgar_control.check_journal_receipt(canonical(r), None)) for r in receipts]
            stored = {}
            for producer in dict.fromkeys(c["producer"] for c in checked):
                stored[producer] = self.get_many(producer, [c["event_key"] for c in checked if c["producer"] == producer])
            for receipt, c in zip(receipts, checked, strict=True):
                edgar_control.confirm_journal_receipt(canonical(receipt), canonical(stored[c["producer"]].get(c["event_key"])))
        except ValueError as error:
            if "mismatch" in str(error):
                raise JournalConflict(str(error)) from None
            raise
        return receipts

    def status(self, *, source: str | None = None, feed: str | None = None) -> dict:
        from . import storage
        return storage.event_status(self.engine, source=source, feed=feed)
