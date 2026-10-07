"""The Company policy's switched-off additions, newest first.

Each ticket that declares rules switched off (or adds a table) is one layer:
peeling it must give back the digest the operator approved before it. A new
layer is one entry in `LAYERS`, and every pinned test sees it.
"""

from __future__ import annotations

import json

from edgar_warehouse.mdm.clean.store import canonical, digest


def _copy(policy: dict) -> dict:
    return json.loads(canonical(policy))


NAME_RULES = ("sec-gleif-name-jurisdiction", "sec-gleif-name-postal")


def company_part(policy: dict) -> dict:
    """The policy as Company sees it: every other kind and its switched-on
    rules left out, so a new kind does not move Company's pins (platform
    validation 05a, operator Q9: "A"). The shared body and reference tables
    stay, because Company's rules read them."""
    body = _copy(policy)
    body["kinds"] = {"company": body["kinds"]["company"]}
    body["automatic_rules"] = [r for r in body.get("automatic_rules") or [] if r.get("kind") == "company"]
    return body


def company_proofs(proofs: dict, policy: dict) -> dict:
    """The pending proofs of the rules Company declares."""
    declared = {rule["rule_id"] for rule in policy["kinds"]["company"].get("rules") or []}
    return {rule_id: proof for rule_id, proof in proofs.items() if rule_id in declared}


def without_real_names(policy: dict) -> dict:
    """Profiling ticket 04b (operator, 2026-10-07: "All relationships must be
    named as close as reality"; each name approved one by one): the
    relationship types under their sources' own names. Peeled, the types are
    the table profiling ticket 04 moved into the policy."""
    from edgar_warehouse.mdm.clean import relationships

    body = _copy(policy)
    body["relationships"] = {"version": "relationship-types-v1", "types": _copy(relationships.TYPES_V0)}
    return body


def without_reference_pins(policy: dict) -> dict:
    """Profiling ticket 02 (operator, 2026-10-07 08:01 ET: "Ticket 02's last
    step needs your approval. Approved"): the policy pins its reference data
    (an RDM code set version and its sha256) instead of embedding the tables.
    Peeled, the tables are embedded again, as before."""
    from edgar_warehouse.rules import files

    body = {k: v for k, v in _copy(policy).items() if k != "reference_pins"}
    body["reference"] = {path.stem: files.load(path) for path in sorted((files.ROOT / "reference").glob("*.yaml"))}
    return body


def without_relationship_types(policy: dict) -> dict:
    """Profiling ticket 04 (operator, 2026-10-06: "Types as data"): the
    relationship types, moved from code into the policy (`relationships`). A
    policy without them masters the same table (`relationships.TYPES_V0`)."""
    return {k: v for k, v in _copy(policy).items() if k != "relationships"}


def without_gleif_parent_links(policy: dict) -> dict:
    """Platform validation 06a: adds GLEIF's relationship file to Company's
    sources, for its accounting-parent links (it fills no field)."""
    body = _copy(policy)
    defaults = body["kinds"]["company"]["defaults"]
    defaults["sources"] = [s for s in defaults["sources"] if s != "gleif.relationships.v1"]
    return body


def without_name_rules_on(policy: dict) -> dict:
    """Company mastering ticket 25: the two name matching rules switched on,
    on the operator's approval ("yes", 2026-09-29 21:04 ET)."""
    body = _copy(policy)
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r["rule_id"] not in NAME_RULES]
    return body


def without_cik_approval(policy: dict) -> dict:
    """Company mastering ticket 15: the operator's approval of the CIK
    matching rule, its contract's three stamps and its activation."""
    body = _copy(policy)
    body["kinds"]["company"]["identifiers"]["cik"]["verification"].update(
        approved_by=None, approved_at=None, reason=None
    )
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r["rule_id"] != "company-cik"]
    return body


def without_cik(policy: dict) -> dict:
    """Company mastering ticket 15: the CIK matching rule and its Identifier
    Contract."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["rules"] = [r for r in company["rules"] if r["rule_id"] != "company-cik"]
    company.pop("identifiers")
    return body


def without_cascade(policy: dict) -> dict:
    """Company mastering ticket 21: the cascade's seven passes."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["rules"] = [r for r in company["rules"] if not r["rule_id"].startswith("sec-gleif-cascade-")]
    return body


def without_place_codes(policy: dict) -> dict:
    """Rules skill ticket 08: the reference tables in the policy body."""
    return {k: v for k, v in _copy(policy).items() if k != "reference"}


LAYERS = [without_real_names, without_reference_pins, without_relationship_types, without_gleif_parent_links, without_name_rules_on, without_cik_approval, without_cik, without_cascade, without_place_codes]


def peel(policy: dict) -> dict:
    """The policy with every layer peeled: what the operator approved."""
    for layer in LAYERS:
        policy = layer(policy)
    return policy


def digests(policy: dict) -> list[str]:
    """The policy's digest, then its digest after each layer is peeled."""
    found = [digest(policy)]
    for layer in LAYERS:
        policy = layer(policy)
        found.append(digest(policy))
    return found
