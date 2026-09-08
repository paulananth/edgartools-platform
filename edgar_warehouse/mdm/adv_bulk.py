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

from edgar_warehouse.mdm.bounded_fetch import bounded_source_sql
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
# mdm-run-throughput map: matches pipeline.py's _SOURCE_REF_PREFETCH_BATCH_SIZE
# -- both chunk a single-column string-id `.in_()` SELECT against
# MdmSourceRef.source_id, proven safe up to 300,000 bound scalar params for
# this psycopg2-based stack. Deliberately NOT applied to _WRITE_BATCH_SIZE
# above, which chunks a multi-column bulk INSERT -- SQLAlchemy's own
# insertmanyvalues_page_size (1000, independent of this constant) already
# governs that operation's real round-trip count; empirically confirmed
# bumping it produces zero fewer physical statements.
_LOOKUP_BATCH_SIZE = 20_000


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _execute_insert_chunks(
    session: Session,
    model: type,
    rows: list[dict[str, Any]],
) -> None:
    for chunk in _chunks(rows, _WRITE_BATCH_SIZE):
        # ORM bulk INSERT omits None-valued columns unless render_nulls is set.
        # ADV attributes are intentionally sparse; omitting them partitions one
        # batch into many column-shape groups and can degrade to one network
        # round trip per row on PostgreSQL.
        session.execute(
            insert(model),
            chunk,
            execution_options={"render_nulls": True},
        )


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


def _bounded_unresolved_rows(
    silver: SilverReader,
    base_sql: str,
    order_by_sql: str,
    limit: int | None,
    existing_count: int,
    exclude,
) -> list[dict[str, Any]]:
    """Shared growing-window fetch for resolve_advisers_bulk/resolve_funds_bulk
    (fundamentals-daily-integration map, Ticket 06). Both callers had the
    identical shape (bounded fetch + stable ORDER BY + exclude
    already-resolved identities) inline before this extraction -- adv_bulk.py
    has already shipped two prior bugs where a fix landed in one of these
    two sibling functions and not the other (commits ee62a968, e6fc0626), so
    this logic is factored once rather than risking a third divergence.

    When `limit` is falsy, returns every row unfiltered and unordered --
    the existing unbounded `mdm run --entity-type all` (no --limit) path,
    left byte-for-byte unchanged.
    """
    if not limit:
        return silver.fetch(base_sql)
    fetch_sql = bounded_source_sql(f"{base_sql} ORDER BY {order_by_sql}", limit, existing_count)
    candidate_rows = silver.fetch(fetch_sql)
    return [row for row in candidate_rows if not exclude(row)]


def resolve_advisers_bulk(
    session: Session,
    silver: SilverReader,
    engine: MDMRuleEngine,
    limit: int | None = None,
) -> int:
    """Project the latest filing for every CRD into adviser golden records."""

    def identity(row: dict[str, Any]) -> str:
        crd = _text_id(row.get("crd_number"))
        if crd:
            return f"crd:{crd}"
        return f"accession:{row.get('accession_number')}"

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

    # release-readiness Ticket 100 / fundamentals-daily-integration Ticket
    # 06: a bare "SELECT * FROM sec_adv_filing LIMIT N" has no ORDER BY and
    # no exclusion of already-resolved CRDs, so a caller that passes the
    # same limit on every call (daily_incremental's daily `mdm mastering
    # --limit 100`) re-fetches the same leading rows in table-scan order
    # forever -- new advisers beyond that window are never reached.
    # _bounded_unresolved_rows ports the same growing-window fix already
    # proven for run_companies (pipeline.py). A row with no crd_number
    # (accession-fallback identity) always passes the exclusion filter --
    # there is no cheap way to know an accession-keyed identity was already
    # resolved without a second round trip, and occasionally re-fetching
    # one is harmless: the _existing_source_ids check below already makes
    # re-processing an already-seen accession a no-op.
    filing_rows = _bounded_unresolved_rows(
        silver,
        "SELECT * FROM sec_adv_filing",
        "crd_number NULLS LAST, accession_number",
        limit,
        len(by_crd),
        lambda row: _text_id(row.get("crd_number")) in by_crd,
    )

    office_rows = silver.fetch(
        "SELECT accession_number, city, state_or_country "
        "FROM sec_adv_office WHERE is_headquarters = TRUE"
    )
    offices = {
        str(row.get("accession_number")): row
        for row in office_rows
    }

    rows = _latest_by_identity(filing_rows, identity)
    if limit:
        rows = rows[: int(limit)]
    if not rows:
        session.commit()
        return 0

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

    def identity(row: dict[str, Any]) -> str:
        pfid = _text_id(row.get("private_fund_id"))
        if pfid:
            return f"pfid:{pfid}"
        return (
            f"accession:{row.get('accession_number')}:"
            f"{row.get('fund_index')}"
        )

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
    existing_funds_by_entity_id = {row.entity_id: row for row in existing_funds}
    by_pfid = {
        str(row.private_fund_id): row
        for row in existing_funds
        if row.private_fund_id is not None
    }

    # Same growing-window fix as resolve_advisers_bulk above (see its
    # comment for the full rationale) -- identity is private_fund_id here
    # instead of crd_number, with the same accession+fund_index fallback
    # the identity() closure already uses.
    source_rows = _bounded_unresolved_rows(
        silver,
        "SELECT * FROM sec_adv_private_fund",
        "private_fund_id NULLS LAST, accession_number, fund_index",
        limit,
        len(by_pfid),
        lambda row: _text_id(row.get("private_fund_id")) in by_pfid,
    )

    rows = _latest_by_identity(source_rows, identity)
    if limit:
        rows = rows[: int(limit)]
    if not rows:
        session.commit()
        return 0

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
    # Ticket 42 (change-propagation map): the dedup/staging key is always
    # accession_number:fund_index -- the same per-accession granularity
    # resolve_advisers_bulk uses -- never private_fund_id. A pfid identifies
    # the FUND (see identity()/by_pfid above, unchanged), not the SOURCE ROW;
    # keying dedup on pfid meant a later accession amending an already-known
    # fund matched `existing_sources` and silently produced no new
    # MdmSourceRef/stage/MdmChangeLog row, even though the golden record
    # itself refreshed -- starving MDMExporter.export_pending (keyed on
    # MdmChangeLog.exported_at IS NULL) of any signal the fund had changed.
    source_ids = [
        f"{row['accession_number']}:{row.get('fund_index')}" for row in rows
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
        # Check the row's own deterministic entity_id first. A fund without
        # a private_fund_id dedups on (adviser_entity_id, name), but
        # adviser_entity_id can flip from None to a real id on a later run
        # once that adviser becomes resolvable -- the stored fund is then
        # keyed under the old (None, name) pair and this lookup misses it,
        # even though identity(row) (and so entity_id) is unchanged. Without
        # this check the code below re-attempts an insert under the same
        # primary key and crashes with a duplicate-key IntegrityError.
        candidate_entity_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity(row)))
        fund = existing_funds_by_entity_id.get(candidate_entity_id)
        if fund is None:
            fund = by_pfid.get(pfid) if pfid else by_adviser_name.get((adviser_entity_id, name))
        entity_id = (
            fund.entity_id
            if fund is not None
            else candidate_entity_id
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
