"""The `context` command on the mastering tables, on each engine, with invented records."""

from argparse import Namespace
from contextlib import contextmanager

import pytest

from edgar_warehouse import context
from edgar_warehouse.context import Context, ContextError
from edgar_warehouse.mastering import links, lookups, merge, reads
from edgar_warehouse.mastering import store as stores
from edgar_warehouse.mastering.store import open_store
from edgar_warehouse.mdm.evidence import assertion
from tests.storage_adapters.test_mastering import COMPANY, FIGI, SEC, SECURITY, figi, record


def asked(subject, key=None, **more):
    return Namespace(**{"subject": subject, "key": key, "search": None, "detail_key": None, "limit": 5, "as_of": None,
                        "as_at": None, "detail": "brief", "page": None, "hops": 1, "relationship_type": "", **more})


def security(key, value, name="INVENTED", **extra):
    return assertion(source_code=FIGI, record_key=key, publication_key="invented", revision=1, effective_at=None,
                     kind="security", fields={"name": name}, identifiers={"figi": value}, **extra)


@contextmanager
def reader(database_factory, monkeypatch, silver_links=()):
    @contextmanager
    def no_silver(self):
        yield None

    monkeypatch.setattr(Context, "_silver", no_silver)
    monkeypatch.setattr(links, "around", lambda silver, ids, relationship_type="": [
        link for link in silver_links if {link["source_id"], link["target_id"]} & set(ids)])
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        db = open_store(runtime)
        try:
            yield db, Context(runtime)
        finally:
            db.rollback()
            db.close()


def test_a_company_is_found_by_its_id_and_by_its_identifier(database_factory, monkeypatch):
    with reader(database_factory, monkeypatch) as (db, ask):
        merge.merge_file(db, COMPANY, [record(SEC, "1", fields={"name": "INVENTED ANVIL"}, cik="0000000021")])
        lookups.build(db)
        db.commit()
        found = ask.answer(asked("company", "cik:0000000021", detail="full"))
        assert (found["name"], found["kind"], found["status"]) == ("INVENTED ANVIL", "company", "accepted")
        assert found["identifiers"] == {"cik": ["0000000021"]}
        assert found["sources"] == {SEC: ["1"]}
        assert ask.answer(asked("company", found["entity_id"]))["name"] == "INVENTED ANVIL"
        with pytest.raises(ContextError, match="No company carries"):
            ask.answer(asked("company", "cik:0000000099"))
        with pytest.raises(ContextError, match="No security carries"):
            ask.answer(asked("security", "cik:0000000021"))
        with pytest.raises(ContextError, match="is a company, not a security"):
            ask.answer(asked("security", found["entity_id"]))


def test_a_merged_away_id_answers_with_its_survivor(database_factory, monkeypatch):
    with reader(database_factory, monkeypatch) as (db, ask):
        a, b = figi("00TSTX01"), figi("00TSTX02")
        merge.merge_file(db, SECURITY, [security("a", a)])
        merge.merge_file(db, SECURITY, [security("b", b)])
        ids = [row[0] for row in db.rows("select entity_id from mastering_master")]
        merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
        db.commit()
        answers = [ask.answer(asked("security", entity)) for entity in ids]
        (survivor,) = {answer["entity_id"] for answer in answers}
        assert [answer.get("merged_from") for answer in answers if answer.get("merged_from")] == [
            entity for entity in ids if entity != survivor]


def test_search_and_detail_keys_read_the_lookups_and_say_when_they_are_behind(database_factory, monkeypatch):
    with reader(database_factory, monkeypatch) as (db, ask):
        one = figi("00TSTZ01")
        listing = {"key": one, "ticker": "INVT", "mic": "XINV", "exchange": "IV", "description": "INVENTED"}
        merge.merge_file(db, COMPANY, [record(SEC, "1", fields={"name": "INVENTED ANVIL"}, cik="0000000021")])
        merge.merge_file(db, SECURITY, [security("a", one, details={"listings": [listing]})])
        db.commit()
        with pytest.raises(ContextError) as behind:
            ask.answer(asked("company", search="anvil"))
        assert behind.value.command == context.LOOKUPS
        lookups.build(db)
        db.commit()
        assert [row["name"] for row in ask.answer(asked("company", search="anvil"))["matches"]] == ["INVENTED ANVIL"]
        assert ask.answer(asked("company", search="missing"))["matches"] == []
        held = ask.answer(asked("security", detail_key=["mic", "XINV", "INVT"]))
        assert [row["entity_id"] for row in held["matches"]] == [reads.master_ids(db, FIGI, {"a"})["a"]]
        with pytest.raises(ContextError, match="takes a key name"):
            ask.answer(asked("security", detail_key=["mic", "XINV"]))
        with pytest.raises(ContextError, match="No detail lookup"):
            ask.answer(asked("company", detail_key=["mic", "XINV", "INVT"]))


def test_a_cross_reference_two_masters_share_is_not_settled_for_the_reader(database_factory, monkeypatch):
    with reader(database_factory, monkeypatch) as (db, ask):
        shared = {"cross_references": {"share_class_figi": "BBG000000001"}}
        merge.merge_file(db, SECURITY, [security("a", figi("00TSTZ02"), **shared), security("b", figi("00TSTZ03"), **shared)])
        lookups.build(db)
        db.commit()
        with pytest.raises(ContextError, match="carried by 2 entities"):
            ask.answer(asked("security", "share_class_figi:BBG000000001"))


@pytest.mark.parametrize("past", [{"as_of": "2020-01-01T00:00:00+00:00"}, {"as_at": "2020-01-01T00:00:00+00:00"}])
def test_a_master_has_no_past_to_read(past):
    with pytest.raises(ContextError, match="current masters"):
        Context(None).answer(asked("company", "cik:0000000021", **past))


def test_links_come_from_silver_with_their_role_and_the_far_end_named(database_factory, monkeypatch):
    stored = []
    with reader(database_factory, monkeypatch, stored) as (db, ask):
        merge.merge_file(db, COMPANY, [record(SEC, "1", fields={"name": "INVENTED ANVIL"}, cik="0000000021"),
                                       record(SEC, "2", fields={"name": "INVENTED BELLOWS"}, cik="0000000022")])
        db.commit()
        by_name = {row[1]: row[0] for row in db.rows(
            "select entity_id, body from mastering_master")}
        one, two = sorted(by_name.values())
        stored.append({"relationship_id": "x" * 64, "type": "OWNS", "scope": "invented", "source_id": one, "target_id": two,
                       "capacity": "director", "derived": False, "last_seen": None, "evidence": [],
                       "periods": [{"valid_from": "2026-01-01T00:00:00+00:00", "valid_from_basis": "reported",
                                    "valid_to": None, "ended_by": None, "path": None}]})
        answer = ask.answer(asked("company", one))
        assert answer["related_count"] == 1
        (link,) = answer["related"]
        assert (link["type"], link["role"], link["to"]["entity_id"]) == ("OWNS", "director", two)
        assert link["basis"] == "stated"
