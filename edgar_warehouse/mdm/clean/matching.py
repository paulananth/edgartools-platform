"""Propose measured name bindings using the rule's pinned record selectors.

Either source can arrive first. Candidate retrieval proposes pairs from the
current readings; the shared native comparison checks the declared census,
names, eligibility and places. The Merge Stage assesses every proposal before
commit. This module never creates a master or activates a rule.
"""

from __future__ import annotations

from collections import defaultdict
from functools import partial

from . import cascade, correction
from .activation import activated
from .catalog import CATALOG, assert_current
from .binding import bound, in_review, nothing, survivors
from .evidence import decision
from .name_census import VERSION as CENSUS_VERSION
from .names import REFERENCE_TABLES
from .store import Conflict, rows

FAMILY = "name_binding"


def active_rules(policy: dict) -> list[tuple[str, dict]]:
    return [
        (kind, rule)
        for kind, block in sorted((policy.get("kinds") or {}).items())
        for rule in block.get("rules") or []
        if rule.get("family") == FAMILY and activated(policy, kind, rule, "bind")
    ]


def _read(record: dict, path: str):
    """Read the declared matching path through the shared native implementation."""
    from edgar_warehouse.rules.source_engine import apply_record_rules
    try:
        return apply_record_rules({"action": "read_matching_field", "record": record, "name": path})
    except ValueError as error:
        raise Conflict(str(error)) from None


def comparison_profile(rule: dict) -> dict:
    """Candidate retrieval and comparison use the same pinned declaration."""
    assert_current()
    profile = rule.get("pair_comparison", CATALOG["legacy_pair_comparison"])
    if not isinstance(profile, str) or profile not in CATALOG["pair_comparisons"]:
        raise Conflict("Name binding names an unknown pair comparison profile")
    return CATALOG["pair_comparisons"][profile]


def candidate_paths(rule: dict) -> dict[str, tuple]:
    profile = comparison_profile(rule)
    census = ("provenance", "matching", profile["census_field"])
    return {
        "identifier": ("identifiers", profile["identifier_namespace"]),
        "census": (*census, profile["census_entries_field"], 0, 0),
        "cascade": (*census, profile["cascade_field"], profile["cascade_identifier_field"]),
    }


def candidate_routes() -> dict[str, tuple]:
    """All build-pinned candidate selectors, with unambiguous opaque keys."""
    from .store import canonical

    assert_current()
    return {
        canonical([profile, role]): path
        for profile in sorted(CATALOG["pair_comparisons"])
        for role, path in candidate_paths({"pair_comparison": profile}).items()
    }


def candidate_value(record: dict, path: tuple) -> str | None:
    """Read a scalar candidate key; absent or malformed paths propose nothing."""
    value = record
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, list) or len(value) <= key:
                return None
            value = value[key]
        else:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
    return value if isinstance(value, str) and value else None


