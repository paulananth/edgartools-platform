"""Mastering on each engine, under the real rules, with invented records."""

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier

import pytest

from edgar_warehouse.mastering import links, lookups, merge, reads, store as stores
from edgar_warehouse.mdm.evidence import assertion, decision, subject_key
from edgar_warehouse.rules import files
from edgar_warehouse.mastering.store import open_store
from tests.support.masters import figi
from tests.support.patching import checked

AS_OF = "2026-11-06T12:00:00+00:00"
POLICY = files.policy()
COMPANY = merge.Settings(POLICY, "invented-digest", "company", AS_OF)
SECURITY = merge.Settings(POLICY, "invented-digest", "security", AS_OF)
SEC, FIGI, GLEIF = "sec.company.v1", "openfigi.security.v4", "gleif.level1.v1"
NPORT = next(r for r in POLICY["kinds"]["security"]["rules"] if r["rule_id"] == "nport-security-cusip")["source"]


def record(source, key, kind="company", fields=None, **identifiers):
    return assertion(source_code=source, record_key=key, publication_key="invented", revision=1, effective_at=None,
                     kind=kind, fields=fields or {"name": f"INVENTED {key}"}, identifiers=identifiers)


@contextmanager
def opened(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        db = open_store(runtime)
        try:
            yield db
        finally:
            db.rollback()
            db.close()


def masters(db):
    db.commit()
    return db.master_bodies([e for (e,) in db.rows("select entity_id from mastering_master")])


def live(db):
    return {e: b for e, b in masters(db).items() if b.get("status") != "alias"}


def test_records_join_or_create_a_master_and_a_later_file_reuses_the_id(database_factory):
    with opened(database_factory) as db:
        one, two, other = record(SEC, "1", cik="0000000017"), record(SEC, "1b", cik="0000000017"), record(SEC, "2", cik="0000000018")
        merge.merge_file(db, COMPANY, [one, two, other])
        found = live(db)
        assert sorted(len(b["subjects"]) for b in found.values()) == [1, 2]
        later = record(SEC, "3", cik="0000000018")
        merge.merge_file(db, COMPANY, [later])
        assert set(live(db)) == set(found)
        assert db.bound([later["subject"]])[later["subject"]] == db.bound([other["subject"]])[other["subject"]]


def test_a_cik_is_stored_as_the_source_gave_it(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(SEC, "0000000017", cik="0000000017")])
        assert db.rows("select value from mastering_identifier where namespace='cik'") == [("0000000017",)]
        merge.merge_file(db, COMPANY, [record(SEC, "0000000017", cik="0000000017")], again=True)
        assert len(live(db)) == 1


def test_identical_records_again_change_no_master(database_factory):
    with opened(database_factory) as db:
        batch = [record(SEC, "1", cik="0000000017")]
        merge.merge_file(db, COMPANY, batch)
        before = masters(db)
        assert merge.merge_file(db, COMPANY, batch)["skipped"]
        checkpoint = db.last_file()
        merge.merge_file(db, COMPANY, batch, again=True)
        assert masters(db) == before
        assert db.changes(checkpoint) == []


def test_every_identifier_a_master_holds_can_be_found_and_two_masters_may_hold_one(database_factory):
    """A SEDOL or a ticker no rule keys on is still held; merging two masters holding one value keeps it once."""
    with opened(database_factory) as db:
        a, b = figi("00TSTX03"), figi("00TSTX04")
        merge.merge_file(db, SECURITY, [record(FIGI, "a", "security", figi=a, ticker="EXA", sedol="B000009")])
        merge.merge_file(db, SECURITY, [record(FIGI, "b", "security", figi=b, ticker="EXA")])
        assert len(db.identifier_holders("ticker", ["EXA"])) == 2
        assert len(db.identifier_holders("sedol", ["B000009"])) == 1
        merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        assert len(live(db)) == 1
        assert db.identifier_holders("ticker", ["EXA"]) == list(live(db))


def test_an_identifier_reaching_two_masters_merges_them_and_a_split_returns_them(database_factory):
    with opened(database_factory) as db:
        a, b = figi("00TSTX01"), figi("00TSTX02")
        first, second = record(FIGI, "a", "security", figi=a), record(FIGI, "b", "security", figi=b)
        merge.merge_file(db, SECURITY, [first])
        merge.merge_file(db, SECURITY, [second])
        assert len(live(db)) == 2
        merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        assert len(live(db)) == 1
        assert sum(m.get("status") == "alias" for m in masters(db).values()) == 1
        (merge_id, keep, gone), = db.merges()
        db.split(keep, gone)
        db.add_decision(decision("reverse", actor="fixture", reason="invented", at=AS_OF, target=merge_id), keep, gone)
        db.add_identifiers([("figi", a if db.bound([first["subject"]])[first["subject"]] == gone else b, gone)])
        db.commit()
        merge.merge_file(db, SECURITY, [first, second], again=True)
        assert len(live(db)) == 2


def test_a_conflict_a_first_rule_settles_withholds_the_other_value(database_factory):
    with opened(database_factory) as db:
        cusip, isin = "INV000017", "XX0000000018"
        merge.merge_file(db, SECURITY, [record(NPORT, "a", "security", cusip=cusip), record(NPORT, "b", "security", isin=isin)])
        both = record(NPORT, "c", "security", cusip=cusip, isin=isin)
        merge.merge_file(db, SECURITY, [both])
        found = live(db)
        assert len(found) == 2
        holder = found[db.bound([both["subject"]])[both["subject"]]]
        assert "isin" not in holder["identifiers"]
        assert db.withheld([both["subject"]]) == {both["subject"]: [{"namespace": "isin", "raw": isin}]}


