"""PersonResolver — Form 3/4/5 reporting-owner resolution.

Matching order:
  1. CIK exact (owner_cik)
  2. Fuzzy name + issuer context + normalized title
  3. Splink ML (only for records where owner_cik IS NULL)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmEntity, MdmPerson
from edgar_warehouse.mdm.match import (
    CIKExactMatcher,
    FuzzyNameMatcher,
    MatchPipeline,
    SplinkMatcher,
)
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolveOutcome, ResolverContext
from edgar_warehouse.mdm.survivorship import run_survivorship_for_entity

PERSON_FIELDS = ["canonical_name", "owner_cik", "primary_role"]


@dataclass
class PersonResolver(BaseResolver):
    entity_type: str = "person"
    domain_fields: list[str] = None  # type: ignore[assignment]
    splink_model: object | None = None

    def __post_init__(self) -> None:
        if self.domain_fields is None:
            self.domain_fields = list(PERSON_FIELDS)

    def _build_pipeline(self, ctx: ResolverContext) -> MatchPipeline:
        matchers = [
            CIKExactMatcher(),
            FuzzyNameMatcher(
                entity_type=self.entity_type,
                engine=ctx.engine,
                context_fields=("issuer_cik",),
            ),
        ]
        if self.splink_model is not None:
            matchers.append(
                SplinkMatcher(
                    entity_type=self.entity_type,
                    engine=ctx.engine,
                    model=self.splink_model,
                )
            )
        return MatchPipeline(matchers=matchers)

    def resolve_one(
        self,
        ctx: ResolverContext,
        source_system: str,
        owner_row: dict,
        issuer_cik: Optional[int] = None,
    ) -> ResolveOutcome:
        owner_cik = owner_row.get("owner_cik")
        name = ctx.engine.normalize_name(owner_row.get("owner_name"))
        title = self._derive_primary_role(ctx, owner_row)
        attrs = {
            "owner_cik": owner_cik,
            "canonical_name": name,
            "issuer_cik": issuer_cik,
            "primary_role": title,
        }

        candidates = self._existing_candidates(ctx, owner_cik, name)
        pipeline = ctx.pipeline or self._build_pipeline(ctx)
        ctx.pipeline = pipeline

        source_id = f"{owner_row['accession_number']}:{owner_row.get('owner_index')}"
        outcome = self.resolve_or_create(ctx, attrs, source_system, source_id, candidates)

        staged = {"canonical_name": name, "owner_cik": owner_cik, "primary_role": title}
        self._stage_attrs(ctx, outcome.entity_id, source_system, source_id, staged)
        self._register_source(
            ctx, outcome.entity_id, source_system, source_id,
            outcome.verdict.score if outcome.verdict else 1.0,
        )

        existing = self._existing_golden(ctx, outcome.entity_id)
        merges = run_survivorship_for_entity(
            ctx.session, ctx.engine, self.entity_type,
            outcome.entity_id, PERSON_FIELDS, existing_values=existing,
        )
        self._upsert_golden(ctx, outcome.entity_id, merges, owner_row.get("owner_name"), title)
        self._log_change(
            ctx, outcome.entity_id,
            {k: v.winning_value for k, v in merges.items()},
        )
        return outcome

    @staticmethod
    def _derive_primary_role(ctx: ResolverContext, row: dict) -> Optional[str]:
        if row.get("is_director"):
            return "Director"
        if row.get("is_officer"):
            return ctx.engine.normalize_title(row.get("officer_title")) or "Officer"
        if row.get("is_ten_percent_owner"):
            return "10PctOwner"
        if row.get("is_other"):
            return "Other"
        return None

    @staticmethod
    def _existing_candidates(
        ctx: ResolverContext, owner_cik: Optional[int], name: Optional[str]
    ) -> list[dict]:
        if owner_cik is None and not name:
            return []
        stmt = select(MdmPerson, MdmEntity).join(
            MdmEntity, MdmEntity.entity_id == MdmPerson.entity_id
        )
        if owner_cik is not None:
            stmt = stmt.where(MdmPerson.owner_cik == int(owner_cik))
        out = []
        for p, _ in ctx.session.execute(stmt).all():
            out.append(
                {
                    "entity_id": p.entity_id,
                    "owner_cik": p.owner_cik,
                    "canonical_name": p.canonical_name,
                }
            )
        return out

    @staticmethod
    def _existing_golden(ctx: ResolverContext, entity_id: str) -> dict:
        row = ctx.session.get(MdmPerson, entity_id)
        if not row:
            return {}
        return {f: getattr(row, f) for f in PERSON_FIELDS}

    @staticmethod
    def _upsert_golden(
        ctx: ResolverContext,
        entity_id: str,
        merges: dict,
        raw_name: Optional[str],
        title: Optional[str],
    ) -> None:
        row = ctx.session.get(MdmPerson, entity_id)
        if row is None:
            row = MdmPerson(
                entity_id=entity_id,
                canonical_name=merges["canonical_name"].winning_value or raw_name or "Unknown",
                name_variants=[raw_name] if raw_name else [],
                role_titles=[title] if title else [],
            )
            ctx.session.add(row)
        else:
            variants = set(row.name_variants or [])
            if raw_name:
                variants.add(raw_name)
            row.name_variants = sorted(variants)
            titles = set(row.role_titles or [])
            if title:
                titles.add(title)
            row.role_titles = sorted(titles)
        for f in PERSON_FIELDS:
            w = merges.get(f)
            if w is not None and w.winning_value is not None:
                setattr(row, f, w.winning_value)
