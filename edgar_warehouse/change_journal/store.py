"""Versioned journal receipts. No legacy store or MDM connection fallback."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.config import canonical, reference


class JournalConflict(ValueError):
    """An original producer key names conflicting immutable content."""


def get_engine(url: str | None = None):
    return create_engine(
        url or os.environ["CHANGE_JOURNAL_DATABASE_URL"], pool_pre_ping=True
    )


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
    keys = {
        "version",
        "producer",
        "event_key",
        "run_id",
        "source",
        "feed",
        "event_type",
        "occurred_at",
        "scope",
        "evidence",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ValueError("Unsupported Change Journal envelope")
    for key in ("producer", "source", "feed", "event_type"):
        if not isinstance(value[key], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}", value[key]
        ):
            raise ValueError(f"Invalid journal {key}")
    if (
        not isinstance(value["event_key"], str)
        or not 1 <= len(value["event_key"]) <= 2048
    ):
        raise ValueError("An original event key is required")
    if str(UUID(value["run_id"])) != value["run_id"]:
        raise ValueError("Journal root run_id must be a canonical UUID")
    stamp = datetime.fromisoformat(value["occurred_at"])
    if stamp.tzinfo is None or stamp.utcoffset() != UTC.utcoffset(stamp):
        raise ValueError("Journal timestamp must have UTC timezone")
    if (
        not isinstance(value["scope"], dict)
        or len(value["scope"]) > 32
        or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or not v
            for k, v in value["scope"].items()
        )
    ):
        raise ValueError("Journal scopes contain identifiers only")
    if (
        not isinstance(value["evidence"], list)
        or not 1 <= len(value["evidence"]) <= 100
    ):
        raise ValueError("Journal events require bounded evidence references")
    for ref in value["evidence"]:
        reference(ref)
    canonical(value)


class ChangeJournal:
    def __init__(self, engine):
        self.engine = engine

    def append(self, value: dict) -> dict:
        validate(value)
        body = canonical(value)
        sha = hashlib.sha256(body.encode()).hexdigest()
        try:
            with self.engine.begin() as conn:
                receipt = conn.scalar(
                    text("SELECT journal.append(:b,:h)"), {"b": body, "h": sha}
                )
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) == "23505":
                raise JournalConflict(
                    "Producer event key already names different content"
                ) from exc
            raise
        # Separate read transaction reconciles durable receipt before a producer
        # acknowledges its local delivery intent. Lost acknowledgements retry.
        return self.verify(receipt, expected=value)

    def get(self, producer: str, event_key: str) -> dict | None:
        with self.engine.connect() as conn:
            return conn.scalar(
                text("SELECT journal.get(:p,:k)"), {"p": producer, "k": event_key}
            )

    def list(
        self,
        *,
        source: str | None = None,
        feed: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
        after: int = 0,
    ) -> list[dict]:
        if (
            type(limit) is not int
            or not 1 <= limit <= 1000
            or type(after) is not int
            or after < 0
        ):
            raise ValueError(
                "Journal inspection requires limit 1..1000 and nonnegative after"
            )
        with self.engine.connect() as conn:
            return conn.scalar(
                text("SELECT journal.list_events(:s,:f,CAST(:r AS uuid),:n,:a)"),
                {"s": source, "f": feed, "r": run_id, "n": limit, "a": after},
            )

    def verify(self, receipt: dict, *, expected: dict | None = None) -> dict:
        if not isinstance(receipt, dict) or set(receipt) != {
            "id",
            "canonical_hash",
            "recorded_at",
            "event",
        }:
            raise ValueError("Malformed Change Journal receipt")
        event = receipt["event"]
        validate(event)
        sha = hashlib.sha256(canonical(event).encode()).hexdigest()
        if receipt["canonical_hash"] != sha or (
            expected is not None and event != expected
        ):
            raise JournalConflict("Journal receipt content or hash mismatch")
        stored = self.get(event["producer"], event["event_key"])
        if stored != receipt:
            raise JournalConflict("Journal durable read-back mismatch")
        return receipt

    def status(self, *, source: str | None = None, feed: str | None = None) -> dict:
        with self.engine.connect() as conn:
            return conn.scalar(
                text("SELECT journal.status(:s,:f)"), {"s": source, "f": feed}
            )
