"""Bulk current-state projection from ADV silver tables into MDM.

Silver remains the immutable history of every ADV filing and private-fund row.
MDM projects the latest record for each authoritative IAPD identifier:

* adviser identity: CRD number (accession fallback when CRD is absent)
* private-fund identity: private_fund_id (accession/index fallback when absent)

The generic resolvers are intentionally row-oriented because they support
fuzzy matching and arbitrary source-priority combinations.  ADV is different:
CRD/PFID are authoritative exact identifiers and production contains hundreds
of thousands of historical rows.  Resolving those rows one at a time turns
every source record into dozens of Snowflake Postgres network round trips.
This module preserves source references, selected attribute-stage evidence,
and change-log export signals while using bounded, batched database writes.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmAdviser,
    MdmChangeLog,
    MdmCompany,
    MdmEntity,
    MdmEntityAttributeStage,
    MdmFund,
    MdmSourceRef,
)
from edgar_warehouse.mdm.resolvers.adviser import ADVISER_FIELDS
from edgar_warehouse.mdm.resolvers.base import SilverReader
from edgar_warehouse.mdm.resolvers.fund import FUND_FIELDS
from edgar_warehouse.mdm.rules import MDMRuleEngine

_WRITE_BATCH_SIZE = 5_000
_LOOKUP_BATCH_SIZE = 5_000


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _execute_insert_chunks(
    session: Session,
    model: type,
    rows: list[dict[str, Any]],
) -> None:
    for chunk in _chunks(rows, _WRITE_BATCH_SIZE):
        session.execute(insert(model), chunk)


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _latest_key(row: dict[str, Any]) -> tuple[date, int, str]:
    effective = _as_date(row.get("effective_date")) or date.min
    accession = str(row.get("accession_number") or "")
    filing_id = accession.rsplit(":", 1)[-1]
    return (
        effective,
        int(filing_id) if filing_id.isdecimal() else 0,
        accession,
    )


def _text_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _latest_by_identity(
    rows: list[dict[str, Any]],
    identity,
) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = identity(row)
        prior = latest.get(key)
        if prior is None or _latest_key(row) > _latest_key(prior):
            latest[key] = row
    return list(latest.values())


def _json_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, (date, datetime, Decimal)) else value
        for key, value in attrs.items()
    }


def _existing_source_ids(
    session: Session,
    entity_type: str,
    source_system: str,
    source_ids: list[str],
) -> set[str]:
    existing: set[str] = set()
    for chunk in _chunks(source_ids, _LOOKUP_BATCH_SIZE):
        existing.update(
            session.scalars(
                select(MdmSourceRef.source_id)
                .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
                .where(MdmEntity.entity_type == entity_type)
                .where(MdmSourceRef.source_system == source_system)
                .where(MdmSourceRef.source_id.in_(chunk))
            )
        )
    return existing


def _stage_rows(
    *,
    entity_id: str,
    source_id: str,
    source_priority: int,
    effective_date: date | None,
    attrs: dict[str, Any],
    fields: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "stage_id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "source_system": "adv_filing",
            "source_id": source_id,
            "field_name": field_name,
            "field_value": None if attrs.get(field_name) is None else str(attrs[field_name]),
            "global_priority": source_priority,
            "effective_date": effective_date,
            "was_selected": attrs.get(field_name) is not None,
        }
        for field_name in fields
    ]


def resolve_advisers_bulk(
    session: Session,
    silver: SilverReader,
    engine: MDMRuleEngine,
    limit: int | None = None,
) -> int:
    """Project the latest filing for every CRD into adviser golden records."""
    sql = "SELECT * FROM sec_adv_filing"
    if limit:
        sql += f" LIMIT {int(limit)}"
    filing_rows = silver.fetch(sql)
    office_rows = silver.fetch(
        "SELECT accession_number, city, state_or_country "
        "FROM sec_adv_office WHERE is_headquarters = TRUE"
    )
    offices = {
        str(row.get("accession_number")): row
        for row in office_rows
    }

    def identity(row: dict[str, Any]) -> str:
        crd = _text_id(row.get("crd_number"))
        if crd:
            return f"crd:{crd}"
        return f"accession:{row.get('accession_number')}"

    rows = _latest_by_identity(filing_rows, identity)
    if not rows:
        session.commit()
        return 0

    existing_advisers = list(session.scalars(select(MdmAdviser)))
    by_crd = {
        str(row.crd_number): row
        for row in existing_advisers
        if row.crd_number is not None
    }
    unclaimed_by_cik = {
        int(row.cik): row
        for row in existing_advisers
        if row.cik is not None and row.crd_number is None
    }
    companies_by_cik = {
        int(row.cik): row.entity_id
        for row in session.scalars(select(MdmCompany))
        if row.cik is not None
    }

    new_entities: list[dict[str, Any]] = []
    new_advisers: list[dict[str, Any]] = []
    source_refs: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    source_priority = engine.get_source_priority("adviser", "adv_filing")
    source_ids = [str(row["accession_number"]) for row in rows]
    existing_sources = _existing_source_ids(
        session, "adviser", "adv_filing", source_ids
    )

    for row in rows:
        crd = _text_id(row.get("crd_number"))
        cik = row.get("cik")
        cik_int = int(cik) if cik is not None else None
        adviser = by_crd.get(crd) if crd else None
        if adviser is None and cik_int is not None:
            adviser = unclaimed_by_cik.pop(cik_int, None)

        entity_id = (
            adviser.entity_id
            if adviser is not None
            else str(uuid.uuid5(uuid.NAMESPACE_URL, identity(row)))
        )
        office = offices.get(str(row["accession_number"]), {})
        attrs = {
            "canonical_name": engine.normalize_name(row.get("adviser_name")),
            "cik": cik_int,
            "crd_number": crd,
            "sec_file_number": row.get("sec_file_number"),
            "adviser_type": row.get("filing_status"),
            "hq_city": office.get("city"),
            "hq_state": office.get("state_or_country"),
            "aum_total": row.get("aum_total"),
            "fund_count": row.get("fund_count"),
        }
        golden = {
            **attrs,
            "canonical_name": attrs["canonical_name"] or "Unknown Adviser",
            "linked_company_entity_id": companies_by_cik.get(cik_int),
        }

        if adviser is None:
            new_entities.append({
                "entity_id": entity_id,
                "entity_type": "adviser",
                "resolution_method": "iapd_crd_exact" if crd else "adv_accession_exact",
                "confidence": 1.0,
                "is_quarantined": False,
            })
            new_advisers.append({"entity_id": entity_id, **golden})
        else:
            for field_name, value in golden.items():
                if value is not None:
                    setattr(adviser, field_name, value)

        source_id = str(row["accession_number"])
        if source_id not in existing_sources:
            source_refs.append({
                "entity_id": entity_id,
                "source_system": "adv_filing",
                "source_id": source_id,
                "source_priority": source_priority,
                "confidence": 1.0,
            })
            stages.extend(_stage_rows(
                entity_id=entity_id,
                source_id=source_id,
                source_priority=source_priority,
                effective_date=_as_date(row.get("effective_date")),
                attrs=attrs,
                fields=ADVISER_FIELDS,
            ))
            changes.append({
                "entity_id": entity_id,
                "entity_type": "adviser",
                "changed_fields": _json_attrs(attrs),
            })

    _execute_insert_chunks(session, MdmEntity, new_entities)
    _execute_insert_chunks(session, MdmAdviser, new_advisers)
    _execute_insert_chunks(session, MdmSourceRef, source_refs)
    _execute_insert_chunks(session, MdmEntityAttributeStage, stages)
    _execute_insert_chunks(session, MdmChangeLog, changes)
    session.commit()
    return len(rows)


def resolve_funds_bulk(
    session: Session,
    silver: SilverReader,
    engine: MDMRuleEngine,
    limit: int | None = None,
) -> int:
    """Project the latest filing row for every private-fund identifier."""
    sql = "SELECT * FROM sec_adv_private_fund"
    if limit:
        sql += f" LIMIT {int(limit)}"
    source_rows = silver.fetch(sql)

    def identity(row: dict[str, Any]) -> str:
        pfid = _text_id(row.get("private_fund_id"))
        if pfid:
            return f"pfid:{pfid}"
        return (
            f"accession:{row.get('accession_number')}:"
            f"{row.get('fund_index')}"
        )

    rows = _latest_by_identity(source_rows, identity)
    if not rows:
        session.commit()
        return 0

    advisers = list(session.scalars(select(MdmAdviser)))
    adviser_by_crd = {
        str(row.crd_number): row.entity_id
        for row in advisers
        if row.crd_number is not None
    }
    adviser_by_accession = {
        source_id: entity_id
        for source_id, entity_id in session.execute(
            select(MdmSourceRef.source_id, MdmSourceRef.entity_id)
            .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
            .where(MdmSourceRef.source_system == "adv_filing")
            .where(MdmEntity.entity_type == "adviser")
        )
    }
    existing_funds = list(session.scalars(select(MdmFund)))
    by_pfid = {
        str(row.private_fund_id): row
        for row in existing_funds
        if row.private_fund_id is not None
    }
    by_adviser_name = {
        (row.adviser_entity_id, row.canonical_name): row
        for row in existing_funds
        if row.private_fund_id is None
    }

    new_entities: list[dict[str, Any]] = []
    new_funds: list[dict[str, Any]] = []
    source_refs: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    source_priority = engine.get_source_priority("fund", "adv_filing")
    source_ids = [
        _text_id(row.get("private_fund_id"))
        or f"{row['accession_number']}:{row.get('fund_index')}"
        for row in rows
    ]
    existing_sources = _existing_source_ids(
        session, "fund", "adv_filing", source_ids
    )

    for row, source_id in zip(rows, source_ids):
        pfid = _text_id(row.get("private_fund_id"))
        adviser_crd = _text_id(row.get("adviser_crd_number"))
        adviser_entity_id = adviser_by_crd.get(adviser_crd)
        if adviser_entity_id is None:
            adviser_entity_id = adviser_by_accession.get(str(row.get("accession_number")))
        name = engine.normalize_name(row.get("fund_name")) or "Unknown Fund"
        fund = by_pfid.get(pfid) if pfid else by_adviser_name.get((adviser_entity_id, name))
        entity_id = (
            fund.entity_id
            if fund is not None
            else str(uuid.uuid5(uuid.NAMESPACE_URL, identity(row)))
        )
        effective_date = _as_date(row.get("effective_date"))
        attrs = {
            "canonical_name": name,
            "fund_type": row.get("fund_type"),
            "jurisdiction": row.get("jurisdiction"),
            "aum_amount": row.get("aum_amount"),
            "aum_as_of_date": effective_date,
        }
        golden = {
            **attrs,
            "adviser_entity_id": adviser_entity_id,
            "private_fund_id": pfid,
        }

        if fund is None:
            new_entities.append({
                "entity_id": entity_id,
                "entity_type": "fund",
                "resolution_method": "iapd_pfid_exact" if pfid else "adviser_name_dedup",
                "confidence": 1.0,
                "is_quarantined": False,
            })
            new_funds.append({"entity_id": entity_id, **golden})
        else:
            for field_name, value in golden.items():
                if value is not None:
                    setattr(fund, field_name, value)

        if source_id not in existing_sources:
            source_refs.append({
                "entity_id": entity_id,
                "source_system": "adv_filing",
                "source_id": source_id,
                "source_priority": source_priority,
                "confidence": 1.0,
            })
            stages.extend(_stage_rows(
                entity_id=entity_id,
                source_id=source_id,
                source_priority=source_priority,
                effective_date=effective_date,
                attrs=attrs,
                fields=FUND_FIELDS,
            ))
            changes.append({
                "entity_id": entity_id,
                "entity_type": "fund",
                "changed_fields": _json_attrs(attrs),
            })

    _execute_insert_chunks(session, MdmEntity, new_entities)
    _execute_insert_chunks(session, MdmFund, new_funds)
    _execute_insert_chunks(session, MdmSourceRef, source_refs)
    _execute_insert_chunks(session, MdmEntityAttributeStage, stages)
    _execute_insert_chunks(session, MdmChangeLog, changes)
    session.commit()
    return len(rows)
