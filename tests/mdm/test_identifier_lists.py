"""A record may carry a list of one identifier kind (ticket 138, part A1).

An OpenFIGI answer holds a FIGI for each of its listings, so its record
carries every listing FIGI. Matching looks up each value; the lookup index
holds each value; a Security may hold any number of values of a kind whose
Identifier Contract claims no reverse limit. Values are invented look-alikes
with valid check digits.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.identifier_types import TYPES
from edgar_warehouse.mdm.clean.matching import candidate_routes
from edgar_warehouse.rules.source_engine import (
    link_matching_records,
    plan_record_matches,
    prepare_master_records,
    prepare_record_lookups,
)

AS_OF = "2026-10-25T12:00:00+00:00"
SOURCE = "fixture.listings"
HELD = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000b"
NORMALIZERS = {kind.normalizer_name: kind.upper for kind in TYPES.values()}


def figi(stem: str) -> str:
    """An invented FIGI: `BBG` and eight characters, with its check digit."""
    for digit in "0123456789":
        if TYPES["figi"].refusal(f"BBG{stem}{digit}")[1] is None:
            return f"BBG{stem}{digit}"
    raise AssertionError(stem)


F1, F2, F3, F4 = (figi(f"00TSTX{n:02d}") for n in range(1, 5))
RULE = {
    "rule_id": "fixture-security-figi",
    "version": "2026-10-25.1",
    "family": "binding",
    "applies_to_verdict": "security",
    "emits": ["bind"],
    "on_no_match": "mint",
    "source": SOURCE,
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "figi"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "figi"}},
    ],
}
CONTRACT = {
    "normalizer": "normalize_identifier@figi-v2",
    "sources": [SOURCE],
    "claim": {"forward": 1, "reverse": None},
}
# Any source's record may join by a FIGI; only the issuing source creates one.
JOIN = {**{k: v for k, v in RULE.items() if k != "source"},
        "rule_id": "fixture-security-figi-join", "on_no_match": "wait"}
POLICY = {
    "automatic_rules": [{
        "kind": "security", "family": "binding", "rule_id": rule["rule_id"],
        "rule_version": rule["version"], "verdict": "bind",
    } for rule in (RULE, JOIN)],
    "kinds": {"security": {"rules": [RULE, JOIN], "identifiers": {"figi": CONTRACT}}},
}


def record(key: str, *figis: str, source: str = SOURCE) -> dict:
    return assertion(
        source_code=source, record_key=key, publication_key="p1", revision=1,
        effective_at=None, kind="security", fields={}, identifiers={"figi": list(figis)},
    )


def match(records, held=None, decisions=(), bound=None, refused=()):
    """Plan, then link: `held` maps a FIGI to the Security holding it;
    `bound` a stored record's subject to its Security."""
    bound = bound or {}
    plan = plan_record_matches({
        "policy": POLICY, "assertions": list(records), "decisions": list(decisions),
        "identities": [], "bound": sorted(bound), "bound_entities": bound,
        "released": [], "normalizers": NORMALIZERS,
    })
    found = [
        {"namespace": "figi", "value": value, "records": {entity: "security"}}
        for value, entity in (held or {}).items()
        if value in plan["wanted"].get("figi", ())
    ]
    return plan, link_matching_records({
        "plan": plan, "found": found, "suspended": [], "newest": {},
        "new_ids": [str(uuid4()) for _ in plan["applicable"]], "refused": list(refused), "as_of": AS_OF,
    })


def given(result, name):
    return {(item["entity_id"], item["raw"]) for item in result[name]}


def test_a_list_mints_one_security_that_holds_every_value():
    plan, result = match([record("one", F1, F2, F3)])
    assert plan["wanted"] == {"figi": sorted([F1, F2, F3])}
    (identity,) = result["identities"]
    assert given(result, "mints") == {(identity["entity_id"], f) for f in (F1, F2, F3)}
    assert [d["entity_id"] for d in result["decisions"]] == [identity["entity_id"]]
    assert result["reviews"] == []


