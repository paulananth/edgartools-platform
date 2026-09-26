"""Company mastering ticket 14: SEC's address countryCode reaches silver.

A foreign address carries its EDGAR country code in `countryCode` and leaves
`stateOrCountry` empty (Shell plc: "X0"). Silver dropped it, so the Company
matching rules could not see Shell's country. These tests hold the extractor
landing it, and hold every place one landing column must be named in step.
"""

from __future__ import annotations

from pathlib import Path

from edgar_warehouse import silver_schema
from edgar_warehouse.loaders.bronze_submission_extractors import stage_address_loader
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_landing_store import SilverLandingStore

REPO = Path(__file__).resolve().parents[2]

# Shell plc's business address as SEC writes it (bronze, CIK 0001306965).
SHELL = {
    "street1": "SHELL CENTRE",
    "street2": "YORK ROAD",
    "city": "LONDON",
    "stateOrCountry": None,
    "zipCode": "SE1 7NA",
    "stateOrCountryDescription": None,
    "isForeignLocation": 1,
    "foreignStateTerritory": "DC",
    "country": "United Kingdom",
    "countryCode": "X0",
}
APPLE = {
    "street1": "ONE APPLE PARK WAY",
    "street2": None,
    "city": "CUPERTINO",
    "stateOrCountry": "CA",
    "zipCode": "95014",
    "stateOrCountryDescription": "CA",
    "isForeignLocation": 0,
    "foreignStateTerritory": None,
    "country": None,
    "countryCode": None,
}


def _rows(business: dict) -> list[dict]:
    return stage_address_loader(
        {"addresses": {"business": business}}, 1306965, "run-1", "raw-1", "bootstrap"
    )


def test_a_foreign_address_lands_its_country_code():
    (row,) = _rows(SHELL)
    assert (row["state_or_country"], row["country_code"]) == (None, "X0")


def test_a_us_address_lands_its_state_and_no_country_code():
    (row,) = _rows(APPLE)
    assert (row["state_or_country"], row["country_code"]) == ("CA", None)


def test_an_address_without_the_key_lands_none():
    (row,) = _rows({"street1": "1 Main", "stateOrCountry": "NY"})
    assert row["country_code"] is None


def test_the_landing_row_keeps_the_country_code():
    landing = LandingExportBuffer()
    db = SilverLandingStore(landing_export=landing)
    try:
        db.stage_submission(
            cik=1306965,
            main_payload={
                "name": "Shell plc",
                "entityType": "other",
                "sic": "1311",
                "tickers": ["SHEL"],
                "addresses": {"business": SHELL},
                "filings": {"recent": {}},
            },
            pagination_payloads=[],
            sync_run_id="run-1",
            raw_object_id="raw-1",
            load_mode="bootstrap",
        )
        (row,) = landing.tables()["sec_company_address"]
    finally:
        db.close()
    assert row["country_code"] == "X0"


def test_every_place_a_landing_column_lives_names_country_code():
    columns = silver_schema.COLUMNS["sec_company_address"]
    assert columns[columns.index("country") + 1] == "country_code"
    bootstrap = REPO / "infra" / "snowflake" / "sql" / "bootstrap"
    create = (bootstrap / "11_silver_landing_schema.sql").read_text()
    table = create[create.index("CREATE TABLE IF NOT EXISTS sec_company_address") :]
    assert "country_code TEXT," in table[: table.index(");")]
    alter = (bootstrap / "21_silver_landing_company_country_code.sql").read_text()
    assert (
        "ALTER TABLE sec_company_address ADD COLUMN IF NOT EXISTS country_code TEXT;"
        in alter
    )
    model = (
        REPO
        / "infra/snowflake/dbt/edgartools_gold/models/silver/sec_company_address.sql"
    ).read_text()
    assert "    country_code,\n" in model
    install = (REPO / "infra" / "scripts" / "install.sh").read_text()
    run = "-f infra/snowflake/sql/bootstrap/"
    assert install.index(f"{run}21_silver_landing_company_country_code.sql") > (
        install.index(f"{run}20_silver_landing_ownership_evidence.sql")
    )
