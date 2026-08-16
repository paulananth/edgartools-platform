"""Generate the dbt silver layer's model SQL from the landing zone's real schema.

Companion to `infra/scripts/generate_silver_landing_ddl.py` (which generates
the landing-zone DDL these models read from) -- same anti-drift mechanism:
reflects `edgar_warehouse.silver_store._DDL` via an in-memory DuckDB
connection (columns via `information_schema.columns`, primary keys via
DuckDB's own `duckdb_constraints()`) rather than hand-transcribing column
lists that could silently drift from `silver_store.py`.

Design, per the silver-snowflake-migration wayfinder map:
- Ticket 01: every silver table is a uniform `dynamic_table`, current-state,
  one row per business key -- collapsed from the append-only landing zone
  via a `parse_sequence`-ordered window function. One exception:
  `sec_guidance_fact_reject` (a quarantine log with no natural key) stays
  append/log-shaped -- a plain view, not a collapsed dynamic table.
- Ticket 02: `parse_sequence` is the uniform tiebreak (`ORDER BY
  parse_sequence DESC` = "last write wins"), replacing the old per-table
  `authority_column` convention entirely.
- Ticket 06: the three accession-join ownership tables get an explicit
  `cik` column (the issuer's CIK) materialized via a join to
  `sec_company_filing`, so every downstream consumer doesn't have to
  independently rediscover that join path.

First-insert-wins/last-write-wins column split: three tables need it
(`sec_company_filing`, `sec_financial_fact`, `sec_financial_derived`), not
five -- verified by reading `silver_store.py`'s actual `_merge_rows_bulk`
call sites directly, not assumed from an earlier categorization.
`sec_adv_filing` and `sec_adv_private_fund` also use `_merge_rows_bulk`,
but their `insert_last_sql`'s `ON CONFLICT DO UPDATE SET` clause updates
*every* non-key column (including columns like `cik` that read as if they
should be immutable) -- there is no first-insert-wins column left for
either table in practice, so they collapse via the same plain
last-write-wins pattern as every other non-split table. `_SPLIT_TABLES`
below cites the exact source lines this was read from, so a future
`silver_store.py` change to these merge functions has something concrete
to diff against.

Usage:
    uv run python infra/scripts/generate_silver_dbt_models.py \
        --out-dir infra/snowflake/dbt/edgartools_gold/models/silver

Safe to re-run: overwrites the generated .sql files in --out-dir
deterministically from the current silver_store.py schema. Files are
committed (dbt has no runtime introspection of silver_store.py), so
regenerate and diff before re-applying if the schema has changed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb

from edgar_warehouse import silver_store
from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY

SOURCE_NAME = "edgartools_silver_landing"

# Mirrors generate_silver_landing_ddl.py's scope exactly -- see that
# generator's module docstring for why pipeline_run_lease is excluded and
# sec_guidance_fact_reject is included beyond PROTECTED_TABLE_REGISTRY.
_EXCLUDED = {"pipeline_run_lease"}
_INCLUDED_BEYOND_REGISTRY = {"sec_guidance_fact_reject"}

# Passthrough tables: no natural key, every row already final. A plain view
# over landing, not a collapsed dynamic_table (Ticket 01's Answer).
_PASSTHROUGH_TABLES = {"sec_guidance_fact_reject"}

# First-insert-wins (immutable-on-conflict) columns per table, read directly
# from silver_store.py's insert_last_sql ON CONFLICT DO UPDATE SET clauses
# (a column absent from that clause is first-insert-wins by construction --
# _merge_rows_bulk's docstring, silver_store.py:4262-4283). Every other
# non-key column for these tables is last-write-wins.
_SPLIT_TABLES = {
    # merge_filings, silver_store.py:1581-1680. UPDATE SET (mutable): form,
    # filing_date, report_date, acceptance_datetime, size, is_xbrl,
    # is_inline_xbrl, primary_document, primary_doc_desc, last_sync_run_id,
    # last_synced_at. NOT in UPDATE SET (immutable): cik, act, file_number,
    # film_number, items.
    "sec_company_filing": {"cik", "act", "file_number", "film_number", "items"},
    # merge_financial_facts, silver_store.py:3765-3826. UPDATE SET
    # (mutable): value, decimals, parser_version (+ ingested_at, not staged
    # data). NOT in UPDATE SET (immutable): fiscal_year, form_type, unit.
    "sec_financial_fact": {"fiscal_year", "form_type", "unit"},
    # merge_financial_derived, silver_store.py:3828-3975. UPDATE SET
    # (mutable): every metric column + parser_version (+ ingested_at). NOT
    # in UPDATE SET (immutable): fiscal_year, form_type.
    "sec_financial_derived": {"fiscal_year", "form_type"},
}

# Ticket 06: accession-join tables get an explicit issuer `cik` column
# materialized via a join to sec_company_filing, keyed on accession_number
# (confirmed collision-free: none of these three tables has an existing
# `cik`-named column of its own -- owner_cik on sec_ownership_reporting_owner
# is a different concept, the insider's CIK, not the issuer's).
_CIK_ENRICHED_TABLES = {
    "sec_ownership_reporting_owner",
    "sec_ownership_non_derivative_txn",
    "sec_ownership_derivative_txn",
}

# Columns needing "last non-null wins" instead of plain "last row wins" --
# found while reading silver_store.py directly, not from an earlier
# categorization (the same discipline that already caught the
# pipeline_run_lease/sec_guidance_fact_reject gaps in the landing generator).
# merge_accounting_flags (silver_store.py:4066-4098) uses
# COALESCE(excluded.X, sec_accounting_flag.X) for these three forensic score
# columns specifically, so an incoming NULL never clobbers an existing score
# -- and update_accounting_flag_scores (silver_store.py:4100-4129), a
# separate backfill call that arrives *after* the initial merge and only
# ever carries these three columns (every other column NULL in that landing
# row), depends on this exact semantic to not wipe out the rest of the row.
# A plain "value from the single latest parse_sequence row" collapse would
# silently lose the backfilled scores whenever a later, unrelated parse
# event for the same key doesn't happen to carry them -- expressed instead
# via LAST_VALUE(col IGNORE NULLS) OVER (... ORDER BY parse_sequence),
# evaluated at the same QUALIFY-selected latest row.
_COALESCE_PRESERVING_COLUMNS = {
    "sec_accounting_flag": {"beneish_m_score", "altman_z_score", "piotroski_f_score"},
    # mdm-ahead-of-silver map, Phase B, Ticket 06: the backfill sweep
    # (edgar_warehouse/mdm_entity_backfill.py) writes a thin landing row --
    # business key + mdm_entity_id only, every other column absent from the
    # Parquet -- exactly the same shape as update_accounting_flag_scores'
    # partial row above. Without this, mdm_entity_id would collapse via the
    # default "value from the single latest parse_sequence row" rule and the
    # sweep's thin append would null out every other column for that key.
    "sec_company": {"mdm_entity_id"},
    "sec_ownership_reporting_owner": {"mdm_entity_id"},
    "sec_ownership_non_derivative_txn": {"mdm_entity_id"},
    "sec_ownership_derivative_txn": {"mdm_entity_id"},
    "sec_adv_filing": {"mdm_entity_id"},
    "sec_adv_private_fund": {"mdm_entity_id"},
}


def _reflect_tables() -> dict[str, dict]:
    """Execute silver_store._DDL in-memory; reflect columns + PK per table."""
    con = duckdb.connect(":memory:")
    con.execute(silver_store._DDL)
    wanted = (set(PROTECTED_TABLE_REGISTRY.keys()) | _INCLUDED_BEYOND_REGISTRY) - _EXCLUDED

    found = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT table_name FROM information_schema.columns WHERE table_schema = 'main'"
        ).fetchall()
    }
    missing = wanted - found
    if missing:
        raise RuntimeError(f"Landing-scoped tables not found in silver_store._DDL: {sorted(missing)}")

    pk_by_table: dict[str, list[str]] = {}
    for table, constraint_type, cols in con.execute(
        "SELECT table_name, constraint_type, constraint_column_names FROM duckdb_constraints() "
        "WHERE constraint_type = 'PRIMARY KEY'"
    ).fetchall():
        pk_by_table[table] = list(cols)

    tables: dict[str, dict] = {}
    for table in sorted(wanted):
        columns = [
            name
            for name, in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
        ]
        tables[table] = {"columns": columns, "pk": pk_by_table.get(table, [])}

    for table in _SPLIT_TABLES:
        if table not in tables:
            raise RuntimeError(f"_SPLIT_TABLES references unknown table {table!r}")
        if not tables[table]["pk"]:
            raise RuntimeError(f"_SPLIT_TABLES table {table!r} has no reflected primary key")
    for table in _CIK_ENRICHED_TABLES:
        if table not in tables:
            raise RuntimeError(f"_CIK_ENRICHED_TABLES references unknown table {table!r}")
        if "cik" in tables[table]["columns"]:
            raise RuntimeError(
                f"{table!r} already has a 'cik' column -- the Ticket 06 enrichment join "
                "would collide with it. Resolve the naming clash before regenerating."
            )
    return tables


def _model_body_simple(table: str, columns: list[str], pk: list[str]) -> str:
    coalesce_cols = _COALESCE_PRESERVING_COLUMNS.get(table, set())
    partition = ", ".join(pk)
    select_lines = []
    for col in columns:
        if col in coalesce_cols:
            select_lines.append(
                f"last_value({col} ignore nulls) over ("
                f"partition by {partition} order by parse_sequence"
                f") as {col}"
            )
        else:
            select_lines.append(col)
    col_list = ",\n    ".join(select_lines)
    comment = ""
    if coalesce_cols:
        comment = (
            f"-- {', '.join(sorted(coalesce_cols))}: last non-null wins, not last row wins --\n"
            f"-- see generate_silver_dbt_models.py's _COALESCE_PRESERVING_COLUMNS for the citation.\n"
        )
    return f"""{comment}select
    {col_list}
