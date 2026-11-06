"""Mastering on each engine, under the real rules, with invented records."""

import json
from contextlib import contextmanager
from uuid import uuid4

import pytest

from edgar_warehouse.mastering import merge, store as stores
from edgar_warehouse.mdm.evidence import assertion, decision
from edgar_warehouse.mdm.identifier_types import TYPES
from edgar_warehouse.rules import files
from edgar_warehouse.mastering.store import open_store

AS_OF = "2026-11-06T12:00:00+00:00"
POLICY = files.policy()
COMPANY = merge.Settings(POLICY, "invented-digest", "company", AS_OF)
SECURITY = merge.Settings(POLICY, "invented-digest", "security", AS_OF)
SEC, FIGI, GLEIF = "sec.company.v1", "openfigi.security.v3", "gleif.level1.v1"
NPORT = next(r for r in POLICY["kinds"]["security"]["rules"] if r["rule_id"] == "nport-security-cusip")["source"]


def figi(stem: str) -> str:
    for digit in "0123456789":
        if TYPES["figi"].refusal(f"BBG{stem}{digit}")[1] is None:
            return f"BBG{stem}{digit}"
    raise AssertionError(stem)


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
    return {e: json.loads(b) for e, b in db.rows("select entity_id,body from mastering_master")}


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
        monkeypatch.setattr(merge, "_write_masters", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("invented failure")))
        with pytest.raises(RuntimeError):
            merge.merge_file(db, COMPANY, batch)
        monkeypatch.undo()
        assert masters(db) == {} and not db.file_done(merge.file_key(batch))
        assert not merge.merge_file(db, COMPANY, batch)["skipped"]
        assert len(live(db)) == 1


def test_a_record_with_no_match_waits_as_an_open_review(database_factory):
    with opened(database_factory) as db:
        waiting = record(GLEIF, "INVENTEDLEI000000017", lei="INVENTEDLEI000000017")
        merge.merge_file(db, COMPANY, [waiting])
        assert masters(db) == {}
        assert db.rows("select reason,open_review from mastering_review where subject=%s", [waiting["subject"]]) == [("binding_required", 1)]


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
        assert copy == dict(db.rows("select entity_id,body from mastering_master"))


def test_the_runtime_login_cannot_erase_a_decision_or_change_a_table(database_factory):
    with opened(database_factory) as db:
        for sql in ("delete from mastering_decision", "update mastering_decision set operation='x'", "drop table mastering_master"):
            with pytest.raises(Exception, match="(?i)denied|owner"):
                db.rows(sql)
            db.rollback()