def test_a_failed_file_leaves_nothing_and_runs_again(database_factory, monkeypatch):
    with opened(database_factory) as db:
        batch = [record(SEC, "1", cik="0000000017")]
        checked(monkeypatch, merge, "_write_masters", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("invented failure")))
        with pytest.raises(RuntimeError):
            merge.merge_file(db, COMPANY, batch)
        monkeypatch.undo()
        assert masters(db) == {} and not db.file_done(merge.file_key(batch))
        assert not merge.merge_file(db, COMPANY, batch)["skipped"]
        assert len(live(db)) == 1


def test_a_record_with_no_match_waits_as_an_open_review(database_factory):
    with opened(database_factory) as db:
        waiting = record("iapd.adv.filings.v2", "ADV000017", cik="0000000017")  # a rule that waits, not creates
        merge.merge_file(db, COMPANY, [waiting])
        assert masters(db) == {}
        assert db.rows("select reason,open_review from mastering_review where subject=%s", [waiting["subject"]]) == [("binding_required", 1)]


def test_a_gleif_record_creates_its_company_or_joins_the_one_holding_its_lei(database_factory):
    """GLEIF finds a Company by its LEI and creates one when none holds it (operator, 2026-11-16: "GLEIF can create
    company no new code only config"): a second delivery of the same LEI joins it, and a Company an N-PORT registrant
    created for the LEI is joined, never doubled."""
    with opened(database_factory) as db:
        created = record(GLEIF, "INVENTEDLEI000000017", lei="INVENTEDLEI000000017")
        merge.merge_file(db, COMPANY, [created])
        (only,) = live(db)
        assert db.bound([created["subject"]]) == {created["subject"]: only}
        assert db.rows("select count(*) from mastering_review where subject=%s and open_review=1",
                       [created["subject"]]) == [(0,)]
        registrant = record("sec.nport.registrant.v2", "0000000099", lei="INVENTEDLEI000000099", cik="0000000099")
        gleif = record(GLEIF, "INVENTEDLEI000000099", lei="INVENTEDLEI000000099")
        merge.merge_file(db, COMPANY, [registrant])
        merge.merge_file(db, COMPANY, [gleif])
        assert len(live(db)) == 2
        assert db.bound([gleif["subject"]])[gleif["subject"]] == db.bound([registrant["subject"]])[registrant["subject"]]


def test_a_steward_override_changes_one_field_and_a_revoke_returns_it(database_factory):
    with opened(database_factory) as db:
        one = record(SEC, "1", cik="0000000017")
        merge.merge_file(db, COMPANY, [one])
        before = next(iter(live(db).values()))["fields"]["name"]["value"]
        held = decision("override", actor="fixture", reason="invented", at=AS_OF, subject=one["subject"],
                        field="name", value="INVENTED STEWARD", evidence=["invented"])
        db.add_decision(held, one["subject"], None)
        db.commit()
        merge.merge_file(db, COMPANY, [one], again=True)
        assert next(iter(live(db).values()))["fields"]["name"]["value"] == "INVENTED STEWARD"
        db.add_decision(decision("revoke", actor="fixture", reason="invented", at=AS_OF, target=held["decision_id"]), None, held["decision_id"])
        db.commit()
        merge.merge_file(db, COMPANY, [one], again=True)
        assert next(iter(live(db).values()))["fields"]["name"]["value"] == before


def test_a_reader_stays_in_step_by_asking_what_changed(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(SEC, "1", cik="0000000017")])
        copy, checkpoint = {}, 0
        for file_no, entity, body in db.changes(0):
            copy[entity], checkpoint = body, file_no
        merge.merge_file(db, COMPANY, [record(SEC, "2", cik="0000000018")])
        for _, entity, body in db.changes(checkpoint):
            copy[entity] = body
        db.commit()
        assert {entity: json.loads(body) for entity, body in copy.items()} == masters(db)


def test_a_reader_finds_a_master_by_source_key_by_identifier_and_after_a_merge(database_factory):
    with opened(database_factory) as db:
        a, b = figi("00TSTY01"), figi("00TSTY02")
        merge.merge_file(db, COMPANY, [record(SEC, "0000000017", cik="0000000017")])
        merge.merge_file(db, SECURITY, [record(FIGI, "a", "security", figi=a)])
        merge.merge_file(db, SECURITY, [record(FIGI, "b", "security", figi=b)])
        ids = reads.master_ids(db, FIGI, {"a", "b", "never loaded"})
        assert set(ids) == {"a", "b"}
        merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        after = reads.master_ids(db, FIGI, {"a", "b", "c"})
        assert len(set(after.values())) == 1
        kept = after["a"]
        assert {reads.master(db, id_)["entity_id"] for id_ in ids.values()} == {kept}
        with pytest.raises(KeyError):
            reads.master(db, "00000000-0000-0000-0000-000000000000")
        lookups.build(db)
        assert reads.carriers(db, POLICY, "security", "figi", a) == {kept: "identifier"}
        company = reads.master_ids(db, SEC, {"0000000017"})["0000000017"]
        assert reads.carriers(db, POLICY, "company", "cik", "0000000017") == {company: "identifier"}
        assert reads.carriers(db, POLICY, "security", "cik", "0000000017") == {}


