"""The Company policy's switched-off additions, newest first.

Each ticket that declares rules switched off (or adds a table) is one layer:
peeling it must give back the digest the operator approved before it. A new
layer is one entry in `LAYERS`, with the policy's digest while that layer is
still on; every pinned test reads the chain from here (`PINNED`).
"""

from __future__ import annotations

import json
from pathlib import Path

from edgar_warehouse.mdm.store import canonical, digest


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


def with_rules_on(policy: dict, kind: str, *rule_ids: str) -> dict:
    """A copy of the policy with these declared matching rules of one kind switched on, for a
    test only: each joins `automatic_rules` as a deterministic binding at its declared version."""
    body = _copy(policy)
    declared = {r["rule_id"]: r for r in body["kinds"][kind]["rules"]}
    # A rule the policy already switches on stays as it is (ticket 138's switch-on).
    active = {(a["kind"], a["rule_id"]) for a in body["automatic_rules"]}
    body["automatic_rules"] = [*body["automatic_rules"], *(
        {"kind": kind, "family": "binding", "rule_id": rule_id, "rule_version": declared[rule_id]["version"],
         "verdict": "bind", "activation": "deterministic"} for rule_id in rule_ids if (kind, rule_id) not in active)]
    return body


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


NPORT_REGISTRANT = "sec.nport.registrant.v2"