from {{{{ source('{SOURCE_NAME}', '{table.upper()}') }}}}
qualify row_number() over (
    partition by {partition}
    order by parse_sequence desc
) = 1
"""


def _model_body_split(table: str, columns: list[str], pk: list[str], immutable: set[str]) -> str:
    non_key = [c for c in columns if c not in pk]
    immutable_cols = [c for c in non_key if c in immutable]
    mutable_cols = [c for c in non_key if c not in immutable]
    partition = ", ".join(pk)
    join_cond = " and ".join(f"f.{k} = l.{k}" for k in pk)
    first_select = ",\n    ".join(pk + immutable_cols)
    last_select = ",\n    ".join(pk + mutable_cols)
    final_select = ",\n    ".join(
        [f"f.{k}" for k in pk] + [f"f.{c}" for c in immutable_cols] + [f"l.{c}" for c in mutable_cols]
    )
    return f"""-- First-insert-wins ({', '.join(immutable_cols)}) from the earliest parse;
-- last-write-wins ({', '.join(mutable_cols)}) from the latest parse -- matches
-- silver_store.py's merge_{table.replace('sec_', '', 1)}-shaped two-pass upsert
-- exactly (see generate_silver_dbt_models.py's _SPLIT_TABLES for the citation).
with first_seen as (
    select
    {first_select}
    from {{{{ source('{SOURCE_NAME}', '{table.upper()}') }}}}
    qualify row_number() over (partition by {partition} order by parse_sequence asc) = 1
),
last_seen as (
    select
    {last_select}
    from {{{{ source('{SOURCE_NAME}', '{table.upper()}') }}}}
    qualify row_number() over (partition by {partition} order by parse_sequence desc) = 1
)
select
    {final_select}
from first_seen f
join last_seen l
    on {join_cond}
"""


def _model_body_passthrough(table: str) -> str:
    return f"""-- Quarantine log, no natural key -- every row is already final, so this
-- is a plain passthrough view, not a collapsed dynamic_table (Ticket 01's
-- Answer). parse_sequence is kept for audit ordering.
select *
from {{{{ source('{SOURCE_NAME}', '{table.upper()}') }}}}
"""


def _apply_cik_enrichment(table: str, base_sql: str) -> str:
    return f"""-- Ticket 06: materializes the issuer's cik here, via a join to
-- sec_company_filing, so downstream consumers (gold, MDM) don't each have
-- to independently know this table needs an accession-number join to
-- resolve issuer CIK (sec_adv_filing.cik-is-NULL-for-ADV-data is the same
-- failure shape this is deliberately avoiding a repeat of).
with collapsed as (
{base_sql.rstrip()}
)
select
    collapsed.*,
    company_filing.cik
from collapsed
left join {{{{ ref('sec_company_filing') }}}} as company_filing
    on company_filing.accession_number = collapsed.accession_number
"""


def generate_model(table: str, info: dict) -> str:
    columns, pk = info["columns"], info["pk"]
    alias = table.upper()

    if table in _PASSTHROUGH_TABLES:
        config_line = f"{{{{ config(alias='{alias}', materialized='view') }}}}"
        body = _model_body_passthrough(table)
    elif table in _SPLIT_TABLES:
        config_line = f"{{{{ silver_model_config('{alias}') }}}}"
        body = _model_body_split(table, columns, pk, _SPLIT_TABLES[table])
    else:
        config_line = f"{{{{ silver_model_config('{alias}') }}}}"
        body = _model_body_simple(table, columns, pk)
        if table in _CIK_ENRICHED_TABLES:
            body = _apply_cik_enrichment(table, body)

    header = (
        f"-- Auto-generated by infra/scripts/generate_silver_dbt_models.py -- do not hand-edit.\n"
        f"-- Reflects edgar_warehouse.silver_store._DDL's {table} table. Regenerate and diff\n"
        f"-- before re-applying if silver_store.py's schema has changed.\n\n"
    )
    return header + config_line + "\n\n" + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("infra/snowflake/dbt/edgartools_gold/models/silver"),
    )
    args = parser.parse_args()

    tables = _reflect_tables()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for table, info in tables.items():
        sql = generate_model(table, info)
        (args.out_dir / f"{table}.sql").write_text(sql)

    sys.stderr.write(f"Generated {len(tables)} silver model files in {args.out_dir}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
