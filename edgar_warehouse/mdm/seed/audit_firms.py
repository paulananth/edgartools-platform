"""Audit firm seed data and seeder function.

Seeds the Big 4 + Next 6 PCAOB-registered audit firms into MDM.  Covers ~99.5%
of all exchange-listed company audits (AD-09).

This module is called by:
  edgar-warehouse mdm seed-audit-firms   (CLI command — idempotent)
  migration 005_fundamentals_relationships.sql  (SQL-only bootstrap path)

The Python seeder uses SQLAlchemy ORM so it runs correctly against any
configured MDM_DATABASE_URL, including local dev, staging, and production.
It is idempotent: firms that already exist (matched by pcaob_firm_id, then
by canonical_name) are skipped without error.

PCAOB IDs sourced from:
  https://pcaobus.org/Registration/Firms (verified 2025-05)
"""

from __future__ import annotations

import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Seed data — Big 4 + Next 6 (10 firms total)
# ---------------------------------------------------------------------------

PCAOB_SEED: list[dict[str, Any]] = [
    # ── Big 4 ──────────────────────────────────────────────────────────────
    {
        "firm_name": "PricewaterhouseCoopers LLP",
        "pcaob_firm_id": "238",
        "big4": True,
        "canonical_name": "pricewaterhousecoopers llp",
        "aliases": ["pwc", "pricewaterhousecoopers", "pricewaterhouse coopers llp"],
    },
    {
        "firm_name": "Deloitte & Touche LLP",
        "pcaob_firm_id": "34",
        "big4": True,
        "canonical_name": "deloitte & touche llp",
        "aliases": ["deloitte", "deloitte & touche", "deloitte touche llp"],
    },
    {
        "firm_name": "Ernst & Young LLP",
        "pcaob_firm_id": "42",
        "big4": True,
        "canonical_name": "ernst & young llp",
        "aliases": ["ey", "ernst & young", "ernst and young llp", "ernst young llp"],
    },
    {
        "firm_name": "KPMG LLP",
        "pcaob_firm_id": "185",
        "big4": True,
        "canonical_name": "kpmg llp",
        "aliases": ["kpmg", "kpmg peat marwick"],
    },
    # ── Next 6 (mid-tier) ───────────────────────────────────────────────────
    {
        "firm_name": "Grant Thornton LLP",
        "pcaob_firm_id": "248",
        "big4": False,
        "canonical_name": "grant thornton llp",
        "aliases": ["grant thornton", "grant thornton international"],
    },
    {
        "firm_name": "BDO USA LLP",
        "pcaob_firm_id": "243",
        "big4": False,
        "canonical_name": "bdo usa llp",
        "aliases": ["bdo", "bdo usa", "bdo seidman llp"],
    },
    {
        "firm_name": "RSM US LLP",
        "pcaob_firm_id": "49",
        "big4": False,
        "canonical_name": "rsm us llp",
        "aliases": ["rsm", "rsm us", "mcgladrey llp", "mcgladrey & pullen"],
    },
    {
        "firm_name": "Forvis Mazars LLP",
        "pcaob_firm_id": "686",
        "big4": False,
        "canonical_name": "forvis mazars llp",
        "aliases": ["forvis", "bkd llp", "dixon hughes goodman llp", "dhg llp"],
    },
    {
        "firm_name": "CBIZ CPAs PC",
        "pcaob_firm_id": "71",
        "big4": False,
        "canonical_name": "cbiz cpas pc",
        "aliases": ["cbiz", "cbiz mhm llc", "mayer hoffman mccann"],
    },
    {
        "firm_name": "Moss Adams LLP",
        "pcaob_firm_id": "659",
        "big4": False,
        "canonical_name": "moss adams llp",
        "aliases": ["moss adams", "moss & adams"],
    },
]


# ---------------------------------------------------------------------------
# Seeder function
# ---------------------------------------------------------------------------

def seed_audit_firms(session: Any) -> dict[str, int]:
    """Upsert Big 4 + Next 6 audit firms into MDM.

    Parameters
    ----------
    session:
        An open SQLAlchemy Session connected to the MDM database.

    Returns
    -------
    dict with keys "inserted" and "skipped" — counts of firms added vs
    already present.
    """
    from edgar_warehouse.mdm.database import MdmAuditFirm, MdmEntity

    inserted = 0
    skipped = 0

    for firm_data in PCAOB_SEED:
        pcaob_id = firm_data["pcaob_firm_id"]
        canonical = firm_data["canonical_name"]

        # Idempotency check: match by PCAOB ID (primary), then canonical name
        existing = (
            session.query(MdmAuditFirm)
            .filter(MdmAuditFirm.pcaob_firm_id == pcaob_id)
            .first()
        )
        if existing is None:
            existing = (
                session.query(MdmAuditFirm)
                .filter(MdmAuditFirm.canonical_name == canonical)
                .first()
            )

        if existing is not None:
            skipped += 1
            continue

        # Create mdm_entity row first (FK parent)
        entity_id = str(uuid.uuid4())
        entity = MdmEntity(
            entity_id=entity_id,
            entity_type="audit_firm",
            resolution_method="seed",
            confidence=1.0,
        )
        session.add(entity)

        # Create mdm_audit_firm row
        audit_firm = MdmAuditFirm(
            entity_id=entity_id,
            firm_name=firm_data["firm_name"],
            pcaob_firm_id=pcaob_id,
            big4=firm_data["big4"],
            canonical_name=canonical,
        )
        session.add(audit_firm)
        inserted += 1

    session.commit()
    return {"inserted": inserted, "skipped": skipped}
