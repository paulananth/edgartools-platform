"""Step 6 of mastering, on each engine under the real rules, with invented records: every bind and creation is recorded
as a decision (the rule and its version, the policy, the source record used and the golden record), so a golden record
and each value it shows can be explained from its source records."""

import json

from edgar_warehouse.mastering import merge
from edgar_warehouse.mdm import adapters
from edgar_warehouse.mdm.evidence import assertion
from tests.storage_adapters.test_mastering import COMPANY, SECURITY, gleif_record, live, opened, sec_holder

FORM4 = "sec.ownership.security.v2"


def binds(db):
    return [json.loads(b) for (b,) in db.rows("select body from mastering_decision where operation='bind'")]


def form4(key, issuer="1234567", symbol="EXZ"):
    return assertion(source_code=FORM4, record_key=key, publication_key="invented", revision=1, effective_at=None,
                     kind="security", fields={"name_of_issuer": "Example Corp"},
                     cross_references={"ticker": symbol, "issuer_symbol_id": adapters._issuer_symbol_id(
                         {"issuer_cik": issuer, "symbol": symbol})})


def test_every_bind_by_an_identifier_rule_or_a_name_rule_is_recorded_with_what_it_used(database_factory):
    with opened(database_factory) as db:
        holder, candidate = sec_holder(), gleif_record()
        merge.merge_file(db, COMPANY, [holder, candidate])
        (golden_id, golden), = live(db).items()
        made = {d["subject"]: d for d in binds(db)}
        assert set(made) == {holder["subject"], candidate["subject"]}  # one decision per record bound
        assert made[holder["subject"]]["rule_id"] == "company-cik"  # an identifier rule
        assert made[candidate["subject"]]["rule_id"].startswith("sec-gleif-name")  # a name rule
        for record_, decision in ((holder, made[holder["subject"]]), (candidate, made[candidate["subject"]])):
            assert decision["entity_id"] == golden_id and decision["evidence"] == [record_["assertion_id"]]
            assert decision["rule_version"] and decision["policy_digest"] == "invented-digest"
        # The golden record is explained by its decisions: its source records are exactly the subjects bound to it.
        assert sorted(golden["subjects"]) == sorted(s for s, d in made.items() if d["entity_id"] == golden_id)


def test_a_creation_by_a_name_rule_is_recorded_and_a_replay_writes_nothing_twice(database_factory):
    with opened(database_factory) as db:
        first, second = form4("one"), form4("two")  # the same issuer and symbol: one Security is created, the second joins
        merge.merge_file(db, SECURITY, [first, second])
        (golden_id, _), = live(db).items()
        made = binds(db)
        assert {d["subject"] for d in made} == {first["subject"], second["subject"]}
        assert {d["rule_id"] for d in made} == {"form4-security-issuer-symbol"} and {d["entity_id"] for d in made} == {golden_id}
        merge.merge_file(db, SECURITY, [first, second], again=True)
        assert len(binds(db)) == 2


def test_a_surviving_value_traces_to_the_source_record_that_supplied_it(database_factory):
    with opened(database_factory) as db:
        holder, candidate = sec_holder(), gleif_record()
        merge.merge_file(db, COMPANY, [holder, candidate])
        (golden_id, golden), = live(db).items()
        winner = golden["fields"]["name"]["winner"]
        used = {a for d in binds(db) if d["entity_id"] == golden_id for a in d["evidence"]}
        assert winner["assertion_id"] in used  # a decision of this golden record names the record the value came from
        assert (winner["source_code"], winner["record_key"]) == ("sec.company.v1", holder["record_key"])
