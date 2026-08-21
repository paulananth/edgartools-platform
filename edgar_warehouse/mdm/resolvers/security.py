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

from sqlalchemy import select, update

from edgar_warehouse.mdm.database import MdmEntity, MdmSecurity
from edgar_warehouse.mdm.match import MatchAction
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolveOutcome, ResolverContext, content_hash
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
        source_id = txn_row.get("source_id") or _ownership_security_source_id(txn_row)

        # 2026-08-21 throughput investigation: run_securities() has no
        # resumable ledger (unlike run_companies(), ticket 7ffda2d7), so a
        # restarted `mdm run` re-processes every ownership-transaction row
        # from scratch. Without this check, every re-run of an unchanged
        # row called _stage_attrs() again, and stage_candidate() always
        # INSERTs a fresh row with no dedup -- mdm_entity_attribute_stage
        # has no pruning anywhere in this codebase (confirmed by search), so
        # a heavily-refiled security (e.g. a large issuer's "Common Stock")
        # accumulated thousands of duplicate stage rows across this
        # session's several Stage 14 restarts, each one read back in full by
        # every future run_survivorship_for_entity() call for that entity --
        # directly measured live: SELECT rowcounts of 8560-12547 for a
        # single entity's stage history, and the corresponding slowdown.
        # Mirrors CompanyResolver.resolve_one's existing skip-if-unchanged
        # fast path (single-path-per-layer map, Ticket 03) exactly: the hash
        # covers everything that changes this call's outcome (title,
        # resolved issuer -- so the NULL-issuer "upgrade" path in this same
        # method still re-runs correctly once an issuer newly resolves).
        row_content_hash = content_hash(
            {"canonical_title": canonical, "issuer_entity_id": issuer_entity_id}
        )
        skip_entity_id = self._skip_if_unchanged(ctx, source_system, source_id, row_content_hash)
        if skip_entity_id is not None:
            return ResolveOutcome(
                entity_id=skip_entity_id,
                is_new=False,
                verdict=None,
                action=MatchAction.SKIPPED_UNCHANGED,
            )

        existing = self._existing_candidates(ctx, issuer_entity_id, canonical)

        if existing:
            entity_id = existing[0]["entity_id"]
            is_new = False
            score = 1.0
            # Upgrade: issuer was unknown when this security was first created but is now resolved.
            # Update in-place rather than creating a duplicate entity.
            if issuer_entity_id:
                sec_row = ctx.session.get(MdmSecurity, entity_id)
                if sec_row is not None and sec_row.issuer_entity_id is None:
                    sec_row.issuer_entity_id = issuer_entity_id
        elif issuer_entity_id:
            # Issuer is known but no exact (title, issuer) match exists.
            # Check for a NULL-issuer security with the same title and upgrade it rather
            # than creating a duplicate entity for the same real-world security.
            null_match = self._existing_candidates(ctx, None, canonical)
            if null_match:
                entity_id = null_match[0]["entity_id"]
                is_new = False
                score = 1.0
                sec_row = ctx.session.get(MdmSecurity, entity_id)
                if sec_row is not None and sec_row.issuer_entity_id is None:
                    sec_row.issuer_entity_id = issuer_entity_id
            else:
                ent = self._create_entity(
                    ctx, resolution_method="issuer_title_dedup", confidence=1.0
                )
                entity_id = ent.entity_id
                is_new = True
                score = 1.0
                ctx.session.add(MdmSecurity(
                    entity_id=entity_id,
                    issuer_entity_id=issuer_entity_id,
                    canonical_title=canonical or "Unknown",
                    security_type=sec_type,
                ))
        else:
            ent = self._create_entity(
                ctx, resolution_method="issuer_title_dedup", confidence=1.0
            )
            entity_id = ent.entity_id
            is_new = True
            score = 1.0
            ctx.session.add(MdmSecurity(
                entity_id=entity_id,
                issuer_entity_id=issuer_entity_id,
                canonical_title=canonical or "Unknown",
                security_type=sec_type,
            ))

        self._stage_attrs(
            ctx, entity_id, source_system, source_id,
            {"canonical_title": canonical, "security_type": sec_type},
        )
        self._register_source(
            ctx, entity_id, source_system, source_id, score,
            source_content_hash=row_content_hash,
        )
        merges = run_survivorship_for_entity(
            ctx.session, ctx.engine, self.entity_type,
            entity_id, SECURITY_FIELDS,
        )
        self._log_change(ctx, entity_id, {k: v.winning_value for k, v in merges.items()})

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
        else:
            # When no issuer is known, only match securities that also have no issuer.
            # Prevents a NULL-issuer lookup from shadowing an issuer-specific entity.
            stmt = stmt.where(MdmSecurity.issuer_entity_id.is_(None))
        return [
            {"entity_id": s.entity_id, "canonical_title": s.canonical_title}
            for s, _ in ctx.session.execute(stmt).all()
        ]


def _ownership_security_source_id(txn_row: dict) -> str:
    accession = txn_row.get("accession_number")
    owner_index = txn_row.get("owner_index")
    txn_index = txn_row.get("txn_index")
    if txn_row.get("is_derivative"):
        return f"{accession}:derivative:{owner_index}:{txn_index}"
    return f"{accession}:{owner_index}:{txn_index}"
