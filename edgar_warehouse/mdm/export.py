"""Incremental export from PostgreSQL -> Snowflake EDGARTOOLS_GOLD.

Reads unexported rows from mdm_change_log, materializes the current golden
record for each entity, upserts to the matching Snowflake MDM_* table, and
stamps exported_at = NOW(). No CDC or Kafka — just a drain table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db


DOMAIN_TO_TABLE = {
    "company": ("mdm_company", "MDM_COMPANY", db.MdmCompany),
    "adviser": ("mdm_adviser", "MDM_ADVISER", db.MdmAdviser),
    "person": ("mdm_person", "MDM_PERSON", db.MdmPerson),
    "security": ("mdm_security", "MDM_SECURITY", db.MdmSecurity),
    "fund": ("mdm_fund", "MDM_FUND", db.MdmFund),
}


class SnowflakeWriter:
    """Interface for write targets. Concrete impl uses snowflake-connector-python."""

    def upsert(self, table: str, rows: list[dict], key: str = "entity_id") -> int:
        raise NotImplementedError


@dataclass
class MDMExporter:
    session: Session
    writer: SnowflakeWriter

    def export_pending(self, since: Optional[datetime] = None, entity_type: Optional[str] = None,
                       batch_size: int = 500) -> int:
        stmt = select(db.MdmChangeLog).where(db.MdmChangeLog.exported_at.is_(None))
        if since:
            stmt = stmt.where(db.MdmChangeLog.changed_at >= since)
        if entity_type:
            stmt = stmt.where(db.MdmChangeLog.entity_type == entity_type)
        stmt = stmt.limit(batch_size)

        pending = list(self.session.scalars(stmt))
        if not pending:
            return 0

        by_type: dict[str, list[str]] = {}
        for row in pending:
            by_type.setdefault(row.entity_type, []).append(row.entity_id)

        total = 0
        for et, entity_ids in by_type.items():
            target = DOMAIN_TO_TABLE.get(et)
            if target is None:
                continue
            _pg_table, sf_table, model = target
            domain_rows = list(
                self.session.scalars(select(model).where(model.entity_id.in_(entity_ids)))
            )
            payload = [self._serialize(r) for r in domain_rows]
            total += self.writer.upsert(sf_table, payload)

        now = datetime.now(timezone.utc)
        change_ids = [r.change_id for r in pending]
        self.session.execute(
            update(db.MdmChangeLog)
            .where(db.MdmChangeLog.change_id.in_(change_ids))
            .values(exported_at=now)
        )
        self.session.commit()
        return total

    @staticmethod
    def _serialize(row: Any) -> dict:
        out: dict = {}
        for col in row.__table__.columns:
            val = getattr(row, col.name)
            if hasattr(val, "isoformat"):
                out[col.name] = val.isoformat()
            else:
                out[col.name] = val
        return out
