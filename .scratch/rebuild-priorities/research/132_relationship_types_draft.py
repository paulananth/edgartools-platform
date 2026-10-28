"""Ticket 132: draft, approve and publish RDM code set `mdm-relationship-types`
version 1 from `rules/merge/relationships.yaml` (relationship-types-v6) and the
types' plain words in `rules/context/definitions.yaml`, both as they stood at
commit BASE (this ticket removed them), on a disposable PostgreSQL 16 (the
shared server is untouched). Each type is a code whose properties are its rules
and whose definition is its plain words and its source; each capacity a child
code `TYPE:capacity`.

Run from the repo root: uv run --no-sync python .scratch/rebuild-priorities/research/132_relationship_types_draft.py
"""
import subprocess
from pathlib import Path

import yaml

from edgar_warehouse.rdm.database import migrate
from edgar_warehouse.rdm.store import RDM
from tests.integration.test_rdm_postgres import server

BASE = "0a1470c1ae93"  # origin/main when ticket 132 began
SOURCE = "rules/merge/relationships.yaml"
WORDS = "rules/context/definitions.yaml"
OUT = Path("rules/reference/published")
# Each group's source or standard, as the YAML's comments name it.
DEFINITIONS = {
    ("IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"):
        "Consolidation: GLEIF's relationship file names; IFRS 10 / ASC 810.",
    ("SUCCESSOR_ENTITY",): "Corporate actions: GLEIF's SuccessorEntity.",
    ("IS_SUBSIDIARY_OF", "BENEFICIAL_OWNER_OF"): "Ownership: Exhibit 21; Schedules 13D/13G and Forms 3/4/5.",
    ("EMPLOYED_BY",): "People: Forms 3/4/5 role flags.",
    ("ISSUED_BY",): "Securities: a Security and its issuer. A holding is not a relationship MDM masters; "
                    "it lands in silver with the MDM ids of its holder and its Security.",
    ("CUSTODIAN",): "Custody: Form ADV Schedule D 5.K(3).",
    ("INVESTMENT_ADVISER_TO", "IS_FUND-MANAGED_BY", "IS_SUBFUND_OF", "IS_FEEDER_TO"):
        "Funds: Form ADV and N-CEN; GLEIF's relationship file names.",
    ("IS_INTERNATIONAL_BRANCH_OF",): "Branches: GLEIF.",
    ("AUDITED_BY",): "Audit: the XBRL cover page; the audit report.",
    ("HAS_MARKET_OPERATOR", "IS_SEGMENT_OF_EXCHANGE"): "Trading venues: ISO 10383; MiFID II's market operator.",
}


def words(name: str) -> str:
    text = name.replace("_", " ").lower()
    return text[0].upper() + text[1:]


def at_base(path: str) -> dict:
    return yaml.safe_load(subprocess.run(["git", "show", f"{BASE}:{path}"], check=True, capture_output=True,
                                         text=True).stdout)


def codes(section: dict, plain: dict) -> list[dict]:
    defined = {name: text for names, text in DEFINITIONS.items() for name in names}
    rows = []
    for name, spec in section["types"].items():
        properties = {k: v for k, v in spec.items() if k != "capacities"}
        rows.append({"code": name, "label": words(name), "definition": f"{plain[name]} Source: {defined[name]}",
                     "properties": properties})
        rows += [{"code": f"{name}:{capacity}", "label": words(capacity), "parent_code": name}
                 for capacity in spec.get("capacities", [])]
    return rows


def main() -> None:
    section = at_base(SOURCE)
    plain = at_base(WORDS)["relationships"]
    assert section["version"] == "relationship-types-v6" and set(plain) == set(section["types"])
    with server() as engine:
        migrate(engine("rdm"), runtime_role="rdm_runtime")
        rdm = RDM(engine("rdm", "rdm_runtime"))
        rdm.draft({"code_set": "mdm-relationship-types", "name": "MDM relationship types",
                   "definition": "The relationship types MDM masters, each with the rules it runs by; "
                                 "its capacities are its child codes.",
                   "authority": "internal", "steward": "operator"},
                  "1", codes(section, plain), created_by="claude (ticket 132)",
                  evidence={"from": [f"{BASE}:{SOURCE}", f"{BASE}:{WORDS}"], "version": section["version"], "types": len(section["types"])},
                  levels=[{"depth": 1, "name": "Relationship type"}, {"depth": 2, "name": "Capacity"}],
                  usage=[{"store": "mdm", "object": "relationship", "field": "type"}],
                  hints=[{"kind": "meaning", "text": "A type's properties: from and to (the kinds at each end), "
                          "from_profile and to_profile, hierarchy, cycles, one_parent, ultimate_parent and "
                          "ultimate_type, keeps_start, ends_parent_links."}])
        rdm.approve("mdm-relationship-types", "1", by="operator",
                    words="Use RDM for keeping types and other information; Add code properties to RDM (Recommended)")
        published = rdm.publish("mdm-relationship-types", "1", out=OUT)
    for extra in (OUT / "mdm-relationship-types" / "1").glob("rdm_*.jsonl"):
        extra.unlink()  # the published folder keeps canonical.jsonl and pin.json, as every code set does
    print(published)


if __name__ == "__main__":
    main()
