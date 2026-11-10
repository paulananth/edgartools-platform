"""Step 2 of mastering: what a record mentions is a relationship, resolved when both golden records exist.

For each relationship kind that links two sources' records (a start date, or a Person's capacity), on invented records under the real
rules (PostgreSQL 16): a record that mentions a party no golden record exists for makes its own golden record and no
other, so the mentioned party is never created from the mention and no link exists; when the mentioned party's own
record is mastered, the link resolves and the golden records are still two, each of its own entity type.
"""

import pytest

from edgar_warehouse.mdm.evidence import subject_key
from tests.integration import test_mdm_postgres as core
from tests.mdm import policy_layers
from edgar_warehouse.rules import files
from tests.support import masters

AT = "2026-06-01T00:00:00+00:00"
# (relationship type, source code, source kind, source identifiers, target code, target kind, target identifiers, target key)
CASES = [
    ("CUSTODIAN", "iapd.adv.filings.v2", "company", {"cik": "0000999001", "crd": "999001"},
     "iapd.adv.custodians.v1", "company", {"bd_number": "8-99901"}, "bd:8-99901"),
    ("RELATED_PERSON", "iapd.adv.filings.v2", "company", {"cik": "0000999002", "crd": "999002"},
     "sec.company.v1", "company", {"cik": "0000999003"}, "0000999003"),
    ("IS_SUBFUND_OF", "sec.nport.fund.v1", "fund_structure", {"sec_series_id": "S999000001"},
     "sec.nport.registrant.v2", "company", {"cik": "0000999004"}, "0000999004"),
]


def record(code, kind, key, identifiers, name, relationships=()):
    # A fund link needs the fund role on both ends, as the N-PORT contracts declare it.
    fund = [{"role": "fund", "authority": "SEC EDGAR", "registration": key, "jurisdiction": None, "valid_from": AT,
             "valid_to": None, "fields": {}}] if code.startswith("sec.nport") else []
    return core.source(key=key, source_code=code, kind=kind, fields={"name": name}, identifiers=identifiers,
                       relationships=list(relationships), profiles=fund)


CAPACITIES = [
    ("EMPLOYED_BY", "sec.ownership.reporting_owner.v1", "person", {"cik": "0000999005"},
     "sec.company.v1", "company", {"cik": "0000999006"}, "0000999006", "officer"),
    ("BENEFICIAL_OWNER_OF", "sec.ownership.reporting_owner.v1", "person", {"cik": "0000999007"},
     "sec.company.v1", "company", {"cik": "0000999008"}, "0000999008", "ten_percent_owner"),
]


@pytest.mark.parametrize("relationship,source,source_kind,source_ids,target,target_kind,target_ids,target_key,capacity",
                         [(*c, "") for c in CASES] + CAPACITIES, ids=[c[0] for c in CASES + CAPACITIES])
def test_a_mentioned_party_is_a_relationship_until_its_own_record_is_mastered(
        database, relationship, source, source_kind, source_ids, target, target_kind, target_ids, target_key, capacity):
    mention = {"type": relationship, "target_subject": subject_key(target, target_key), "scope": "", "valid_to": None,
               "properties": {}, "valid_from": AT, "valid_from_basis": "observed"}
    if capacity:  # a Person's link is a dated sighting of the capacity held (relationships.fold_sightings)
        mention |= {"capacity": capacity, "on": AT, "held": True, "title": None}
    masters.seed(database.application, [record(source, source_kind, "own-1", source_ids, "Example Source", [mention])])
    assert {b["kind"] for b in masters.bodies(database.application).values()} == {source_kind}  # only its own
    assert len(masters.bodies(database.application)) == 1  # the mentioned party was not created
    assert masters.links(database.application, of_type=relationship) == []  # and nothing links yet
    masters.seed(database.application, [record(target, target_kind, target_key, target_ids, "Example Target")])
    assert sorted(b["kind"] for b in masters.bodies(database.application).values()) == sorted([source_kind, target_kind])
    (link,) = masters.links(database.application, of_type=relationship)
    assert link["source_id"] != link["target_id"]


GLEIF = "gleif.level1.v1"
LEI_A, LEI_B = "9999000000EXAMPLE016", "9999000000EXAMPLE024"  # invented
GLEIF_TARGETS = [
    # (relationship type, the source record's code, kind and identifiers; the mentioned LEI is LEI_B's GLEIF record)
    ("SUCCESSOR_ENTITY", GLEIF, "company", {"lei": LEI_A}),
    ("IS_DIRECTLY_CONSOLIDATED_BY", GLEIF, "company", {"lei": LEI_A}),
    ("IS_ULTIMATELY_CONSOLIDATED_BY", GLEIF, "company", {"lei": LEI_A}),
    ("ISSUED_BY", "sec.nport.security.v2", "security", {"cusip": "ZZ0000013"}),
]


def policy():
    """The LEI rule for GLEIF records is declared and not switched on in the repo policy (ticket 203), so it is on in a copy."""
    return policy_layers.with_rules_on(files.policy(), "company", "gleif-issuer-lei")


def gleif(lei, relationships=()):
    return core.source(key=lei, source_code=GLEIF, kind="company", fields={"name": "Example Target"},
                       identifiers={"lei": lei}, relationships=list(relationships),
                       provenance={"matching": {"nport_issuer": ["held"]}})


def company_with_lei(lei):
    """The Company a GLEIF record attaches to: GLEIF never creates one, so another source's record holds the LEI."""
    return record("iapd.adv.custodians.v1", "company", f"lei:{lei}", {"lei": lei}, "Example Company")


@pytest.mark.parametrize("relationship,source,source_kind,source_ids", GLEIF_TARGETS, ids=[c[0] for c in GLEIF_TARGETS])
def test_a_relationship_to_a_gleif_record_resolves_once_a_company_holds_its_lei(
        database, relationship, source, source_kind, source_ids):
    """A relationship to a GLEIF record resolves once a Company holds its LEI; the mention creates no Company."""
    mention = {"type": relationship, "target_subject": subject_key(GLEIF, LEI_B), "scope": "", "valid_to": None,
               "properties": {}, "valid_from": AT, "valid_from_basis": "observed"}
    own = [record(source, source_kind, "own-1", source_ids, "Example Source", [mention])]
    if source == GLEIF:  # the mentioning GLEIF record attaches to the Company holding its LEI
        own = [company_with_lei(LEI_A), gleif(LEI_A, [mention])]
    masters.seed(database.application, own, policy())
    before = len(masters.bodies(database.application))
    assert before == 1  # its own golden record only: the mentioned LEI's party was not created
    assert masters.links(database.application, policy(), of_type=relationship) == []
    masters.seed(database.application, [company_with_lei(LEI_B), gleif(LEI_B)], policy())
    assert len(masters.bodies(database.application)) == 2  # the target Company exists once; GLEIF's record joined it
    (link,) = masters.links(database.application, policy(), of_type=relationship)
    assert link["source_id"] != link["target_id"]
