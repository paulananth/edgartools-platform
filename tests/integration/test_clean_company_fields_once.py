"""A Company version keeps its chosen fields once, in its body (015)."""

from pathlib import Path

from sqlalchemy import text

from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database
MIGRATIONS = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"
FIELDS = "SELECT * FROM mdm.company_master_field ORDER BY entity_id, field_name"


def company(database, n, name):
    found = core.source("fields-once", revision=n, fields={"name": name, "address": {"city": "Boston"}},
                        identifiers={"cik": "42"})
    if n == 1:
        identity, binding = core.identity_and_binding(found)
        core.apply(database, n, assertions=[found], identities=[identity], decisions=[binding])
    else:
        core.apply(database, n, assertions=[found])


def test_a_company_has_no_second_copy_of_its_fields(database):
    company(database, 1, "Acme")
    with database.application.connect() as conn:
        columns = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='mdm' AND table_name='company'"))}
        assert "fields" not in columns and "body" in columns
        (row,) = conn.execute(text(FIELDS + " LIMIT 1")).mappings().all() or [None]
    assert row is not None


def test_versions_stored_before_read_the_same_after(database):
    """A populated store: Company versions written with `company.fields` (before 015)
    give the same `company_master_field` rows once 015 has dropped the column."""
    baseline = (MIGRATIONS / "001_mdm.sql").read_text()
    start = baseline.index("CREATE FUNCTION mdm.record_company_version(")
    old_fn = baseline[start:baseline.index("$$;\n", start) + 4].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    # 017 changed both functions; the store before 015 had 014's write_batch.
    later = (MIGRATIONS / "014_outbox_names_batch.sql").read_text()
    start = later.index("CREATE OR REPLACE FUNCTION mdm.write_batch(")
    old_batch = later[start:later.index("$$;\n", start) + 4]
    start = baseline.index("CREATE VIEW mdm.company_master_field AS")
    old_view = baseline[start:baseline.index(";", baseline.index("WHERE (c.valid_to IS NULL)", start)) + 1]
    with database.admin.begin() as conn:
        conn.exec_driver_sql("DROP VIEW mdm.company_master_field")
        conn.exec_driver_sql("ALTER TABLE mdm.company ADD COLUMN fields jsonb")
        conn.exec_driver_sql("DROP FUNCTION mdm.record_company_version(jsonb, text, timestamp with time zone)")
        conn.exec_driver_sql(old_fn.replace("%", "%%"))  # psycopg2 formats a bare %
        conn.exec_driver_sql(old_batch.replace("%", "%%"))
        conn.exec_driver_sql(old_view)
    company(database, 1, "Acme")
    company(database, 2, "Acme Holdings")
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company WHERE fields = body->'fields'")) == 2
        before = [dict(r) for r in conn.execute(text(FIELDS)).mappings()]
    with database.admin.begin() as conn:
        conn.execute(text((MIGRATIONS / "015_company_fields_once.sql").read_text()))
        conn.execute(text((MIGRATIONS / "017_unchanged_batch_no_outbox.sql").read_text()))
    with database.admin.connect() as conn:
        after = [dict(r) for r in conn.execute(text(FIELDS)).mappings()]
    assert before and after == before
    company(database, 3, "Acme Group")
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company")) == 3
        assert conn.scalar(text("SELECT field_value FROM mdm.company_master_field WHERE field_name='name'")) == "Acme Group"
