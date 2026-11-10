"""Step 2 of mastering: what a record mentions is a relationship, resolved when both golden records exist.

For each relationship kind that links two sources' records and states a start date, on invented records under the real
rules (PostgreSQL 16): a record that mentions a party no golden record exists for makes its own golden record and no
other, so the mentioned party is never created from the mention and no link exists; when the mentioned party's own
record is mastered, the link resolves and the golden records are still two, each of its own entity type.
"""

import pytest

from edgar_warehouse.mdm.evidence import subject_key
from tests.integration import test_mdm_postgres as core
from tests.support import masters

AT = "2026-06-01T00:00:00+00:00"
# (relationship type, source code, source kind, source identifiers, target code, target kind, target identifiers, target key)
CASES = [
    ("CUSTODIAN", "iapd.adv.filings.v2", "company", {"cik": "0000999001", "crd": "999001"},
     "iapd.adv.custodians.v1", "company", {"bd_number": "8-99901"}, "bd:8-99901"),
    ("RELATED_PERSON", "iapd.adv.filings.v2", "company", {"cik": "0000999002", "crd": "999002"},
     "sec.company.v1", "company", {"cik": "0000999003"}, "0000999003"),
    ("IS_SUBFUND_OF", "sec.nport.fund.v1", "fund_structure", {"sec_series_id": "S999000001"},
     "sec.nport.registrant.v1", "company", {"cik": "0000999004"}, "0000999004"),
]


def record(code, kind, key, identifiers, name, relationships=()):
    # A fund link needs the fund role on both ends, as the N-PORT contracts declare it.
    fund = [{"role": "fund", "authority": "SEC EDGAR", "registration": key, "jurisdiction": None, "valid_from": AT,
             "valid_to": None, "fields": {}}] if code.startswith("sec.nport") else []
    return core.source(key=key, source_code=code, kind=kind, fields={"name": name}, identifiers=identifiers,
                       relationships=list(relationships), profiles=fund)


@pytest.mark.parametrize("relationship,source,source_kind,source_ids,target,target_kind,target_ids,target_key", CASES,
                         ids=[c[0] for c in CASES])
def test_a_mentioned_party_is_a_relationship_until_its_own_record_is_mastered(
        database, relationship, source, source_kind, source_ids, target, target_kind, target_ids, target_key):
    mention = {"type": relationship, "target_subject": subject_key(target, target_key), "scope": "", "valid_to": None,
               "properties": {}, "valid_from": AT, "valid_from_basis": "observed"}
    masters.seed(database.application, [record(source, source_kind, "own-1", source_ids, "Example Source", [mention])])
    assert {b["kind"] for b in masters.bodies(database.application).values()} == {source_kind}  # only its own
    assert len(masters.bodies(database.application)) == 1  # the mentioned party was not created
    assert masters.links(database.application, of_type=relationship) == []  # and nothing links yet
    masters.seed(database.application, [record(target, target_kind, target_key, target_ids, "Example Target")])
    assert sorted(b["kind"] for b in masters.bodies(database.application).values()) == sorted([source_kind, target_kind])
    (link,) = masters.links(database.application, of_type=relationship)
    assert link["source_id"] != link["target_id"]
