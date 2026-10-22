"""SEC-to-GLEIF name matching, proposed inside the Merge Stage.

Company mastering ticket 08. A waiting GLEIF record joins the Company its SEC
record already holds by CIK when an active `name_binding` rule's tests all
hold. The rules are measured, not deterministic: each activates only with its
proof at the operator's 95% band (`activation.py`).

A pair is found from either side, because the two sources load separately:
- a GLEIF record in this batch meets an SEC record already in the Stage;
- an SEC record in this batch meets a GLEIF record already waiting.

The Name Census (`name_census.py`) the SEC record carries only **proposes**
the pair. Every test runs here, on the Stage rows: both name keys are
re-derived, the census must name exactly this CIK and this LEI at the GLEIF
record's own last update, and the place tests read both records.

This module only proposes, as `binding.py` does. The Merge Stage assesses
every proposal before it commits (Q13). It never creates a Company.
"""

from __future__ import annotations

from collections import defaultdict
from functools import partial

from . import cascade, correction
from .activation import activated
from .binding import bound, in_review, nothing, survivors
from .evidence import decision
from .name_census import VERSION as CENSUS_VERSION
from .names import _EDGAR_ISO
from .store import Conflict, rows

FAMILY = "name_binding"


def active_rules(policy: dict) -> list[tuple[str, dict]]:
    return [
        (kind, rule)
        for kind, block in sorted((policy.get("kinds") or {}).items())
        for rule in block.get("rules") or []
        if rule.get("family") == FAMILY and activated(policy, kind, rule, "bind")
    ]


_value, _matching = cascade.field_value, cascade.matching_values


def _read(record: dict, path: str):
    """Read the declared matching path through the shared native implementation."""
    from edgar_warehouse.rules.source_engine import apply_record_rules
    try:
        return apply_record_rules({"action": "read_matching_field", "record": record, "name": path})
    except ValueError as error:
        raise Conflict(str(error)) from None


def _census_lei(record: dict) -> str | None:
    """The first LEI the record's census entry names; the rule needs exactly one."""
    leis = (_matching(record).get("name_census") or {}).get("leis") or []
    return leis[0][0] if leis else None


def _cascade_lei(record: dict) -> str | None:
    """The LEI the census's cascade assigned this record's CIK (ticket 21)."""
    return ((_matching(record).get("name_census") or {}).get("cascade") or {}).get("lei")


def _pair_lei(rule: dict):
    """How a rule finds the GLEIF record for an SEC one: a cascade pass reads
    the cascade's answer, the other rules the census entry."""
    if any(t["primitive"] == cascade.TEST for t in rule["when"]):
        return _cascade_lei, "cascade_lei"
    return _census_lei, "census_lei"


def compare_candidate_records(rule: dict, pairs: list[tuple[dict, dict]]) -> list[list[bool]]:
    """Transfer a batch of candidate pairs and its pinned reference rules once."""
    from edgar_warehouse.rules.source_engine import compare_record_pairs
    from .identifier_types import TYPES

    try:
        return compare_record_pairs({
            "rule": rule, "pairs": pairs,
            "code_tables": {"edgar-iso-v1": _EDGAR_ISO},
            "normalizers": {kind.normalizer_name: kind.upper for kind in TYPES.values()},
            "census_version": CENSUS_VERSION, "cascade_version": cascade.VERSION,
        })
    except ValueError as error:
        raise Conflict(str(error)) from None


def compare_pair_test(name: str, left: dict, right: dict, args: dict) -> bool:
    return compare_candidate_records({"when": [{"primitive": name, "args": args}]}, [(left, right)])[0][0]


HELD_LEI_TEST = "holds_no_other_lei@1"
PAIR_TESTS = {
    name: partial(compare_pair_test, name) for name in (
        "name_census_match@1", "gleif_entity_eligible@1", "jurisdiction_agrees@1",
        "jurisdictions_do_not_conflict@1", "postal_agrees@1", cascade.TEST,
    )
}


