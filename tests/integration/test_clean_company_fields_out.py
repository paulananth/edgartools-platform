"""Three Company columns leave MDM (026; ticket 129, fixes 2 and 3).

GLEIF's record-keeping dates and the SIC code's label are no longer Company
columns. A populated store keeps every stored version: its whole projection
stays in `body`, and the chosen fields read the same after the migration.
"""

from pathlib import Path

from sqlalchemy import text

from tests.integration import test_clean_mdm_postgres as core

MIGRATIONS = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"
GONE = ("sic_description", "gleif_last_update", "gleif_next_renewal")
FIELDS = "SELECT * FROM mdm.company_master_field ORDER BY entity_id, field_name"
VERSIONS = "SELECT entity_id, from_generation, body FROM mdm.company ORDER BY entity_id, from_generation"


def columns(conn) -> set[str]:
    return {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='mdm' AND table_name='company'"))}


def company(database, n, name):
    found = core.source("fields-out", revision=n, fields={"name": name}, identifiers={"cik": "42"})
    if n == 1:
        identity, binding = core.identity_and_binding(found)
        core.apply(database, n, assertions=[found], identities=[identity], decisions=[binding])
    else:
        core.apply(database, n, assertions=[found])


def test_a_company_has_none_of_the_three_columns(database):
    with database.application.connect() as conn:
        assert not set(GONE) & columns(conn)


def test_versions_stored_before_read_the_same_after(database):
    """A populated store: versions written by 017's writer, with the three columns
    filled, keep their bodies and chosen fields once 026 has dropped them."""
    later = (MIGRATIONS / "017_unchanged_batch_no_outbox.sql").read_text()
    start = later.index("CREATE FUNCTION mdm.record_company_version(")
    old_fn = later[start:later.index("$$;\n", start) + 4].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    with database.admin.begin() as conn:
        for name in GONE:
            conn.exec_driver_sql(f"ALTER TABLE mdm.company ADD COLUMN {name} text")
        conn.exec_driver_sql(old_fn.replace("%", "%%"))  # psycopg2 formats a bare %
    company(database, 1, "Acme")
    company(database, 2, "Acme Holdings")
    # The fixture policy chooses name and address only; fill the three columns
    # as a store that chose them holds them.
    with database.admin.begin() as conn:
        conn.exec_driver_sql("UPDATE mdm.company SET sic_description='An invented label', "
                             "gleif_last_update='2026-01-01T00:00:00Z', gleif_next_renewal='2027-01-01T00:00:00Z'")
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company WHERE gleif_last_update IS NOT NULL")) == 2
        versions = [dict(r) for r in conn.execute(text(VERSIONS)).mappings()]
        before = [dict(r) for r in conn.execute(text(FIELDS)).mappings()]
    with database.admin.begin() as conn:
        conn.execute(text((MIGRATIONS / "026_company_fields_out.sql").read_text()))
    with database.admin.connect() as conn:
        assert not set(GONE) & columns(conn)
        assert [dict(r) for r in conn.execute(text(VERSIONS)).mappings()] == versions
        assert [dict(r) for r in conn.execute(text(FIELDS)).mappings()] == before
    company(database, 3, "Acme Group")
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company")) == 3
        assert conn.scalar(text(
            "SELECT field_value FROM mdm.company_master_field WHERE field_name='name'")) == "Acme Group"
