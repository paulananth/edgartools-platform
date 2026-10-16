"""edgar_warehouse/silver_schema.py is the hand-maintained source of each
landing table's column order and NOT NULL set (silver-merge-engine-migration
Ticket 13; hand-maintained since Ticket 17 deleted the engine it was
generated from).

One guard: the snapshot must equal
infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql, the hand-
maintained landing DDL. This repo has already lost a schema's generator
twice (that landing DDL, the MDM mirror schema), so the snapshot is never
left with nothing checking it.
"""

from __future__ import annotations

import re
from pathlib import Path

from edgar_warehouse import silver_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
LANDING_SQL = REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap" / "11_silver_landing_schema.sql"



def _landing_sql_columns() -> dict[str, list[tuple[str, bool]]]:
    """(column, not_null) per landing table, in DDL order, parse_sequence dropped.
    Snowflake forces NOT NULL on PRIMARY KEY columns; the landing DDL keeps
    parse_sequence as the sole PK and DROPs its NOT NULL, so NOT NULL here
    comes only from the column's own declaration."""
    out: dict[str, list[tuple[str, bool]]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", LANDING_SQL.read_text(), re.DOTALL
    ):
        columns = []
        for raw in match.group(2).split("\n"):
            line = raw.split("--")[0].strip().lstrip(",").strip()
            if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE")):
                continue
            columns.append((line.split()[0].lower(), "NOT NULL" in line.upper()))
        out[match.group(1).lower()] = [c for c in columns if c[0] != "parse_sequence"]
    return out


def test_snapshot_covers_exactly_the_landing_tables():
    assert set(silver_schema.COLUMNS) == set(_landing_sql_columns())
    assert set(silver_schema.REQUIRED) == set(silver_schema.COLUMNS)


def test_snapshot_columns_match_the_landing_ddl_in_order():
    for table, landing_columns in _landing_sql_columns().items():
        assert list(silver_schema.COLUMNS[table]) == [c for c, _ in landing_columns], table


def test_snapshot_required_matches_the_landing_ddl_not_null():
    """The half that gates every write: _record_landing_passthrough raises on
    a row missing a REQUIRED column, so REQUIRED must be what Snowflake will
    reject too."""
    for table, landing_columns in _landing_sql_columns().items():
        landing_required = [c for c, not_null in landing_columns if not_null]
        assert list(silver_schema.REQUIRED[table]) == landing_required, table


def test_every_table_requires_something():
    """A table with no NOT NULL column would make the passthrough's guard a
    no-op for it; every landing table keys on cik or accession_number."""
    for table, required in silver_schema.REQUIRED.items():
        assert required, table
        assert set(required) <= set(silver_schema.COLUMNS[table]), table


def test_snapshot_mappings_are_read_only():
    import pytest

    for mapping in (silver_schema.COLUMNS, silver_schema.REQUIRED):
        with pytest.raises(TypeError):
            mapping["sec_company"] = ()  # type: ignore[index]


def test_every_dbt_silver_model_selects_its_landing_columns():
    """Each silver model names every column its landing table has, so a new
    landing column (as `country_code` was, company mastering ticket 14) cannot
    land and then be dropped by its silver model. A model that selects `*`
    passes everything through and is not checked."""
    models = REPO_ROOT / "infra" / "snowflake" / "dbt" / "edgartools_gold" / "models" / "silver"
    checked = 0
    for path in sorted(models.glob("*.sql")):
        text = re.sub(r"--[^\n]*", "", path.read_text())
        source = re.search(r"source\('edgartools_silver_landing',\s*'(\w+)'\)", text)
        assert source, path.name
        if re.search(r"select\s+\*", text, re.IGNORECASE):
            continue
        columns = silver_schema.COLUMNS[source.group(1).lower()]
        missing = [c for c in columns if not re.search(rf"\b{c}\b", text)]
        assert missing == [], f"{path.name} does not select {missing}"
        checked += 1
    assert checked >= 30
    assert "country_code" in silver_schema.COLUMNS["sec_company_address"]


def test_a_live_table_gains_the_column_before_dbt_reads_it():
    bootstrap = REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap"
    alter = (bootstrap / "21_silver_landing_company_country_code.sql").read_text()
    assert "ALTER TABLE sec_company_address ADD COLUMN IF NOT EXISTS country_code TEXT;" in alter
    install = (REPO_ROOT / "infra" / "scripts" / "install.sh").read_text()
    run = "-f infra/snowflake/sql/bootstrap/"
    assert install.index(f"{run}21_silver_landing_company_country_code.sql") > (
        install.index(f"{run}20_silver_landing_ownership_evidence.sql"))
    assert install.index(f"{run}21_silver_landing_company_country_code.sql") < install.index("dbt run --target")
