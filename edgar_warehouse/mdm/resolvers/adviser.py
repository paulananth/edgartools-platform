"""AdviserResolver — dual-identity (CIK + CRD) MDM resolution for advisers.

Source: silver sec_adv_filing + sec_adv_office. One adviser can file via a
single CIK while exposing multiple CRD numbers across amendments; the
resolver links each CRD to the primary CIK-keyed entity and, when the CIK
belongs to a registered company, writes linked_company_entity_id.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmAdviser, MdmCompany, MdmEntity
from edgar_warehouse.mdm.match import CIKExactMatcher, FuzzyNameMatcher, MatchPipeline
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolveOutcome, ResolverContext
from edgar_warehouse.mdm.survivorship import run_survivorship_for_entity

ADVISER_FIELDS = [
    "canonical_name",
    "cik",
    "crd_number",
    "sec_file_number",
    "adviser_type",
    "hq_city",
    "hq_state",
    "aum_total",
    "fund_count",
]


@dataclass
class AdviserResolver(BaseResolver):
    entity_type: str = "adviser"
    domain_fields: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.domain_fields is None:
            self.domain_fields = list(ADVISER_FIELDS)

    def _build_pipeline(self, ctx: ResolverContext) -> MatchPipeline:
        return MatchPipeline(
            matchers=[
                CIKExactMatcher(),
                FuzzyNameMatcher(entity_type=self.entity_type, engine=ctx.engine),
            ]
        )

    def resolve_one(
        self,
        ctx: ResolverContext,
        source_system: str,
        adv_filing: dict,
        office: Optional[dict] = None,
        effective_date=None,
    ) -> ResolveOutcome:
        cik = adv_filing.get("cik")
        crd = adv_filing.get("crd_number")
        name = ctx.engine.normalize_name(adv_filing.get("adviser_name"))
        attrs_for_match = {"cik": cik, "canonical_name": name}

        candidates = self._existing_candidates(ctx, cik, crd)
        pipeline = ctx.pipeline or self._build_pipeline(ctx)
        ctx.pipeline = pipeline

        outcome = self.resolve_or_create(
            ctx, attrs_for_match, source_system, adv_filing["accession_number"], candidates
        )

        staged = {
            "canonical_name": name,
            "cik": cik,
            "crd_number": crd,
            "sec_file_number": adv_filing.get("sec_file_number"),
            "adviser_type": adv_filing.get("filing_status"),
            "hq_city": (office or {}).get("city"),
            "hq_state": (office or {}).get("state_or_country"),
            "aum_total": adv_filing.get("aum_total"),
            "fund_count": adv_filing.get("fund_count"),
        }
        self._stage_attrs(
            ctx,
            outcome.entity_id,
            source_system,
            adv_filing["accession_number"],
            staged,
            effective_date=effective_date or adv_filing.get("effective_date"),
        )
        self._register_source(
            ctx,
            outcome.entity_id,
            source_system,
            adv_filing["accession_number"],
            outcome.verdict.score if outcome.verdict else 1.0,
        )

        existing = self._existing_golden(ctx, outcome.entity_id)
        merges = run_survivorship_for_entity(
            ctx.session,
            ctx.engine,
            self.entity_type,
            outcome.entity_id,
            ADVISER_FIELDS,
            existing_values=existing,
        )

        self._upsert_golden(ctx, outcome.entity_id, merges)
        self._link_to_company(ctx, outcome.entity_id, cik)
        self._log_change(
            ctx,
            outcome.entity_id,
            {k: v.winning_value for k, v in merges.items()},
        )
        return outcome

    @staticmethod
    def _existing_candidates(
        ctx: ResolverContext, cik: Optional[int], crd: Optional[str]
    ) -> list[dict]:
        if cik is None and crd is None:
            return []
        stmt = (
            select(MdmAdviser, MdmEntity)
            .join(MdmEntity, MdmEntity.entity_id == MdmAdviser.entity_id)
            .where(
                (MdmAdviser.cik == cik) | (MdmAdviser.crd_number == crd)
                if (cik is not None and crd is not None)
                else (MdmAdviser.cik == cik)
                if cik is not None
                else (MdmAdviser.crd_number == crd)
            )
        )
        out = []
        for adv, _ent in ctx.session.execute(stmt).all():
            out.append(
                {
                    "entity_id": adv.entity_id,
                    "cik": adv.cik,
                    "crd_number": adv.crd_number,
                    "canonical_name": adv.canonical_name,
                }
            )
        return out

    @staticmethod
    def _existing_golden(ctx: ResolverContext, entity_id: str) -> dict:
        row = ctx.session.get(MdmAdviser, entity_id)
        if not row:
            return {}
        return {f: getattr(row, f) for f in ADVISER_FIELDS}

    @staticmethod
    def _upsert_golden(ctx: ResolverContext, entity_id: str, merges: dict) -> None:
        row = ctx.session.get(MdmAdviser, entity_id)
        if row is None:
            row = MdmAdviser(
                entity_id=entity_id,
                canonical_name=merges["canonical_name"].winning_value or "Unknown Adviser",
            )
            ctx.session.add(row)
        for f in ADVISER_FIELDS:
            w = merges.get(f)
            if w is not None and w.winning_value is not None:
                setattr(row, f, w.winning_value)

    @staticmethod
    def _link_to_company(ctx: ResolverContext, adviser_id: str, cik: Optional[int]) -> None:
        if cik is None:
            return
        company = ctx.session.execute(
            select(MdmCompany).where(MdmCompany.cik == int(cik))
        ).scalar_one_or_none()
        if company is None:
            return
        adv = ctx.session.get(MdmAdviser, adviser_id)
        if adv is not None:
            adv.linked_company_entity_id = company.entity_id
