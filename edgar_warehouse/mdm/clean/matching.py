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

from .activation import activated
from .binding import _survivors, nothing
from .evidence import decision
from .name_census import VERSION as CENSUS_VERSION
from .names import (
    edgar_jurisdiction,
    jurisdictions_agree,
    jurisdictions_conflict,
    legal_form_key,
    postal_codes_agree,
    sec_legal_form_key,
)
from .store import Conflict, rows

FAMILY = "name_binding"


def active_rules(policy: dict) -> list[tuple[str, dict]]:
    return [
        (kind, rule)
        for kind, block in sorted((policy.get("kinds") or {}).items())
        for rule in block.get("rules") or []
        if rule.get("family") == FAMILY and activated(policy, kind, rule, "bind")
    ]


def _value(record: dict, field: str):
    item = (record.get("fields") or {}).get(field) or {}
    return item.get("value") if item.get("op") == "value" else None


def _matching(record: dict) -> dict:
    return (record.get("provenance") or {}).get("matching") or {}


def _census_match(sec: dict, gleif: dict, _args: dict) -> bool:
    entry = _matching(sec).get("name_census") or {}
    lei = (gleif.get("identifiers") or {}).get("lei")
    key = sec_legal_form_key(_value(sec, "name"))
    return (
        entry.get("version") == CENSUS_VERSION
        and entry.get("cik_count") == 1
        and entry.get("ciks") == [sec["record_key"]]
        and entry.get("lei_count") == 1
        and entry.get("other_name_holders") == 0
        and entry.get("leis") == [[lei, _value(gleif, "gleif_last_update") or ""]]
        and bool(key)
        and entry.get("key") == key == legal_form_key(_value(gleif, "name"))
    )


def _eligible(_sec: dict, gleif: dict, args: dict) -> bool:
    # A GLEIF record the Stage holds as a Company is GENERAL already: the
    # contract admits no other category as a Company (`gleif_source.py`).
    return (
        gleif.get("kind") == "company"
        and _value(gleif, "gleif_entity_status") in args["entity_statuses"]
        and _value(gleif, "gleif_registration_status")
        not in args["refused_registration_statuses"]
    )


def _sec_place(sec: dict) -> str | None:
    return edgar_jurisdiction(_value(sec, "state_of_incorporation"))


def _jurisdiction_agrees(sec: dict, gleif: dict, _args: dict) -> bool:
    return jurisdictions_agree(_sec_place(sec), _value(gleif, "jurisdiction"))


def _no_conflict(sec: dict, gleif: dict, _args: dict) -> bool:
    return not jurisdictions_conflict(
        _sec_place(sec),
        _value(gleif, "jurisdiction"),
        sec_business_country=_matching(sec).get("business_country"),
    )


def _postal_agrees(sec: dict, gleif: dict, _args: dict) -> bool:
    s, g = _matching(sec), _matching(gleif)
    return postal_codes_agree(
        s.get("business_postal_code"),
        s.get("business_country"),
        g.get("headquarters_postal_code"),
        g.get("headquarters_country"),
    )


# The record-pair tests; `holds_no_other_lei@1` needs master state and is
# checked with the Company in hand.
PAIR_TESTS = {
    "name_census_match@1": _census_match,
    "gleif_entity_eligible@1": _eligible,
    "jurisdiction_agrees@1": _jurisdiction_agrees,
    "jurisdictions_do_not_conflict@1": _no_conflict,
    "postal_agrees@1": _postal_agrees,
}


def _passes(rule: dict, sec: dict, gleif: dict) -> bool:
    for test in rule["when"]:
        name = test["primitive"]
        if name == "holds_no_other_lei@1":
            continue
        if name not in PAIR_TESTS:
            raise Conflict(f"Name binding test {name} has no implementation")
        if not PAIR_TESTS[name](sec, gleif, test.get("args") or {}):
            return False
    return True


