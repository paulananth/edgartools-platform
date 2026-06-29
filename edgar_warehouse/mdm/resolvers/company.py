"""CompanyResolver — resolves SEC companies to MDM entities.

Source: silver tables sec_company, sec_company_ticker, sec_tracked_universe.
Primary match: CIK exact (definitive). Fuzzy name is available but rarely
needed because SEC CIK is a stable, unique key.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmCompany, MdmEntity, MdmSourceRef
from edgar_warehouse.mdm.match import CIKExactMatcher, FuzzyNameMatcher, MatchPipeline
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolveOutcome, ResolverContext
from edgar_warehouse.mdm.survivorship import run_survivorship_for_entity

logger = logging.getLogger(__name__)

_PARENT_CIK_SOURCE_WARNING_KEY = "company.parent_cik_source"
_PARENT_CIK_KEYS = ("parent_company_cik", "parent_cik", "ultimate_parent_cik")

COMPANY_FIELDS = [
    "canonical_name",
    "ein",
    "sic_code",
    "sic_description",
    "state_of_incorporation",
    "fiscal_year_end",
    "ticker",
    "primary_ticker",
    "primary_exchange",
    "tracking_status",
    "parent_company_entity_id",
]


@dataclass
class CompanyResolver(BaseResolver):
    entity_type: str = "company"
    domain_fields: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.domain_fields is None:
            self.domain_fields = list(COMPANY_FIELDS)

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
        company_row: dict,
        ticker_row: Optional[dict] = None,
        tracking_row: Optional[dict] = None,
    ) -> ResolveOutcome:
        cik = int(company_row["cik"])
        name = ctx.engine.normalize_name(company_row.get("entity_name"))
        attrs_for_match = {"cik": cik, "canonical_name": name}

        candidates = self._existing_candidates(ctx, cik)
        pipeline = ctx.pipeline or self._build_pipeline(ctx)
        ctx.pipeline = pipeline

        outcome = self.resolve_or_create(
            ctx, attrs_for_match, source_system, str(cik), candidates
        )

        primary_ticker = (ticker_row or {}).get("ticker")
        primary_exchange = (ticker_row or {}).get("exchange")
        tracking_status = (tracking_row or {}).get("tracking_status")
        parent_company_entity_id = self._parent_company_entity_id(ctx, company_row)

        staged = {
            "canonical_name": name,
            "ein": company_row.get("ein"),
            "sic_code": company_row.get("sic"),
            "sic_description": company_row.get("sic_description"),
            "state_of_incorporation": company_row.get("state_of_incorporation"),
            "fiscal_year_end": company_row.get("fiscal_year_end"),
            "ticker": primary_ticker,
            "primary_ticker": primary_ticker,
            "primary_exchange": primary_exchange,
            "tracking_status": tracking_status,
            "parent_company_entity_id": parent_company_entity_id,
        }
        self._stage_attrs(ctx, outcome.entity_id, source_system, str(cik), staged)
        self._register_source(
            ctx,
            outcome.entity_id,
            source_system,
            str(cik),
            outcome.verdict.score if outcome.verdict else 1.0,
        )

        existing = self._existing_golden(ctx, outcome.entity_id)
        merge_results = run_survivorship_for_entity(
            ctx.session,
            ctx.engine,
            self.entity_type,
            outcome.entity_id,
            COMPANY_FIELDS,
            existing_values=existing,
        )

        self._upsert_golden(ctx, outcome.entity_id, cik, merge_results)
        changed = {k: v.winning_value for k, v in merge_results.items()}
        self._log_change(ctx, outcome.entity_id, changed_fields=changed)
        return outcome

    @staticmethod
    def _existing_candidates(ctx: ResolverContext, cik: int) -> list[dict]:
        stmt = (
            select(MdmCompany, MdmEntity)
            .join(MdmEntity, MdmEntity.entity_id == MdmCompany.entity_id)
            .where(MdmCompany.cik == cik)
        )
        out = []
        for comp, _ent in ctx.session.execute(stmt).all():
            out.append(
                {
                    "entity_id": comp.entity_id,
                    "cik": comp.cik,
                    "canonical_name": comp.canonical_name,
                }
            )
        return out

    @staticmethod
    def _existing_golden(ctx: ResolverContext, entity_id: str) -> dict:
        row = ctx.session.get(MdmCompany, entity_id)
        if not row:
            return {}
        return {
            "canonical_name": row.canonical_name,
            "ein": row.ein,
            "sic_code": row.sic_code,
            "sic_description": row.sic_description,
            "state_of_incorporation": row.state_of_incorporation,
            "fiscal_year_end": row.fiscal_year_end,
            "ticker": row.ticker,
            "primary_ticker": row.primary_ticker,
            "primary_exchange": row.primary_exchange,
            "tracking_status": row.tracking_status,
            "parent_company_entity_id": row.parent_company_entity_id,
        }

    @staticmethod
    def _upsert_golden(
        ctx: ResolverContext,
        entity_id: str,
        cik: int,
        merges: dict,
    ) -> None:
        row = ctx.session.get(MdmCompany, entity_id)
        if row is None:
            row = MdmCompany(
                entity_id=entity_id,
                cik=cik,
                canonical_name=merges["canonical_name"].winning_value or f"CIK-{cik}",
            )
            ctx.session.add(row)
        for field_name in COMPANY_FIELDS:
            winner = merges.get(field_name)
            if winner is not None and winner.winning_value is not None:
                setattr(row, field_name, winner.winning_value)

    @staticmethod
    def _parent_company_entity_id(ctx: ResolverContext, company_row: dict) -> Optional[str]:
        if not any(key in company_row for key in _PARENT_CIK_KEYS):
            if _PARENT_CIK_SOURCE_WARNING_KEY not in ctx.warned:
                ctx.warned.add(_PARENT_CIK_SOURCE_WARNING_KEY)
                logger.warning(
                    "No parent CIK source column (%s) found on sec_company rows this run; "
                    "HAS_PARENT_COMPANY relationships will not be derived. "
                    "See TODOS.md parent_company_entity_id_always_none.",
                    " / ".join(_PARENT_CIK_KEYS),
                )
            return None

        parent_cik = (
            company_row.get("parent_company_cik")
            or company_row.get("parent_cik")
            or company_row.get("ultimate_parent_cik")
        )
        if parent_cik in (None, ""):
            return None
        try:
            parent_cik_int = int(parent_cik)
        except (TypeError, ValueError):
            return None
        return ctx.session.scalar(
            select(MdmCompany.entity_id).where(MdmCompany.cik == parent_cik_int)
        )