def _passes(rule: dict, sec: dict, gleif: dict) -> bool:
    return compare_candidate_records(rule, [(sec, gleif)])[0][0]


def _refused_by_flag(rule: dict, sec: dict, gleif: dict) -> bool:
    return compare_candidate_records(rule, [(sec, gleif)])[0][1]


def _latest(found: list[dict]) -> dict[str, dict]:
    by_subject: dict[str, dict] = {}
    for body in sorted(
        found, key=lambda a: (a["revision"], a.get("mapping_version", 1))
    ):
        by_subject[body["subject"]] = body
    return by_subject


# The only lookups `_stored` runs: fixed expressions, never caller text.
_LOOKUPS = {
    "lei": "reading->'identifiers'->>'lei'",
    "census_lei": "reading->'provenance'->'matching'->'name_census'->'leis'->0->>0",
    "cascade_lei": "reading->'provenance'->'matching'->'name_census'->'cascade'->>'lei'",
}


def _stored(conn, source: str, lookup: str, values: list[str]) -> list[dict]:
    """The latest stored version of each record of `source` matching `lookup`."""
    if not values:
        return []
    where = _LOOKUPS[lookup]
    return [
        r["reading"]
        for r in rows(
            conn,
            f"""SELECT reading FROM mdm.stage_record
            WHERE source_code = :source AND {where} = ANY(:values)""",
            source=source,
            values=sorted(set(values)),
        )
    ]


def _bindings(
    conn, subjects: set[str], decisions: list[dict], released: set[str] = frozenset()
) -> dict[str, set]:
    entities: dict[str, set] = defaultdict(set)
    for d in decisions:
        if d["operation"] == "bind" and d["subject"] in subjects:
            entities[d["subject"]].add(d["entity_id"])
    for subject, entity in bound(conn, subjects).items():
        if subject not in released:
            entities[subject].add(entity)
    return entities


def _held_leis(conn, source: str, entities: set[str], released: set[str] = frozenset()) -> dict:
    """The LEIs each Company already holds through its bound GLEIF records,
    not counting a record this batch releases (ticket 13)."""
    held: dict[str, set] = defaultdict(set)
    for r in rows(
        conn,
        """SELECT entity_id::text AS entity_id, reading->'identifiers'->>'lei' AS lei
        FROM mdm.stage_record
        WHERE entity_id = ANY(CAST(:entities AS uuid[])) AND source_code = :source
          AND reading->'identifiers'->>'lei' IS NOT NULL
          AND NOT subject = ANY(:released)""",
        entities=sorted(entities),
        source=source,
        released=sorted(released),
    ):
        held[r["entity_id"]].add(r["lei"])
    return held


