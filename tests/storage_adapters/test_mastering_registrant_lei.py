"""An N-PORT registrant's LEI is searched like any identifier (step 3), on each engine under the real rules. Invented records."""

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import COMPANY, live, opened, record

CUSTODIANS, REGISTRANT = "iapd.adv.custodians.v1", "sec.nport.registrant.v2"
LEI = "9999000000EXAMPLE016"  # invented; the check digits are valid
OTHER = "9999000000EXAMPLE105"


def registrant(key, **identifiers):
    return record(REGISTRANT, key, "company", **identifiers)


def test_a_registrant_joins_the_company_that_holds_its_lei(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(CUSTODIANS, f"lei:{LEI}", "company", lei=LEI)])
        (held, _), = live(db).items()
        stated = registrant("0000999201", cik="0000999201", lei=LEI)
        merge.merge_file(db, COMPANY, [stated])
        assert list(live(db)) == [held]  # no second Company
        assert db.bound([stated["subject"]])[stated["subject"]] == held
        assert set(live(db)[held]["identifiers"]["cik"]) == {"0000999201"}


def test_a_registrant_with_a_lei_no_company_holds_creates_one_with_both_identifiers(database_factory):
    with opened(database_factory) as db:
        stated = registrant("0000999202", cik="0000999202", lei=OTHER)
        merge.merge_file(db, COMPANY, [stated])
        (created, body), = live(db).items()
        assert set(body["identifiers"]["lei"]) == {OTHER} and set(body["identifiers"]["cik"]) == {"0000999202"}


def test_two_companies_holding_the_lei_send_the_registrant_to_review(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(CUSTODIANS, f"lei:{LEI}", "company", lei=LEI),
                                       record(REGISTRANT, "0000999203", "company", cik="0000999203")])
        assert len(live(db)) == 2
        both = registrant("0000999203x", cik="0000999203", lei=LEI)
        counts = merge.merge_file(db, COMPANY, [both])
        assert counts["conflicting_identifiers"] == 1 and len(live(db)) == 2
