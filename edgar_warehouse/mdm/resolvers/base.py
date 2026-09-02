"""Base resolver scaffolding shared by every domain."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmChangeLog,
    MdmEntity,
    MdmSourceRef,
)
from edgar_warehouse.mdm.match import MatchAction, MatchPipeline, MatchVerdict
from edgar_warehouse.mdm.rules import MDMRuleEngine
from edgar_warehouse.mdm.survivorship import stage_candidate


def content_hash(fields: dict[str, Any]) -> str:
    """Stable hash over the exact fields a resolver stages for one source
    row, used to detect an unchanged row across separate ``mdm mastering``
    invocations (single-path-per-layer map, Ticket 03). Callers must pass
    the same field set every time -- adding/removing a key changes the
    hash for every row, which is the desired (fail-safe, not fail-silent)
    behavior on a genuine field-set change, not a bug.
    """
    canonical = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SilverReader(Protocol):
    """Minimal protocol for silver-layer reads (DuckDB or stub)."""

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:  # pragma: no cover
        ...


@dataclass
class ResolverContext:
    session: Session
    engine: MDMRuleEngine
    silver: SilverReader
    pipeline: Optional[MatchPipeline] = None
    run_id: str = ""
    # One-time warning markers, keyed by an arbitrary id (e.g. "company.parent_cik_source"),
    # so resolvers can flag a structural data gap once per run instead of once per row.
    warned: set = field(default_factory=set)


@dataclass
class ResolveOutcome:
    entity_id: str
    is_new: bool
    verdict: Optional[MatchVerdict]
    action: MatchAction


@dataclass
class BaseResolver:
    """Shared create-or-match + staging primitives."""

    entity_type: str
    domain_fields: list[str] = field(default_factory=list)

    def _create_entity(
        self,
        ctx: ResolverContext,
        resolution_method: str,
        confidence: float,
        is_quarantined: bool = False,
    ) -> MdmEntity:
        entity = MdmEntity(
            entity_type=self.entity_type,
            resolution_method=resolution_method,
            confidence=confidence,
            is_quarantined=is_quarantined,
        )
        ctx.session.add(entity)
        ctx.session.flush()
        return entity

    def _register_source(
        self,
        ctx: ResolverContext,
        entity_id: str,
        source_system: str,
        source_id: str,
        confidence: float,
        source_content_hash: Optional[str] = None,
    ) -> None:
        ref = MdmSourceRef(
            entity_id=entity_id,
            source_system=source_system,
            source_id=str(source_id),
            source_priority=ctx.engine.get_source_priority(self.entity_type, source_system),
            confidence=confidence,
            source_content_hash=source_content_hash,
        )
        ctx.session.merge(ref)

    def _skip_if_unchanged(
        self,
        ctx: ResolverContext,
        source_system: str,
        source_id: str,
        content_hash_value: str,
    ) -> Optional[str]:
        """Return the existing entity_id if this source row's content hash
        matches what was stored at its last successful match, else None to
        signal a full resolve is required (single-path-per-layer map,
        Ticket 03). A resolver that never passes ``source_content_hash`` to
        ``_register_source`` leaves every row's stored hash NULL, which
        never matches a real hash -- callers opt in per source_system by
        computing and passing a hash; nothing changes for callers that
        don't.
        """
        stmt = select(MdmSourceRef).where(
            MdmSourceRef.source_system == source_system,
            MdmSourceRef.source_id == str(source_id),
        )
        ref = ctx.session.execute(stmt).scalars().first()
        if ref is not None and ref.source_content_hash == content_hash_value:
            return ref.entity_id
        return None

    def _stage_attrs(
        self,
        ctx: ResolverContext,
        entity_id: str,
        source_system: str,
        source_id: str,
        attrs: dict[str, Any],
        effective_date=None,
    ) -> None:
        for field_name, value in attrs.items():
            if field_name not in self.domain_fields:
                continue
            stage_candidate(
                ctx.session,
                ctx.engine,
                self.entity_type,
                entity_id,
                source_system,
                str(source_id),
                field_name,
                value,
                effective_date=effective_date,
            )

    def _log_change(
        self,
        ctx: ResolverContext,
        entity_id: str,
        changed_fields: Optional[dict] = None,
    ) -> None:
        from edgar_warehouse.mdm.run_identity import normalize_or_create_run_id

        ctx.run_id = normalize_or_create_run_id(ctx.run_id)[0]
        ctx.session.add(
            MdmChangeLog(
                entity_id=entity_id,
                entity_type=self.entity_type,
                changed_fields=changed_fields or {},
                run_id=ctx.run_id,
            )
        )

    def resolve_or_create(
        self,
        ctx: ResolverContext,
        attrs: dict,
        source_system: str,
        source_id: str,
        candidates: list[dict],
    ) -> ResolveOutcome:
        """Run matching pipeline against candidates; return the decision."""
        verdict: Optional[MatchVerdict] = None
        if ctx.pipeline is not None:
            verdict = ctx.pipeline.resolve(attrs, candidates)

        if verdict is None or verdict.action == MatchAction.QUARANTINE:
            entity = self._create_entity(
                ctx,
                resolution_method=verdict.method if verdict else "new",
                confidence=verdict.score if verdict else 0.0,
                is_quarantined=(verdict is not None and verdict.action == MatchAction.QUARANTINE),
            )
            return ResolveOutcome(
                entity_id=entity.entity_id,
                is_new=True,
                verdict=verdict,
                action=MatchAction.QUARANTINE if verdict else MatchAction.AUTO_MERGE,
            )

        assert verdict.candidate_entity_id is not None
        return ResolveOutcome(
            entity_id=verdict.candidate_entity_id,
            is_new=False,
            verdict=verdict,
            action=verdict.action,
        )