def test_a_list_joins_the_security_that_holds_any_value_and_adds_the_rest():
    _, result = match([record("one", F1, F2, F3)], held={F2: HELD})
    assert result["identities"] == []
    assert [d["entity_id"] for d in result["decisions"]] == [HELD]
    assert given(result, "joins") == {(HELD, F2)}
    # The values no Security held are new holdings: a concurrent bundle
    # that gives one to another Security makes this proposal stale.
    assert given(result, "mints") == {(HELD, F1), (HELD, F3)}


def test_two_records_sharing_any_value_in_one_batch_make_one_security():
    _, result = match([record("one", F1, F2), record("two", F2, F3)])
    (identity,) = result["identities"]
    assert {d["entity_id"] for d in result["decisions"]} == {identity["entity_id"]}
    assert given(result, "mints") == {(identity["entity_id"], f) for f in (F1, F2, F3)}


def test_records_sharing_no_value_make_two_securities():
    _, result = match([record("one", F1), record("two", F2)])
    assert len(result["identities"]) == 2


def test_a_record_from_a_source_that_does_not_issue_the_identifier_adds_none():
    # It joins by the value a Security holds, but its other values are not
    # the Security's: only the issuing source's record establishes a value.
    other = "fixture.filings"
    _, result = match([record("filed", F1, F2, source=other), record("later", F2, source=other)],
                      held={F1: HELD})
    assert [d["entity_id"] for d in result["decisions"]] == [HELD]
    assert result["mints"] == [] and result["identities"] == []


def test_a_redelivered_record_gives_its_new_value_to_its_security():
    # A stored answer re-captured with one more listing: a later record in
    # the batch finds the Security by it, and the save re-checks it.
    again = record("one", F1, F3)
    _, result = match([again, record("two", F3)], held={F1: HELD}, bound={again["subject"]: HELD})
    assert [d["entity_id"] for d in result["decisions"]] == [HELD]
    assert result["identities"] == []
    assert given(result, "mints") == {(HELD, F3)}


def test_a_refused_bind_gives_its_values_to_no_security():
    first = record("one", F1, F2)
    _, result = match([first, record("two", F2)], held={F1: HELD},
                      refused=[[first["subject"], rule["rule_id"], rule["version"]] for rule in (RULE, JOIN)])
    assert {d["subject"] for d in result["decisions"]} == {record("two", F2)["subject"]}
    assert all(raw != F2 or entity != HELD for entity, raw in given(result, "mints"))


def test_values_on_two_securities_wait_for_review_until_merge_is_built():
    # Part A2 makes this `on_several: merge`, the oldest surviving.
    _, result = match([record("one", F1, F2)], held={F1: HELD, F2: OTHER})
    assert result["decisions"] == [] and result["identities"] == []
    assert [r["reason"] for r in result["reviews"]] == ["conflicting_identifiers"]


def test_a_caller_bound_list_holds_each_value():
    caller = record("one", F1, F2)
    decision = {"operation": "bind", "subject": caller["subject"], "entity_id": HELD}
    plan, result = match([caller, record("two", F2, F4)], decisions=[decision])
    assert {(h["value"], *h["records"]) for h in plan["caller_holders"]} == {(F1, HELD), (F2, HELD)}
    assert [d["entity_id"] for d in result["decisions"]] == [HELD]


def lookups(item, bindings=None):
    return prepare_record_lookups({
        "readings": [item], "previous": {}, "subjects": [item["subject"]],
        "bindings": bindings or {}, "quarantined": {}, "batch_id": "b",
        "occurrences": {}, "normalizers": NORMALIZERS,
        "candidate_routes": candidate_routes(), "policy": POLICY,
    })


def test_the_lookup_index_holds_each_value_of_a_list():
    item = record("one", F2.lower(), F1)
    current, changes = lookups(item, {item["subject"]: HELD})
    assert current[item["subject"]]["normalized_identifiers"] == {"figi": [F2, F1]}
    groups = [json.loads(c["type"].split("/", 2)[2]) for c in changes
              if c["type"].startswith("lookup/identifier_records/")]
    assert sorted(g[1] for g in groups) == sorted([F1, F2])


