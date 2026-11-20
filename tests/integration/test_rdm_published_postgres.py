"""Real PG16: `rdm.published_code`, the published-only table the managed mirror carries (connectivity ticket 06).

A draft or approved version never appears; a version appears once, when it is published, with the rows
`rdm.code_context` gives; a code set keeps one version, so the version a publish replaces, and a retired code set, leave every table in the publish's own
transaction; no row is changed or removed otherwise; a
populated store gets its rows from the same writer.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.rdm import database
from edgar_warehouse.rdm.store import RDM
from tests.integration.test_rdm_postgres import OPERATOR, server

CODES = [{"code": "F", "label": "Finance"}, {"code": "F1", "label": "Banks", "parent_code": "F"}]
# Something in every table a version has rows in.
EXTRAS = {"levels": [{"depth": 1, "name": "Section"}, {"depth": 2, "name": "Group"}],
          "crosswalk": [{"from_code": "F", "to_set": "outside", "to_version": "1", "to_code": "6", "match_type": "exact"}],
          "usage": [{"store": "silver", "object": "filer", "field": "industry"}],
          "hints": [{"kind": "meaning", "text": "A sector."}]}
VERSION_TABLES = (("code", "code_set", "version"), ("code_label", "code_set", "version"),
                  ("code_path", "code_set", "version"), ("level", "code_set", "version"),
                  ("crosswalk_row", "from_set", "from_version"), ("code_set_usage", "code_set", "version"),
                  ("code_set_hint", "code_set", "version"), ("published_code", "code_set", "version"),
                  ("code_set_version", "code_set", "version"))
COLUMNS = ("code_set, code_set_name, version, code, label, definition, synonyms, path, label_path, level, depth, "
           "parent_code, crosswalk, sha256, valid_from, code_status, code_valid_from, code_valid_to, invalid_reason, "
           "approved_by, approved_at, published_at, value, unit, properties")


@pytest.fixture(scope="module")
def stores(tmp_path_factory):
    out = tmp_path_factory.mktemp("published")
    with server() as engine:
        owner, runtime = engine("rdm"), engine("rdm", "rdm_runtime")
        store = RDM(runtime)
        database.migrate(owner, runtime_role="rdm_runtime")
        store.draft({"code_set": "one", "name": "One"}, "1", CODES, created_by="test", **EXTRAS)
        store.approve("one", "1", **OPERATOR)
        store.publish("one", "1", out=out)
        store.draft({"code_set": "one"}, "2", CODES, created_by="test", supersedes="1", **EXTRAS)
        store.approve("one", "2", **OPERATOR)
        store.publish("one", "2", out=out)
        store.draft({"code_set": "gone", "name": "Gone"}, "1", CODES, created_by="test", **EXTRAS)
        store.approve("gone", "1", **OPERATOR)
        store.publish("gone", "1", out=out)
        store.retire("gone", "1")
        store.draft({"code_set": "two", "name": "Two"}, "1", CODES, created_by="test")  # a draft
        store.draft({"code_set": "three", "name": "Three"}, "1", CODES, created_by="test")
        store.approve("three", "1", **OPERATOR)  # approved, not published
        yield owner, runtime


def versions(engine):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT code_set || ' ' || version, count(*) FROM rdm.published_code GROUP BY 1")).all())


def test_only_the_published_version_appears(stores):
    _, runtime = stores
    assert versions(runtime) == {"one 2": 2}


def test_a_publish_leaves_only_its_version_in_every_table_and_a_retire_leaves_none(stores):
    owner, _ = stores
    with owner.connect() as conn:
        for table, set_column, version_column in VERSION_TABLES:
            held = {"one": set(), "gone": set()}
            for key, version in conn.execute(text(f"SELECT {set_column}, {version_column} FROM rdm.{table}")):
                if key in held:
                    held[key].add(version)
            assert held == {"one": {"2"}, "gone": set()}, table


def test_the_table_holds_exactly_the_views_rows(stores):
    _, runtime = stores
    with runtime.connect() as conn:
        assert conn.scalar(text(f"SELECT count(*) FROM (SELECT {COLUMNS} FROM rdm.code_context "
                                f"EXCEPT SELECT {COLUMNS} FROM rdm.published_code) d")) == 0
        assert conn.scalar(text(f"SELECT count(*) FROM (SELECT {COLUMNS} FROM rdm.published_code "
                                f"EXCEPT SELECT {COLUMNS} FROM rdm.code_context) d")) == 0


@pytest.mark.parametrize("statement", [
    "UPDATE rdm.published_code SET label = 'x'",
    "DELETE FROM rdm.published_code",
    "SELECT rdm.write_published_codes('one', '2')",  # already written
])
def test_a_written_row_is_never_changed_and_nothing_is_written_early(stores, statement):
    owner, runtime = stores
    with pytest.raises(DBAPIError, match="written once|duplicate key"):
        with owner.begin() as conn:
            conn.execute(text(statement))
    assert versions(runtime) == {"one 2": 2}


@pytest.mark.parametrize("change, message", [
    ("DELETE FROM rdm.code WHERE code_set = 'one'", "Only a draft"),
    ("DELETE FROM rdm.code_path WHERE code_set = 'one'", "Paths are written once"),
    ("DELETE FROM rdm.code_set_version WHERE code_set = 'one'", "Only a replaced or retired version is deleted"),
    ("UPDATE rdm.code SET label = 'x' WHERE code_set = 'one'", "Only a draft"),
])
def test_the_version_that_stays_cannot_be_deleted_or_changed(stores, change, message):
    owner, runtime = stores
    with pytest.raises(DBAPIError, match=message):
        with owner.begin() as conn:
            conn.execute(text(change))
    assert versions(runtime) == {"one 2": 2}


@pytest.mark.parametrize("statement", ["UPDATE rdm.published_code SET label = 'x'", "DELETE FROM rdm.published_code",
    "INSERT INTO rdm.published_code SELECT * FROM rdm.published_code"])
def test_the_runtime_cannot_write_the_table_directly(stores, statement):
    _, runtime = stores
    with pytest.raises(DBAPIError, match="permission denied"):
        with runtime.begin() as conn:
            conn.execute(text(statement))


def test_the_runtime_cannot_write_a_version_twice(stores):
    _, runtime = stores
    with pytest.raises(DBAPIError, match="duplicate key"):
        with runtime.begin() as conn:
            conn.execute(text("SELECT rdm.write_published_codes('one', '2')"))
    assert versions(runtime) == {"one 2": 2}


def test_an_approved_version_writes_nothing(stores):
    owner, runtime = stores
    with owner.begin() as conn:
        assert conn.scalar(text("SELECT rdm.write_published_codes('three', '1')")) == 0
    assert versions(runtime) == {"one 2": 2}


def test_a_populated_store_gets_its_rows_from_the_same_writer(stores):
    owner, runtime = stores
    with owner.begin() as conn:
        conn.execute(text("ALTER TABLE rdm.published_code DISABLE TRIGGER published_code_guard"))
        conn.execute(text("TRUNCATE rdm.published_code"))
        conn.execute(text("SELECT rdm.write_published_codes(code_set, version) FROM rdm.code_set_version "
                          "WHERE status IN ('published', 'retired')"))
        conn.execute(text("ALTER TABLE rdm.published_code ENABLE TRIGGER published_code_guard"))
    assert versions(runtime) == {"one 2": 2}
    undescribed = None
    with runtime.connect() as conn:
        undescribed = conn.scalars(text(
            "SELECT a.attname FROM pg_attribute a WHERE a.attrelid = 'rdm.published_code'::regclass AND a.attnum > 0 "
            "AND col_description(a.attrelid, a.attnum) IS NULL")).all()
    assert undescribed == []


def test_the_migration_fills_a_store_that_already_holds_published_and_retired_versions(stores):
    owner, runtime = stores
    sql = (database.MIGRATIONS / "001-published-code.sql").read_text()
    with owner.begin() as conn:
        conn.execute(text("DROP TABLE rdm.published_code"))
        conn.execute(text("DROP FUNCTION rdm.write_published_codes(text, text)"))
        conn.execute(text("DROP FUNCTION rdm.guard_published()"))
        conn.exec_driver_sql(sql.replace("%", "%%"))
    database.migrate(owner, runtime_role="rdm_runtime", existing_only=True)  # the grants follow the table
    assert versions(runtime) == {"one 2": 2}
