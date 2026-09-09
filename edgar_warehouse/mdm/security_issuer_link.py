"""mdm-relationship-versioning-gap Ticket 06: link CUSIP-stub securities
(13F-derived, no Form-4 anchor) to their issuer ``MdmCompany`` row.

13F holdings report issuer identity as CUSIP + free-text ``issuer_name``,
with no shared key against the Form-4-derived security universe (Form 3/4/5
XML carries no CUSIP at all -- confirmed against edgartools' own
``Ownership`` model) and no CUSIP-to-CIK crosswalk available to this
system. Fuzzy name matching against the known company universe is the only
viable link.

This deliberately reuses ``edgar_warehouse.mdm.match.FuzzyNameMatcher`` and
the already-seeded ``('company', 'fuzzy_name')`` threshold
(``002_seed_data.sql``, auto_merge_min=0.95, review_min=0.85) rather than a
new, unproven threshold pair -- the entity being matched genuinely IS a
company. Note this is a materially different exercise of that matcher than
its one other production caller: ``CompanyResolver`` scopes its own
candidate list by exact CIK (at most one candidate, "rarely needed" per its
own docstring), so this is that matcher's first real multi-candidate
application. The existing thresholds were chosen for company-name matching
generally, not specifically validated against 13F issuer-name noise, so a
mismatch found in production should prompt revisiting the threshold values,
not the matcher choice.

Review-tier candidates (score in [review_min, auto_merge_min)) are
deliberately NOT written to ``mdm_match_review`` -- that table's
``accept_review`` always calls ``_merge_entities`` (discard one side,
keep the other), which is correct for its actual use (deduping two
same-type entities) but would silently and destructively merge a security
into a company here, since these are two different entity types being
linked, not deduped. Review-tier matches are logged only, for manual
follow-up; below review_min is left untouched exactly as today, with no
log noise for a near-certain non-match.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmCompany, MdmEntity, MdmSecurity
from edgar_warehouse.mdm.match import MatchAction, MatchVerdict, FuzzyNameMatcher
from edgar_warehouse.mdm.rules import MDMRuleEngine


def load_company_candidates(session: Session) -> list[dict]:
    """Fetch the full company candidate pool once per run.

    Unlike every other fuzzy-match use in this codebase, issuer_name carries
    no CIK to narrow the candidate list by -- this must compare against the
    whole company universe, so the caller should fetch this once (mirroring
    the bulk-prefetch pattern this codebase already uses elsewhere for
    per-batch lookups) rather than per security.
    """
    stmt = select(MdmCompany.entity_id, MdmCompany.canonical_name)
    return [
        {"entity_id": entity_id, "canonical_name": canonical_name}
        for entity_id, canonical_name in session.execute(stmt).all()
    ]


def match_issuer_candidate(
    engine: MDMRuleEngine, issuer_name: Optional[str], candidates: list[dict]
) -> Optional[MatchVerdict]:
    """Score ``issuer_name`` against the company candidate pool.

    Returns None if there's nothing to score (no name, or no candidates --
    an empty company universe, which should never happen in a real MDM
    Postgres instance but is a legitimate empty-fixture case in tests), or
    if the ('company', 'fuzzy_name') threshold isn't configured
    (``MDMRuleEngine.get_threshold`` raises ``KeyError`` -- a real gap in
    ``mdm_match_threshold`` seeding, not something this best-effort,
    opportunistic linking should ever let crash the caller's derivation).
    """
    if not issuer_name or not candidates:
        return None
    matcher = FuzzyNameMatcher(entity_type="company", engine=engine)
    try:
        return matcher.match({"canonical_name": issuer_name}, candidates)
    except KeyError:
        return None


def _log_review_candidate(verdict: MatchVerdict, *, cusip: str, issuer_name: str) -> None:
    """Structured event for a REVIEW-tier issuer-link candidate -- manual
    follow-up only, never written to ``mdm_match_review`` (see module
    docstring for why: its ``accept_review`` always merges one entity into
    another, which would be destructively wrong for a security-to-company
    FK link rather than a same-type dedup).
    """
    print(json.dumps({
        "event": "mdm_issuer_link_candidate_below_threshold",
        "cusip": cusip,
        "issuer_name": issuer_name,
        "candidate_entity_id": verdict.candidate_entity_id,
        "candidate_canonical_name": verdict.evidence.get("name_b"),
        "score": verdict.score,
        "ts": datetime.now(timezone.utc).isoformat(),
    }), file=sys.stderr, flush=True)


def resolve_issuer_entity_id(
    engine: MDMRuleEngine,
    issuer_name: Optional[str],
    candidates: list[dict],
    *,
    cusip: str = "",
) -> Optional[str]:
    """Apply ``match_issuer_candidate``'s verdict: only AUTO_MERGE actually
    links. REVIEW logs a structured event for manual follow-up; QUARANTINE
    (below review_min) is silent -- a near-certain non-match isn't worth
    logging for every one of thousands of low-score comparisons.
    """
    verdict = match_issuer_candidate(engine, issuer_name, candidates)
    if verdict is None:
        return None
    if verdict.action == MatchAction.AUTO_MERGE:
        return verdict.candidate_entity_id
    if verdict.action == MatchAction.REVIEW:
        _log_review_candidate(verdict, cusip=cusip, issuer_name=issuer_name)
    return None


@dataclass
class SecurityIssuerLinkBackfillSummary:
    examined: int = 0
    linked: int = 0
    review_logged: int = 0
    skipped_no_name: int = 0
    skipped_no_match: int = 0


def backfill_missing_issuer_links(
    session: Session, *, dry_run: bool = False
) -> SecurityIssuerLinkBackfillSummary:
    """Retroactively link already-existing CUSIP-stub securities that
    predate this fix (or any security whose issuer link never got set) --
    mirrors mdm-relationship-versioning-gap Ticket 05's targeted-correction
    shape: fix the write path forward (``pipeline.py``'s
    ``_ensure_security_by_cusip``), backfill already-existing rows here.
    """
    summary = SecurityIssuerLinkBackfillSummary()
    candidates = load_company_candidates(session)
    engine = MDMRuleEngine.load(session)

    # Scoped to resolution_method='cusip_stub' -- matching the ticket's own
    # live diagnostic query exactly, not the broader "any security missing
    # an issuer link" -- a security created some other way that also lacks
    # an issuer link is a different, undiscussed problem, not this ticket's.
    stmt = (
        select(MdmSecurity)
        .join(MdmEntity, MdmEntity.entity_id == MdmSecurity.entity_id)
        .where(
            MdmSecurity.issuer_entity_id.is_(None),
            MdmSecurity.cusip.isnot(None),
            MdmEntity.resolution_method == "cusip_stub",
        )
    )
    for security in session.scalars(stmt):
        summary.examined += 1
        issuer_name = security.canonical_title
        if not issuer_name:
            summary.skipped_no_name += 1
            continue
        verdict = match_issuer_candidate(engine, issuer_name, candidates)
        if verdict is None or verdict.action == MatchAction.QUARANTINE:
            summary.skipped_no_match += 1
            continue
        if verdict.action == MatchAction.REVIEW:
            summary.review_logged += 1
            _log_review_candidate(verdict, cusip=security.cusip, issuer_name=issuer_name)
            continue
        # AUTO_MERGE
        if not dry_run:
            security.issuer_entity_id = verdict.candidate_entity_id
        summary.linked += 1

    return summary