def without_nport_registrant(policy: dict) -> dict:
    """Rebuild priorities ticket 79, part 2 (operator, 2026-10-15: "agreed"):
    the N-PORT registrant as a Company source, last in `defaults.sources` and
    in the CIK contract's sources, with its matching rule (declared, not
    switched on). Peeled, the policy is the one before."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["defaults"]["sources"] = [s for s in company["defaults"]["sources"] if s not in (NPORT_REGISTRANT, "sec.nport.registrant.v1")]
    cik = company["identifiers"]["cik"]
    cik["sources"] = [s for s in cik["sources"] if s not in (NPORT_REGISTRANT, "sec.nport.registrant.v1")]
    company["rules"] = [r for r in company["rules"] if r["rule_id"] != "nport-registrant-cik"]
    return body


def without_adv_switch_on(policy: dict) -> dict:
    """Rebuild priorities ticket 76 (operator, 2026-10-17 08:31 ET: "Switch on
    all three (Recommended)"): the Form ADV matching rules switched on, with
    their Identifier Contracts' verification on the ticket 76 run. Peeled, the
    policy is the one before."""
    body = _copy(policy)
    for namespace in ("crd", "lei", "bd_number"):
        body["kinds"]["company"]["identifiers"][namespace].pop("verification")
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r["rule_id"] not in FORM_ADV_RULES]
    return body


def without_nport_switch_on(policy: dict) -> dict:
    """Rebuild priorities ticket 79 (operator, 2026-10-17 21:03 ET: "Switch on all
    six (Recommended)"): `nport-registrant-cik` switched on, its CIK Identifier
    Contract re-verified on the registrant Proving Run. Peeled, the rule is
    declared only and the contract keeps ticket 05's verification."""
    body = _copy(policy)
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r["rule_id"] != "nport-registrant-cik"]
    body["kinds"]["company"]["identifiers"]["cik"]["verification"] = {
        "corpus_sha256": "3607ae6c80216e90d8decbe827c8688ec3c608d232be868d58c8d231585360cc",
        "approved_by": "operator", "approved_at": "2026-09-29T11:27:26Z",
        "reason": "ticket 15: approved policy digest 0d4d5cb0...0702; ticket 05 Proving Run, 6,414 of "
                  "6,414 Companies by their CIK, 0 controls, no CIK on two Companies, a second pass "
                  "changed nothing"}
    return body


def without_p2_p3_deleted(policy: dict) -> dict:
    """Rebuild priorities ticket 09 (operator, 2026-10-17: "Delete both
    (Recommended)"): cascade passes P2 (street and postcode) and P3 (street
    and city) deleted, too few new links to prove. Peeled, they stand again
    after P1, which they equal but for their name and the parts compared."""
    body = _copy(policy)
    rules = body["kinds"]["company"]["rules"]
    at = next(i for i, r in enumerate(rules) if r["rule_id"] == "sec-gleif-cascade-p1")
    restored = []
    for name, parts in (("P2", ["street", "postcode"]), ("P3", ["street", "city"])):
        rule = _copy(rules[at])
        rule["rule_id"] = f"sec-gleif-cascade-{name.lower()}"
        rule["when"][0]["args"].update({"pass": name, "compare": parts})
        restored.append(rule)
    rules[at + 1:at + 1] = restored
    return body


# P5's measured entry as switched on at 18:20 ET (ticket 09), before it compared the postcode too.
P5_CITY_ENTRY = {
    "kind": "company",
    "family": "name_binding",
    "rule_id": "sec-gleif-cascade-p5",
    "rule_version": "2026-09-28.1",
    "verdict": "bind",
    "activation": "measured",
    "proof": {
        "method": "wilson_lower_bound",
        "one_sided_confidence": 0.95,
        "n": 84,
        "correct": 84,
        "lower_bound": 0.968796,
        "adversarial": {
            "fixture_sha256": "41bb780ea61234c4b165589907a1378d557f8dbe31ecd53572bc68a4745f01c8",
            "n": 39,
            "violations": 0
        },
        "cohort": {
            "companies": 6414,
            "new_links": 84,
            "files": {
                "p5-labels.jsonl": "48f4ec9c18104eff19ba19b514fc4eb4773afb0e3b8a353135af5d3ce73d8fd3",
                "p5-adversarial.jsonl": "41bb780ea61234c4b165589907a1378d557f8dbe31ecd53572bc68a4745f01c8",
                "ticket09-labels.csv": "ddc26bfdf0340ee57708cbf083bed00c13fe9e5396a80f1ccb29947d2625b1ae",
                "ticket09-labels.codex-completed.csv": "475d7dd80db264bbbc7ba8c4bcf9082988d931ded0e2ffcb108738495d08a3c2",
                "operator-answers.json": "640327dc14be3060b21afc9c967c24ed17c98d7ce6811f13d34b29965650fef6",
                "operator-notes.json": "0e22f3ab43e8c3cf6554bcac510de014072190036e5386f3eff3c424740b1a19"
            }
        },
        "approved_by": "operator",
        "approved_at": "2026-10-30T22:20:25Z",
        "reason": "ticket 09, the cascade pass P5 (name and city): every new link on the 6,414-Company cohort labelled, 84/84 the same entity (42 Codex independent review, 42 operator), 0 of 39 adversarial (other name, incorporation conflict, name held by another candidate)",
        "approved_words": "P5 now, hold P1/P4/P6 (Recommended)"
    }
}


def without_p5_postcode(policy: dict) -> dict:
    """Rebuild priorities ticket 09 (operator, 2026-10-30: "do not use p1 or p4,
    p5 can match on postel code"; "Link them (Recommended)"): P5 compares the
    city or the postcode, and P1 and P4 are deleted. Peeled, P1 and P4 stand
    again before P5, which compares the city alone under its first proof."""
    body = _copy(policy)
    rules = body["kinds"]["company"]["rules"]
    at = next(i for i, r in enumerate(rules) if r["rule_id"] == "sec-gleif-cascade-p5")
    rules[at]["version"] = "2026-09-28.1"
    rules[at]["when"][0]["args"]["compare"] = ["city"]
    restored = []
    for name, parts in (("P1", ["street", "city", "postcode"]), ("P4", ["postcode"])):
        rule = _copy(rules[at])
        rule["rule_id"] = f"sec-gleif-cascade-{name.lower()}"
        rule["when"][0]["args"].update({"pass": name, "compare": parts})
        restored.append(rule)
    rules[at:at] = restored
    body["automatic_rules"] = [_copy(P5_CITY_ENTRY) if r.get("rule_id") == "sec-gleif-cascade-p5" else r
                               for r in body["automatic_rules"]]
    return body


def without_p5_switch_on(policy: dict) -> dict:
    """Rebuild priorities ticket 09 (operator, 2026-10-30 18:20 ET: "P5 now, hold
    P1/P4/P6 (Recommended)"): cascade pass P5 switched on, on its labelled new
    links and its adversarial arms. Peeled, P5 is declared only."""
    body = _copy(policy)
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r["rule_id"] != "sec-gleif-cascade-p5"]
    return body


