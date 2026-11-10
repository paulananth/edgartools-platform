"""Step 2 of mastering: each source record has one entity type and joins only golden records of that type (invented records)."""

from tests.storage_adapters.test_mastering import (
    COMPANY, FUND, PERSON, PERSON_SOURCE, SEC, FUND_SOURCE, live, opened, record, merge)


def test_an_individual_with_the_cik_of_a_company_gets_its_own_person_golden_record(database_factory):
    with opened(database_factory) as db:
        company = record(SEC, "c1", "company", {"name": "INVENTED CO"}, cik="0000000501")
        merge.merge_file(db, COMPANY, [company])
        person = record(PERSON_SOURCE, "p1", "person", {"name": "INVENTED PERSON"}, cik="0000000501")
        merge.merge_file(db, PERSON, [person])
        bound = db.bound([company["subject"], person["subject"]])
        kinds = {s: live(db)[e]["kind"] for s, e in bound.items()}
        assert kinds == {company["subject"]: "company", person["subject"]: "person"}
        assert bound[company["subject"]] != bound[person["subject"]]


def test_a_fund_series_never_joins_a_company_or_person(database_factory):
    with opened(database_factory) as db:
        company = record(SEC, "c2", "company", {"name": "INVENTED CO TWO"}, cik="0000000502")
        fund = record(FUND_SOURCE, "f2", "fund_structure", {"name": "INVENTED FUND"}, sec_series_id="S000000502")
        merge.merge_file(db, COMPANY, [company])
        merge.merge_file(db, FUND, [fund])
        bound = db.bound([company["subject"], fund["subject"]])
        assert {live(db)[e]["kind"] for e in bound.values()} == {"company", "fund_structure"}
