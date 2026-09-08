"""Per-type high-water-mark checkpoint for MDMPipeline.derive_relationships()'s
incremental source filter (mdm-relationship-incremental-filters wayfinder
map, Ticket 04), plus a resumable CIK/CRD-range sweep cursor for the two
types whose derivation batches over a range that can exceed one capped
run's budget (mdm-relationship-versioning-gap wayfinder map, Ticket 01).

Mirrors lease.py's own upsert shape against a new table -- see
``edgar_warehouse.mdm.database.MdmRelationshipDerivationCheckpoint`` for the
schema and its "no row means scan everything" contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmRelationshipDerivationCheckpoint


def _insert_factory(session: Session):
    dialect_name = session.get_bind().dialect.name
    return sqlite_insert if dialect_name == "sqlite" else postgresql_insert


def get_relationship_watermark(session: Session, checkpoint_key: str) -> Optional[str]:
    """Return this key's current watermark value, or None if never checkpointed.

    None means "scan everything" to every caller -- there is no row yet, not
    a watermark of "the beginning of time".
    """
    row = session.get(MdmRelationshipDerivationCheckpoint, checkpoint_key)
    return row.watermark_value if row is not None else None


def advance_relationship_watermark(
    session: Session,
    checkpoint_key: str,
    *,
    rel_type_name: str,
    watermark_column: str,
    watermark_value: Optional[str],
    updated_at: Optional[datetime] = None,
) -> None:
    """Upsert this key's checkpoint row.

    A no-op when ``watermark_value`` is None -- the caller processed no rows
    this run (empty source, or every row already behind a checkpoint that
    hasn't moved), so there is nothing to advance to. Never regresses the
    watermark backwards: the SET clause only fires when the new value is
    strictly greater than what's stored (plain lexicographic comparison,
    valid for both watermark kinds in use today -- accession-number strings
    and ISO8601 timestamps both compare correctly with ``>``), so a
    concurrent or out-of-order caller can never move this checkpoint back.

    The WHERE guard also fires when the *existing* row's ``watermark_value``
    is NULL (mdm-relationship-versioning-gap Ticket 01's code review caught
    this: SQL's three-valued logic makes ``NULL < excluded.watermark_value``
    evaluate to NULL, never TRUE, so a bare ``<`` comparison would silently
    block the update forever whenever ``record_relationship_sweep_progress``
    had already created a row with a NULL ``watermark_value`` -- exactly the
    state every multi-call sweep passes through before completing. Safe for
    every other relationship type too: their rows, written only through this
    function, never hold a NULL ``watermark_value`` in the first place (the
    no-op-if-None guard above prevents it), so this added branch is simply
    unreachable for them.
    """
    if watermark_value is None:
        return
    now = updated_at or datetime.now(timezone.utc)
    insert_factory = _insert_factory(session)
    stmt = insert_factory(MdmRelationshipDerivationCheckpoint).values(
        checkpoint_key=checkpoint_key,
        rel_type_name=rel_type_name,
        watermark_column=watermark_column,
        watermark_value=watermark_value,
        updated_at=now,
    )
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=[MdmRelationshipDerivationCheckpoint.checkpoint_key],
        set_={
            "watermark_column": excluded.watermark_column,
            "watermark_value": excluded.watermark_value,
            "updated_at": excluded.updated_at,
        },
        where=(
            MdmRelationshipDerivationCheckpoint.watermark_value.is_(None)
            | (MdmRelationshipDerivationCheckpoint.watermark_value < excluded.watermark_value)
        ),
    )
    session.execute(stmt)


@dataclass(frozen=True)
class RelationshipCheckpointState:
    """One key's full checkpoint state, for a sweep-aware caller
    (INSTITUTIONAL_HOLDS/MANAGES_FUND) that needs more than just the
    stable watermark -- see ``get_relationship_checkpoint_state``."""

    watermark_value: Optional[str]
    cursor_value: Optional[str]
    pending_watermark_value: Optional[str]


def get_relationship_checkpoint_state(
    session: Session, checkpoint_key: str
) -> RelationshipCheckpointState:
    """Return this key's full checkpoint state in one query -- the stable
    watermark plus an in-progress sweep's resume cursor and accumulated
    watermark candidate, all None if never checkpointed."""
    row = session.get(MdmRelationshipDerivationCheckpoint, checkpoint_key)
    if row is None:
        return RelationshipCheckpointState(None, None, None)
    return RelationshipCheckpointState(
        row.watermark_value, row.cursor_value, row.pending_watermark_value
    )


def record_relationship_sweep_progress(
    session: Session,
    checkpoint_key: str,
    *,
    rel_type_name: str,
    watermark_column: str,
    cursor_value: Optional[str],
    pending_watermark_value: Optional[str],
    updated_at: Optional[datetime] = None,
) -> None:
    """Persist an in-progress (not yet complete) CIK/CRD sweep's resume
    position and accumulated watermark candidate.

    Always overwrites ``cursor_value``/``pending_watermark_value`` -- this
    is "here's the current progress of this still-running sweep," always
    correct to move forward, unlike ``watermark_value``'s monotonic guard.
    Never touches ``watermark_value`` itself: the stable boundary this
    sweep is scanning against must not move until
    ``complete_relationship_sweep`` confirms the whole range was covered
    under it -- moving it mid-sweep would let a not-yet-revisited slice
    of CIK/CRD space get silently watermarked-out by a later, unrelated
    call's progress.
    """
    now = updated_at or datetime.now(timezone.utc)
    insert_factory = _insert_factory(session)
    stmt = insert_factory(MdmRelationshipDerivationCheckpoint).values(
        checkpoint_key=checkpoint_key,
        rel_type_name=rel_type_name,
        watermark_column=watermark_column,
        watermark_value=None,
        cursor_value=cursor_value,
        pending_watermark_value=pending_watermark_value,
        updated_at=now,
    )
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=[MdmRelationshipDerivationCheckpoint.checkpoint_key],
        set_={
            "cursor_value": excluded.cursor_value,
            "pending_watermark_value": excluded.pending_watermark_value,
            "updated_at": excluded.updated_at,
        },
    )
    session.execute(stmt)


def complete_relationship_sweep(
    session: Session,
    checkpoint_key: str,
    *,
    rel_type_name: str,
    watermark_column: str,
    watermark_value: Optional[str],
    updated_at: Optional[datetime] = None,
) -> None:
    """A CIK/CRD sweep just covered the entire range under one stable
    watermark boundary: advance the stable ``watermark_value`` (monotonic,
    via the existing ``advance_relationship_watermark`` -- a no-op if
    ``watermark_value`` is None, meaning nothing new was found anywhere in
    the whole range) and reset ``cursor_value``/``pending_watermark_value``
    to NULL so the next call starts a fresh sweep from the beginning under
    the new watermark.
    """
    advance_relationship_watermark(
        session,
        checkpoint_key,
        rel_type_name=rel_type_name,
        watermark_column=watermark_column,
        watermark_value=watermark_value,
        updated_at=updated_at,
    )
    now = updated_at or datetime.now(timezone.utc)
    session.execute(
        update(MdmRelationshipDerivationCheckpoint)
        .where(MdmRelationshipDerivationCheckpoint.checkpoint_key == checkpoint_key)
        .values(cursor_value=None, pending_watermark_value=None, updated_at=now)
    )
