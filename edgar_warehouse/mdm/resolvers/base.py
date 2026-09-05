"""Base resolver scaffolding shared by every domain."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmChangeLog,
    MdmEntity,
    MdmMatchReview,
    MdmSourceRef,
)
from edgar_warehouse.mdm.match import MatchAction, MatchPipeline, MatchVerdict
from edgar_warehouse.mdm.rules import MDMRuleEngine
from edgar_warehouse.mdm.survivorship import MergeResult, stage_candidate


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
        existing: dict,
        merge_results: dict[str, MergeResult],
    ) -> None:
        """Write one mdm_change_log row, but only if survivorship actually
        picked a different winning value than what's already stored.

        Without this comparison, every entity a resolver touches gets a
        fresh changelog row on every mastering pass regardless of whether
        anything changed -- confirmed live to have accumulated 584,338
        change_log rows (one entity alone: 40,356), which in turn made
        every `mdm publish` re-drain a backlog that regenerates itself
        instead of shrinking. `merge_results` carries every field's current
        winning value unconditionally; `existing` is the entity's
        already-stored golden-record values, so the diff belongs here.
        """
        changed_fields = {
            field_name: result.winning_value
            for field_name, result in merge_results.items()
            if existing.get(field_name) != result.winning_value
        }
        if not changed_fields:
            return

        from edgar_warehouse.mdm.run_identity import normalize_or_create_run_id

        ctx.run_id = normalize_or_create_run_id(ctx.run_id)[0]
        ctx.session.add(
            MdmChangeLog(
                entity_id=entity_id,
                entity_type=self.entity_type,
                changed_fields=changed_fields,
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
        *,
        reconciliation_mode: bool = False,
    ) -> ResolveOutcome:
        """Run matching pipeline against candidates; return the decision.

        ``reconciliation_mode`` (change-propagation Ticket 50, the MDM
        Reconciliation Backstop) is the one caller-visible behavior change
        this ticket adds -- default False leaves every existing caller
        (ordinary ``mdm mastering``) byte-for-byte unchanged. When True and
        this exact ``(source_system, source_id)`` row already has a live
        MDM entity assignment, rescoring routes through
        ``_reconcile_against_existing`` instead of the plain create/merge
        path below -- see that method's docstring for the finding
        disposition. A row with no existing assignment (genuinely new,
        even during a backstop pass) always falls through to the unchanged
        path below.
        """
        verdict: Optional[MatchVerdict] = None
        if ctx.pipeline is not None:
            verdict = ctx.pipeline.resolve(attrs, candidates)

        if reconciliation_mode:
            existing_entity_id = self._current_entity_id(ctx, source_system, source_id)
            if existing_entity_id is not None:
                return self._reconcile_against_existing(ctx, existing_entity_id, verdict)

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

    def _current_entity_id(
        self, ctx: ResolverContext, source_system: str, source_id: str
    ) -> Optional[str]:
        """The entity this exact source row is *currently* mapped to, if
        any -- unlike ``_skip_if_unchanged``, this ignores content hash
        entirely (Ticket 50 always rescores; it only needs to know what a
        row is already attached to so a rescore can be compared against it).
        """
        stmt = select(MdmSourceRef.entity_id).where(
            MdmSourceRef.source_system == source_system,
            MdmSourceRef.source_id == str(source_id),
        )
        return ctx.session.execute(stmt).scalar_one_or_none()

    def _reconcile_against_existing(
        self,
        ctx: ResolverContext,
        existing_entity_id: str,
        verdict: Optional[MatchVerdict],
    ) -> ResolveOutcome:
        """Ticket 50's finding disposition for a row that already has a live
        MDM entity assignment (the "already-resolved golden records" list
        in the design ticket this implements):

          - No verdict, or the best candidate found IS the existing
            assignment -> no-op; rescoring only reconfirmed it.
          - AUTO_MERGE onto a *different* entity -> the two golden records
            are the same real-world thing; merge the existing one into the
            new candidate via the existing merge_entities machinery.
          - REVIEW band -> insert MdmMatchReview (deduped against an
            existing pending pair) and leave the assignment untouched until
            a human accepts it.
          - QUARANTINE (below review_min), regardless of what low-confidence
            candidate it nominally prefers -> no-op. A live golden record is
            never auto-split because a backstop score went cold. This is
            deliberately narrower than Ticket 38's own "queue for review
            only if it now prefers someone else" aside: FuzzyNameMatcher/
            SplinkMatcher always attach a best-effort candidate_entity_id
            even far below review_min (confirmed by reading match.py), so
            honoring that aside literally would flood the review queue with
            near-arbitrary low-confidence pairs on the very first backstop
            run over live production data. Ticket 50's own checklist bullet
            2 only requires review-band inserts; this implements that.
        """
        if verdict is None or verdict.candidate_entity_id == existing_entity_id:
            action = verdict.action if verdict is not None else MatchAction.QUARANTINE
            return ResolveOutcome(
                entity_id=existing_entity_id, is_new=False, verdict=verdict, action=action
            )

        assert verdict.candidate_entity_id is not None
        if verdict.action == MatchAction.AUTO_MERGE:
            # The private, non-committing _merge_entities -- not the public
            # merge_entities wrapper, which commits immediately (stewardship.py).
            # A commit here would land a half-processed row: _stage_attrs/
            # _register_source/survivorship in resolve_one still run after
            # resolve_or_create returns. accept_review() (stewardship.py) uses
            # the same private variant for the identical reason.
            from edgar_warehouse.mdm.stewardship import _merge_entities

            _merge_entities(
                ctx.session,
                keep=verdict.candidate_entity_id,
                discard=existing_entity_id,
                reason="mdm_reconciliation_backstop",
                run_id=ctx.run_id or "",
            )
            return ResolveOutcome(
                entity_id=verdict.candidate_entity_id,
                is_new=False,
                verdict=verdict,
                action=verdict.action,
            )

        if verdict.action == MatchAction.REVIEW:
            self._queue_match_review(
                ctx,
                candidate_entity_id=verdict.candidate_entity_id,
                existing_entity_id=existing_entity_id,
                verdict=verdict,
            )
            return ResolveOutcome(
                entity_id=existing_entity_id, is_new=False, verdict=verdict, action=verdict.action
            )

        # QUARANTINE: never auto-split a live golden record.
        return ResolveOutcome(
            entity_id=existing_entity_id, is_new=False, verdict=verdict, action=verdict.action
        )

    @staticmethod
    def _queue_match_review(
        ctx: ResolverContext,
        *,
        candidate_entity_id: str,
        existing_entity_id: str,
        verdict: MatchVerdict,
    ) -> None:
        already_pending = ctx.session.execute(
            select(MdmMatchReview.review_id).where(
                MdmMatchReview.status == "pending",
                or_(
                    and_(
                        MdmMatchReview.entity_id_a == candidate_entity_id,
                        MdmMatchReview.entity_id_b == existing_entity_id,
                    ),
                    and_(
                        MdmMatchReview.entity_id_a == existing_entity_id,
                        MdmMatchReview.entity_id_b == candidate_entity_id,
                    ),
                ),
            )
        ).first()
        if already_pending is not None:
            return
        ctx.session.add(
            MdmMatchReview(
                entity_id_a=candidate_entity_id,
                entity_id_b=existing_entity_id,
                match_score=verdict.score,
                match_evidence=verdict.evidence,
                status="pending",
            )
        )