def test_a_single_value_is_still_indexed_as_one_value():
    item = assertion(source_code=SOURCE, record_key="one", publication_key="p1", revision=1,
                     effective_at=None, kind="security", fields={}, identifiers={"figi": F1})
    current, _ = lookups(item)
    assert current[item["subject"]]["normalized_identifiers"] == {"figi": F1}


@pytest.mark.parametrize("bad", [[F1, None], [F1, 7], []])
def test_a_list_holds_strings_only_and_is_not_empty(bad):
    with pytest.raises(ValueError, match="identifier"):
        match([record("one", *bad)])


def masters(reverse, kind="security"):
    claims = {
        subject: {"kind": kind, "identifiers": {"figi": values}}
        for subject, values in (("s1", [F1, F2]), ("s2", [F3]))
    }
    return prepare_master_records({
        "identities": {HELD: {"entity_id": HELD, "kind": kind}}, "canonical": {HELD: HELD},
        "bindings": {"s1": HELD, "s2": HELD}, "quarantined": {}, "claims": claims,
        "policy": {"kinds": {kind: {"version": "t", "defaults": {"sources": []},
                                    "identifiers": {"figi": {**CONTRACT, "claim": {"forward": 1, "reverse": reverse}}}}}},
        "overrides": [], "decisions": [], "as_of": AS_OF, "policy_digest": "t", "profile_kinds": {},
    })


def test_a_master_holds_any_number_of_values_when_the_contract_sets_no_reverse_limit():
    projected, reviews, _ = masters(None)
    assert projected[HELD]["status"] == "accepted"
    assert projected[HELD]["identifiers"] == {"figi": sorted([F1, F2, F3])}
    assert reviews == []


def test_a_master_over_its_reverse_limit_goes_to_review():
    projected, reviews, _ = masters(1)
    assert projected[HELD]["status"] == "review"
    assert [r["reason"] for r in reviews] == ["authoritative_identifier_conflict"]


def test_a_contract_maps_a_list_of_one_identifier_kind_checked_and_once_each():
    from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
    from tests.support.reading import reading

    contract = {"schema_version": "1", "adapter": {
        "version": "fixture-v1", "kind": "security", "record_key": ["id"],
        "identifiers": {"figi": "figis"}, "identifier_formats": {"figi": "figi"},
        "reading": reading({"name": "name"})}}
    publication = {"artifact_sha256": "0" * 64, "member": "m", "publication_key": "p1", "revision": 1}

    def mapped(figis):
        return normalize({"id": "1", "name": "Invented", "figis": figis}, source_code=SOURCE,
                         publication=publication, contract=contract)

    body = mapped([F2.lower(), F1, None, " ", F2])
    assert body["identifiers"] == {"figi": [F2, F1]}
    assert "figi" not in mapped([None, ""])["identifiers"]
    # A listed value failing its check is set aside with its reason, counted; the record stays.
    bad = F1[:-1] + str((int(F1[-1]) + 1) % 10)
    kept = mapped([F1, bad])
    assert kept["identifiers"] == {"figi": [F1]}
    assert kept["provenance"]["identifiers_set_aside"] == [
        {"namespace": "figi", "value": bad, "reason": "invalid_figi_checksum"}]
    assert "identifiers_set_aside" not in body["provenance"]
    with pytest.raises(UnsupportedRecord, match="figi"):
        mapped(F1[:-1] + str((int(F1[-1]) + 1) % 10))


def test_a_record_finding_a_held_security_binds_before_any_record_creates_one():
    # Sorted by subject, "a-isin" would come first and create a Security, and
    # "b-cusip" would then reach two. Looking up first, the CUSIP record binds
    # to the held Security and the ISIN record finds it by the FIGI they share.
    first = assertion(source_code=SOURCE, record_key="a-isin", publication_key="p1", revision=1,
                      effective_at=None, kind="security", fields={}, identifiers={"figi": [F2, F3]})
    second = record("b-cusip", F1, F2)
    ordered = sorted([first, second], key=lambda r: r["subject"])
    _, result = match(ordered, held={F1: HELD})
    assert result["identities"] == [] and result["reviews"] == []
    assert {d["entity_id"] for d in result["decisions"]} == {HELD}
