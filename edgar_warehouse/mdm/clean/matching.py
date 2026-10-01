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

from . import cascade, correction
from .activation import activated
from .binding import bound, in_review, nothing, survivors
from .evidence import decision
from .name_census import VERSION as CENSUS_VERSION
from .names import (
    edgar_jurisdiction,
    jurisdictions_agree,
    jurisdictions_conflict,
    postal_codes_agree,
)
from .primitives import NORMALIZERS
from .quality import withheld
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
    """A rule's declared path: `matching.<name>` or a field name. Data, never code.

    A value the feed's quality rule withheld is not there to match on
    (ticket 22).
    """
    if withheld(record, path if path.startswith("matching.") else f"fields.{path}"):
        return None
    if path.startswith("matching."):
        return _matching(record).get(path.removeprefix("matching."))
    return _value(record, path)


def _normalizer(name: str):
    if name not in NORMALIZERS:
        raise Conflict(f"Name binding names an unknown normalizer: {name}")
    return NORMALIZERS[name]


# The one code table `sec_codes` may name. Its content is
# `rules/reference/sec-place-codes.yaml`, which the policy body carries, so
# the policy's digest pins it: an edit to the table is a new policy.
SEC_CODES = {"edgar-iso-v1": edgar_jurisdiction}


def _codes(args: dict):
    if args.get("sec_codes") not in SEC_CODES:
        raise Conflict(
            f"Name binding names an unknown code table: {args.get('sec_codes')}"
        )
    return SEC_CODES[args["sec_codes"]]


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


def _census_match(sec: dict, gleif: dict, args: dict) -> bool:
    entry = _matching(sec).get("name_census") or {}
    lei = (gleif.get("identifiers") or {}).get("lei")
    key = _normalizer(args["sec_normalizer"])(_value(sec, "name"))
    return (
        entry.get("version") == CENSUS_VERSION
        and entry.get("cik_count") == 1
        and entry.get("ciks") == [sec["record_key"]]
        and entry.get("lei_count") == 1
        and entry.get("other_name_holders") == 0
        and entry.get("leis") == [[lei, _value(gleif, "gleif_last_update") or ""]]
        and bool(key)
        and entry.get("key")
        == key
        == _normalizer(args["gleif_normalizer"])(_value(gleif, "name"))
    )


def _cascade_pass(sec: dict, gleif: dict, args: dict) -> bool:
    """The census's cascade bound this pair in this pass (ticket 21), and the
    Stage rows still say so: the same LEI and last update, the same name key
    (the GLEIF legal name, unless the census matched one of its other names,
    which the Stage record does not hold), no flag the rule refuses, and the
    pass's address parts agree on the addresses the quality rule left fit.

    The over-shared cut is the census's to make: it needs every entity. It
    leaves a place only its country, so such a pair binds only in a pass that
    compares no more than the country, where the cut changes nothing here."""
    answer = (_matching(sec).get("name_census") or {}).get("cascade") or {}
    key = _normalizer(args["sec_normalizer"])(_value(sec, "name"))
    gleif_key = _normalizer(args["gleif_normalizer"])(_value(gleif, "name"))
    return (
        answer.get("version") == cascade.VERSION
        and answer.get("pass") == args["pass"]
        and answer.get("lei") == (gleif.get("identifiers") or {}).get("lei")
        and answer.get("last_update") == (_value(gleif, "gleif_last_update") or "")
        and bool(key)
        and answer.get("key") == key
        and (gleif_key == key or answer.get("via") == "other name")
        and not set(answer.get("flags") or []) & set(args.get("refused_flags") or [])
        and cascade.agrees(
            cascade.filer_of(sec).place,
            cascade.fit_place(gleif, _matching(gleif)),
            args["compare"],
        )
    )


def _eligible(_sec: dict, gleif: dict, args: dict) -> bool:
    # The GLEIF contract admits only GENERAL as a Company (`gleif_source.py`),
    # so that is the one category this test can honour; any other fails closed.
    if args.get("categories") != ["GENERAL"]:
        raise Conflict("Name binding can require only the GENERAL category")
    return (
        gleif.get("kind") == "company"
        and _value(gleif, "gleif_entity_status") in args["entity_statuses"]
        and _value(gleif, "gleif_registration_status")
        not in args["refused_registration_statuses"]
    )


def _jurisdiction_agrees(sec: dict, gleif: dict, args: dict) -> bool:
    return jurisdictions_agree(
        _codes(args)(_read(sec, args["sec_field"])), _read(gleif, args["gleif_field"])
    )


def _no_conflict(sec: dict, gleif: dict, args: dict) -> bool:
    return not jurisdictions_conflict(
        _codes(args)(_read(sec, args["sec_field"])),
        _read(gleif, args["gleif_field"]),
        sec_business_country=_read(sec, args["sec_business_country"]),
    )


def _postal_agrees(sec: dict, gleif: dict, args: dict) -> bool:
    return postal_codes_agree(
        _read(sec, args["sec_code"]),
        _read(sec, args["sec_country"]),
        _read(gleif, args["gleif_code"]),
        _read(gleif, args["gleif_country"]),
    )


# Every name-binding test the registry holds, implemented here: the record-pair
# tests, and the one that needs master state (`HELD_LEI_TEST`), checked with
# the Company in hand. A unit test holds this equal to the registry.
HELD_LEI_TEST = "holds_no_other_lei@1"
PAIR_TESTS = {
    "name_census_match@1": _census_match,
    "gleif_entity_eligible@1": _eligible,
    "jurisdiction_agrees@1": _jurisdiction_agrees,
    "jurisdictions_do_not_conflict@1": _no_conflict,
    "postal_agrees@1": _postal_agrees,
    cascade.TEST: _cascade_pass,
}


def _passes(rule: dict, sec: dict, gleif: dict) -> bool:
    for test in rule["when"]:
        name = test["primitive"]
        if name == HELD_LEI_TEST:
            continue
        if name not in PAIR_TESTS:
            raise Conflict(f"Name binding test {name} has no implementation")
        if not PAIR_TESTS[name](sec, gleif, test.get("args") or {}):
            return False
    return True


def _refused_by_flag(rule: dict, sec: dict, gleif: dict) -> bool:
    """A cascade pair that passes every test but carries a flag its rule
    refuses: it goes to a Steward, not to a bind (operator, 2026-09-28: if a
    stratum fails its proof, "those pairs go to a Steward for review")."""
    lenient = []
    for test in rule["when"]:
        args = test.get("args") or {}
        if test["primitive"] == cascade.TEST and args.get("refused_flags"):
            test = {**test, "args": {**args, "refused_flags": []}}
        lenient.append(test)
    return lenient != rule["when"] and _passes({**rule, "when": lenient}, sec, gleif)


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
        pairs = []
        for gleif in gleif_all.values():
            if bindings.get(gleif["subject"]):
                continue  # already joined; a name match never re-binds
            lei = (gleif.get("identifiers") or {}).get("lei")
            for sec in sec_by_lei.get(lei, []):
                companies = bindings.get(sec["subject"]) or set()
                if len(companies) != 1:
                    continue
                if _passes(rule, sec, gleif):
                    pairs.append((gleif, sec, next(iter(companies))))
                elif _refused_by_flag(rule, sec, gleif):
                    result["reviews"].append(
                        {
                            "reason": "cascade_flagged_pair",
                            "namespace": "lei",
                            "subject": gleif["subject"],
                            "assertion_id": gleif["assertion_id"],
                        }
                    )
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