def _latest(found: list[dict]) -> dict[str, dict]:
    by_subject: dict[str, dict] = {}
    for body in sorted(
        found, key=lambda a: (a["revision"], a.get("mapping_version", 1))
    ):
        by_subject[body["subject"]] = body
    return by_subject


def _stored(conn, source: str, where: str, values: list[str]) -> list[dict]:
    """The latest stored version of each record of `source` matching `where`."""
    if not values:
        return []
    return [
        r["body"]
        for r in rows(
            conn,
            f"""SELECT DISTINCT ON (source_code, record_key) body
            FROM mdm_v2.assertion
            WHERE source_code = :source AND {where} = ANY(:values)
            ORDER BY source_code, record_key, revision DESC, mapping_version DESC""",
            source=source,
            values=sorted(set(values)),
        )
    ]


def _bindings(conn, subjects: set[str], decisions: list[dict]) -> dict[str, set]:
    bound: dict[str, set] = defaultdict(set)
    for d in decisions:
        if d["operation"] == "bind" and d["subject"] in subjects:
            bound[d["subject"]].add(d["entity_id"])
    for r in rows(
        conn,
        """SELECT body->>'subject' AS subject, body->>'entity_id' AS entity_id
        FROM mdm_v2.decision
        WHERE operation='bind' AND body->>'subject' = ANY(:subjects)""",
        subjects=sorted(subjects),
    ):
        bound[r["subject"]].add(r["entity_id"])
    return bound


def _held_leis(conn, source: str, entities: set[str]) -> dict:
    """The LEIs each Company already holds through its bound GLEIF records."""
    held: dict[str, set] = defaultdict(set)
    for r in rows(
        conn,
        """SELECT DISTINCT d.body->>'entity_id' AS entity_id,
               a.body->'identifiers'->>'lei' AS lei
        FROM mdm_v2.decision d
        JOIN mdm_v2.assertion a ON a.body->>'subject' = d.body->>'subject'
        WHERE d.operation='bind' AND d.body->>'entity_id' = ANY(:entities)
          AND a.source_code = :source
          AND a.body->'identifiers'->>'lei' IS NOT NULL""",
        entities=sorted(entities),
        source=source,
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
        # Each side of a pair: from this batch, or the latest stored version.
        lei_of_sec = {
            (_matching(a).get("name_census") or {}).get("leis", [[None]])[0][0]
            for a in sec_here
        } - {None}
        gleif_all = _latest(
            _stored(conn, source, "body->'identifiers'->>'lei'", sorted(lei_of_sec))
            + gleif_here
        )
        leis = [(a.get("identifiers") or {}).get("lei") for a in gleif_all.values()]
        sec_all = _latest(
            _stored(
                conn,
                holder,
                "body->'provenance'->'matching'->'name_census'->'leis'->0->>0",
                [lei for lei in leis if lei],
            )
            + sec_here
        )
        sec_by_lei = defaultdict(list)
        for sec in sec_all.values():
            entry = _matching(sec).get("name_census") or {}
            if entry.get("leis"):
                sec_by_lei[entry["leis"][0][0]].append(sec)
        subjects = set(gleif_all) | set(sec_all)
        bound = _bindings(conn, subjects, decisions + result["decisions"])
        pairs = []
        for gleif in gleif_all.values():
            if bound.get(gleif["subject"]):
                continue  # already joined; a name match never re-binds
            lei = (gleif.get("identifiers") or {}).get("lei")
            for sec in sec_by_lei.get(lei, []):
                companies = bound.get(sec["subject"]) or set()
                if len(companies) == 1 and _passes(rule, sec, gleif):
                    pairs.append((gleif, sec, next(iter(companies))))
        if not pairs:
            continue
        survivors = _survivors(conn, {entity for _, _, entity in pairs})
        pairs = [(g, s, survivors.get(e, e)) for g, s, e in pairs]
        held = _held_leis(conn, source, {e for _, _, e in pairs})
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
            # A legal entity has one LEI: a Company holding another defers.
            if held[entity] - {lei}:
                continue
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
