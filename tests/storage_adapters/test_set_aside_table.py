"""`silver.set_aside`: the identifiers of the records a classification rule held back, by the feed's own contract, as a
snapshot beside master_binding (company phase 2, ticket 02). Invented records and an invented contract."""
import json
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.mastering import links, store as stores
from edgar_warehouse.mastering.store import open_store
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file

SPEC = Path(__file__).resolve().parents[2] / "rules" / "silver" / "silver-set-aside.yaml"
HELD = "select namespace, value, source_code, reason, probable_kind from {table} order by 1, 2, 3"
ADAPTERS = {
    "invented.filer.v1": {"identifiers": {"cik": "cik"}, "identifier_formats": {"cik": "sec_cik"}},
    "invented.listing.v1": {"identifiers": {"cik": "issuer", "ticker": "tickers"}, "identifier_formats": {"cik": "sec_cik"}},
    "invented.nested.v1": {"identifiers": {"lei": "entity.lei.$", "cik": "entity.registration.cik"}, "identifier_formats": {"cik": "sec_cik"}},
}


@contextmanager
def opened(database_factory):
    """MDM and silver each in its own isolated database, as MySQL keeps them (PostgreSQL takes the same)."""
    with database_factory("mdm") as (mdm_owner, mdm, mdm_role), database_factory("silver") as (owner, runtime, role):
        stores.install(mdm_owner, runtime_role=mdm_role)
        silver.migrate(owner, runtime_role=role)
        silver.register(owner, spec_file(SPEC, None), runtime_role=role)
        db = open_store(mdm)
        try:
            yield owner, runtime, mdm, db
        finally:
            db.rollback()
            db.close()


def held_back(db, *records):
    """(id, source code, reason, raw record, probable kind) rows into mastering_deferred."""
    db.add_deferred([(ident, code, reason, 0, json.dumps({"source_code": code, "reason": reason, "raw_record": raw,
                                                          **({"probable_kind": kind} if kind else {})}))
                     for ident, code, reason, raw, kind in records])
    db.commit()


def held(engine):
    table = "silver.set_aside" if engine.dialect.name == "postgresql" else "set_aside"  # MySQL's silver is its own database
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(HELD.format(table=table)))]


def test_a_record_a_classification_rule_held_back_is_set_aside_by_its_formatted_identifiers_and_nothing_else(database_factory):
    with opened(database_factory) as (owner, runtime, mdm, db):
        held_back(db,
                  ("d1", "invented.filer.v1", "classification_deferred", {"cik": "17", "entity_name": "Example Holdings LLC"}, "fund_structure"),
                  ("d2", "invented.filer.v1", "classification_entity_undetermined", {"cik": "18"}, None),
                  ("d3", "invented.filer.v1", "relationship_end_missing", {"cik": "19"}, None),  # waits on something missing: a gap
                  ("d8", "invented.filer.v1", "classification_not_activated", {"cik": "23"}, None),
                  ("d4", "invented.listing.v1", "classification_deferred", {"issuer": "20", "tickers": ["EXA", "EXB"]}, None),
                  ("d7", "invented.nested.v1", "classification_deferred",
                   {"entity": {"lei": {"$": "INVENTEDLEI000000001"}, "name": "Example", "registration": {"cik": "22"}}}, "branch"))
        assert links.set_aside(runtime, mdm, ADAPTERS.get) == 8
        assert held(owner) == [
            ("cik", "0000000017", "invented.filer.v1", "classification_deferred", "fund_structure"),
            ("cik", "0000000018", "invented.filer.v1", "classification_entity_undetermined", None),
            ("cik", "0000000020", "invented.listing.v1", "classification_deferred", None),
            ("cik", "0000000022", "invented.nested.v1", "classification_deferred", "branch"),
            ("cik", "0000000023", "invented.filer.v1", "classification_not_activated", None),
            ("lei", "INVENTEDLEI000000001", "invented.nested.v1", "classification_deferred", "branch"),
            ("ticker", "EXA", "invented.listing.v1", "classification_deferred", None),
            ("ticker", "EXB", "invented.listing.v1", "classification_deferred", None)]


def test_a_record_no_longer_held_back_leaves_the_table_and_a_refused_identifier_drops_only_itself(database_factory):
    with opened(database_factory) as (owner, runtime, mdm, db):
        held_back(db, ("d1", "invented.filer.v1", "classification_deferred", {"cik": "17"}, None),
                  ("d2", "invented.filer.v1", "classification_deferred", {"cik": "18"}, None))
        links.set_aside(runtime, mdm, ADAPTERS.get)
        db.cursor.execute("delete from mastering_deferred where deferred_id = 'd2'")
        db.commit()
        held_back(db, ("d5", "no.contract.v1", "classification_deferred", {"cik": "21"}, None),
                  ("d6", "invented.filer.v1", "classification_deferred", {"cik": "not a cik"}, None),
                  ("d9", "invented.listing.v1", "classification_deferred", {"issuer": "not a cik", "tickers": ["EXC"]}, None))
        assert links.set_aside(runtime, mdm, ADAPTERS.get) == 2
        assert held(owner) == [("cik", "0000000017", "invented.filer.v1", "classification_deferred", None),
                               ("ticker", "EXC", "invented.listing.v1", "classification_deferred", None)]


def test_one_identifier_two_feeds_held_back_is_two_rows_and_one_feed_holding_it_twice_keeps_the_first_reason(database_factory):
    with opened(database_factory) as (owner, runtime, mdm, db):
        held_back(db, ("d1", "invented.filer.v1", "classification_entity_undetermined", {"cik": "17"}, None),
                  ("d2", "invented.filer.v1", "classification_deferred", {"cik": "17"}, "person"),
                  ("d3", "invented.listing.v1", "classification_deferred", {"issuer": "17"}, None))
        links.set_aside(runtime, mdm, ADAPTERS.get)
        assert held(owner) == [("cik", "0000000017", "invented.filer.v1", "classification_deferred", "person"),
                               ("cik", "0000000017", "invented.listing.v1", "classification_deferred", None)]
