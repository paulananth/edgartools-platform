"""Which rules a Mastering Policy may hold, and which verdicts act alone.

A rule in a policy is **declared**: it fires and its result goes to a Steward.
An `automatic_rules` entry switches one of its verdicts **on**: the Merge
Stage acts on it alone. An entry names `(kind, family, rule_id, rule_version,
verdict)` and nothing else: listed is on.

`check_policy` refuses a body, by name and with its reason, unless every rule
is well formed and every entry names a rule version and verdict the policy
holds. An identifier matching rule that is on needs a complete Identifier
Contract for its namespace.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .classification import check_rule
from .primitives import NORMALIZERS, primitive_family
from .store import Conflict, canonical

from .catalog import CATALOG, assert_current

ENTRY = frozenset({"kind", "family", "rule_id", "rule_version", "verdict"})


def _rules(body: dict) -> Iterable[tuple[str, dict]]:
    for kind, block in sorted((body.get("kinds") or {}).items()):
        for rule in block.get("rules") or []:
            yield kind, rule


def check_policy(body: dict) -> None:
    """Refuse a body whose rules or `automatic_rules` entries do not hold."""
    assert_current()
    kinds = body.get("kinds") or {}
    if "relationships" in body:
        from .relationships import types_of

        # The pinned relationship types, checked by the Rust engine; a policy
        # without them registers, and mastering refuses it (ticket 132).
        types_of(body)
    _check_shared_namespaces(kinds)
    seen = set()
    for kind, rule in _rules(body):
        key = (kind, rule.get("rule_id"), rule.get("version"))
        if key in seen:
            raise Conflict(
                f"Rule {rule.get('rule_id')} version {rule.get('version')} "
                f"appears twice in kind {kind}"
            )
        seen.add(key)
        family = rule.get("family")
        if family not in RULE_CHECKS:
            raise Conflict(
                f"Rule {rule.get('rule_id')} has an unknown family: {family}"
            )
        RULE_CHECKS[family](kind, rule, kinds)
    # The cascade's passes together: distinct, one threshold, one
    # eligibility (ticket 21); each pass alone is checked above.
    from .cascade import spec

    spec(body)
    active = set()
    for entry in body.get("automatic_rules") or []:
        if not isinstance(entry, dict):
            raise Conflict(
                f"An automatic_rules entry must be an object naming a rule: {entry!r}"
            )
        key = (
            entry.get("kind"),
            entry.get("family"),
            entry.get("rule_id"),
            entry.get("verdict"),
        )
        if key in active:
            raise Conflict(f"Verdict {key} is listed twice")
        active.add(key)
        _check_entry(kinds, entry)


def _check_shared_namespaces(kinds: dict) -> None:
    """Kinds that each declare a namespace share its values: the Merge Stage
    looks one up across every kind's issuers (platform validation 05a). So
    their contracts must name one authority and one normalizer, or one value
    could read as two. Each kind keeps its own sources, claim and compatibility:
    those are checked per kind when its rule is on."""
    found: dict[str, tuple[str, tuple]] = {}
    for kind, block in sorted(kinds.items()):
        for namespace, contract in sorted((block.get("identifiers") or {}).items()):
            name = contract.get("normalizer")
            terms = (contract.get("authority"), (block.get("normalizers") or {}).get(name, name))
            first_kind, first_terms = found.setdefault(namespace, (kind, terms))
            if first_terms != terms:
                raise Conflict(
                    f"Kinds {first_kind} and {kind} declare Identifier Contract {namespace} "
                    "with a different authority or normalizer"
                )


def _check_entry(kinds: dict, entry: dict) -> None:
    """A listed verdict is on. The entry names a rule version and verdict the
    policy holds; an identifier matching rule also needs its namespace's
    Identifier Contract complete, since a wrong contract is how it goes wrong."""
    if set(entry) != ENTRY:
        raise Conflict(
            f"An automatic_rules entry for {entry.get('rule_id')} names exactly "
            f"{sorted(ENTRY)}: {sorted(set(entry) ^ ENTRY)}"
        )
    block, rule = _resolve(kinds, entry)
    if rule.get("family") == "binding":
        for namespace in binding_namespaces(rule):
            contract = (block.get("identifiers") or {}).get(namespace)
            if not contract:
                raise Conflict(
                    f"Rule {rule['rule_id']} is on, but namespace {namespace} has no "
                    "Identifier Contract"
                )
            _check_contract(namespace, contract)


def _resolve(kinds: dict, entry: dict) -> tuple[dict, dict]:
    kind, rule_id, verdict = (
        entry.get("kind"),
        entry.get("rule_id"),
        entry.get("verdict"),
    )
    if kind not in kinds:
        raise Conflict(f"automatic_rules names kind {kind}, which the policy does not hold")
    block = kinds[kind]
    rules = [r for r in block.get("rules") or [] if r.get("rule_id") == rule_id]
    if not rules:
        raise Conflict(f"automatic_rules names rule {rule_id}, which is absent from {kind}")
    rule = rules[0]
    if rule.get("family") != entry.get("family"):
        raise Conflict(
            f"automatic_rules names {rule_id} as {entry.get('family')}, but it is a "
            f"{rule.get('family')} rule"
        )
    if rule.get("version") != entry.get("rule_version"):
        # An edited rule is a new version; the entry names the one that is on.
        raise Conflict(
            f"automatic_rules names {rule_id} version {entry.get('rule_version')}, but "
            f"the policy holds version {rule.get('version')}"
        )
    if verdict not in (rule.get("emits") or ()):
        raise Conflict(
            f"automatic_rules names verdict {verdict}, which {rule_id} does not emit"
        )
    return block, rule


def activated(body: dict, kind: str, rule: dict, verdict: str) -> bool:
    """Whether this exact rule version's verdict may act without a Steward.

    Trusts `check_policy` to have refused a body whose entry does not hold; it
    only finds the entry. An edited rule (a new version) matches none.
    """
    return any(
        isinstance(entry, dict)
        and entry.get("kind") == kind
        and entry.get("family") == rule.get("family")
        and entry.get("rule_id") == rule.get("rule_id")
        and entry.get("rule_version") == rule.get("version")
        and entry.get("verdict") == verdict
        for entry in body.get("automatic_rules") or []
    )


def rule_version_conflicts(body: dict, registered: Iterable[dict]) -> list[tuple]:
    """Rules this body holds under a version another body holds differently.

    §10 check 9. The per-kind digest cannot catch it: `rules` is deliberately
    outside the authority a field records, so it is guaranteed not to move when
    a rule changes. A new version is free; reusing one for different steps is
    the one case refused.
    """
    held = {}
    for other in registered:
        for kind, rule in _rules(other):
            held.setdefault(
                (kind, rule.get("rule_id"), rule.get("version")), set()
            ).add(canonical(rule))
    return sorted(
        {
            (kind, rule.get("rule_id"), rule.get("version"))
            for kind, rule in _rules(body)
            if held.get((kind, rule.get("rule_id"), rule.get("version")), set())
            - {canonical(rule)}
        }
    )


# The namespaces an identifier rule may name: the keys source evidence stores
# (`cik`, not the spec's `sec.cik`) that an Identifier Contract in the policy
# declares (operator, 2026-10-09: "Read the list from the rules"), so a rule
# can never name a namespace no source issues and silently match nothing, and
# a new identifier needs no code. Each is lower-case words: binding reads it as
# a JSON key inside SQL.
NAMESPACE = re.compile(r"[a-z][a-z0-9_]*")


def declared_namespaces(kinds: dict) -> frozenset[str]:
    """The namespaces the kinds' Identifier Contracts declare."""
    found = frozenset(n for block in kinds.values() for n in (block.get("identifiers") or {}))
    if bad := sorted(n for n in found if not isinstance(n, str) or not NAMESPACE.fullmatch(n)):
        raise Conflict(f"An identifier namespace is lower-case words: {bad}")
    return found


