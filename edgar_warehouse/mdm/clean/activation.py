"""Which rules a Mastering Policy may hold, and which verdicts may act alone.

A rule in a policy is **declared**: it fires and its result goes to a Steward.
An `automatic_rules` entry makes one of its verdicts **active**: the Merge
Stage acts on it alone. Activation is per `(rule_id, rule_version, verdict)`,
never per rule (`policy-language.md` §9).

This replaces the blanket refusal of every `automatic_rules` body. A body is
refused, by name and with its reason, unless every rule is well formed (§10)
and every activation carries a proof whose arithmetic holds against its kind's
accepted bar (§9.2). The check runs at registration and again per batch, so a
body that reached the store some other way is refused the same way.

**It verifies arithmetic, not truth.** A fabricated `n: 3000, correct: 3000`
passes. The defences are attribution — the proof travels inside the pinned
body, next to the rule — and a re-score of the named files outside the Merge
Stage (§9.2).

Binding rules are identifier-only (company mastering ticket 04) and activate
`deterministic`ally on a verified Identifier Contract (§9.3); fuzzy binding
has its own statistical gate (ticket 08).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import NormalDist

from .classification import check_rule
from .evidence import KINDS
from .primitives import NORMALIZERS, primitive_family
from .store import Conflict, canonical

# The accepted bar per (kind, family): the least a document may declare
# (company mastering ticket 02, decision 4). A document may raise its own bar,
# never lower it, and a pair with no accepted bar cannot declare one. Keyed by
# family so lowering one decision never lowers another: Company classification
# acts at 95% (confidence bands, company-policy.md, 2026-09-24), while merging
# two published Company IDs keeps Q10/Q11's 99.9% by having no entry here.
ACCEPTED_BARS = {
    ("company", "classification"): {
        "min_precision": 0.95,
        "one_sided_confidence": 0.95,
    },
    ("person", "classification"): {
        "min_precision": 0.99,
        "one_sided_confidence": 0.975,
    },
}
METHOD = "wilson_lower_bound"
# A stated lower bound reproduces when it is no higher than the recomputed one
# and within this of it: a bound written to five decimals, as the spec's own
# example is (0.99545 for 0.9954530), passes; a bound rounded *up* never does,
# because the bar is judged on the recomputed value, not the stated one.
TOLERANCE = 1e-5


def wilson_lower_bound(correct: int, n: int, confidence: float) -> float:
    """One-sided Wilson score lower bound on a proportion."""
    if type(n) is not int or type(correct) is not int or not 0 <= correct <= n or n < 1:
        raise Conflict(f"Proof sample is invalid: {correct} correct of {n}")
    z = NormalDist().inv_cdf(confidence)
    p = correct / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - spread) / (1 + z * z / n)


def _rules(body: dict) -> Iterable[tuple[str, dict]]:
    for kind, block in sorted((body.get("kinds") or {}).items()):
        for rule in block.get("rules") or []:
            yield kind, rule


def check_policy(body: dict) -> None:
    """Refuse a body whose rules or activations do not hold (§9.2, §10)."""
    kinds = body.get("kinds") or {}
    for kind, block in sorted(kinds.items()):
        for family, bar in sorted((block.get("bars") or {}).items()):
            _check_bar(kind, family, bar)
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
            raise Conflict(f"Verdict {key} is activated twice")
        active.add(key)
        _check_activation(kinds, entry)


def _check_bar(kind: str, family: str, bar: dict) -> None:
    accepted = ACCEPTED_BARS.get((kind, family))
    if accepted is None:
        raise Conflict(
            f"{kind}/{family} has no accepted bar, so a document may declare none"
        )
    if bar.get("method") != METHOD:
        raise Conflict(f"Bar for {kind}/{family} names an unsupported method")
    for name in ("min_precision", "one_sided_confidence"):
        if not isinstance(bar.get(name), (int, float)) or bar[name] < accepted[name]:
            raise Conflict(
                f"Bar for {kind}/{family} sets {name} {bar.get(name)}, below the "
                f"accepted {accepted[name]}"
            )


def _check_activation(kinds: dict, entry: dict) -> None:
    """One shared resolution, then the check its activation kind names.

    Resolution is what every activation needs: the kind, the rule, its exact
    version and a verdict it emits. What proves an activation differs:
    a measured proof against a bar (§9.2), or a verified Identifier Contract
    (§9.3). Kept as one table so a third way is one entry, not a branch.
    """
    how = entry.get("activation")
    if how not in ACTIVATIONS:
        raise Conflict(
            f"Activation of {entry.get('rule_id')}: {how} activation is not a "
            "supported kind of activation"
        )
    families, check = ACTIVATIONS[how]
    if entry.get("family") not in families:
        raise Conflict(
            f"Activation of {entry.get('rule_id')}: {how} activation applies to "
            f"{' and '.join(sorted(families))} rules, not {entry.get('family')}"
        )
    block, rule = _resolve(kinds, entry)
    check(entry["kind"], block, rule, entry)


def _resolve(kinds: dict, entry: dict) -> tuple[dict, dict]:
    kind, rule_id, verdict = (
        entry.get("kind"),
        entry.get("rule_id"),
        entry.get("verdict"),
    )
    if kind not in kinds:
        raise Conflict(f"Activation names kind {kind}, which the policy does not hold")
    block = kinds[kind]
    rules = [r for r in block.get("rules") or [] if r.get("rule_id") == rule_id]
    if not rules:
        raise Conflict(f"Activation names rule {rule_id}, which is absent from {kind}")
    rule = rules[0]
    if rule.get("family") != entry.get("family"):
        raise Conflict(
            f"Activation names {rule_id} as {entry.get('family')}, but it is a "
            f"{rule.get('family')} rule"
        )
    if rule.get("version") != entry.get("rule_version"):
        # A rule edited after its proof is orphaned, never re-proved by default.
        raise Conflict(
            f"Activation names {rule_id} version {entry.get('rule_version')}, but "
            f"the policy holds version {rule.get('version')}"
        )
    if verdict not in (rule.get("emits") or ()):
        raise Conflict(
            f"Activation names verdict {verdict}, which {rule_id} does not emit"
        )
    return block, rule


def _check_measured(kind: str, block: dict, rule: dict, entry: dict) -> None:
    family, verdict = entry["family"], entry["verdict"]
    if verdict not in KINDS:
        raise Conflict(f"Activation names verdict {verdict}, which decides no kind")
    bar = (block.get("bars") or {}).get(family)
    if bar is None:
        raise Conflict(
            f"Kind {kind} has no bar for {family}, so nothing there activates"
        )
    _check_proof(kind, bar, entry.get("proof") or {})


def _check_deterministic(kind: str, block: dict, rule: dict, entry: dict) -> None:
    """§9.3: an identifier-only rule activates on its verified contracts.

    It has no precision to measure; its failure mode is a wrong Identifier
    Contract. So every namespace it names must have a complete one.
    """
    for namespace in binding_namespaces(rule):
        contract = (block.get("identifiers") or {}).get(namespace)
        if not contract:
            raise Conflict(
                f"Activation of {rule['rule_id']}: namespace {namespace} has no "
                "Identifier Contract"
            )
        _check_contract(namespace, contract)


def _check_proof(kind: str, bar: dict, proof: dict) -> None:
    if proof.get("method") != bar["method"]:
        raise Conflict(
            f"Proof method {proof.get('method')} is not the bar's {bar['method']}"
        )
    if proof.get("one_sided_confidence") != bar["one_sided_confidence"]:
        raise Conflict(
            f"Proof confidence {proof.get('one_sided_confidence')} is not the bar's "
            f"{bar['one_sided_confidence']}"
        )
    recomputed = wilson_lower_bound(
        proof.get("correct"), proof.get("n"), proof["one_sided_confidence"]
    )
    stated = proof.get("lower_bound")
    if (
        not isinstance(stated, (int, float))
        or stated > recomputed
        or recomputed - stated > TOLERANCE
    ):
        raise Conflict(
            f"Proof lower bound {stated} does not reproduce from its sample "
            f"({recomputed:.6f})"
        )
    if recomputed < bar["min_precision"]:
        raise Conflict(
            f"Proof lower bound {recomputed:.6f} is below the {kind} bar "
            f"{bar['min_precision']}"
        )
    adversarial = proof.get("adversarial") or {}
    if adversarial.get("violations") != 0 or not adversarial.get("fixture_sha256"):
        raise Conflict(
            "Proof has adversarial violations or names no adversarial fixture"
        )
    if not (proof.get("cohort") or {}).get("files"):
        raise Conflict("Proof cohort names no files")
    if not all(proof.get(k) for k in ("approved_by", "approved_at", "reason")):
        raise Conflict("Proof lacks its approval: approved_by, approved_at and reason")


def activated(body: dict, kind: str, rule: dict, verdict: str) -> bool:
    """Whether this exact rule version's verdict may act without a Steward.

    Trusts `check_policy` to have refused a body whose entry does not hold; it
    only finds the entry. A rule edited after its proof matches none.
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


