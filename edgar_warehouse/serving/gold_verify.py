"""Verify that EDGARTOOLS_GOLD's dynamic tables are actually populated.

Snowflake-env-provisioning map, Ticket 06 ("Decide what 'fully live' is
verified by"): every other domain (MDM connectivity, graph parity, AWS
E2E) had an automated pass/fail check before this existed; gold's own
go-live stage only echoed a reminder for the operator to check row counts
by hand, so nothing failed the install if gold never actually populated.
This closes that gap as a standalone, independently runnable check --
callable from install.sh's gold-refresh stage, but not dependent on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The 21 EDGARTOOLS_GOLD dynamic tables built by dbt's gold_model_config
# macro (infra/snowflake/dbt/edgartools_gold/models/gold/*.sql, confirmed via
# grep for gold_model_config('...') calls). Deliberately excludes
# edgartools_gold_status and mdm_company: both are `materialized='view'`
# (edgartools_gold_status inherits dbt_project.yml's project-level default
# for models/gold/; mdm_company sets it explicitly as a compat view over
# MDM_COMPANY_ENTITY) -- neither is an independent dynamic table with its
# own populated state to verify.
#
# Older references elsewhere in this repo (CLAUDE.md, 08_loader_role.sql's
# GRANT OWNERSHIP list) say "20 gold dynamic tables" -- ADV_FUND_COUNT_
# RECONCILIATION is a newer addition (.scratch/adv-firm-roster-crosscheck/)
# not yet reflected there. This list is grep-derived from the live dbt
# models directory, the authoritative source, not copied from those older
# references.
GOLD_LIVE_TABLES: tuple[str, ...] = (
    "ACCOUNTING_FLAGS",
    "ADVISER_DISCLOSURES",
    "ADVISER_OFFICES",
    "ADV_FUND_COUNT_RECONCILIATION",
    "COMPANY",
    "CONSENSUS_ESTIMATES",
    "EARNINGS_CALENDAR",
    "EARNINGS_RELEASES",
    "EXECUTIVE_RECORDS",
    "FILING_ACTIVITY",
    "FILING_DETAIL",
    "FINANCIAL_DERIVED",
    "FINANCIAL_FACTORS",
    "FINANCIAL_FACTS",
    "GUIDANCE_FACTS",
    "INSTITUTIONAL_HOLDINGS",
    "OWNERSHIP_ACTIVITY",
    "OWNERSHIP_HOLDINGS",
    "PRIVATE_FUNDS",
    "TICKER_REFERENCE",
    "TRANSCRIPT_EVENTS",
)


@dataclass(frozen=True)
class GoldLiveVerificationResult:
    passed: bool
    database: str
    schema: str
    row_counts: dict[str, int] = field(default_factory=dict)
    empty_tables: tuple[str, ...] = ()
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "schema": self.schema,
            "empty_tables": list(self.empty_tables),
            "errors": dict(self.errors),
            "passed": self.passed,
            "row_counts": dict(self.row_counts),
            "tables_checked": len(self.row_counts),
        }


def verify_gold_live(
    connection: Any,
    *,
    database: str,
    schema: str = "EDGARTOOLS_GOLD",
    tables: tuple[str, ...] = GOLD_LIVE_TABLES,
) -> GoldLiveVerificationResult:
    """Query row counts for every expected EDGARTOOLS_GOLD dynamic table.

    Fails (``passed=False``) if any expected table is empty *or* missing --
    a query error (table doesn't exist, not authorized) is itself a
    verification failure, not a tool error to propagate: an incomplete
    deploy on a brand-new account is exactly the failure mode this command
    exists to catch, and one table's query error should not stop the rest
    from being checked.
    """
    row_counts: dict[str, int] = {}
    empty_tables: list[str] = []
    errors: dict[str, str] = {}
    cursor = connection.cursor()
    try:
        for table in tables:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{database}"."{schema}"."{table}"')
                count = int(cursor.fetchone()[0])
            except Exception as exc:  # noqa: BLE001 - any driver error is a check failure, not a crash
                errors[table] = str(exc)
                count = 0
            row_counts[table] = count
            if count == 0:
                empty_tables.append(table)
    finally:
        cursor.close()

    return GoldLiveVerificationResult(
        passed=not empty_tables,
        database=database,
        schema=schema,
        row_counts=row_counts,
        empty_tables=tuple(empty_tables),
        errors=errors,
    )