ON_NO_MATCH = frozenset({"mint", "wait"})
# What a record reaching two or more masters does (ticket 138 part A2a):
# `review` (the default) or `merge` them, the oldest surviving.
ON_SEVERAL = frozenset({"review", "merge"})
# What a record whose values reach two masters, and merge none, does (part
# A2b): `review` (the default) or bind by `first`, this rule's master,
# withholding the values the other masters hold.
ON_CONFLICT = frozenset({"review", "first"})
# Company compatibility is kind equality only: Q9 says a name change never
# revokes a binding, and a name-similarity test is fuzzy matching (ticket 08).
COMPATIBILITY = frozenset({"kind_equal@1"})


def binding_namespaces(rule: dict) -> list[str]:
    return sorted(
        {(test.get("args") or {}).get("namespace") for test in rule.get("when") or []
         if primitive_family(test.get("primitive")) == "binding"}
    )


def check_binding_rule(kind: str, rule: dict, kinds: dict) -> None:
    """A binding rule is identifier-only here, and says what a miss does.

    `on_no_match` is data on the rule: `mint` creates a new Company (the SEC
    universe is the base, Q1); `wait` leaves the record in the Stage (operator,
    2026-09-24: an unlinked GLEIF record waits). Fuzzy binding is ticket 08.
    Record tests (the classification family) may narrow the records a rule
    applies to (ticket 97: a GLEIF record an N-PORT holding names as issuer);
    they read the record alone, never master state.
    """
    rule_id = rule.get("rule_id")
    if rule.get("applies_to_verdict") != kind:
        raise Conflict(
            f"Binding rule {rule_id} applies to {rule.get('applies_to_verdict')}, "
            f"but sits in kind {kind}"
        )
    if rule.get("emits") != ["bind"]:
        raise Conflict(f"Binding rule {rule_id} must emit exactly bind")
    if rule.get("on_no_match") not in ON_NO_MATCH:
        raise Conflict(
            f"Binding rule {rule_id} must say what a miss does: on_no_match "
            f"{sorted(ON_NO_MATCH)}"
        )
    tests = rule.get("when") or []
    if not tests:
        raise Conflict(f"Binding rule {rule_id} has no when")
    for test in tests:
        if primitive_family(test.get("primitive")) not in ("binding", "classification"):
            raise Conflict(
                f"Binding rule {rule_id} calls {test.get('primitive')}, which is "
                "neither a binding test nor a record test"
            )
    namespaces = binding_namespaces(rule)
    declared = declared_namespaces(kinds)
    if len(namespaces) != 1:
        raise Conflict(f"Binding rule {rule_id} must name exactly one namespace: {namespaces}")
    if namespaces[0] not in declared:
        raise Conflict(
            f"Binding rule {rule_id} must name exactly one namespace an Identifier "
            f"Contract declares: {namespaces[0]} has no Identifier Contract "
            f"(declared: {sorted(declared)})"
        )
    if not any(t["primitive"] == "identifier_match@1" for t in tests):
        raise Conflict(f"Binding rule {rule_id} does not match an identifier")
    several = rule.get("on_several", "review")
    if several not in ON_SEVERAL:
        raise Conflict(f"Binding rule {rule_id}: on_several is one of {sorted(ON_SEVERAL)}")
    if rule.get("on_conflict", "review") not in ON_CONFLICT:
        raise Conflict(f"Binding rule {rule_id}: on_conflict is one of {sorted(ON_CONFLICT)}")
    contract = ((kinds.get(kind) or {}).get("identifiers") or {}).get(namespaces[0]) or {}
    if several == "merge" and contract.get("consolidates") is not True:
        # Only an identifier stated to consolidate merges masters (ticket 138:
        # a listing FIGI); a filed CUSIP and ISIN never merge two Securities.
        raise Conflict(
            f"Binding rule {rule_id} merges only by an identifier whose Identifier Contract "
            f"states consolidates: true: {namespaces[0]}"
        )
    if several == "merge" and rule.get("source") not in _issuing_sources(kind, namespaces[0], kinds):
        # A value a source files without issuing it is lookup only (Design 5,
        # operator 2026-10-26: "Lookup only"): it never merges two masters.
        raise Conflict(
            f"Binding rule {rule_id} merges only from its issuing source: "
            f"{rule.get('source')} does not issue {namespaces[0]}"
        )
    if rule["on_no_match"] == "mint":
        _check_minting_source(kind, rule, namespaces[0], kinds)