# The namespaces an identifier rule may name: exactly the keys source evidence
# stores (`cik`, `lei`), not the spec's `sec.cik`, so a rule can never name a
# namespace no record carries and silently match nothing.
NAMESPACES = frozenset({"cik", "lei"})
ON_NO_MATCH = frozenset({"mint", "wait"})
# Company compatibility is kind equality only: Q9 says a name change never
# revokes a binding, and a name-similarity test is fuzzy matching (ticket 08).
COMPATIBILITY = frozenset({"kind_equal@1"})


def binding_namespaces(rule: dict) -> list[str]:
    return sorted(
        {(test.get("args") or {}).get("namespace") for test in rule.get("when") or []}
    )


def check_binding_rule(kind: str, rule: dict, kinds: dict) -> None:
    """A binding rule is identifier-only here, and says what a miss does.

    `on_no_match` is data on the rule: `mint` creates a new Company (the SEC
    universe is the base, Q1); `wait` leaves the record in the Stage (operator,
    2026-09-24: an unlinked GLEIF record waits). Fuzzy binding is ticket 08.
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
        if primitive_family(test.get("primitive")) != "binding":
            raise Conflict(
                f"Binding rule {rule_id} calls {test.get('primitive')}, which is "
                "not a binding test"
            )
    namespaces = binding_namespaces(rule)
    if len(namespaces) != 1 or namespaces[0] not in NAMESPACES:
        raise Conflict(
            f"Binding rule {rule_id} must name exactly one namespace of "
            f"{sorted(NAMESPACES)}: {namespaces}"
        )
    if not any(t["primitive"] == "identifier_match@1" for t in tests):
        raise Conflict(f"Binding rule {rule_id} does not match an identifier")
    if rule["on_no_match"] == "mint":
        _check_minting_source(kind, rule, namespaces[0], kinds)


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
    contract = ((kinds.get(kind) or {}).get("identifiers") or {}).get(namespace)
    issuers = (contract or {}).get("sources")
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
    compatibility = contract.get("compatibility") or {}
    if (
        not compatibility.get("field")
        # A binding test (§5 has no family of its own for it); kind equality
        # is the only one this build holds.
        or compatibility.get("predicate") not in COMPATIBILITY
    ):
        raise Conflict(f"{where} states no compatibility check")
    verification = contract.get("verification") or {}
    if not (
        isinstance(verification.get("corpus_sha256"), str)
        and len(verification["corpus_sha256"]) == 64
        and all(verification.get(k) for k in ("approved_by", "approved_at", "reason"))
    ):
        raise Conflict(f"{where} is not verified: corpus hash and approval required")
    tolerance = contract.get("tolerance") or {}
    if not (
        tolerance.get("unit")
        and type(tolerance.get("warm_up_decisions")) is int
        and isinstance(tolerance.get("max_per_10k"), (int, float))
    ):
        raise Conflict(f"{where} has an incomplete tolerance block")


RULE_CHECKS = {
    "classification": _check_classification_rule,
    "binding": check_binding_rule,
}
# Which rule families each kind of activation may prove. Sets, so ticket 08's
# measured (fuzzy) binding is one more member, not a reshaped table.
ACTIVATIONS = {
    "measured": (frozenset({"classification"}), _check_measured),
    "deterministic": (frozenset({"binding"}), _check_deterministic),
}