def test_lookups_find_names_details_and_cross_references_and_a_rebuild_changes_nothing(database_factory):
    with opened(database_factory) as db:
        one, two, three = figi("00TSTZ01"), figi("00TSTZ02"), figi("00TSTZ03")
        listing = {"key": one, "ticker": "INVT", "mic": "XINV", "exchange": "IV", "description": "INVENTED"}

        def security(key, value, name, **extra):
            return assertion(source_code=FIGI, record_key=key, publication_key="invented", revision=1, effective_at=None,
                             kind="security", fields={"name": name}, identifiers={"figi": value}, **extra)

        merge.merge_file(db, COMPANY, [record(SEC, "1", fields={"name": "INVENTED ANVIL WORKS"}, cik="0000000021"),
                                       record(SEC, "2", fields={"name": "INVENTED BELLOWS"}, cik="0000000022")])
        merge.merge_file(db, SECURITY, [security("a", one, "INVENTED", details={"listings": [listing]}),
                                        security("b", two, "INVENTED", details={"listings": [{**listing, "key": two}]}),
                                        security("c", three, "OTHER", cross_references={"share_class_figi": "BBG000000001"})])
        with pytest.raises(lookups.NotBuilt):
            lookups.search(db, "company", "anvil", 5)
        assert lookups.build(db)["masters"] == 5
        anvil = lookups.search(db, "company", "anvil", 5)
        assert [row["name"] for row in anvil] == ["INVENTED ANVIL WORKS"]
        assert [row["name"] for row in lookups.search(db, "company", "-anvil", 5)] == ["INVENTED BELLOWS"]
        assert lookups.search(db, "person", "anvil", 5) == []
        assert [row["name"] for row in lookups.search(db, "company", "nvil wo", 5)] == ["INVENTED ANVIL WORKS"]
        assert lookups.search(db, "company", "%_", 5) == []
        held = reads.master_ids(db, FIGI, {"a", "b", "c"})
        assert {row["entity_id"] for row in lookups.holders_of_detail(db, "mic", ["XINV", "INVT"])} == {held["a"], held["b"]}
        assert reads.carriers(db, POLICY, None, "share_class_figi", "BBG000000001") == {held["c"]: "cross_reference"}
        rows = sorted(db.rows("select token,entity_id from mastering_lookup"))
        assert lookups.build(db)["masters"] == 0
        assert sorted(db.rows("select token,entity_id from mastering_lookup")) == rows
        merge.merge_file(db, COMPANY, [record(SEC, "3", fields={"name": "INVENTED CRUCIBLE"}, cik="0000000023")])
        with pytest.raises(lookups.NotBuilt):
            lookups.search(db, "company", "anvil", 5)
        assert lookups.build(db)["masters"] == 1
        assert [row["name"] for row in lookups.search(db, "company", "crucible", 5)] == ["INVENTED CRUCIBLE"]


def test_a_merged_away_master_leaves_the_lookups(database_factory):
    with opened(database_factory) as db:
        a, b = figi("00TSTW01"), figi("00TSTW02")
        merge.merge_file(db, SECURITY, [record(FIGI, "a", "security", figi=a)])
        merge.merge_file(db, SECURITY, [record(FIGI, "b", "security", figi=b)])
        lookups.build(db)
        assert len(lookups.search(db, "security", "invented", 5)) == 2
        merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        lookups.build(db)
        assert len(lookups.search(db, "security", "invented", 5)) == 1


def test_the_runtime_login_cannot_erase_a_decision_or_change_a_table(database_factory):
    with opened(database_factory) as db:
        for sql in ("delete from mastering_decision", "update mastering_decision set operation='x'", "drop table mastering_master"):
            with pytest.raises(Exception, match="(?i)denied|owner"):
                db.rows(sql)
            db.rollback()


LEI = "INVENTEDLEI000000017"








