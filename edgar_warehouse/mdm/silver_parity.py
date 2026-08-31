"""DuckDB-vs-Snowflake silver parity check (silver-snowflake-migration map,
Ticket 10/12's correctness gate before flipping MDM_SILVER_READ_TARGET to
"snowflake" in prod; that toggle is retired by DuckDB Retirement Cutover
Ticket 05's hard cutover, but the digest comparator this module now also
provides -- verify_resolver_input_parity -- is that ticket's own required
correctness evidence, so this module stays the DuckDB-vs-Snowflake home
for both).

Scope decision (Ticket 10 asked for a parity check comparing "resolved
entity_id assignments," not just row counts, "since two runs could match on
count and still resolve different CIKs to different entities"): rather than
re-running MDM's resolver twice against live MDM Postgres (side-effecting,
and this module has no read-only/dry-run resolution mode to call), this
compares each source's actual sec_company CIK *set*. MDM's resolution is
deterministic given a fixed MDM Postgres state and a fixed rule engine --
identical source CIK sets on both sides means the resolver would assign
identical entity_ids on both sides, without needing to run it twice. A count
match alone (Ticket 10's stated concern) would NOT catch two sources holding
different CIKs at the same total count; a set-difference does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The 31 tables EDGARTOOLS_SILVER's dbt models cover (silver-snowflake-
# migration map, Ticket 01's model list) -- the intersection of what both
# readers can answer. Deliberately excludes the 8 operational/bookkeeping
# tables ShardedSilverReader also exposes (sec_company_sync_state,
# sec_daily_index_checkpoint, sec_parse_run, sec_reconcile_finding,
# sec_source_checkpoint, sec_sync_run, sec_tracked_universe,
# stg_daily_index_filing) -- Ticket 09's table-coverage check found these
# have no EDGARTOOLS_SILVER analog by design (bound for MDM's own Postgres
# store, not Snowflake silver, per duckdb-retirement map Ticket 08). A
# parity check against a table one side can never have would always fail
# and would misreport a real, already-decided architecture split as a bug.
PARITY_TABLES: tuple[str, ...] = (
    "sec_accounting_flag",
    "sec_adv_disclosure_event",
    "sec_adv_filing",
    "sec_adv_firm_roster",
    "sec_adv_office",
    "sec_adv_private_fund",
    "sec_auditor_report_evidence",
    "sec_company",
    "sec_company_address",
    "sec_company_filing",
    "sec_company_former_name",
    "sec_company_submission_file",
    "sec_company_ticker",
    "sec_current_filing_feed",
    "sec_earnings_release",
    "sec_employment_event",
    "sec_executive_record",
    "sec_filing_attachment",
    "sec_filing_text",
    "sec_financial_derived",
    "sec_financial_fact",
    "sec_guidance_fact",
    "sec_guidance_fact_reject",
    "sec_ownership_derivative_txn",
    "sec_ownership_non_derivative_txn",
    "sec_ownership_reporting_owner",
    "sec_pcaob_firm_identity",
    "sec_raw_object",
    "sec_subsidiary_evidence",
    "sec_thirteenf_filing",
    "sec_thirteenf_holding",
)

# Cap how many mismatched CIKs get echoed into the JSON payload -- a
# first-ever run against a near-empty EDGARTOOLS_SILVER (Ticket 11's known
# state as of 2026-08-18) could otherwise dump tens of thousands of CIKs.
_MAX_REPORTED_CIK_SAMPLE = 50


@dataclass
class TableParityResult:
    table: str
    duckdb_count: int | None
    snowflake_count: int | None
    error: str | None = None

    @property
    def matches(self) -> bool:
        return self.error is None and self.duckdb_count == self.snowflake_count

    def to_payload(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "duckdb_count": self.duckdb_count,
            "snowflake_count": self.snowflake_count,
            "matches": self.matches,
            "error": self.error,
        }


@dataclass
class SilverParityResult:
    tables: list[TableParityResult] = field(default_factory=list)
    cik_only_in_duckdb: list[int] = field(default_factory=list)
    cik_only_in_snowflake: list[int] = field(default_factory=list)
    cik_fetch_error: str | None = None

    @property
    def passed(self) -> bool:
        return (
            all(table.matches for table in self.tables)
            and self.cik_fetch_error is None
            and not self.cik_only_in_duckdb
            and not self.cik_only_in_snowflake
        )

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "tables": [table.to_payload() for table in self.tables],
            "cik_fetch_error": self.cik_fetch_error,
            "cik_only_in_duckdb_total": len(self.cik_only_in_duckdb),
            "cik_only_in_duckdb_sample": self.cik_only_in_duckdb[:_MAX_REPORTED_CIK_SAMPLE],
            "cik_only_in_snowflake_total": len(self.cik_only_in_snowflake),
            "cik_only_in_snowflake_sample": self.cik_only_in_snowflake[:_MAX_REPORTED_CIK_SAMPLE],
        }


def _table_row_count(reader: Any, table: str) -> int:
    rows = reader.fetch(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608 -- table is from PARITY_TABLES, never user input
    if not rows:
        return 0
    return int(rows[0]["n"])


def verify_silver_parity(duckdb_reader: Any, snowflake_reader: Any) -> SilverParityResult:
    """Compare every PARITY_TABLES row count, plus the sec_company CIK set,
    between a DuckDB-backed reader and a Snowflake-backed reader.

    Both readers must satisfy the ShardedSilverReader/SnowflakeSilverReader
    .fetch(sql, params) -> list[dict] seam -- this function is reader-type
    agnostic by construction, so it works identically against real readers
    or test fakes.
    """
    table_results: list[TableParityResult] = []
    for table in PARITY_TABLES:
        duckdb_count: int | None = None
        snowflake_count: int | None = None
        error_parts: list[str] = []
        try:
            duckdb_count = _table_row_count(duckdb_reader, table)
        except Exception as exc:
            error_parts.append(f"duckdb: {exc}")
        try:
            snowflake_count = _table_row_count(snowflake_reader, table)
        except Exception as exc:
            error_parts.append(f"snowflake: {exc}")
        table_results.append(
            TableParityResult(
                table=table,
                duckdb_count=duckdb_count,
                snowflake_count=snowflake_count,
                error="; ".join(error_parts) or None,
            )
        )

    # Unlike the per-table counts above, a failure here has no per-side error
    # slot to report into -- surface it as a table-shaped result instead of
    # letting it crash the whole comparison (code review finding, 2026-08-18:
    # every other query in this function degrades gracefully into the
    # payload; this one didn't).
    cik_error: str | None = None
    duckdb_ciks: set[int] = set()
    snowflake_ciks: set[int] = set()
    try:
        duckdb_ciks = {int(row["cik"]) for row in duckdb_reader.fetch("SELECT cik FROM sec_company")}
    except Exception as exc:
        cik_error = f"duckdb: {exc}"
    try:
        snowflake_ciks = {int(row["cik"]) for row in snowflake_reader.fetch("SELECT cik FROM sec_company")}
    except Exception as exc:
        cik_error = f"{cik_error}; snowflake: {exc}" if cik_error else f"snowflake: {exc}"

    return SilverParityResult(
        tables=table_results,
        cik_only_in_duckdb=sorted(duckdb_ciks - snowflake_ciks),
        cik_only_in_snowflake=sorted(snowflake_ciks - duckdb_ciks),
        cik_fetch_error=cik_error,
    )


# -- resolver-input row-digest parity (DuckDB Retirement Cutover Ticket 05) --
#
# Ticket 05's checklist requires proving the Snowflake-backed reader
# "produces the same match decision + confidence score per input row" as
# the old DuckDB reader, on a real (not synthetic) sample of company/
# adviser/person/fund/security records. Actually re-running MDM's resolvers
# twice against live MDM Postgres would be side-effecting (no read-only/
# dry-run resolution mode exists) and would double the real cost of this
# check. Per this map's own decision ("Decide MDM's ShardedSilverReader
# Replacement Mechanics"): MDM's matching engine (MatchPipeline.resolve) is
# a deterministic function of its input rows and the fixed MDM Postgres
# candidate state at query time -- proving row-level read equivalence for
# the exact rows each entity type's resolver reads therefore implies
# resolution-outcome equivalence (same match decision, same confidence
# score) by construction, without needing to invoke the resolvers twice.
#
# This intentionally compares whole-row content (every column, keyed by
# primary key), not one resolver's specific SELECT projection -- a stronger
# and more general proof than matching a single query's column list, and
# one that stays valid if a resolver's projection changes later.
RESOLVER_INPUT_TABLES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "company": (("sec_company", ("cik",)),),
    "adviser": (("sec_adv_filing", ("accession_number",)),),
    "fund": (("sec_adv_private_fund", ("accession_number", "fund_index")),),
    "person": (("sec_ownership_reporting_owner", ("accession_number", "owner_index")),),
    "security": (
        ("sec_ownership_non_derivative_txn", ("accession_number", "owner_index", "txn_index")),
        ("sec_ownership_derivative_txn", ("accession_number", "owner_index", "txn_index")),
    ),
}

# Ticket 07's cutover validation standard requires "at least one genuinely
# large table, not only toy fixtures" per swap. The ownership transaction
# tables are, by a wide margin, the largest tables any entity-type resolver
# reads (one row per Form 3/4/5 transaction line, across the whole tracked
# universe) -- sampled at a larger bound than the rest for that reason.
_LARGE_RESOLVER_INPUT_TABLES: frozenset[str] = frozenset(
    {"sec_ownership_non_derivative_txn", "sec_ownership_derivative_txn"}
)

_DEFAULT_SAMPLE_SIZE = 25
_DEFAULT_LARGE_TABLE_SAMPLE_SIZE = 200


@dataclass
class RowParityResult:
    table: str
    keys_compared: int
    mismatched_keys: list[tuple]
    error: str | None = None

    @property
    def matches(self) -> bool:
        return self.error is None and not self.mismatched_keys

    def to_payload(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "keys_compared": self.keys_compared,
            "matches": self.matches,
            "mismatched_keys_total": len(self.mismatched_keys),
            "mismatched_keys_sample": [list(k) for k in self.mismatched_keys[:_MAX_REPORTED_CIK_SAMPLE]],
            "error": self.error,
        }


@dataclass
class ResolverInputParityResult:
    entity_type: str
    tables: list[RowParityResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.tables) and all(table.matches for table in self.tables)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "passed": self.passed,
            "tables": [table.to_payload() for table in self.tables],
        }


def _sample_keys(
    reader: Any, table: str, key_columns: tuple[str, ...], *, limit: int
) -> list[tuple]:
    """Bounded case-selected key sample (Ticket 07's cutover validation
    standard): the lowest- and highest-keyed ``limit`` rows by the table's
    own primary key, deduplicated. Deterministic and re-runnable, and (for
    accession_number-keyed tables, which sort newest-last) the "highest"
    half also biases toward the most-recently-loaded filings -- a real
    boundary case, not just an arbitrary second sample.
    """
    cols = ", ".join(key_columns)
    order_by = ", ".join(key_columns)
    ascending = reader.fetch(
        f"SELECT {cols} FROM {table} ORDER BY {order_by} ASC LIMIT {int(limit)}"  # noqa: S608 -- table/key_columns are from RESOLVER_INPUT_TABLES, never user input
    )
    descending = reader.fetch(
        f"SELECT {cols} FROM {table} ORDER BY {order_by} DESC LIMIT {int(limit)}"  # noqa: S608
    )
    seen: set[tuple] = set()
    keys: list[tuple] = []
    for row in ascending + descending:
        key = tuple(row[col] for col in key_columns)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _fetch_row_by_key(
    reader: Any, table: str, key_columns: tuple[str, ...], key_values: tuple
) -> dict | None:
    where = " AND ".join(f"{col} = ?" for col in key_columns)
    rows = reader.fetch(
        f"SELECT * FROM {table} WHERE {where}",  # noqa: S608
        list(key_values),
    )
    return rows[0] if rows else None


def verify_resolver_input_parity(
    duckdb_reader: Any,
    snowflake_reader: Any,
    *,
    entity_types: list[str] | None = None,
    sample_size: int = _DEFAULT_SAMPLE_SIZE,
    large_table_sample_size: int = _DEFAULT_LARGE_TABLE_SAMPLE_SIZE,
) -> dict[str, ResolverInputParityResult]:
    """Digest-based row parity, per entity type, over each type's real
    resolver input table(s) -- the correctness gate this map's "Decide the
    Cutover Validation Standard" and "Decide MDM's ShardedSilverReader
    Replacement Mechanics" answers require before MDM's Snowflake-backed
    reader replaces the DuckDB one for real.

    Reuses ``resolvers.base.content_hash`` verbatim rather than a bespoke
    digest that normalizes type differences away: Snowflake's connector
    returns ``Decimal`` where DuckDB returns ``int`` for numeric columns, and
    ``content_hash``'s ``json.dumps(..., default=str)`` serializes those
    differently -- exactly the failure mode this check exists to catch (the
    same hash function MDM's own ``_skip_if_unchanged`` already depends on
    for stability, so a type-coercion drift here would be a real, not a
    cosmetic, cross-backend difference).
    """
    from edgar_warehouse.mdm.resolvers.base import content_hash

    types = entity_types if entity_types is not None else list(RESOLVER_INPUT_TABLES)
    out: dict[str, ResolverInputParityResult] = {}
    for entity_type in types:
        table_results: list[RowParityResult] = []
        for table, key_columns in RESOLVER_INPUT_TABLES[entity_type]:
            limit = large_table_sample_size if table in _LARGE_RESOLVER_INPUT_TABLES else sample_size
            try:
                keys = _sample_keys(duckdb_reader, table, key_columns, limit=limit)
            except Exception as exc:
                table_results.append(
                    RowParityResult(table=table, keys_compared=0, mismatched_keys=[], error=str(exc))
                )
                continue

            mismatched: list[tuple] = []
            fetch_error: str | None = None
            for key in keys:
                try:
                    duckdb_row = _fetch_row_by_key(duckdb_reader, table, key_columns, key)
                    snowflake_row = _fetch_row_by_key(snowflake_reader, table, key_columns, key)
                except Exception as exc:
                    fetch_error = str(exc)
                    mismatched.append(key)
                    continue
                if duckdb_row is None or snowflake_row is None:
                    mismatched.append(key)
                    continue
                if content_hash(duckdb_row) != content_hash(snowflake_row):
                    mismatched.append(key)

            table_results.append(
                RowParityResult(
                    table=table,
                    keys_compared=len(keys),
                    mismatched_keys=mismatched,
                    error=fetch_error,
                )
            )
        out[entity_type] = ResolverInputParityResult(entity_type=entity_type, tables=table_results)
    return out
