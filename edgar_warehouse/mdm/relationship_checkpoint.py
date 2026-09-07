"""Per-type high-water-mark checkpoint for MDMPipeline.derive_relationships()'s
incremental source filter (mdm-relationship-incremental-filters wayfinder
map, Ticket 04).

Mirrors lease.py's own upsert shape against a new table -- see
``edgar_warehouse.mdm.database.MdmRelationshipDerivationCheckpoint`` for the
schema and its "no row means scan everything" contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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
            MdmRelationshipDerivationCheckpoint.watermark_value < excluded.watermark_value
        ),
    )
    session.execute(stmt)
