"""SecurityResolver — resolves security titles to MDM entities.

Securities appear as strings in ownership transaction rows
(sec_ownership_non_derivative_txn.security_title). We dedupe by
(issuer_entity_id, normalized_title) — the same common stock across
multiple filings should resolve to one MDM security.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmEntity, MdmSecurity
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolveOutcome, ResolverContext
from edgar_warehouse.mdm.survivorship import run_survivorship_for_entity

SECURITY_FIELDS = ["canonical_title", "security_type", "cusip", "isin"]

_TITLE_TYPE_RE = [
    (re.compile(r"common stock", re.IGNORECASE), "common_stock"),
    (re.compile(r"preferred stock", re.IGNORECASE), "preferred_stock"),
    (re.compile(r"option", re.IGNORECASE), "option"),
    (re.compile(r"restricted stock unit|rsu", re.IGNORECASE), "rsu"),
    (re.compile(r"warrant", re.IGNORECASE), "warrant"),
    (re.compile(r"convertible", re.IGNORECASE), "convertible"),
]


def _infer_type(title: str) -> str:
    for rx, kind in _TITLE_TYPE_RE:
        if rx.search(title):
            return kind
    return "other"


@dataclass
class SecurityResolver(BaseResolver):
    entity_type: str = "security"
    domain_fields: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.domain_fields is None:
            self.domain_fields = list(SECURITY_FIELDS)

    def resolve_one(
        self,
        ctx: ResolverContext,
        source_system: str,
        txn_row: dict,
        issuer_entity_id: Optional[str],
    ) -> ResolveOutcome:
        title = txn_row.get("security_title") or ""
        canonical = " ".join(w.capitalize() for w in title.split()) if title else ""
        sec_type = _infer_type(canonical)

        existing = self._existing_candidates(ctx, issuer_entity_id, canonical)
        source_id = f"{txn_row['accession_number']}:{txn_row.get('owner_index')}:{txn_row.get('txn_index')}"

        if existing:
            entity_id = existing[0]["entity_id"]
            is_new = False
            score = 1.0
        else:
            ent = self._create_entity(
                ctx, resolution_method="issuer_title_dedup", confidence=1.0
            )
            entity_id = ent.entity_id
            is_new = True
            score = 1.0
            row = MdmSecurity(
                entity_id=entity_id,
                issuer_entity_id=issuer_entity_id,
                canonical_title=canonical or "Unknown",
                security_type=sec_type,
            )
            ctx.session.add(row)

        self._stage_attrs(
            ctx, entity_id, source_system, source_id,
            {"canonical_title": canonical, "security_type": sec_type},
        )
        self._register_source(ctx, entity_id, source_system, source_id, score)
        merges = run_survivorship_for_entity(
            ctx.session, ctx.engine, self.entity_type,
            entity_id, SECURITY_FIELDS,
        )
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
        ctx: ResolverContext, issuer_entity_id: Optional[str], canonical_title: str
    ) -> list[dict]:
        if not canonical_title:
            return []
        stmt = (
            select(MdmSecurity, MdmEntity)
            .join(MdmEntity, MdmEntity.entity_id == MdmSecurity.entity_id)
            .where(MdmSecurity.canonical_title == canonical_title)
        )
        if issuer_entity_id:
            stmt = stmt.where(MdmSecurity.issuer_entity_id == issuer_entity_id)
        return [
            {"entity_id": s.entity_id, "canonical_title": s.canonical_title}
            for s, _ in ctx.session.execute(stmt).all()
        ]
