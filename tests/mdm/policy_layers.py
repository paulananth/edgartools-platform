"""The Company policy's switched-off additions, newest first.

Each ticket that declares rules switched off (or adds a table) is one layer:
peeling it must give back the digest the operator approved before it. A new
layer is one entry in `LAYERS`, with the policy's digest while that layer is
still on; every pinned test reads the chain from here (`PINNED`).
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


FORM_ADV_SOURCES = ("iapd.adv.filings.v1", "iapd.adv.custodians.v1")
FORM_ADV_RULES = ("iapd-adv-crd", "iapd-adv-custodian-lei", "iapd-adv-custodian-bd")


def without_form_adv(policy: dict) -> dict:
    """Profiling ticket 07 (operator, 2026-10-09: the design "Approve as
    proposed (Recommended)"; "custodian must be in mdm"): the Form ADV
    sources, their three identifier matching rules (declared, not switched on)
    with the Identifier Contracts for crd, lei and bd_number. Peeled, the
    policy is the one before."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["defaults"]["sources"] = [s for s in company["defaults"]["sources"] if s not in FORM_ADV_SOURCES]
    company["rules"] = [r for r in company["rules"] if r["rule_id"] not in FORM_ADV_RULES]
    for namespace in ("crd", "lei", "bd_number"):
        company["identifiers"].pop(namespace)
    return body


def without_parent_history(policy: dict) -> dict:
    """Profiling ticket 04b, part B (operator, 2026-10-07: "It should also
    consider corporate actions"): the calculated ultimate parent keeps its
    history (accounting-chain-v2), and a successor entity ends parent links.
    Peeled, the types are the ones part A named."""
    body = _copy(policy)
    types = body["relationships"]["types"]
    types["IS_DIRECTLY_CONSOLIDATED_BY"]["ultimate_parent"] = "accounting-chain-v1"
    types["SUCCESSOR_ENTITY"].pop("ends_parent_links")
    body["relationships"]["version"] = "relationship-types-v2"
    return body


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
    Peeled, the tables are embedded again, as before. The table's YAML is
    removed; it is rebuilt from the pinned version, which equals it code for
    code (tests/mdm/test_sec_place_codes.py)."""
    from tests.support import place_codes

    body = {k: v for k, v in _copy(policy).items() if k != "reference_pins"}
    body["reference"] = {"sec-place-codes": {"codes": place_codes.table()}}
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


# Newest first: each layer, and Company's policy digest with it and every
# layer after it still on.
LAYERS = [
    # Not yet approved: the operator approves its digest with the proof.
    (without_form_adv, "af0fa7cce9845419238d7ed23aa5fb7c1c8ccd576f2137e2b4ef3c732369a7cc"),
    (without_parent_history, "c608d93a9e72f965624ff467321f8aecab4e6cd13074cd1fbda7d6fc82001605"),
    (without_real_names, "bf682fa4e2ba378ded491a6d6aa46b2a417682f1de4d5d20adb1490177efb2f6"),
    # Approved: "Ticket 02's last step needs your approval. Approved" (2026-10-07 08:01 ET).
    (without_reference_pins, "058759172d1de36cc397ee89aa0c4630c11c86dcc29a4c6d5f42c96b0e4c8ee4"),
    (without_relationship_types, "1e38238fbb48390f13188c52ff312606aead9d942380dac31f0f5a1154203da4"),
    (without_gleif_parent_links, "6978715fa0b862e00caecc791c239c5b3ed8ffdf7450521bf761c886a5708ae5"),
    # Approved: "yes" (2026-09-29 21:04 ET, company mastering ticket 25).
    (without_name_rules_on, "75bd2b6744c075750c5f86632aa7e9fd504be03a648f91a1b0f3ab8c51e33dbe"),
    # Approved 0d4d5cb0...0702 on 2026-09-29 07:27 ET (ticket 15).
    (without_cik_approval, "15e07b302482bbbe191fd5b89855373f04f18db31a3c9caaa733f1bc87b9b6d6"),
    (without_cik, "0d4d5cb0f190a4486c7cc65c7ba71b4dc173e3ce82eb2734261caea7c6c20702"),
    (without_cascade, "8bdc2f68294bbe93aebaa1949090073d1bec4f2adb95fddfdc11594344f6555d"),
    (without_place_codes, "3520e890d46020e1c0a579807151b9d1cadcf5adab535172811b8e96f99b1e17"),
]

# Every layer peeled: the policy the operator approved (2026-09-25 15:21 ET).
APPROVED = "983352e81d295a165a1391e82fa8a24a710e6f638361a577f18f541917fd4049"

# The digest chain `digests` must give for Company's part of the policy.
PINNED = [pinned for _, pinned in LAYERS] + [APPROVED]


def peel(policy: dict) -> dict:
    """The policy with every layer peeled: what the operator approved."""
    for layer, _ in LAYERS:
        policy = layer(policy)
    return policy


def digests(policy: dict) -> list[str]:
    """The policy's digest, then its digest after each layer is peeled."""
    found = [digest(policy)]
    for layer, _ in LAYERS:
        policy = layer(policy)
        found.append(digest(policy))
    return found
