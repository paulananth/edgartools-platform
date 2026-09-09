"""MDM rule engine.

Loads every rule row from PostgreSQL at pipeline startup and exposes typed
accessors. All runtime decisions in normalize/survivorship/match consult this
engine; no thresholds, aliases, or priority numbers are hardcoded in Python.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmFieldSurvivorship,
    MdmMatchThreshold,
    MdmNormalizationRule,
    MdmSourcePriority,
)

ALL = "all"
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")
_APOSTROPHE_RE = re.compile(r"['’]")


@dataclass(frozen=True)
class FieldRule:
    entity_type: str
    field_name: str
    rule_type: str
    source_system: Optional[str]
    preferred_source_order: Optional[list[str]]

    @property
    def has_preferred_order(self) -> bool:
        return bool(self.preferred_source_order)


@dataclass
class MDMRuleEngine:
    _source_priority: dict[tuple[str, str], int] = field(default_factory=dict)
    _field_survivorship: dict[tuple[str, str], FieldRule] = field(default_factory=dict)
    _match_thresholds: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    _normalization: dict[str, dict[str, str]] = field(default_factory=dict)
    # normalize_name is a pure function of (name, self._normalization), and
    # self._normalization never changes after load() -- safe to memoize by
    # raw input string for this engine instance's lifetime. Ticket 06's
    # security-issuer-link backfill (mdm-relationship-versioning-gap map)
    # calls FuzzyNameMatcher.match() once per security against the SAME
    # ~74K-candidate pool every time, re-normalizing every candidate name
    # from scratch on every call -- ~900M redundant calls, measured live at
    # a 13+ hour extrapolated runtime versus 27 minutes for the identical
    # work done with pre-normalized candidates. run_companies/
    # _run_grouped_concurrent share one MDMRuleEngine instance across
    # ThreadPoolExecutor worker threads (pipeline.py) -- a plain dict here
    # is still safe under that concurrent access because the function being
    # cached is pure: two threads racing on the same miss just redo the
    # same idempotent computation, never produce a wrong cached value, and
    # CPython's GIL protects the dict's own internal structure from
    # corruption. No lock needed for that reason -- don't add one.
    _normalize_name_cache: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session) -> "MDMRuleEngine":
        engine = cls()
        engine._source_priority = engine._load_source_priority(session)
        engine._field_survivorship = engine._load_field_survivorship(session)
        engine._match_thresholds = engine._load_match_thresholds(session)
        engine._normalization = engine._load_normalization_rules(session)
        return engine

    # -- loaders -----------------------------------------------------------

    @staticmethod
    def _load_source_priority(session: Session) -> dict[tuple[str, str], int]:
        stmt = select(MdmSourcePriority).where(MdmSourcePriority.is_active == True)
        return {(r.entity_type, r.source_system): r.priority for r in session.scalars(stmt)}

    @staticmethod
    def _load_field_survivorship(session: Session) -> dict[tuple[str, str], FieldRule]:
        stmt = select(MdmFieldSurvivorship).where(MdmFieldSurvivorship.is_active == True)
        out: dict[tuple[str, str], FieldRule] = {}
        for row in session.scalars(stmt):
            out[(row.entity_type, row.field_name)] = FieldRule(
                entity_type=row.entity_type,
                field_name=row.field_name,
                rule_type=row.rule_type,
                source_system=row.source_system,
                preferred_source_order=list(row.preferred_source_order)
                if row.preferred_source_order
                else None,
            )
        return out

    @staticmethod
    def _load_match_thresholds(session: Session) -> dict[tuple[str, str], tuple[float, float]]:
        stmt = select(MdmMatchThreshold).where(MdmMatchThreshold.is_active == True)
        return {
            (r.entity_type, r.match_method): (r.auto_merge_min, r.review_min)
            for r in session.scalars(stmt)
        }

    @staticmethod
    def _load_normalization_rules(session: Session) -> dict[str, dict[str, str]]:
        stmt = select(MdmNormalizationRule).where(MdmNormalizationRule.is_active == True)
        out: dict[str, dict[str, str]] = {}
        for row in session.scalars(stmt):
            out.setdefault(row.rule_type, {})[row.input_value.upper()] = row.canonical_value
        return out

    # -- accessors ---------------------------------------------------------

    def get_source_priority(self, entity_type: str, source_system: str) -> int:
        key = (entity_type, source_system)
        if key in self._source_priority:
            return self._source_priority[key]
        fallback = self._source_priority.get((ALL, source_system))
        if fallback is None:
            raise KeyError(f"No source priority rule for {entity_type}/{source_system}")
        return fallback

    def get_field_rule(self, entity_type: str, field_name: str) -> Optional[FieldRule]:
        return self._field_survivorship.get((entity_type, field_name))

    def get_threshold(self, entity_type: str, method: str) -> tuple[float, float]:
        key = (entity_type, method)
        if key not in self._match_thresholds:
            raise KeyError(f"No match threshold for {entity_type}/{method}")
        return self._match_thresholds[key]

    def source_rank(self, entity_type: str, source_system: str) -> int:
        """Alias of get_source_priority; used by survivorship ordering."""
        return self.get_source_priority(entity_type, source_system)

    # -- normalization -----------------------------------------------------

    def normalize_name(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return name
        # normalize_name(name) for a truthy `name` always returns a str
        # (possibly empty), never None -- a `.get(name)` hit is unambiguous.
        cached = self._normalize_name_cache.get(name)
        if cached is not None:
            return cached
        result = self._normalize_name_uncached(name)
        self._normalize_name_cache[name] = result
        return result

    def _normalize_name_uncached(self, name: str) -> str:
        text = name.strip().lower()
        # Drop apostrophes rather than routing them through the general
        # punctuation-to-space substitution below -- a possessive name like
        # "McDonald's" must normalize to one token ("mcdonalds"), matching a
        # canonical name that never had the apostrophe, not split into two
        # tokens ("mcdonald", "s") that no longer align with anything.
        text = _APOSTROPHE_RE.sub("", text)
        text = _PUNCT_RE.sub(" ", text)
        tokens = _WS_RE.split(text)
        suffixes = self._normalization.get("legal_suffix", {})
        cleaned: list[str] = []
        for tok in tokens:
            if not tok:
                continue
            replacement = suffixes.get(tok.upper())
            if replacement is None:
                cleaned.append(tok)
            elif replacement:
                cleaned.append(replacement)
            # else: empty replacement → drop the token entirely
        # Drop a trailing share-class designation ("Class A"/"Class B"/...).
        # Security issuer names carry this constantly (Form 3/4/5 filer
        # names); MdmCompany.canonical_name essentially never does -- the
        # issuer's identity doesn't change by share class. Scoped narrowly
        # to "class" immediately followed by a single letter so a lone
        # letter elsewhere in a name is never touched.
        if len(cleaned) >= 2 and cleaned[-2] == "class" and len(cleaned[-1]) == 1:
            cleaned = cleaned[:-2]
        joined = " ".join(cleaned).strip()
        return " ".join(w.capitalize() for w in joined.split())

    def normalize_title(self, title: Optional[str]) -> Optional[str]:
        if not title:
            return title
        raw = _PUNCT_RE.sub(" ", title.upper()).strip()
        raw = _WS_RE.sub(" ", raw)
        aliases = self._normalization.get("title_alias", {})
        if raw in aliases:
            return aliases[raw]
        return " ".join(w.capitalize() for w in raw.lower().split())

    def normalize_address(self, address: Optional[dict]) -> Optional[dict]:
        if not address:
            return address
        out = dict(address)
        street = out.get("street")
        if street:
            abbrs = self._normalization.get("address_abbr", {})
            tokens = _WS_RE.split(street.strip())
            out["street"] = " ".join(abbrs.get(t.upper().rstrip("."), t) for t in tokens if t)
        state = out.get("state")
        if state:
            states = self._normalization.get("state_code", {})
            key = state.upper().strip()
            out["state"] = states.get(key, state if len(state) == 2 else state.upper())
        country = out.get("country")
        if country:
            countries = self._normalization.get("country_code", {})
            key = country.upper().strip()
            out["country"] = countries.get(key, country.upper() if len(country) <= 3 else country)
        return out

    # -- introspection helpers used by stewardship/admin UI ---------------

    def all_active_sources(self) -> set[str]:
        return {src for (_, src) in self._source_priority.keys()}

    def all_entity_types(self) -> set[str]:
        return {et for (et, _) in self._source_priority.keys()} - {ALL}
