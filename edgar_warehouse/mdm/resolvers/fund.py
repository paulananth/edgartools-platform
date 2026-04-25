"""FundResolver — private-fund dedup across ADV amendments.

Fund identity = (adviser_entity_id, normalized fund_name). AUM and
as_of_date follow the most_recent survivorship rule so repeated ADV
amendments refresh the current AUM without losing history in
mdm_entity_attribute_stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmEntity, MdmFund
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolveOutcome, ResolverContext
from edgar_warehouse.mdm.survivorship import run_survivorship_for_entity

FUND_FIELDS = ["canonical_name", "fund_type", "jurisdiction", "aum_amount", "aum_as_of_date"]


@dataclass
class FundResolver(BaseResolver):
    entity_type: str = "fund"
    domain_fields: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.domain_fields is None:
            self.domain_fields = list(FUND_FIELDS)

    def resolve_one(
        self,
        ctx: ResolverContext,
        source_system: str,
        fund_row: dict,
        adviser_entity_id: Optional[str],
        effective_date=None,
    ) -> ResolveOutcome:
        name = ctx.engine.normalize_name(fund_row.get("fund_name"))
        existing = self._existing_candidates(ctx, adviser_entity_id, name)
        source_id = f"{fund_row['accession_number']}:{fund_row.get('fund_index')}"

        if existing:
            entity_id = existing[0]["entity_id"]
            is_new = False
        else:
            ent = self._create_entity(
                ctx, resolution_method="adviser_name_dedup", confidence=1.0
            )
            entity_id = ent.entity_id
            is_new = True
            ctx.session.add(
                MdmFund(
                    entity_id=entity_id,
                    adviser_entity_id=adviser_entity_id,
                    canonical_name=name or "Unknown Fund",
                    fund_type=fund_row.get("fund_type"),
                    jurisdiction=fund_row.get("jurisdiction"),
                    aum_amount=fund_row.get("aum_amount"),
                )
            )

        staged = {
            "canonical_name": name,
            "fund_type": fund_row.get("fund_type"),
            "jurisdiction": fund_row.get("jurisdiction"),
            "aum_amount": fund_row.get("aum_amount"),
            "aum_as_of_date": effective_date,
        }
        self._stage_attrs(
            ctx, entity_id, source_system, source_id, staged,
            effective_date=effective_date,
        )
        self._register_source(ctx, entity_id, source_system, source_id, 1.0)
        merges = run_survivorship_for_entity(
            ctx.session, ctx.engine, self.entity_type,
            entity_id, FUND_FIELDS,
        )
        row = ctx.session.get(MdmFund, entity_id)
        if row is not None:
            for f in FUND_FIELDS:
                w = merges.get(f)
                if w is not None and w.winning_value is not None:
                    setattr(row, f, w.winning_value)
        self._log_change(ctx, entity_id, {k: v.winning_value for k, v in merges.items()})

        from edgar_warehouse.mdm.match import MatchAction
        return ResolveOutcome(
            entity_id=entity_id,
            is_new=is_new,
            verdict=None,
            action=MatchAction.AUTO_MERGE,
        )

    @staticmethod
    def _existing_candidates(
        ctx: ResolverContext, adviser_entity_id: Optional[str], name: Optional[str]
    ) -> list[dict]:
        if not name:
            return []
        stmt = (
            select(MdmFund, MdmEntity)
            .join(MdmEntity, MdmEntity.entity_id == MdmFund.entity_id)
            .where(MdmFund.canonical_name == name)
        )
        if adviser_entity_id:
            stmt = stmt.where(MdmFund.adviser_entity_id == adviser_entity_id)
        return [
            {"entity_id": f.entity_id, "canonical_name": f.canonical_name}
            for f, _ in ctx.session.execute(stmt).all()
        ]
