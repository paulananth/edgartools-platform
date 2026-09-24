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

Not yet here, and refused by name rather than ignored: binding rules and
`deterministic` activation (company mastering ticket 04, which brings the
identifier primitives they need).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import NormalDist

from .classification import check_rule
from .evidence import KINDS
from .store import Conflict, canonical

# Each kind's accepted bar: the least a document may declare (company mastering
# ticket 02, decision 4; Company Q11). A document may raise its own bar, never
# lower it, and a kind with no accepted bar cannot activate anything.
ACCEPTED_BARS = {
    "company": {"min_precision": 0.999, "one_sided_confidence": 0.95},
    "person": {"min_precision": 0.99, "one_sided_confidence": 0.975},
}
METHOD = "wilson_lower_bound"
# A stated lower bound reproduces when it matches the recomputed one to this
# many places; enough for any bound written to six decimals.
TOLERANCE = 1e-6


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
        if family == "binding":
            raise Conflict(
                f"Rule {rule.get('rule_id')}: binding rules are not implemented "
                "(company mastering ticket 04)"
            )
        if family != "classification":
            raise Conflict(
                f"Rule {rule.get('rule_id')} has an unknown family: {family}"
            )
        check_rule(rule)
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
    accepted = ACCEPTED_BARS.get(kind)
    if accepted is None:
        raise Conflict(f"Kind {kind} has no accepted bar, so it may declare none")
    if bar.get("method") != METHOD:
        raise Conflict(f"Bar for {kind}/{family} names an unsupported method")
    for name in ("min_precision", "one_sided_confidence"):
        if not isinstance(bar.get(name), (int, float)) or bar[name] < accepted[name]:
            raise Conflict(
                f"Bar for {kind}/{family} sets {name} {bar.get(name)}, below the "
                f"accepted {accepted[name]}"
            )


def _check_activation(kinds: dict, entry: dict) -> None:
    kind, family = entry.get("kind"), entry.get("family")
    rule_id, verdict = entry.get("rule_id"), entry.get("verdict")
    if entry.get("activation") != "measured":
        raise Conflict(
            f"Activation of {rule_id}: {entry.get('activation')} activation is not "
            "implemented (company mastering ticket 04)"
        )
    if family != "classification":
        raise Conflict(
            f"Activation of {rule_id}: {family} activation is not implemented "
            "(company mastering ticket 04)"
        )
    if kind not in kinds:
        raise Conflict(f"Activation names kind {kind}, which the policy does not hold")
    block = kinds[kind]
    rules = [r for r in block.get("rules") or [] if r.get("rule_id") == rule_id]
    if not rules:
        raise Conflict(f"Activation names rule {rule_id}, which is absent from {kind}")
    rule = rules[0]
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
    if verdict not in KINDS:
        raise Conflict(f"Activation names verdict {verdict}, which decides no kind")
    bar = (block.get("bars") or {}).get(family)
    if bar is None:
        raise Conflict(
            f"Kind {kind} has no bar for {family}, so nothing there activates"
        )
    _check_proof(kind, bar, entry.get("proof") or {})


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
    if not isinstance(stated, (int, float)) or abs(recomputed - stated) > TOLERANCE:
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