def without_one_value_per_identifier(policy: dict) -> dict:
    """Rebuild priorities ticket 138: each Company identifier states the one
    value per Company the engine always enforced (`claim.reverse: 1`), since
    the engine now reads the limit and a Security's identifiers have none.
    Peeled, the policy is the one before."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["version"] = "company-2026-09-25.13"
    for contract in company["identifiers"].values():
        contract["claim"]["reverse"] = None
    return body


def without_holds_removed(policy: dict) -> dict:
    """Rebuild priorities ticket 25 (operator, 2026-10-22: "Agreed Remove HOLDS
    from MDM's relationship types"): a holding is a silver row, not a
    relationship MDM masters. Peeled, the policy is the one before."""
    body = _copy(policy)
    body["relationships"]["types"]["HOLDS"] = {"from": ["company", "fund_structure", "person"], "to": ["security"]}
    body["relationships"]["version"] = "relationship-types-v5"
    return body


def without_issued_by_keeps_start(policy: dict) -> dict:
    """Rebuild priorities ticket 113 (operator, 2026-10-19: "if issued by
    already exist do not overight"; a backfill: "Keep the earlier date
    (Recommended)"): ISSUED_BY keeps its start. Peeled, the policy is the one
    before."""
    body = _copy(policy)
    body["relationships"]["types"]["ISSUED_BY"].pop("keeps_start")
    body["relationships"]["version"] = "relationship-types-v4"
    return body


def without_custodian(policy: dict) -> dict:
    """Rebuild priorities ticket 75 (operator, 2026-10-14: "Yes, a new ticket
    (Recommended)"): the CUSTODIAN relationship type, an adviser to the
    custodians its Form ADV names. Peeled, the policy is the one before."""
    body = _copy(policy)
    body["relationships"]["types"].pop("CUSTODIAN")
    body["relationships"]["version"] = "relationship-types-v3"
    return body


def without_issuer_lei(policy: dict) -> dict:
    """Rebuild priorities tickets 22 and 97 (operator, 2026-10-16: "Issuers
    only, by LEI (Recommended)"): GLEIF's own record as an LEI source, and the
    issuer LEI matching rule (declared, not switched on; it joins and waits,
    never creates: "Wait, config only"). Peeled, the policy is the one before."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    lei = company["identifiers"]["lei"]
    lei["sources"] = [s for s in lei["sources"] if s != "gleif.level1.v1"]
    company["rules"] = [r for r in company["rules"] if r["rule_id"] != "gleif-issuer-lei"]
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


def without_types_in_rdm(policy: dict) -> dict:
    """Ticket 132 (operator, 2026-10-27: "Use RDM for keeping types and other
    information"): the relationship types moved from the policy body into RDM
    code set mdm-relationship-types, which the policy pins. Peeled, they are
    the body's own section again (relationship-types-v6)."""
    from edgar_warehouse.mdm import relationships

    body = _copy(policy)
    types = relationships.types_of(body)
    body["reference_pins"].pop(body["relationships"]["pin"])
    body["relationships"] = {"version": "relationship-types-v6", "types": types}
    return body


def without_real_names(policy: dict) -> dict:
    """Profiling ticket 04b (operator, 2026-10-07: "All relationships must be
    named as close as reality"; each name approved one by one): the
    relationship types under their sources' own names. Peeled, the types are
    the table profiling ticket 04 moved into the policy."""
    from edgar_warehouse.rules import files

    body = _copy(policy)
    # The earlier table is a version of its own RDM code set (ticket 188), read by its pinned version.
    codes = files.published_reference({"code_set": "mdm-relationship-types-before-real-names", "version": "1",
                                       "sha256": "d0677cc9df0e00c2a1ed620f6f063203a6c8e3dca044c779a9c5a561565f7120"})
    table: dict = {}
    for row in codes:
        if row["parent_code"] is None:
            table[row["code"]] = dict(row["properties"])
        else:
            table[row["parent_code"]].setdefault("capacities", []).append(row["code"].split(":", 1)[1])
    body["relationships"] = {"version": "relationship-types-v1", "types": table}
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
    policy without them masters what relationship-types-v1 held."""
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
    # Every rule that activates on the CIK contract goes with its approval.
    body["automatic_rules"] = [r for r in body["automatic_rules"]
                               if r["rule_id"] not in ("company-cik", "nport-registrant-cik")]
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


def without_one_issuer(policy: dict) -> dict:
    """Ticket 24 (operator, 2026-11-04: "This can't be true 'Security with two issuers keep two
    ISSUED_BY links' fix the root cause"): the relationship types pinned at version 3, which states
    that a Security has one issuer at a time. Peeled, the pin is version 2."""
    body = _copy(policy)
    pin = body["reference_pins"][body["relationships"]["pin"]]
    pin["version"] = "2"
    pin["sha256"] = "0ef43fd1905cb62d323acebfdfb341702c78e96e4670952d7c9dbdb074662078"
    return body


def without_other_capacity(policy: dict) -> dict:
    """Ticket 182 (operator, 2026-11-03: "Capacity `other` on EMPLOYED_BY (Recommended)"): the relationship
    types pinned at version 2, which adds the capacity `other` to EMPLOYED_BY. Peeled, the pin is version 1."""
    body = _copy(policy)
    pin = body["reference_pins"][body["relationships"]["pin"]]
    pin["version"] = "1"
    pin["sha256"] = "9a0a3525e9427ab88405240a81b85be9d89a54c540b0c53770bdd269df7c4d33"
    return body


# The three cascade rules before they were named by what they compare: id, version, pass label.
RETIRED_PASS_NAMES = {
    "sec-gleif-name-city-or-postcode": ("sec-gleif-cascade-p5", "2026-10-30.1", "P5"),
    "sec-gleif-name-country": ("sec-gleif-cascade-p6", "2026-09-28.1", "P6"),
    "sec-gleif-name-alone": ("sec-gleif-cascade-p7", "2026-09-28.1", "P7"),
}
RETIRED_ENTRY_REASON = (
    "ticket 09, the cascade pass P5 (name and city or postcode; P1 and P4 deleted): every new link over the "
    "whole SEC population labelled, 251/251 the same entity (110 Codex independent review, 141 operator), 0 of "
    "159 adversarial (other name, incorporation conflict, name held by another candidate)")


def without_pass_business_names(policy: dict) -> dict:
    """Operator, 2026-11-03: "i dont want anything named p1, p4 it should have the actual policy" and "yes
    rename all four": each cascade rule is named by what it compares. Peeled, the rules carry their pass
    numbers again (ids, versions, pass labels, and the measured entry's id, version and reason)."""
    body = _copy(policy)
    for rule in body["kinds"]["company"]["rules"]:
        if rule["rule_id"] in RETIRED_PASS_NAMES:
            rule["rule_id"], rule["version"], label = RETIRED_PASS_NAMES[rule["rule_id"]]
            rule["when"][0]["args"]["pass"] = label
    for entry in body["automatic_rules"]:
        if entry.get("rule_id") in RETIRED_PASS_NAMES:
            entry["rule_id"], entry["rule_version"], _ = RETIRED_PASS_NAMES[entry["rule_id"]]
            entry["proof"]["reason"] = RETIRED_ENTRY_REASON
    return body


def without_name_only_passes_deleted(policy: dict) -> dict:
    """Operator, 2026-11-03: "delete p6 and p7". The passes "name and country" (2 labelled pairs that read as a
    namesake) and "name alone" (a different entity among 14 labels) deleted. Peeled, they stand again after
    "name and city or postcode", which they equal but for their name and the parts compared."""
    body = _copy(policy)
    rules = body["kinds"]["company"]["rules"]
    at = next(i for i, r in enumerate(rules) if r["rule_id"] == "sec-gleif-name-city-or-postcode")
    restored = []
    for rule_id, label, parts in (("sec-gleif-name-country", "name and country", []),
                                  ("sec-gleif-name-alone", "name alone", None)):
        rule = _copy(rules[at])
        rule["rule_id"] = rule_id
        rule["when"][0]["args"].update({"pass": label, "compare": parts})
        restored.append(rule)
    rules[at + 1:at + 1] = restored
    return body


def without_custodian_name_rule(policy: dict) -> dict:
    """Ticket 01 (operator, 2026-11-04: "Complete and then run and switch on", exact name only,
    "Agreed"): the Form ADV custodian name rule, declared and switched on after its limited test on
    the real June 2026 names. Peeled, the policy is the one before."""
    body = _copy(policy)
    body["kinds"]["company"]["rules"] = [r for r in body["kinds"]["company"]["rules"]
                                         if r["rule_id"] != "iapd-adv-custodian-name"]
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r.get("rule_id") != "iapd-adv-custodian-name"]
    return body


LEI_REASON = 'tickets 75 and 76: Form ADV run beside GLEIF and SEC, 13 months, 24,760 Companies, no CRD, LEI or BD number on two Companies, 15,339 custodian links, a third pass changed nothing'


def without_registrant_lei(policy: dict) -> dict:
    """The N-PORT registrant's LEI searched (ticket 203; operator, 2026-11-10: "Master it ;consider it a source"):
    its matching rule and activation, the registrant among the LEI contract's sources, and the contract's
    verification as it was (ticket 76's)."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["rules"] = [r for r in company["rules"] if r["rule_id"] != "nport-registrant-lei"]
    body["automatic_rules"] = [e for e in body["automatic_rules"] if e.get("rule_id") != "nport-registrant-lei"]
    lei = company["identifiers"]["lei"]
    lei["sources"] = [x for x in lei["sources"] if x not in (NPORT_REGISTRANT, "sec.nport.registrant.v1")]
    lei["verification"] = {
        "corpus_sha256": "9a0a7bbe236126d31b0411cf2296ca25684bb0bbd1a971e65dc7966558d34d93",
        "approved_by": "operator", "approved_at": "2026-10-17T12:31:29Z", "reason": LEI_REASON}
    return body


def without_custodian_name_creation(policy: dict) -> dict:
    """The Form ADV custodian rules that create a Company by name, and by name and place (operator, 2026-11-09:
    "master using name and company type", "Name plus place (Recommended)"), with their activations."""
    body = _copy(policy)
    gone = {"iapd-adv-custodian-name-form", "iapd-adv-custodian-name-place"}
    body["kinds"]["company"]["rules"] = [r for r in body["kinds"]["company"]["rules"] if r["rule_id"] not in gone]
    body["automatic_rules"] = [e for e in body["automatic_rules"] if e.get("rule_id") not in gone]
    return body


def without_phase_1_listed_operating(policy: dict) -> dict:
    """Phase 1 (ticket 204; operator, 2026-11-09: "For phase 1 master only publically traded companies (filter)",
    "Operating and listed a real company"): the Company classification rule and its measured proof of the version
    before, held in `fixtures/company_classification_2026_09_25_13.json` as they were."""
    body = _copy(policy)
    held = json.loads((Path(__file__).parent / "fixtures/company_classification_2026_09_25_13.json").read_text())
    rules = body["kinds"]["company"]["rules"]
    # The rule keeps the source name the policy already uses (the SEC source was renamed after the lineage began).
    body["kinds"]["company"]["rules"] = [{**held["rule"], "source": r["source"]} if r["rule_id"] == "sec-company-candidate" else r
                                         for r in rules]
    body["automatic_rules"] = [held["entry"] if e.get("rule_id") == "sec-company-candidate" else e
                               for e in body["automatic_rules"]]
    return body


def without_related_person(policy: dict) -> dict:
    """Operator, 2026-11-08: "RELATED_PERSON (Recommended)": the relationship types pinned at version 4,
    which adds Form ADV's related person. Peeled, the pin is version 3."""
    body = _copy(policy)
    pin = body["reference_pins"][body["relationships"]["pin"]]
    pin["version"] = "3"
    pin["sha256"] = "4d9f696384fb3aa72aa0fa9b7dff6a3a22450d010488e6af580dca4658c94e70"
    return body


ADVISER_CIK_EARLIER = {"iapd-adv-crd": "2026-10-09.1", "iapd-adv-custodian-name": "2026-11-04.exact-name"}


def without_adviser_cik(policy: dict) -> dict:
    """Operator, 2026-11-08: "Both" (the Form ADV CIK join with the Schedule D 7.A link): the adviser CIK
    rule, declared and switched on after its limited test. Peeled, the policy is the one before.
    The filings carry their CIKs under a new dataset code, so peeled, the filings are iapd.adv.filings.v1
    again and the two rules reading them are back at their earlier versions."""
    body = json.loads(json.dumps(_copy(policy)).replace('"iapd.adv.filings.v2"', '"iapd.adv.filings.v1"'))
    body["kinds"]["company"]["rules"] = [r for r in body["kinds"]["company"]["rules"] if r["rule_id"] != "iapd-adv-cik"]
    body["automatic_rules"] = [r for r in body["automatic_rules"] if r.get("rule_id") != "iapd-adv-cik"]
    cik = body["kinds"]["company"]["identifiers"]["cik"]
    cik["sources"] = [s for s in cik["sources"] if s != "iapd.adv.filings.v1"]
    for rule in [*body["kinds"]["company"]["rules"], *body["automatic_rules"]]:
        earlier = ADVISER_CIK_EARLIER.get(rule.get("rule_id"))
        if earlier:
            rule["version" if "version" in rule else "rule_version"] = earlier
    return body


# Newest first: each layer, and Company's policy digest with it and every
# layer after it still on.
LAYERS = [
    # The N-PORT registrant's LEI searched (ticket 203, 2026-11-10).
    (without_registrant_lei, "5d55689332d36c4e29b44649752e839ab0dcc201dbf2618d17894de3e962b398"),
    # The custodian rules that create a Company by name, and by name and place (ticket 204, 2026-11-09).
    (without_custodian_name_creation, "c66426dcb0e136b719cb5b6b4fc9a6d02e305c36683f17bef4a7a26f1417c627"),
    # The Company classification: listed operating filers only (ticket 204, 2026-11-09).
    (without_phase_1_listed_operating, "db8423032eb2c7824baf205df6fb768620c1b4c128d394df181e2d5a2b26bd45"),
    # Relationship types version 4, RELATED_PERSON: "RELATED_PERSON (Recommended)" (2026-11-08).
    (without_related_person, "eeaa64a8a8ffbf294c805f793900880051965e335a9884078edf14be8ec42f95"),
    # The Form ADV adviser CIK rule: "Both" (2026-11-08).
    (without_adviser_cik, "4d817e5c79b216511d6780d9bb682663a6ba25c9210af113d34a0f1599b8dac6"),
    # The Form ADV custodian name rule (ticket 01, exact name only).
    (without_custodian_name_rule, "788ffd4fd739d65cb2014f5278c49724b3f2ace4a32c4cffc85780070b991d2f"),
    # A Security has one issuer at a time (ticket 24, relationship types version 3).
    (without_one_issuer, "97905f9416668c213d74eabe9aea2c237c77d6faec1394f15927a402b2e24baf"),
    # The two name-only passes deleted: "delete p6 and p7" (2026-11-03, ticket 09).
    (without_name_only_passes_deleted, "1df4a51dff797cb4d0bb92832e0727f1558ab37534e2ca6d2620259ae92cc05c"),
    # Cascade rules named by what they compare: "yes rename all four" (2026-11-03, ticket 09).
    (without_pass_business_names, "cc088e7403557025320b9d86bb2abc0486acb830de938639c32f392295123ce9"),
    # The capacity `other` on EMPLOYED_BY: "Capacity `other` on EMPLOYED_BY (Recommended)" (2026-11-03, ticket 182).
    (without_other_capacity, "a24c4ac2bd970feba807d28fc4ae9b5539adc49e7826c9aadff45424629244e7"),
    # P5 compares the city or the postcode; P1 and P4 deleted: "do not use p1 or p4, p5 can match on
    # postel code" and "Link them (Recommended)" (2026-10-30, ticket 09).
    (without_p5_postcode, "939847064fb977b01787a7d473f7cc8dca1f29dafa888e3e977063a17e68179c"),
    # Switched on: "P5 now, hold P1/P4/P6 (Recommended)" (2026-10-30 18:20 ET, ticket 09).
    (without_p5_switch_on, "68879d5e6a1e75489073021f7c72a34d2d601041ce3e7676b09577e0e761218c"),
    # The types in RDM: "Use RDM for keeping types and other information" (2026-10-27, ticket 132).
    (without_types_in_rdm, "a3bf10f406abe5d8cad20c698f1b51f2f81661a76a3944620edfc0c304f99cd5"),
    # Recorded under the standing rule on its tests (2026-10-25, ticket 138).
    (without_one_value_per_identifier, "81abb7cc110debcac75ddf846f92bab112938758d6bc225e6ebbf70c0ac72189"),
    # Removed: "Agreed Remove HOLDS from MDM's relationship types" (2026-10-22, ticket 25).
    (without_holds_removed, "0b8f20457f7775d8c6bc14badc4e9ee7a08147e198b42bc409bdc2e14741dd89"),
    # Recorded under the standing rule on its tests (2026-10-19, ticket 113).
    (without_issued_by_keeps_start, "eacd7b763ae928188f339f7fb8c9e57f4bdb0c8132f804f8fd2355dc29f92909"),
    # Switched on: "Switch on all six (Recommended)" (2026-10-17 21:03 ET, ticket 79).
    (without_nport_switch_on, "d11d8361d90eb9e03c83272e135c9a9179f21bcd7310b7cfd0fbed8174024b31"),
    # Deleted: "Delete both (Recommended)" (2026-10-17, ticket 09).
    (without_p2_p3_deleted, "6276a992486dda4bae01330580763ceb707bb8896bb0e45288ab3194c641439c"),
    # Switched on: "Switch on all three (Recommended)" (2026-10-17 08:31 ET).
    (without_adv_switch_on, "a5e9b1133ec597add432e3d3d0fbea1886f9f3baa4424c6c063f02824cc8dba8"),
    # Not yet approved: the operator approves its digest with the proof.
    (without_custodian, "bd71d9ad021660644ae3a14185c3ceea4923fd175cf94b23a1e3c187bce09f3c"),
    (without_issuer_lei, "7dc2e9f1cf68ae76fbf151b617997f2f8478be3092931d5e943ddb9cb3b4c5e5"),
    (without_nport_registrant, "c69bd4a452fc3b5e9a7b722b876d04f7b7a33891fddf6509a57c968c8ef481b0"),
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