def propose(
    conn,
    policy: dict,
    *,
    assertions: list[dict],
    decisions: list[dict],
    as_of: str,
    released: set[str],
) -> dict:
    """The bindings the active name-binding rules propose for this batch.

    `decisions` holds the caller's and the identifier rules' bindings for this
    batch, so an SEC record bound in the same batch holds its Company.
    """
    rules = active_rules(policy)
    result = nothing()
    if not rules or not assertions:
        return result
    batch = _latest(assertions)
    for _kind, rule in rules:
        source, holder = rule["source"], rule["holder_source"]
        gleif_here = [
            a
            for a in batch.values()
            if a["source_code"] == source and a["kind"] == rule["applies_to_verdict"]
        ]
        sec_here = [a for a in batch.values() if a["source_code"] == holder]
        lei_of, lookup = _pair_lei(rule)
        # Each side of a pair: from this batch, or the latest stored version.
        lei_of_sec = {lei_of(a) for a in sec_here} - {None}
        gleif_all = _latest(
            _stored(conn, source, "lei", sorted(lei_of_sec)) + gleif_here
        )
        # A quarantined record is left out of matching (ticket 13), stored
        # or delivered: a later batch's SEC record never pairs with it.
        for subject in correction.quarantined(conn, set(gleif_all), decisions):
            del gleif_all[subject]
        leis = [(a.get("identifiers") or {}).get("lei") for a in gleif_all.values()]
        sec_all = _latest(
            _stored(
                conn,
                holder,
                lookup,
                [lei for lei in leis if lei],
            )
            + sec_here
        )
        sec_by_lei = defaultdict(list)
        for sec in sec_all.values():
            if lei := lei_of(sec):
                sec_by_lei[lei].append(sec)
        subjects = set(gleif_all) | set(sec_all)
        bindings = _bindings(conn, subjects, decisions + result["decisions"], released)
        refused = correction.refused(conn, set(gleif_all), decisions)
        candidates = []
        for gleif in gleif_all.values():
            if bindings.get(gleif["subject"]):
                continue
            lei = (gleif.get("identifiers") or {}).get("lei")
            for sec in sec_by_lei.get(lei, []):
                companies = bindings.get(sec["subject"]) or set()
                if len(companies) == 1:
                    candidates.append((gleif, sec, next(iter(companies))))
        outcomes = compare_candidate_records(rule, [(sec, gleif) for gleif, sec, _ in candidates])
        pairs = []
        for (gleif, sec, entity), (passed, flagged) in zip(candidates, outcomes, strict=True):
            if passed:
                pairs.append((gleif, sec, entity))
            elif flagged:
                result["reviews"].append({
                    "reason": "cascade_flagged_pair", "namespace": "lei",
                    "subject": gleif["subject"], "assertion_id": gleif["assertion_id"],
                })
        if not pairs:
            continue
        merged = survivors(conn, {entity for _, _, entity in pairs})
        pairs = [(g, s, merged.get(e, e)) for g, s, e in pairs]
        held = _held_leis(conn, source, {e for _, _, e in pairs}, released)
        suspended = in_review(conn, {e for _, _, e in pairs})
        targets: dict[str, set] = defaultdict(set)
        for gleif, _sec, entity in pairs:
            targets[gleif["subject"]].add(entity)
        for gleif, sec, entity in pairs:
            lei = gleif["identifiers"]["lei"]
            if len(targets[gleif["subject"]]) > 1:
                result["reviews"].append(
                    {
                        "reason": "ambiguous_name_match",
                        "namespace": "lei",
                        "subject": gleif["subject"],
                        "assertion_id": gleif["assertion_id"],
                    }
                )
                targets[gleif["subject"]] = set()  # one review, no binding
                continue
            if not targets[gleif["subject"]]:
                continue
            if entity in suspended:
                # As for identifier rules (`binding.in_review`): a Company in
                # review for a contradiction gains no record by a rule.
                result["reviews"].append(
                    {
                        "reason": "suspended_identifier",
                        "namespace": "lei",
                        "subject": gleif["subject"],
                        "assertion_id": gleif["assertion_id"],
                    }
                )
                targets[gleif["subject"]] = set()
                continue
            # A legal entity has one LEI: a Company holding another defers,
            # when the rule asks it to.
            vetoes = any(t["primitive"] == HELD_LEI_TEST for t in rule["when"])
            if vetoes and held[entity] - {lei}:
                continue
            if (gleif["subject"], rule["rule_id"], rule["version"]) in refused:
                continue  # a correction revoked this record's link under this version
            result["decisions"].append(
                decision(
                    "bind",
                    actor=f"rule:{rule['rule_id']}@{rule['version']}",
                    # Evidence describes the subject bound; the SEC record the
                    # name matched is named here, and holds the Company.
                    reason=f"name_match lei with {sec['assertion_id']}",
                    at=as_of,
                    subject=gleif["subject"],
                    entity_id=entity,
                    evidence=[gleif["assertion_id"]],
                    rule_id=rule["rule_id"],
                    rule_version=rule["version"],
                )
            )
            held[entity].add(lei)
            targets[gleif["subject"]] = set()
    return result
