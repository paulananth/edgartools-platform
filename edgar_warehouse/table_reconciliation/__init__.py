"""Table-Specific Reconciliation tooling for the DuckDB Retirement Cutover
(Ticket 08): proves, per table, bronze-to-silver key expectations, declared
primary-key uniqueness, required-parent integrity, and a canonical
semantic-content digest match between DuckDB canonical and Snowflake
``EDGARTOOLS_SILVER`` -- reusing this repo's Production Release Readiness
vocabulary (see ``docs/release-readiness/maxconcurrency4-data-integrity-
proof.md`` and ``CONTEXT.md``) rather than a bespoke one.

Public entry points:

- ``contracts.TABLE_CONTRACTS`` -- per-table declared keys/parents/cardinality.
- ``collector.reconcile_table`` -- runs all four checks for one table.
- ``report.build_report`` -- runs every table, returns the fail-closed report.
- ``cli.execute`` -- the ``edgar-warehouse table-reconcile`` command handler.
"""
from __future__ import annotations

from edgar_warehouse.table_reconciliation.collector import (
    TableReconciliationResult,
    reconcile_table,
)
from edgar_warehouse.table_reconciliation.contracts import TABLE_CONTRACTS, TableContract
from edgar_warehouse.table_reconciliation.report import build_report, compare_to_previous

__all__ = [
    "TABLE_CONTRACTS",
    "TableContract",
    "TableReconciliationResult",
    "reconcile_table",
    "build_report",
    "compare_to_previous",
]
