"""DuckDB-vs-Snowflake silver parity check (silver-snowflake-migration map,
Ticket 10/12's correctness gate before flipping MDM_SILVER_READ_TARGET to
"snowflake" in prod).

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
