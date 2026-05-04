"""MDM-side helpers for tracked-universe queries and upserts.

Provides read/write primitives that make mdm_company.tracking_status
the source of truth for which companies the warehouse should process.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmCompany, MdmEntity


def get_tracked_ciks(engine: Engine, status_filter: str = "active") -> list[int]:
    """Return CIKs from mdm_company where tracking_status == status_filter."""
    with Session(engine) as session:
        rows = session.execute(
            select(MdmCompany.cik).where(MdmCompany.tracking_status == status_filter)
        ).all()
        return [row[0] for row in rows]


def update_tracking_status(engine: Engine, cik: int, new_status: str) -> bool:
    """Set tracking_status for one CIK. Returns True if the row existed."""
    with Session(engine) as session:
        company = session.execute(
            select(MdmCompany).where(MdmCompany.cik == cik)
        ).scalar_one_or_none()
        if company is None:
            return False
        company.tracking_status = new_status
        session.commit()
        return True


def bulk_upsert_universe(
    engine: Engine,
    rows: list[dict[str, Any]],
    default_status: str = "active",
) -> int:
    """Upsert SEC company rows into mdm_entity + mdm_company.

    Each row must contain: cik (int), ticker (str), exchange (str | None).
    Creates a shell entity if CIK is not already in MDM.
    Never overwrites canonical_name or tracking_status already set by the MDM resolver.
    Returns the number of rows processed.
    """
    count = 0
    with Session(engine) as session:
        for row in rows:
            cik = int(row["cik"])
            ticker = str(row.get("ticker") or "")
            exchange = row.get("exchange")

            company = session.execute(
                select(MdmCompany).where(MdmCompany.cik == cik)
            ).scalar_one_or_none()

            if company is None:
                entity = MdmEntity(
                    entity_id=str(uuid.uuid4()),
                    entity_type="company",
                    resolution_method="cik_exact",
                    confidence=1.0,
                )
                session.add(entity)
                session.flush()
                company = MdmCompany(
                    entity_id=entity.entity_id,
                    cik=cik,
                    canonical_name=ticker or str(cik),
                    primary_ticker=ticker or None,
                    primary_exchange=exchange,
                    tracking_status=default_status,
                )
                session.add(company)
            else:
                if company.tracking_status is None:
                    company.tracking_status = default_status
                if ticker and company.primary_ticker is None:
                    company.primary_ticker = ticker
                if exchange and company.primary_exchange is None:
                    company.primary_exchange = exchange

            count += 1

        session.commit()
    return count
