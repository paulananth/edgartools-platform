"""Decide a source record's identity kind from a governed, versioned rule.

Today a Dataset Contract decides the kind with a lookup table on one column
(`adapters.normalize`). That works for a source that states what it is, and
not at all for an SEC reporting owner whose only evidence is a name.

A Mastering Policy holds the real rules. A Dataset Contract names one, and the
decided kind is stamped on the assertion and hashed into its id
(`evidence.assertion`), so it is settled when the record is read and never
afterwards. The policy is therefore resolved at read time, beside the contract
(operator decision, 2026-09-23).

A rule is an ordered list of steps. The **first step whose `when` list holds
entirely** supplies the verdict; a `when` list is a conjunction. There is no
`OR` inside a step, no loop, and no document-supplied expression — first-match
ordering over steps is how an *unless* is written, and each of the others
would make a pinned digest fail to reproduce its result
(`policy-language.md` §5-§6).
"""

from __future__ import annotations

from .evidence import KINDS
from .primitives import call, primitive_family
from .store import Conflict

# Every kind a rule may decide, plus the two verdicts that decide no kind.
# Derived rather than restated: this list was written out by hand and was the
# third copy of the kind set, after evidence.KINDS and the CHECK constraint on
# mdm_v2.identity. The SQL copy cannot be derived away and is held equal by
# tests/integration/test_clean_per_kind_views.py instead.
CLASSIFICATION_VERDICTS = KINDS | {"entity_undetermined", "deferred"}


def resolve_rule(policy: dict, named: dict | None) -> dict | None:
    """The classification rule a Dataset Contract names, by kind, id and version.

    A contract that names none keeps the adapter's own kind mapping, which is
    how every source registered before this existed keeps working.

    Naming a rule that is absent is refused rather than ignored: a contract
    that points at nothing would silently fall back to the table it was
    written to replace. Pointing at a *different* version is a mapping change,
    so it produces a new mapping version and a second row rather than
    re-reading old evidence under new rules (ticket 01).
    """
    if not named:
        return None
    block = (policy.get("kinds") or {}).get(named["kind"]) or {}
    for rule in block.get("rules") or []:
        if rule.get("rule_id") == named["rule_id"]:
            if rule.get("version") != named["version"]:
                raise Conflict(
                    f"Dataset Contract names classification rule {named['rule_id']} "
                    f"version {named['version']}, which the policy does not hold"
                )
            return rule
    raise Conflict(
        f"Dataset Contract names an absent classification rule: {named['rule_id']}"
    )


def check_rule(rule: dict) -> None:
    """Refuse a classification rule that is not well formed (§10 checks 1-2).

    Run at registration, so a malformed rule never becomes a digest, and again
    before every evaluation, so a rule that reached a batch some other way is
    refused the same way rather than half-run.
    """
    if rule.get("family") != "classification":
        raise Conflict(
            f"Rule {rule.get('rule_id')} is not a classification rule: {rule.get('family')}"
        )
    emits = set(rule.get("emits") or ())
    steps = rule.get("steps") or []
    catch_alls = sum(1 for step in steps if step.get("otherwise"))
    if catch_alls != 1:
        found = (
            "no catch-all step" if not catch_alls else f"{catch_alls} catch-all steps"
        )
        raise Conflict(
            f"Classification rule {rule.get('rule_id')} has {found}: "
            "exactly one otherwise step is required"
        )
    for step in steps:
        verdict = step.get("verdict")
        if verdict not in emits or verdict not in CLASSIFICATION_VERDICTS:
            raise Conflict(
                f"Step {step.get('step')} emits an undeclared verdict: {verdict}"
            )
        if step.get("otherwise"):
            continue
        if not step.get("when"):
            # An empty list reads as "always true" and is easy to mis-edit into
            # silence, so a catch-all must say so (prototype finding 3).
            raise Conflict(
                f"Step {step.get('step')} has an empty when; write otherwise: true"
            )
        for test in step["when"]:
            if primitive_family(test.get("primitive")) != "classification":
                raise Conflict(
                    f"Step {step.get('step')} calls {test.get('primitive')}, "
                    "which is not a classification test"
                )


def fired(rule: dict, record: dict, doc: dict) -> tuple[str, str]:
    """The verdict the first matching step supplies, and that step's name.

    The step is returned because the record keeps it: an assertion's
    provenance names the rule, version and step that labelled it
    (`policy-language.md` §6), so it explains itself with no lookup elsewhere.
    """
    check_rule(rule)
    for step in rule["steps"]:
        if step.get("otherwise") or all(
            _holds(test, record, doc) for test in step["when"]
        ):
            return step["verdict"], str(step["step"])
    raise AssertionError("check_rule guarantees a catch-all step")


def classify(rule: dict, record: dict, doc: dict) -> str:
    """The verdict the first matching step supplies."""
    return fired(rule, record, doc)[0]


def _holds(test: dict, record: dict, doc: dict) -> bool:
    result = bool(call(test["primitive"], test.get("args") or {}, record, doc))
    return not result if test.get("negate") else result