def test_install_drops_a_mastering_table_the_code_no_longer_uses(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        with owner.begin() as conn:
            where = "mdm." if owner.dialect.name == "postgresql" else ""  # PostgreSQL: the mastering tables are in the mdm schema
            conn.exec_driver_sql(f"create table {where}mastering_unused(name varchar(16) primary key)")
        stores.install(owner, runtime_role=role)
        with owner.connect() as conn:
            tables = {name for (name,) in conn.exec_driver_sql("select table_name from information_schema.tables")}
        assert "mastering_unused" not in tables
        assert {f"mastering_{name}" for name in (*stores.WRITTEN, "decision")} <= tables


def test_two_writers_on_the_same_identifiers_leave_one_master_each(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        files_of = [[record(SEC, f"{side}{n}", cik=str(n + 1)) for n in range(200)] for side in ("left", "right")]
        files_of[1].reverse()
        start = Barrier(2)

        def write(records):
            db = open_store(runtime)
            try:
                start.wait()
                return merge.merge_file(db, COMPANY, records)
            finally:
                db.close()

        with ThreadPoolExecutor(2) as pool:
            done = list(pool.map(write, files_of))
        assert [item["skipped"] for item in done] == [False, False]
        db = open_store(runtime)
        try:
            assert db.rows("select count(*) from (select namespace,value from mastering_identifier "
                           "group by namespace,value having count(*)>1) doubled")[0][0] == 0
            assert len(live(db)) == 200
            assert all(len(body["subjects"]) == 2 for body in live(db).values())
        finally:
            db.close()


def test_four_writers_creating_the_same_identifiers_at_once_leave_one_master_each(database_factory):
    """Creating needs no lock of the kind (operator, 2026-11-16: "There is no need for lock"): four merges that give the
    same 100 identifiers, in four orders, at once, leave one golden record for each, holding all four records."""
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name != "postgresql":
            pytest.skip("Only PostgreSQL merges one kind beside others")
        stores.install(owner, runtime_role=role)
        files_of = [[record(SEC, f"w{w}-{n}", cik=f"{n + 1:010d}") for n in range(100)] for w in range(4)]
        for w, records in enumerate(files_of):
            records[:] = records[w * 25:] + records[:w * 25]
        start = Barrier(4)

        def write(records):
            db = open_store(runtime)
            try:
                start.wait()
                return merge.merge_file(db, COMPANY, records)
            finally:
                db.close()

        with ThreadPoolExecutor(4) as pool:
            done = list(pool.map(write, files_of))
        assert [item["skipped"] for item in done] == [False] * 4
        db = open_store(runtime)
        try:
            assert db.rows("select count(*) from (select namespace,value from mastering_identifier "
                           "group by namespace,value having count(*)>1) doubled")[0][0] == 0
            assert len(live(db)) == 100 and all(len(body["subjects"]) == 4 for body in live(db).values())
        finally:
            db.close()


@contextmanager
def two_stores(database_factory):
    """Two sessions on one mastering store."""
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        opened_ = [open_store(runtime), open_store(runtime)]
        try:
            yield opened_
        finally:
            for db in opened_:
                db.rollback()
                db.close()


def test_a_merge_of_another_kind_runs_beside_one_in_flight_and_a_reader_misses_neither(database_factory, monkeypatch):
    """A Security merge does not wait for a Company merge. The Company merge started first and commits last:
    its golden record is numbered after the Security's, so a reader that stopped in between still gets it."""
    with two_stores(database_factory) as (first, second):
        seen, finish = {}, first.finish_file

        def while_in_flight(key, records):  # the Company's golden record is written and not yet committed
            pool = ThreadPoolExecutor(1)
            try:
                security = record(FIGI, "a", "security", figi=figi("00TSTX05"))
                seen["merged"] = pool.submit(merge.merge_file, second, SECURITY, [security]).result(timeout=30)
            finally:
                pool.shutdown(wait=False)
            seen["checkpoint"] = max(file_no for file_no, _, _ in second.changes(0))
            second.commit()
            finish(key, records)

        monkeypatch.setattr(first, "finish_file", while_in_flight)
        merge.merge_file(first, COMPANY, [record(SEC, "1", cik="0000000017")])
        assert seen["merged"]["skipped"] is False and seen["checkpoint"] == 1
        later = [(file_no, json.loads(body)["kind"]) for file_no, _, body in second.changes(seen["checkpoint"])]
        assert later == [(2, "company")]
        assert sorted(body["kind"] for body in live(second).values()) == ["company", "security"]


def test_the_whole_store_lock_waits_for_a_merge_in_flight(database_factory):
    """`clear` takes the whole store: it starts only when no merge of any kind is open."""
    with two_stores(database_factory) as (first, second):
        first.take_lock("company")
        pool = ThreadPoolExecutor(1)
        try:
            waiting = pool.submit(second.take_lock)
            with pytest.raises(TimeoutError):
                waiting.result(timeout=1)
            first.commit()
            waiting.result(timeout=30)
        finally:
            first.rollback()
            pool.shutdown(wait=False)


def _beside(first, second, during):
    """Run `during(second)` while `first`'s merge is written and not yet committed; answers what it returned."""
    seen, finish = {}, first.finish_file

    def while_in_flight(key, records):
        pool = ThreadPoolExecutor(1)
        try:
            seen["result"] = pool.submit(during, second).result(timeout=20)
        finally:
            pool.shutdown(wait=False)
        finish(key, records)

    first.finish_file = while_in_flight
    return seen


def test_a_merge_that_only_joins_golden_records_runs_beside_another_of_its_kind(database_factory):
    """Two Company merges that only join stored golden records run side by side: the second commits while the first
    is still open, and each record is bound."""
    with two_stores(database_factory) as (first, second):
        if first.dialect == "mysql":
            pytest.skip("MySQL merges one kind at a time")
        merge.merge_file(first, COMPANY, [record(SEC, "1", cik="0000000017"), record(SEC, "2", cik="0000000018")])
        joining = [record(SEC, "1b", cik="0000000017")], [record(SEC, "2b", cik="0000000018")]
        seen = _beside(first, second, lambda db: merge.merge_file(db, COMPANY, joining[1]))
        merge.merge_file(first, COMPANY, joining[0])
        assert seen["result"]["skipped"] is False
        assert all(len(body["subjects"]) == 2 for body in live(first).values()) and len(live(first)) == 2


def test_merges_beside_each_other_that_join_one_golden_record_keep_every_record(database_factory):
    """Two merges joining records to the same golden records at once, in opposite orders: every golden record holds
    every record bound to it, and no identifier is on two of them."""
    with two_stores(database_factory) as (first, second):
        merge.merge_file(first, COMPANY, [record(SEC, str(n), cik=f"{n + 1:010d}") for n in range(50)])
        files = [[record(SEC, f"{side}{n}", cik=f"{n + 1:010d}") for n in range(50)] for side in ("left", "right")]
        files[1].reverse()
        start = Barrier(2)

        def write(db, records):
            start.wait()
            return merge.merge_file(db, COMPANY, records)

        with ThreadPoolExecutor(2) as pool:
            done = list(pool.map(write, [first, second], files))
        assert [item["skipped"] for item in done] == [False, False]
        assert len(live(first)) == 50 and all(len(body["subjects"]) == 3 for body in live(first).values())
        assert first.rows("select count(*) from (select namespace,value from mastering_identifier "
                          "group by namespace,value having count(*)>1) doubled")[0][0] == 0


def test_a_record_left_waiting_beside_a_merge_that_gives_its_identifier_is_released(database_factory):
    """An adviser filing waits for the Company holding its CIK. Another merge, still open, gives a stored Company that
    CIK: neither sees the other, and once both commit the filing joins the Company."""
    with two_stores(database_factory) as (first, second):
        if first.dialect == "mysql":
            pytest.skip("MySQL merges one kind at a time")
        merge.merge_file(first, COMPANY, [record(SEC, "1", cik="0000000017")])
        filing = record("iapd.adv.filings.v2", "ADV1", cik="0000000099")
        seen = _beside(first, second, lambda db: merge.merge_file(db, COMPANY, [filing]))
        merge.merge_file(first, COMPANY, [record(SEC, "1c", cik=["0000000017", "0000000099"])])
        assert seen["result"]["skipped"] is False
        (company,) = live(first)
        assert first.bound([filing["subject"]]) == {filing["subject"]: company}


def test_a_merge_that_creates_golden_records_by_identifier_runs_beside_one_in_flight_of_its_kind(database_factory):
    """A merge that creates a golden record for an identifier no one holds needs no lock of its kind (operator,
    2026-11-16: "There is no need for lock"): the identifier it gives is claimed, so another merge that gives the
    same one is sent to join it. It commits while the first merge is still open."""
    with two_stores(database_factory) as (first, second):
        if first.dialect == "mysql":
            pytest.skip("MySQL merges one kind at a time")
        merge.merge_file(first, COMPANY, [record(SEC, "1", cik="0000000017")])
        first.take_lock("company", shared=True)
        pool = ThreadPoolExecutor(1)
        try:
            creating = pool.submit(merge.merge_file, second, COMPANY, [record(SEC, "2", cik="0000000018")])
            assert creating.result(timeout=10)["skipped"] is False  # while the first is open
        finally:
            first.rollback()
            pool.shutdown(wait=False)
        assert len(live(first)) == 2


def test_a_batch_over_the_claim_cap_merges_in_parts_beside_one_in_flight_of_its_kind(database_factory, monkeypatch):
    """A fresh load's pieces claim more identifier values than the cap, and used to merge alone, holding the kind's lock
    while a worker computed (measured: 84% of the active sessions waiting on it). They are split by what they claim, and each
    part merges beside the others."""
    with two_stores(database_factory) as (first, second):
        if first.dialect == "mysql":
            pytest.skip("MySQL merges one kind at a time")
        monkeypatch.setattr(stores, "CLAIMS", 3)
        merge.merge_file(first, COMPANY, [record(SEC, "1", cik="0000000017")])
        first.take_lock("company", shared=True)  # a merge of the same kind is in flight
        pool = ThreadPoolExecutor(1)
        try:
            batch = [record(SEC, str(n), cik=f"00000001{n:02d}") for n in range(20, 32)]
            made = pool.submit(merge.merge_file, second, COMPANY, batch).result(timeout=20)  # not waiting for the first
            assert made["skipped"] is False
            assert len(made["files"]) > 1 and sum(part["records"] for part in made["files"]) == 12
        finally:
            first.rollback()
            pool.shutdown(wait=False)
        assert len(live(first)) == 13


def test_a_batch_with_one_record_that_merges_golden_records_is_split_and_gives_the_same_masters(database_factory, monkeypatch):
    with opened(database_factory) as db:
        if db.dialect == "mysql":
            pytest.skip("MySQL merges one kind at a time")
        monkeypatch.setattr(stores, "CLAIMS", 4)
        a, b = figi("00TSTX01"), figi("00TSTX02")
        merge.merge_file(db, SECURITY, [record(FIGI, "a", "security", figi=a), record(FIGI, "b", "security", figi=b)])
        batch = [record(FIGI, f"n{n}", "security", figi=figi(f"00TSTY{n:02d}")) for n in range(6)]
        batch.append(record(FIGI, "c", "security", figi=[a, b]))  # joins the two golden records: a decision for a merge alone
        made = merge.merge_file(db, SECURITY, batch)
        assert sum(part["records"] for part in made["files"]) == 7
        assert len(live(db)) == 1 + 6  # a and b became one; the six are new
        assert sum(m.get("status") == "alias" for m in masters(db).values()) == 1
        merge.merge_file(db, SECURITY, batch)  # the same batch again changes nothing
        assert len(live(db)) == 7


def test_a_part_that_merges_alone_is_counted_by_its_reason(database_factory, monkeypatch):
    """The cost of each reason a merge goes alone is read from these counts (ticket mastering-locks/02): a part with no
    reason counts nothing, and a part that merges golden records counts that reason once."""
    with opened(database_factory) as db:
        if db.dialect == "mysql":
            pytest.skip("MySQL merges one kind at a time")
        monkeypatch.setattr(stores, "CLAIMS", 4)
        a, b = figi("00TSTW01"), figi("00TSTW02")
        plain = merge.merge_file(db, SECURITY, [record(FIGI, "a", "security", figi=a), record(FIGI, "b", "security", figi=b)])
        assert plain["alone"] == {}
        joining = merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        assert joining["alone"] == {"a merge of golden records": 1}


@pytest.mark.parametrize("engine", ["postgresql", "mysql"])
def test_every_integer_column_is_bigint(engine):
    schema = (Path(stores.__file__).parent / "schema" / f"{engine}.sql").read_text()
    assert not re.findall(r"\b(?:tiny|small|medium)?int(?:eger)?\b", schema)


def test_a_link_waits_for_its_other_end_and_keeps_its_earliest_start(database_factory):
    custodian = "iapd.adv.custodians.v1"
    issuer = subject_key(custodian, "issuer")

    def filed(on, revision):
        link = {"type": "ISSUED_BY", "target_subject": issuer, "scope": "invented", "valid_from": on, "valid_to": None,
                "valid_from_basis": "observed", "properties": {}}
        return assertion(source_code=NPORT, record_key="share", publication_key="invented", revision=revision,
                         effective_at=None, kind="security", fields={"name": "INVENTED SHARE"},
                         identifiers={"cusip": "037833100"}, relationships=[link])

    with opened(database_factory) as db:
        merge.merge_file(db, SECURITY, [filed("2026-03-01T00:00:00+00:00", 1)])
        edges, waiting = links.calculate(db, POLICY, AS_OF, {})
        assert edges == [] and waiting == {"unresolved_endpoint": 1}
        merge.merge_file(db, COMPANY, [record(custodian, "issuer", lei="529900T8BM49AURSDO55")])
        edges, waiting = links.calculate(db, POLICY, AS_OF, {})
        assert not waiting
        (row,) = links.rows_of(edges)["relationship"]
        assert (row["relationship_type"], row["valid_from_basis"]) == ("ISSUED_BY", "observed")
        assert {row["source_master_id"], row["target_master_id"]} == set(live(db))
        merge.merge_file(db, SECURITY, [filed("2026-06-01T00:00:00+00:00", 2)])
        later, _ = links.calculate(db, POLICY, AS_OF, links.stored_of([row]))
        assert [r["valid_from"] for r in links.rows_of(later)["relationship"]] == [row["valid_from"]]


def test_a_link_reads_only_the_kind_status_and_profiles_of_its_golden_records(database_factory, monkeypatch):
    """The links build holds every link end's golden record at once, so it reads the three fields Rust uses, never the body."""
    custodian = "iapd.adv.custodians.v1"
    link = {"type": "ISSUED_BY", "target_subject": subject_key(custodian, "issuer"), "scope": "invented",
            "valid_from": "2026-03-01T00:00:00+00:00", "valid_to": None, "valid_from_basis": "observed", "properties": {}}
    share = assertion(source_code=NPORT, record_key="share", publication_key="invented", revision=1, effective_at=None,
                      kind="security", fields={"name": "INVENTED SHARE"}, identifiers={"cusip": "037833100"},
                      relationships=[link])
    with opened(database_factory) as db:
        merge.merge_file(db, SECURITY, [share])
        merge.merge_file(db, COMPANY, [record(custodian, "issuer", lei="529900T8BM49AURSDO55")])
        states = db.master_states(list(live(db)))
        assert sorted(state["kind"] for state in states.values()) == ["company", "security"]
        assert all(set(state) <= {"kind", "status", "profiles"} for state in states.values())

        def whole(entities):
            raise AssertionError("the links build read whole golden records")

        monkeypatch.setattr(db, "master_bodies", whole)
        edges, waiting = links.calculate(db, POLICY, AS_OF, {})
        assert not waiting
        assert [row["relationship_type"] for row in links.rows_of(edges)["relationship"]] == ["ISSUED_BY"]



def test_every_master_assembles_to_what_survivorship_gave_through_create_join_change_merge_and_split(database_factory, monkeypatch):
    """MASTER-FIELDS.md: the store keeps a master in columns, rows and text; assembled, it is the body survivorship wrote."""
    from edgar_warehouse.mastering import master_row

    written, split = {}, master_row.split

    def recorded(body):
        written[body["entity_id"]] = json.loads(json.dumps(body))
        return split(body)

    monkeypatch.setattr(master_row, "split", recorded)
    with opened(database_factory) as db:
        def check(step):
            db.commit()
            assert db.master_bodies(list(written)) == written, step

        a, b = figi("00TSTX11"), figi("00TSTX12")
        first, second = record(FIGI, "a", "security", figi=a), record(FIGI, "b", "security", figi=b)
        merge.merge_file(db, SECURITY, [first])
        check("create")
        merge.merge_file(db, SECURITY, [record(FIGI, "a2", "security", figi=a)])
        check("join")
        merge.merge_file(db, SECURITY, [{**first, "fields": {"name": "INVENTED a CHANGED"}, "revision": 2}])
        check("change")
        merge.merge_file(db, SECURITY, [second])
        merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        check("merge and alias")
        (merge_id, keep, gone), = db.merges()
        db.split(keep, gone)
        db.add_decision(decision("reverse", actor="fixture", reason="invented", at=AS_OF, target=merge_id), keep, gone)
        db.add_identifiers([("figi", a if db.bound([first["subject"]])[first["subject"]] == gone else b, gone)])
        db.commit()
        merge.merge_file(db, SECURITY, [first, second], again=True)
        check("split")
        kept = [json.loads(t) for (t,) in db.rows("select body from mastering_master")]
        assert not any({"entity_id", "identifiers", "subjects", "profiles", "kind", "status", "canonical_id"} & set(k) for k in kept)
        assert not any(stamp in value for k in kept for value in (k.get("fields") or {}).values()
                       for stamp in ("policy_digest", "kind_version"))

PERSON = merge.Settings(POLICY, "invented-digest", "person", AS_OF)
FUND = merge.Settings(POLICY, "invented-digest", "fund_structure", AS_OF)
PERSON_SOURCE, FUND_SOURCE = "sec.submissions.person.v1", "sec.nport.fund.v1"


def test_person_and_fund_join_by_their_identifier_and_a_rerun_changes_nothing(database_factory):
    """Person by CIK and Fund by series id, each kind under the real rules, on each engine (invented records)."""
    with opened(database_factory) as db:
        person = lambda key, cik: record(PERSON_SOURCE, key, "person", {"name": f"INVENTED PERSON {key}"}, cik=cik)
        fund = lambda key, series: record(FUND_SOURCE, key, "fund_structure", {"name": f"INVENTED FUND {key}"},
                                          sec_series_id=series)
        people = [person("p1", "0000000901"), person("p1-again", "0000000901"), person("p2", "0000000902")]
        funds = [fund("f1", "S000000901"), fund("f1-again", "S000000901"), fund("f2", "S000000902")]
        assert merge.merge_file(db, PERSON, people).get("merges", 0) == 0
        assert merge.merge_file(db, FUND, funds).get("merges", 0) == 0
        held = {b["kind"] for b in live(db).values()}
        assert held == {"person", "fund_structure"}
        assert sum(1 for b in live(db).values() if b["kind"] == "person") == 2  # one master a CIK
        assert sum(1 for b in live(db).values() if b["kind"] == "fund_structure") == 2  # one master a series
        before = masters(db)
        merge.merge_file(db, PERSON, people, again=True)
        merge.merge_file(db, FUND, funds, again=True)
        assert masters(db) == before


def sec_filer_without_a_pass():
    return assertion(source_code=SEC, record_key="0000000017", publication_key="invented", revision=1, effective_at=None,
                     kind="company", identifiers={"cik": "0000000017"},
                     fields={"name": "INVENTED CO", "state_of_incorporation": "CA"},
                     provenance={"matching": {"business_postal_code": "90000", "business_country": "US"}})


def test_the_waterfall_pairs_reach_the_merge_as_name_keys_and_a_second_call_changes_nothing(database_factory):
    pair = {"lei": LEI, "pass": "name and city or postcode"}
    with opened(database_factory) as db:
        filer = sec_filer_without_a_pass()
        merge.merge_file(db, COMPANY, [filer])
        keys = "select value,subject from mastering_name_key where role='cascade'"
        assert db.rows(keys) == []

        counts = merge.apply_pairs(db, COMPANY, SEC, {"0000000017": pair, "0000000099": pair})

        assert counts["records"] == 1  # the pair of a CIK the store does not hold is no record
        assert db.rows(keys) == [(LEI, filer["subject"])]
        stored = {e: b for e, b in masters(db).items() if b.get("status") != "alias"}
        assert merge.apply_pairs(db, COMPANY, SEC, {"0000000017": pair}) == {"records": 0}
        assert {e: b for e, b in masters(db).items() if b.get("status") != "alias"} == stored


ADDRESS = {"street": "1 EXAMPLE WAY", "city": "ANYTOWN", "postcode": "12345", "country": "US"}


def placed_filer(*, revision=1, name="INVENTED CO"):
    return assertion(source_code=SEC, record_key="0000000017", publication_key="invented", revision=revision, effective_at=None,
                     kind="company", identifiers={"cik": "0000000017"},
                     fields={"name": name, "state_of_incorporation": "CA"},
                     provenance={"matching": {"address": ADDRESS, "business_country": "US"}})


def placed_entity():
    return assertion(source_code=GLEIF, record_key=LEI, publication_key="invented", revision=1,
                     effective_at="2026-09-01T00:00:00+00:00", kind="company", identifiers={"lei": LEI},
                     fields={"name": "Invented Co.", "jurisdiction": "US-CA", "gleif_entity_status": "ACTIVE",
                             "gleif_registration_status": "ISSUED", "gleif_last_update": "2026-09-01T00:00:00Z"},
                     provenance={"matching": {"headquarters_address": ADDRESS}})


def joined(db, *, gleif_first=False):
    """Merge the invented filer and GLEIF entity, then give the merge the waterfall pass's pair: the two records
    are one golden record. Answers (filer, entity)."""
    from collections import Counter
    from edgar_warehouse.mdm import waterfall_passes, waterfall

    spec = waterfall_passes.spec(POLICY)
    filer, entity = placed_filer(), placed_entity()
    if gleif_first:
        merge.merge_file(db, COMPANY, [entity])  # it creates its own Company: the pair cannot join it afterwards
    merge.merge_file(db, COMPANY, [filer])
    found = waterfall.assignments(
        waterfall.stored_filers(db, SEC), [waterfall_passes.entity_of(entity, frozenset({"INVENTED CO"}), eligible=True)],
        spec["passes"], gleif_addresses=Counter(), over_shared=spec["over_shared"])
    merge.apply_pairs(db, COMPANY, SEC, found)
    if not gleif_first:
        merge.merge_file(db, COMPANY, [entity])  # a load's order: the pair is applied first, so the record joins
    return filer, entity


@pytest.mark.parametrize("gleif_first", [False, True])
def test_the_pass_pairs_and_the_merge_joins_the_company_when_the_pair_comes_first_and_a_second_pass_changes_nothing(
        database_factory, gleif_first):
    """A load's order, the filer, its pair, then the GLEIF record, gives one Company: the engine lets a record a name
    rule holds a pair for wait, and the rule joins it. A GLEIF record that came before its filer was paired created its
    own Company, which a name rule cannot join afterwards: a known limit, kept here so it is seen."""
    from collections import Counter
    from edgar_warehouse.mdm import waterfall_passes, waterfall

    spec = waterfall_passes.spec(POLICY)
    with opened(database_factory) as db:
        filer, entity = placed_filer(), placed_entity()
        if gleif_first:
            merge.merge_file(db, COMPANY, [entity])
        merge.merge_file(db, COMPANY, [filer])
        assert len(live(db)) == (2 if gleif_first else 1)

        found = waterfall.assignments(
            waterfall.stored_filers(db, SEC), [waterfall_passes.entity_of(entity, frozenset({"INVENTED CO"}), eligible=True)],
            spec["passes"], gleif_addresses=Counter(), over_shared=spec["over_shared"])
        assert set(found) == {"0000000017"}
        merge.apply_pairs(db, COMPANY, SEC, found)
        if not gleif_first:
            merge.merge_file(db, COMPANY, [entity])

        if gleif_first:
            assert len(live(db)) == 2  # the limit: two Companies for one filer
        else:
            (master,) = live(db).values()
            assert sorted(master["subjects"]) == sorted([filer["subject"], entity["subject"]])
            assert master["identifiers"]["lei"] == [LEI]
        assert db.rows("select count(*) from mastering_review where open_review=1") == [(0,)]
        before = live(db)
        assert merge.apply_pairs(db, COMPANY, SEC, found) == {"records": 0} and live(db) == before


@pytest.mark.parametrize("gleif_first", [False, True])
@pytest.mark.parametrize("historical", [False, True])
def test_configured_preparation_pairs_and_merges_through_the_stage(
        database_factory, tmp_path, monkeypatch, gleif_first, historical):
    from edgar_warehouse.rules import preparation
    from tests.support.waterfall import capture, native

    with opened(database_factory) as db:
        filer, entity = placed_filer(revision=2, name=None if historical else "INVENTED CO"), placed_entity()
        if gleif_first:
            merge.merge_file(db, COMPANY, [entity])
        if historical:
            earlier = placed_filer()
            merge.merge_file(db, COMPANY, [earlier])
        merge.merge_file(db, COMPANY, [filer])

        @contextmanager
        def registered(digest, environment):
            yield db  # restricted runtime store; registry validation has its own boundary checks

        monkeypatch.setattr(preparation, "registered_store", registered)
        folder = capture(tmp_path / "capture", [native(lei=LEI, city=ADDRESS["city"],
                                                       updated="2026-09-01T00:00:00Z")])
        arguments = dict(reading=files.source("gleif"), target="mastering", capture=folder,
                         folder=tmp_path / "preparation", facts=["publication_count=1"], as_of=AS_OF,
                         deadline=float("inf"), say=lambda _: None, environment={})
        [done] = preparation.prepare_load(**arguments)
        assert (done["pairs"], done["applied"]) == (1, 1)
        if historical:
            earlier_body = json.loads(db.rows("select body from mastering_record where assertion_id=%s",
                                             [earlier["assertion_id"]])[0][0])
            assert "name_count" not in earlier_body["provenance"]["matching"]
            latest_body = json.loads(db.rows("select body from mastering_record where assertion_id=%s",
                                            [filer["assertion_id"]])[0][0])
            assert latest_body["fields"] == filer["fields"]
        from edgar_warehouse.mdm import matching
        staged_filer = json.loads(db.rows("select body from mastering_record where assertion_id=%s", [filer["assertion_id"]])[0][0])
        rule = next(r for r in POLICY["kinds"]["company"]["rules"] if r["family"] == "name_binding")
        if not historical:
            assert matching.compare_candidate_records(rule, [(staged_filer, entity)])[0][0], staged_filer["provenance"]
        if not gleif_first:
            merge.merge_file(db, COMPANY, [entity])
        if gleif_first:
            assert len(live(db)) == 2  # its own Company came first: a name rule cannot join it (the known limit)
        else:
            (master,) = live(db).values()
            assert sorted(master["subjects"]) == sorted([filer["subject"], entity["subject"]])
        before = live(db)
        checked(monkeypatch, preparation, "project_capture", lambda *a, **k: pytest.fail("unchanged input re-read"))
        [repeated] = preparation.prepare_load(**arguments)
        assert repeated["applied"] == 0 and live(db) == before


def test_changed_pair_evidence_is_retained_when_its_lookup_key_already_exists(database_factory):
    with opened(database_factory) as db:
        filer = placed_filer()
        merge.merge_file(db, COMPANY, [filer])
        from collections import Counter
        from edgar_warehouse.mdm import waterfall_passes, waterfall
        entity = placed_entity()
        spec = waterfall_passes.spec(POLICY)
        [answer] = waterfall.assignments([waterfall_passes.filer_of(filer)],
            [waterfall_passes.entity_of(entity, frozenset({"INVENTED CO"}), eligible=True)], spec["passes"],
            gleif_addresses=Counter(), over_shared=spec["over_shared"]).values()
        original = {**answer, "last_update": "2026-08-01T00:00:00Z"}
        updated = {**original, "last_update": "2026-09-01T00:00:00Z"}
        assert merge.apply_pairs(db, COMPANY, SEC, {"0000000017": original})["records"] == 1
        assert merge.apply_pairs(db, COMPANY, SEC, {"0000000017": updated})["records"] == 1
        body = json.loads(db.rows("select body from mastering_record where assertion_id=%s", [filer["assertion_id"]])[0][0])
        assert body["provenance"]["matching"]["name_count"]["cascade"] == {"version": "sec-gleif-cascade-v1", **updated}
        assert db.rows("select value,subject from mastering_name_key where role='cascade'") == [(LEI, filer["subject"])]
        merge.merge_file(db, COMPANY, [entity])
        (master,) = live(db).values()
        assert sorted(master["subjects"]) == sorted([filer["subject"], entity["subject"]])
        before = live(db)
        assert merge.apply_pairs(db, COMPANY, SEC, {"0000000017": updated}) == {"records": 0}
        assert live(db) == before


def test_pair_evidence_keys_and_waiter_release_roll_back_together_and_retry_completes(database_factory, monkeypatch):
    with opened(database_factory) as db:
        filer = placed_filer()
        merge.merge_file(db, COMPANY, [filer])
        before = db.rows("select body from mastering_record where assertion_id=%s", [filer["assertion_id"]])
        release = merge._release_waiting

        def interrupted(store, settings, arrived, tried=None):
            current = json.loads(store.rows("select body from mastering_record where assertion_id=%s",
                                            [filer["assertion_id"]])[0][0])
            assert current["provenance"]["matching"]["name_count"]["cascade"]["lei"] == LEI
            assert store.rows("select value from mastering_name_key where role='cascade'") == [(LEI,)]
            raise RuntimeError("interrupted waiter release")

        checked(monkeypatch, merge, "_release_waiting", interrupted)
        pair = {"0000000017": {"lei": LEI, "pass": "name and city or postcode"}}
        with pytest.raises(RuntimeError, match="interrupted waiter release"):
            merge.apply_pairs(db, COMPANY, SEC, pair)
        assert db.rows("select body from mastering_record where assertion_id=%s", [filer["assertion_id"]]) == before
        assert db.rows("select value from mastering_name_key where role='cascade'") == []
        monkeypatch.setattr(merge, "_release_waiting", release)
        assert merge.apply_pairs(db, COMPANY, SEC, pair)["records"] == 1
        assert merge.apply_pairs(db, COMPANY, SEC, pair) == {"records": 0}


def test_a_merge_keeps_its_file_in_memory_and_leaves_no_working_tables(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(SEC, "1", cik="0000000001"), record(GLEIF, "2", lei="INVENTEDLEI000000001")])
        tables = {row[0] for row in db.rows(
            "select table_name from information_schema.tables where table_name like 'mastering\\_%%'")}
        assert not {name for name in tables if name.startswith("mastering_stage")}, sorted(tables)
        assert db.rows("select count(*) from mastering_record")[0][0] == 2


def test_postgresql_keeps_the_mastering_tables_in_the_mdm_schema_and_nothing_in_public(database_factory):
    """Operator, 2026-11-21: "mdm schema never use public": a PostgreSQL store's tables are in its own schema."""
    with opened(database_factory) as db:
        if db.dialect != "postgresql":
            pytest.skip("only PostgreSQL has schemas inside a database")
        held = lambda schema: {name for (name,) in db.rows("select table_name from information_schema.tables where table_schema=%s", [schema])}
        assert {"mastering_master", "mastering_identifier"} <= held("mdm")
        assert held("public") == set()
        assert db.rows("select current_schema()")[0][0] == "mdm"