def _issuing_sources(kind: str, namespace: str, kinds: dict) -> list:
    """The sources the kind's Identifier Contract names as issuing the namespace."""
    return ((((kinds.get(kind) or {}).get("identifiers") or {}).get(namespace)) or {}).get("sources") or []


def _check_minting_source(kind: str, rule: dict, namespace: str, kinds: dict) -> None:
    """Only the identifier's issuer creates a Company from it.

    An unlinked GLEIF record waits in the Stage (operator, 2026-09-24); a rule
    that may create a Company must therefore be scoped to a source that
    issues its namespace, never left open to every source.
    """
    rule_id = rule.get("rule_id")
    source = rule.get("source")
    if not source:
        raise Conflict(f"Binding rule {rule_id} creates Companies but names no source")
    # Fail closed: without its own kind's contract naming the issuer, a rule
    # that creates Companies is refused even while it is inactive.
    issuers = _issuing_sources(kind, namespace, kinds)
    if not issuers:
        raise Conflict(
            f"Binding rule {rule_id} creates Companies, but kind {kind} has no "
            f"Identifier Contract naming an issuing source for {namespace}"
        )
    if source not in issuers:
        raise Conflict(
            f"Binding rule {rule_id} creates Companies from {source}, which "
            f"does not issue {namespace}: {issuers}"
        )


