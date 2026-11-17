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


def test_a_registrant_whose_lei_finds_a_company_holding_another_cik_creates_its_own(database_factory):
    """A sponsor's LEI filed by several trusts: the LEI finds a Company only where it holds no other CIK."""
    with opened(database_factory) as db:
        first = registrant("0000999204", cik="0000999204", lei=LEI)
        merge.merge_file(db, COMPANY, [first])
        (held, _), = live(db).items()
        second = registrant("0000999205", cik="0000999205", lei=LEI)
        merge.merge_file(db, COMPANY, [second])
        companies = live(db)
        assert len(companies) == 2
        assert set(companies[held]["identifiers"]["cik"]) == {"0000999204"}
        (created,) = set(companies) - {held}
        assert set(companies[created]["identifiers"]["cik"]) == {"0000999205"}
        assert db.bound([second["subject"]])[second["subject"]] == created
        assert set(companies[held]["identifiers"]["lei"]) == {LEI}
        assert not companies[created]["identifiers"].get("lei")  # one Company holds the LEI
        gleif = record("gleif.level1.v1", LEI, "company", lei=LEI)
        merge.merge_file(db, COMPANY, [gleif])
        assert db.bound([gleif["subject"]])[gleif["subject"]] == held  # the LEI still finds one Company


def test_two_registrants_of_one_file_sharing_a_lei_stay_two_companies(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [registrant("0000999206", cik="0000999206", lei=LEI),
                                       registrant("0000999207", cik="0000999207", lei=LEI)])
        assert sorted(sorted(body["identifiers"]["cik"]) for body in live(db).values()) == [["0000999206"], ["0000999207"]]
        assert sum(bool(body["identifiers"].get("lei")) for body in live(db).values()) == 1


def test_a_record_stating_no_cik_joins_the_company_its_lei_finds_whatever_cik_it_holds(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [registrant("0000999208", cik="0000999208", lei=LEI)])
        (held, _), = live(db).items()
        gleif = record("gleif.level1.v1", LEI, "company", lei=LEI)
        merge.merge_file(db, COMPANY, [gleif])
        assert list(live(db)) == [held] and db.bound([gleif["subject"]])[gleif["subject"]] == held