def compare_candidate_records(rule: dict, pairs: list[tuple[dict, dict]]) -> list[list[bool]]:
    """Transfer a batch of candidate pairs and its pinned reference rules once."""
    from edgar_warehouse.rules.source_engine import compare_record_pairs
    from .identifier_types import TYPES

    profile = comparison_profile(rule)
    try:
        return compare_record_pairs({
            "rule": rule, "pairs": pairs,
            "code_tables": REFERENCE_TABLES,
            "normalizers": {kind.normalizer_name: kind.upper for kind in TYPES.values()},
            "census_version": CENSUS_VERSION, "cascade_version": cascade.VERSION,
            "pair_comparison": profile,
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


def _stored(conn, source: str, path: tuple, values: list[str]) -> list[dict]:
    """Probe one indexed JSON key at a time, then check array positions exactly.

    Containment gives a candidate superset for array routes. Comparing the
    declared scalar path removes later entries and non-scalar values before
    any binding proposal is made. Only constant storage expressions reach SQL.
    """
    import json
    from .record_reads import RecordReader

    if not values:
        return []
    if isinstance(conn, RecordReader):
        routes = [name for name, held in (conn.routes or {}).items() if tuple(path) == held]
        return conn.candidates(source,routes,values)
    if path[:1] == ("identifiers",):
        expression, tail = "reading->'identifiers'", path[1:]
    elif path[:2] == ("provenance", "matching"):
        expression, tail = "reading->'provenance'->'matching'", path[2:]
    else:
        raise Conflict("Unsupported candidate path")
    wanted = set(values)
    probes = []
    for value in sorted(wanted):
        probe = value
        for key in reversed(tail):
            if key == 0:
                probe = [probe]
            elif isinstance(key, str):
                probe = {key: probe}
            else:
                raise Conflict("Unsupported candidate array position")
        probes.append(json.dumps(probe))
    return [
        r["reading"]
        for r in rows(
            conn,
            f"""SELECT DISTINCT s.reading FROM unnest(CAST(:probes AS jsonb[])) k(doc)
            CROSS JOIN LATERAL (
                SELECT reading, source_code FROM mdm.stage_record
                WHERE ({expression}) @> k.doc OFFSET 0
            ) s WHERE s.source_code = :source""",
            source=source,
            probes=probes,
        )
        if candidate_value(r["reading"], path) in wanted
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


def _held_identifiers(conn, source: str, namespace: str, entities: set[str], released: set[str] = frozenset()) -> dict:
    """Identifiers already held through bound records, excluding releases."""
    held: dict[str, set] = defaultdict(set)
    if not entities:
        return held
    from .record_reads import RecordReader
    if isinstance(conn, RecordReader):
        for record in conn.current(conn.members(entities)).values():
            if record["source_code"] == source and record["subject"] not in released:
                value = (record.get("identifiers") or {}).get(namespace)
                if value is not None:
                    held[record["entity_id"]].add(value)
        return held
    for r in rows(
        conn,
        """SELECT s.entity_id::text AS entity_id, s.reading->'identifiers'->>:namespace AS value
        FROM unnest(CAST(:entities AS uuid[])) k(id) CROSS JOIN LATERAL (
            SELECT entity_id,reading,source_code,subject FROM mdm.stage_record
            WHERE entity_id=k.id AND entity_id IS NOT NULL OFFSET 0
        ) s WHERE s.source_code = :source
          AND s.reading->'identifiers'->>:namespace IS NOT NULL
          AND NOT s.subject = ANY(:released)""",
        namespace=namespace,
        entities=sorted(entities),
        source=source,
        released=sorted(released),
    ):
        held[r["entity_id"]].add(r["value"])
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
    batch, so a holder record bound in the same batch already names its master.
    """
    rules = active_rules(policy)
    result = nothing()
    if not rules or not assertions:
        return result
    batch = _latest(assertions)
    for _kind, rule in rules:
        source, holder = rule["source"], rule["holder_source"]
        candidates_here = [
            a
            for a in batch.values()
            if a["source_code"] == source and a["kind"] == rule["applies_to_verdict"]
        ]
        holders_here = [a for a in batch.values() if a["source_code"] == holder]
        paths = candidate_paths(rule)
        namespace = comparison_profile(rule)["identifier_namespace"]
        lookup = paths["cascade" if any(t["primitive"] == cascade.TEST for t in rule["when"]) else "census"]
        def value_of(record):
            return candidate_value(record, lookup)
        # Each side of a pair: from this batch, or the latest stored version.
        holder_values = {value_of(a) for a in holders_here} - {None}
        candidates_all = _latest(
            _stored(conn, source, paths["identifier"], sorted(holder_values)) + candidates_here
        )
        # A quarantined record is left out of matching (ticket 13), stored
        # or delivered: a later batch's holder never pairs with it.
        for subject in correction.quarantined(conn, set(candidates_all), decisions):
            del candidates_all[subject]
        values = [candidate_value(a, paths["identifier"]) for a in candidates_all.values()]
        holders_all = _latest(
            _stored(
                conn,
                holder,
                lookup,
                [value for value in values if value],
            )
            + holders_here
        )
        holders_by_value = defaultdict(list)
        for holder_record in holders_all.values():
            if value := value_of(holder_record):
                holders_by_value[value].append(holder_record)
        subjects = set(candidates_all) | set(holders_all)
        bindings = _bindings(conn, subjects, decisions + result["decisions"], released)
        refused = correction.refused(conn, set(candidates_all), decisions)
        candidates = []
        for candidate in candidates_all.values():
            if bindings.get(candidate["subject"]):
                continue
            value = candidate_value(candidate, paths["identifier"])
            for holder_record in holders_by_value.get(value, []):
                entities = bindings.get(holder_record["subject"]) or set()
                if len(entities) == 1:
                    candidates.append((candidate, holder_record, next(iter(entities))))
        outcomes = compare_candidate_records(rule, [(holder_record, candidate) for candidate, holder_record, _ in candidates])
        pairs = []
        for (candidate, holder_record, entity), (passed, flagged) in zip(candidates, outcomes, strict=True):
            if passed:
                pairs.append((candidate, holder_record, entity))
            elif flagged:
                result["reviews"].append({
                    "reason": "cascade_flagged_pair", "namespace": namespace,
                    "subject": candidate["subject"], "assertion_id": candidate["assertion_id"],
                })
        if not pairs:
            continue
        merged = survivors(conn, {entity for _, _, entity in pairs})
        pairs = [(g, s, merged.get(e, e)) for g, s, e in pairs]
        held = _held_identifiers(conn, source, namespace, {e for _, _, e in pairs}, released)
        suspended = in_review(conn, {e for _, _, e in pairs})
        targets: dict[str, set] = defaultdict(set)
        for candidate, _holder_record, entity in pairs:
            targets[candidate["subject"]].add(entity)
        for candidate, holder_record, entity in pairs:
            value = candidate_value(candidate, paths["identifier"])
            if len(targets[candidate["subject"]]) > 1:
                result["reviews"].append(
                    {
                        "reason": "ambiguous_name_match",
                        "namespace": namespace,
                        "subject": candidate["subject"],
                        "assertion_id": candidate["assertion_id"],
                    }
                )
                targets[candidate["subject"]] = set()  # one review, no binding
                continue
            if not targets[candidate["subject"]]:
                continue
            if entity in suspended:
                # As for identifier rules (`binding.in_review`): a master in
                # review for a contradiction gains no record by a rule.
                result["reviews"].append(
                    {
                        "reason": "suspended_identifier",
                        "namespace": namespace,
                        "subject": candidate["subject"],
                        "assertion_id": candidate["assertion_id"],
                    }
                )
                targets[candidate["subject"]] = set()
                continue
            # The configured namespace's held-value veto applies only when
            # the rule explicitly asks for it.
            vetoes = any(t["primitive"] == HELD_LEI_TEST for t in rule["when"])
            if vetoes and held[entity] - {value}:
                continue
            if (candidate["subject"], rule["rule_id"], rule["version"]) in refused:
                continue  # a correction revoked this record's link under this version
            result["decisions"].append(
                decision(
                    "bind",
                    actor=f"rule:{rule['rule_id']}@{rule['version']}",
                    # Evidence describes the subject bound; the matched holder
                    # is named here and already holds the master.
                    reason=f"name_match {namespace} with {holder_record['assertion_id']}",
                    at=as_of,
                    subject=candidate["subject"],
                    entity_id=entity,
                    evidence=[candidate["assertion_id"]],
                    rule_id=rule["rule_id"],
                    rule_version=rule["version"],
                )
            )
            held[entity].add(value)
            targets[candidate["subject"]] = set()
    return result