def _check_classification_rule(kind: str, rule: dict, kinds: dict) -> None:
    check_rule(rule)


def _check_contract(namespace: str, contract: dict) -> None:
    """§7.2: everything the claim rests on, declared and verifiable."""
    where = f"Identifier Contract {namespace}"
    if not contract.get("authority"):
        raise Conflict(f"{where} names no issuing authority")
    # The datasets through which a Company can hold this identifier: its
    # issuer's own records, never another source that happens to carry it.
    sources = contract.get("sources")
    if (
        not isinstance(sources, list)
        or not sources
        or not all(isinstance(s, str) and s for s in sources)
    ):
        raise Conflict(f"{where} names no issuing source datasets")
    if contract.get("normalizer") not in NORMALIZERS:
        raise Conflict(f"{where} names an unknown normalizer")
    forward = (contract.get("claim") or {}).get("forward")
    if type(forward) is not int or forward < 1:
        raise Conflict(f"{where} states no forward claim")
    # How many values one master may hold: a count, or null for any number
    # (a Security's listing FIGIs, ticket 138).
    reverse = (contract.get("claim") or {}).get("reverse")
    if reverse is not None and (type(reverse) is not int or reverse < 1):
        raise Conflict(f"{where} states a reverse claim that is not a count")
    if "consolidates" in contract and type(contract["consolidates"]) is not bool:
        raise Conflict(f"{where} states consolidates as true or false")
    compatibility = contract.get("compatibility") or {}
    if (
        not compatibility.get("field")
        # A binding test (§5 has no family of its own for it); kind equality
        # is the only one this build holds.
        or compatibility.get("predicate") not in COMPATIBILITY
    ):
        raise Conflict(f"{where} states no compatibility check")


# The tests a name-binding rule must call: never the name alone (§10 check 5,
# as for `name_similarity`), always the pinned name count and one place test.


def check_name_binding_rule(kind: str, rule: dict, kinds: dict) -> None:
    """A measured SEC-to-GLEIF matching rule (ticket 08).

    It only joins: a waiting GLEIF record to the Company its SEC record holds.
    It never creates a Company, so its `on_no_match` is `wait`.
    """
    rule_id = rule.get("rule_id")
    profile = rule.get("pair_comparison", CATALOG["legacy_pair_comparison"])
    if not isinstance(profile, str) or profile not in CATALOG["pair_comparisons"]:
        raise Conflict(f"Name binding rule {rule_id} names an unknown pair comparison profile")
    if CATALOG["pair_comparisons"][profile]["eligibility_kind"] != kind:
        raise Conflict(f"Name binding rule {rule_id} comparison profile applies to another kind")
    if rule.get("applies_to_verdict") != kind:
        raise Conflict(
            f"Binding rule {rule_id} applies to {rule.get('applies_to_verdict')}, "
            f"but sits in kind {kind}"
        )
    if rule.get("emits") != ["bind"]:
        raise Conflict(f"Binding rule {rule_id} must emit exactly bind")
    if rule.get("on_no_match") != "wait":
        raise Conflict(f"Name binding rule {rule_id} never creates a Company: wait")
    if not rule.get("source") or not rule.get("holder_source"):
        raise Conflict(
            f"Name binding rule {rule_id} must name the source it joins and the "
            "source whose record holds the Company"
        )
    tests = [t.get("primitive") for t in rule.get("when") or []]
    for test in tests:
        if primitive_family(test) != "name_binding":
            raise Conflict(
                f"Name binding rule {rule_id} calls {test}, which is not a name "
                "binding test"
            )
    if "cascade_pass@1" in tests:
        _check_cascade_pass(rule_id, rule, tests)
        return
    raise Conflict(f"Name binding rule {rule_id} must be one waterfall pass (`cascade_pass@1`)")


