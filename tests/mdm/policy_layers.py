"""Test help for the Mastering Policy."""

from __future__ import annotations

import json

from edgar_warehouse.mdm.store import canonical


def _copy(policy: dict) -> dict:
    return json.loads(canonical(policy))


def with_rules_on(policy: dict, kind: str, *rule_ids: str) -> dict:
    """A copy of the policy with these declared matching rules of one kind switched on, for a
    test only: each joins `automatic_rules` at its declared version."""
    body = _copy(policy)
    declared = {r["rule_id"]: r for r in body["kinds"][kind]["rules"]}
    # A rule the policy already switches on stays as it is (ticket 138's switch-on).
    active = {(a["kind"], a["rule_id"]) for a in body["automatic_rules"]}
    body["automatic_rules"] = [*body["automatic_rules"], *(
        {"kind": kind, "family": "binding", "rule_id": rule_id, "rule_version": declared[rule_id]["version"],
         "verdict": "bind"} for rule_id in rule_ids if (kind, rule_id) not in active)]
    return body
