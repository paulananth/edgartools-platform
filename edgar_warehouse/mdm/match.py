"""Entity matching engine.

Matchers run in priority order (first match wins):

  1. CIK exact     — definitive, confidence = 1.0
  2. Fuzzy name    — Jaro-Winkler on normalized names + context (issuer, title)
  3. Splink ML     — probabilistic matcher, trained on CIK-confirmed pairs

Confidence thresholds come from mdm_match_threshold via MDMRuleEngine.
Each matcher returns a MatchVerdict the caller uses to decide:
  - auto-merge (>= auto_merge_min)
  - curation queue (>= review_min and < auto_merge_min)
  - quarantine (< review_min → new unresolved entity)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

try:  # optional dependency; installed via the [mdm] extra
    import jellyfish  # type: ignore
except ImportError:  # pragma: no cover - import guard
    jellyfish = None  # type: ignore

from edgar_warehouse.mdm.rules import MDMRuleEngine


class MatchAction(str, Enum):
    AUTO_MERGE = "auto_merge"
    REVIEW = "review"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class MatchVerdict:
    score: float
    method: str
    action: MatchAction
    candidate_entity_id: Optional[str]
    evidence: dict


class Matcher(Protocol):
    method: str

    def match(
        self,
        attrs: dict,
        candidates: list[dict],
    ) -> Optional[MatchVerdict]:  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# CIK exact matcher
# ---------------------------------------------------------------------------

@dataclass
class CIKExactMatcher:
    method: str = "cik_exact"

    def match(self, attrs: dict, candidates: list[dict]) -> Optional[MatchVerdict]:
        target = attrs.get("cik") or attrs.get("owner_cik")
        if target is None:
            return None
        for c in candidates:
            existing = c.get("cik") or c.get("owner_cik")
            if existing is not None and int(existing) == int(target):
                return MatchVerdict(
                    score=1.0,
                    method=self.method,
                    action=MatchAction.AUTO_MERGE,
                    candidate_entity_id=c["entity_id"],
                    evidence={"cik": int(target)},
                )
        return None


# ---------------------------------------------------------------------------
# Fuzzy name matcher (Jaro-Winkler + context fields)
# ---------------------------------------------------------------------------

def _jw(a: str, b: str) -> float:
    if jellyfish is None:
        # Deterministic fallback keeps tests runnable if jellyfish missing
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        longest = max(len(a), len(b))
        return 1 - (abs(len(a) - len(b)) / longest) if longest else 0.0
    return float(jellyfish.jaro_winkler_similarity(a, b))


@dataclass
class FuzzyNameMatcher:
    entity_type: str
    engine: MDMRuleEngine
    name_field: str = "canonical_name"
    context_fields: tuple[str, ...] = ()
    method: str = "fuzzy_name"

    def match(self, attrs: dict, candidates: list[dict]) -> Optional[MatchVerdict]:
        name = self.engine.normalize_name(attrs.get(self.name_field) or attrs.get("name"))
        if not name or not candidates:
            return None
        auto_min, review_min = self.engine.get_threshold(self.entity_type, self.method)

        best: tuple[float, dict] | None = None
        for c in candidates:
            cname = self.engine.normalize_name(c.get(self.name_field) or c.get("name"))
            if not cname:
                continue
            score = _jw(name, cname)
            # Context boost: require matching context fields to clear auto_min
            if self.context_fields:
                ok = all(
                    attrs.get(f) is not None
                    and c.get(f) is not None
                    and str(attrs[f]) == str(c[f])
                    for f in self.context_fields
                )
                if not ok and score >= auto_min:
                    score = min(score, auto_min - 0.01)
            if best is None or score > best[0]:
                best = (score, c)

        if best is None:
            return None
        score, cand = best
        action = self._classify(score, auto_min, review_min)
        return MatchVerdict(
            score=score,
            method=self.method,
            action=action,
            candidate_entity_id=cand["entity_id"],
            evidence={
                "name_a": name,
                "name_b": self.engine.normalize_name(cand.get(self.name_field)),
                "context_fields": list(self.context_fields),
            },
        )

    @staticmethod
    def _classify(score: float, auto_min: float, review_min: float) -> MatchAction:
        if score >= auto_min:
            return MatchAction.AUTO_MERGE
        if score >= review_min:
            return MatchAction.REVIEW
        return MatchAction.QUARANTINE


# ---------------------------------------------------------------------------
# Splink ML matcher (framework hook; model trained offline)
# ---------------------------------------------------------------------------

@dataclass
class SplinkMatcher:
    """Splink-backed probabilistic matcher.

    The model object is injected at construction time. Training lives in
    `scripts/mdm/train_splink.py` (not in this module) because training
    consumes the full CIK-confirmed pair corpus.
    """

    entity_type: str
    engine: MDMRuleEngine
    model: object | None = None
    method: str = "ml_splink"

    def match(self, attrs: dict, candidates: list[dict]) -> Optional[MatchVerdict]:
        if self.model is None or not candidates:
            return None
        auto_min, review_min = self.engine.get_threshold(self.entity_type, self.method)
        # The Splink predict_pairwise hook returns (candidate_idx, score).
        predict = getattr(self.model, "predict_pairwise", None)
        if predict is None:
            return None
        best_idx, best_score = predict(attrs, candidates)  # type: ignore[misc]
        cand = candidates[best_idx]
        action = FuzzyNameMatcher._classify(best_score, auto_min, review_min)
        return MatchVerdict(
            score=float(best_score),
            method=self.method,
            action=action,
            candidate_entity_id=cand["entity_id"],
            evidence={"model": type(self.model).__name__},
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class MatchPipeline:
    """Run matchers in priority order; first auto_merge wins, otherwise keep best."""

    matchers: list[Matcher]

    def resolve(self, attrs: dict, candidates: list[dict]) -> Optional[MatchVerdict]:
        best: Optional[MatchVerdict] = None
        for m in self.matchers:
            v = m.match(attrs, candidates)
            if v is None:
                continue
            if v.action == MatchAction.AUTO_MERGE:
                return v
            if best is None or v.score > best.score:
                best = v
        return best
