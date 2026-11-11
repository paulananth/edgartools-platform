"""Step 6 of mastering, on each engine under the real rules, with invented records: every judgement is recorded as a
decision (the rule and its version, the policy, the source record used and the golden record): a name match, a creation
by an exact name, a merge, a steward's resolution. A join by an identifier is no judgement and writes none (operator,
2026-11-10); the record's `bound_id` and the golden record's winners explain it."""

import json

from edgar_warehouse.mastering import merge
from edgar_warehouse.mdm import adapters
from edgar_warehouse.mdm.evidence import assertion
from tests.storage_adapters.test_mastering import SEC, SECURITY, joined, live, opened

FORM4 = "sec.ownership.security.v2"


def binds(db):
    return [json.loads(b) for (b,) in db.rows("select body from mastering_decision where operation='bind'")]


def form4(key, issuer="1234567", symbol="EXZ"):
    return assertion(source_code=FORM4, record_key=key, publication_key="invented", revision=1, effective_at=None,
                     kind="security", fields={"name_of_issuer": "Example Corp"},
                     cross_references={"ticker": symbol, "issuer_symbol_id": adapters._issuer_symbol_id(
                         {"issuer_cik": issuer, "symbol": symbol})})


def test_a_name_match_is_recorded_with_what_it_used_and_an_identifier_join_is_not(database_factory):
    with opened(database_factory) as db:
        holder, candidate = joined(db)
        (golden_id, golden), = live(db).items()
        (decision,) = binds(db)  # the name rule's, and only it: the CIK rule's join writes none
        assert decision["subject"] == candidate["subject"] and decision["rule_id"].startswith("sec-gleif-name")
        assert decision["entity_id"] == golden_id and decision["evidence"] == [candidate["assertion_id"]]
        assert decision["rule_version"] and decision["policy_digest"] == "invented-digest"
        # Both records are on the golden record all the same: where each went is its own `bound_id`.
        assert sorted(golden["subjects"]) == sorted([holder["subject"], candidate["subject"]])


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
        holder, candidate = joined(db)
        (golden_id, golden), = live(db).items()
        winner = golden["fields"]["name"]["winner"]
        assert winner["assertion_id"] == holder["assertion_id"]
        assert (winner["source_code"], winner["record_key"]) == ("sec.company.v1", holder["record_key"])


def test_every_bound_record_is_explained_and_one_moved_by_hand_is_not(database_factory):
    from edgar_warehouse.mastering import reads

    with opened(database_factory) as db:
        joined(db)  # a creation, and a name match with its decision
        merge.merge_file(db, SECURITY, [form4("one"), form4("two")])  # a creation, and a join by the same name rule
        found = reads.explained(db)

        assert found["unexplained"] == 0 and found["unexplained_by_source"] == {}
        assert found["records_bound"] == found["by_decision"] + found["created"] + found["by_identifier"] == 4

        # A record moved by hand to another golden record, with no decision and no identifier in common, is unexplained.
        stray = next(s for (s,) in db.rows("select subject from mastering_record where source_code=%s", [SEC]))
        other = next(e for (e,) in db.rows("select distinct entity_id from mastering_record where source_code=%s", [FORM4]))
        db.cursor.execute("update mastering_record set entity_id=%s where subject=%s", [other, stray])
        db.commit()
        moved = reads.explained(db)

        assert moved["unexplained"] >= 1 and SEC in moved["unexplained_by_source"]


def test_a_file_of_only_set_aside_records_is_merged_with_nothing_released(database_factory):
    """A bundle whose every document is set aside (not a listed operating company) has no kind: the merge records the
    set-aside records and the file is done. It raised KeyError('') on the empty kind (hosted SEC company load)."""
    from edgar_warehouse.mastering import merge as merge_module
    from tests.storage_adapters.test_mastering import AS_OF, POLICY, SEC

    aside = {"deferred_id": "d1", "source_code": SEC, "reason": "not_listed_operating", "record_locator": "x:1"}
    with opened(database_factory) as db:
        done = merge_module.merge_file(db, merge_module.Settings(POLICY, "invented-digest", "", AS_OF), [],
                                       deferred=[aside], quiet={})

        assert done["skipped"] is False and done["released"] == 0 and done["records"] == 0
        assert db.rows("select count(*) from mastering_deferred") == [(1,)]


def test_the_lei_scope_is_every_lei_the_store_holds_or_a_pair_names(database_factory, tmp_path):
    import json

    from edgar_warehouse.rules import derivations

    with opened(database_factory) as db:
        joined(db)  # a company, a GLEIF record with a LEI, and the waterfall pair of the company's name
        path, count = derivations.derive("lei_scope", "approved_scope", folder=tmp_path, store=db)

        scope = json.loads(path.read_text())
        assert count == len(scope) >= 1 and all(value == {"selected": True} for value in scope.values())
        (pair,) = [v for (v,) in db.rows("select distinct value from mastering_name_key where role='cascade'")]
        held = {v for (v,) in db.rows("select distinct lei from mastering_record where lei is not null")}
        assert pair in scope and held <= set(scope)