def _check_cascade_pass(rule_id: str, rule: dict, tests: list) -> None:
    """One pass of the cascade (ticket 21). It rests on the name count's answer,
    one to one over both whole sources, not on a Stage's scope; the pass
    states which address parts it compares, down to the name alone, as the
    operator ruled (2026-09-27)."""
    from .cascade import CONFLICT, NOT_UNIQUE, PARTS

    if tests.count("cascade_pass@1") != 1:
        raise Conflict(f"Cascade rule {rule_id} is exactly one pass and no other name rule")
    if not {"gleif_entity_eligible@1", "holds_no_other_lei@1"} <= set(tests):
        raise Conflict(f"Cascade rule {rule_id} must test eligibility and the one-LEI veto")
    args = next(t.get("args") or {} for t in rule["when"] if t.get("primitive") == "cascade_pass@1")
    compare = args.get("compare")
    if (
        not isinstance(args.get("pass"), str)
        or not (compare is None or (isinstance(compare, list) and all(
            part != [] and all(one in PARTS for one in (part if isinstance(part, list) else [part]))
            for part in compare)))
        or type(args.get("over_shared")) is not int
        or args["over_shared"] < 1
        or args.get("sec_normalizer") not in NORMALIZERS
        or args.get("gleif_normalizer") not in NORMALIZERS
        or not set(args.get("refused_flags") or []) <= {CONFLICT, NOT_UNIQUE}
    ):
        raise Conflict(f"Cascade rule {rule_id} has invalid pass arguments")


EXACT_NAME_KEYS = frozenset({"name_id@1", "name_place_id@1", "issuer_symbol_id@1"})


def check_exact_name_rule(kind: str, rule: dict, kinds: dict) -> None:
    """An exact-name matching rule (ticket 01): a source's record joins the one master
    that records of the holder sources hold under the same name id. It never guesses
    between masters (`review`). With none it waits (`wait`) or, where the operator has
    ruled that the name makes the golden record, creates it (`mint`)."""
    rule_id = rule.get("rule_id")
    if rule.get("applies_to_verdict") != kind:
        raise Conflict(f"Exact-name rule {rule_id} applies to {rule.get('applies_to_verdict')}, but sits in kind {kind}")
    if rule.get("emits") != ["bind"]:
        raise Conflict(f"Exact-name rule {rule_id} must emit exactly bind")
    if rule.get("on_no_match") not in ("wait", "mint") or rule.get("on_several") != "review":
        raise Conflict(f"Exact-name rule {rule_id} needs on_no_match wait or mint, and on_several review")
    holders = rule.get("holder_sources")
    # A rule that creates may have no other source holding its key: its own records hold it.
    if (not rule.get("source") or not isinstance(holders, list) or (not holders and rule.get("on_no_match") != "mint")
            or not all(isinstance(h, str) and h for h in holders) or rule["source"] in holders):
        raise Conflict(f"Exact-name rule {rule_id} must name its source and the other sources whose records hold the masters")
    reference = rule.get("cross_reference", "name_id")
    if not isinstance(reference, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,15}", reference):
        raise Conflict(f"Exact-name rule {rule_id} names its cross reference in at most 16 lowercase letters, digits or underscores")
    if rule.get("key") not in EXACT_NAME_KEYS or rule.get("when"):
        raise Conflict(f"Exact-name rule {rule_id} rests on one of the ids {sorted(EXACT_NAME_KEYS)} and no other test")


RULE_CHECKS = {
    "classification": _check_classification_rule,
    "binding": check_binding_rule,
    "name_binding": check_name_binding_rule,
    "exact_name_binding": check_exact_name_rule,
}
