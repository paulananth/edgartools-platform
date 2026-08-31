"""Computes the four Table-Specific Reconciliation checks for one table
against a real DuckDB canonical reader and a real Snowflake
``EDGARTOOLS_SILVER`` reader.

**Freshness skew is handled deliberately, not ignored.** DuckDB canonical is
written continuously; ``EDGARTOOLS_SILVER`` dynamic tables refresh on a
6-hour ``target_lag`` (CLAUDE.md's own gold/silver lag notes). A naive
full-table digest comparison run at an arbitrary moment would report a
"FAIL" for every row DuckDB captured since Snowflake's last refresh -- not a
defect, just normal lag. Two independent scoping strategies close this,
chosen per table based on what the table's contract declares:

- **Authority-column scoping** (tables with a declared ``authority_column``):
  read Snowflake's own ``MAX(authority_column)`` as its refresh watermark,
  then only compare DuckDB rows at or before that watermark. Rows newer than
  the watermark are reported as ``out_of_scope`` -- a third outcome,
  distinct from PASS and FAIL, exactly matching this repo's own
  MaxConcurrency4 Data Integrity Evidence precedent for handling timing
  windows explicitly rather than papering over them.
- **Key-intersection scoping** (tables with no ``authority_column`` -- no
  timestamp to scope by): compare only the keys present on *both* sides
  right now. Keys present on only one side are reported as
  ``duckdb_only_count``/``snowflake_only_count`` -- informational, not a
  digest FAIL, since one-directional lag is not distinguishable from a real
  defect without a timestamp to reason about.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from edgar_warehouse.table_reconciliation import sql_checks
from edgar_warehouse.table_reconciliation.contracts import ParentLink, TableContract
from edgar_warehouse.table_reconciliation.digest import (
    sorted_key_set_digest,
    sorted_semantic_row_digest,
)
from edgar_warehouse.table_reconciliation.sql_checks import Reader

CheckStatus = Literal["pass", "fail", "skipped_table_missing"]


@dataclass(frozen=True)
class ParentIntegrityResult:
    link: ParentLink
    orphan_count: int
    status: CheckStatus


@dataclass(frozen=True)
class PkUniquenessResult:
    duplicate_group_count: int
    status: CheckStatus


@dataclass(frozen=True)
class SemanticDigestResult:
    """``duckdb_key_digest``/``snowflake_key_digest`` and
    ``duckdb_semantic_digest``/``snowflake_semantic_digest`` are computed
    over the *same* cohort of keys on both sides (see module docstring for
    how that cohort is scoped) -- a digest match means content-equal for
    exactly the rows this run judged comparable, not a full-table claim
    when the table exceeds ``cohort_size``.
    """

    scope_mode: Literal["authority_column", "key_intersection"]
    cohort_size: int
    compared_key_count: int
    out_of_scope_count: int
    duckdb_only_count: int
    snowflake_only_count: int
    duckdb_key_digest: str
    snowflake_key_digest: str
    duckdb_semantic_digest: str
    snowflake_semantic_digest: str
    status: CheckStatus
    cohort_keys_digest: str


@dataclass(frozen=True)
class TableReconciliationResult:
    table_name: str
    cardinality: str
    bronze_to_silver: ParentIntegrityResult | None
    required_parent: ParentIntegrityResult | None
    pk_uniqueness: PkUniquenessResult
    semantic_digest: SemanticDigestResult
    legitimate_zero_note: str
    overall_status: CheckStatus


_DEFAULT_COHORT_SIZE = 500


def _integrity_result(reader: Reader, link: ParentLink) -> ParentIntegrityResult:
    if not sql_checks.table_exists(reader, link.child_table) or not sql_checks.table_exists(
        reader, link.parent_table
    ):
        return ParentIntegrityResult(link=link, orphan_count=0, status="skipped_table_missing")
    orphans = sql_checks.orphan_count(
        reader,
        child_table=link.child_table,
        child_column=link.child_column,
        parent_table=link.parent_table,
        parent_column=link.parent_column,
    )
    return ParentIntegrityResult(link=link, orphan_count=orphans, status="pass" if orphans == 0 else "fail")


def _pk_uniqueness_result(reader: Reader, contract: TableContract) -> PkUniquenessResult:
    if not sql_checks.table_exists(reader, contract.table_name):
        return PkUniquenessResult(duplicate_group_count=0, status="skipped_table_missing")
    duplicates = sql_checks.duplicate_key_group_count(reader, contract.table_name, contract.business_keys)
    return PkUniquenessResult(
        duplicate_group_count=duplicates, status="pass" if duplicates == 0 else "fail"
    )


def _semantic_digest_result(
    duckdb_reader: Reader,
    snowflake_reader: Reader,
    contract: TableContract,
    *,
    cohort_size: int,
) -> SemanticDigestResult:
    key_cols = contract.business_keys

    if contract.authority_column:
        watermark = sql_checks.max_authority_value(snowflake_reader, contract.table_name, contract.authority_column)
        if watermark is None:
            scope_mode: Literal["authority_column", "key_intersection"] = "authority_column"
            where_sql = "1 = 0"  # Snowflake has never refreshed this table -- nothing is in scope yet.
            where_params: list[Any] = []
            out_of_scope_count = sql_checks.count_rows(duckdb_reader, contract.table_name)
        else:
            scope_mode = "authority_column"
            # Unquoted, validated identifiers -- matches sql_checks.py's own
            # convention (Snowflake folds unquoted identifiers to uppercase
            # at creation; a double-quoted lowercase reference is a
            # case-sensitive literal that fails to match the real object).
            authority_column = sql_checks.safe_identifier(contract.authority_column)
            table_name = sql_checks.safe_identifier(contract.table_name)
            where_sql = f"{authority_column} <= ?"
            where_params = [watermark]
            total = sql_checks.count_rows(duckdb_reader, contract.table_name)
            in_scope_rows = duckdb_reader.fetch(
                f"SELECT COUNT(*) AS c FROM {table_name} WHERE {where_sql}", where_params
            )
            out_of_scope_count = total - int(in_scope_rows[0]["c"])
        duckdb_keys = sql_checks.fetch_key_cohort(
            duckdb_reader, contract.table_name, key_cols, limit=cohort_size, where_sql=where_sql, where_params=where_params
        )
        snowflake_keys_for_cohort = duckdb_keys
    else:
        scope_mode = "key_intersection"
        out_of_scope_count = 0
        duckdb_keys = sql_checks.fetch_key_cohort(duckdb_reader, contract.table_name, key_cols, limit=cohort_size)
        snowflake_keys = sql_checks.fetch_key_cohort(snowflake_reader, contract.table_name, key_cols, limit=cohort_size)
        duckdb_set = set(duckdb_keys)
        snowflake_set = set(snowflake_keys)
        intersection = duckdb_set & snowflake_set
        duckdb_keys = sorted(intersection, key=lambda k: [str(v) for v in k])
        snowflake_keys_for_cohort = duckdb_keys

    if not duckdb_keys:
        return SemanticDigestResult(
            scope_mode=scope_mode,
            cohort_size=cohort_size,
            compared_key_count=0,
            out_of_scope_count=out_of_scope_count,
            duckdb_only_count=0,
            snowflake_only_count=0,
            duckdb_key_digest=sorted_key_set_digest([]),
            snowflake_key_digest=sorted_key_set_digest([]),
            duckdb_semantic_digest=sorted_semantic_row_digest([], key_columns=key_cols, exclude_columns=contract.semantic_exclude_columns),
            snowflake_semantic_digest=sorted_semantic_row_digest([], key_columns=key_cols, exclude_columns=contract.semantic_exclude_columns),
            status="pass",
            cohort_keys_digest=sorted_key_set_digest([]),
        )

    duckdb_rows = sql_checks.fetch_rows_by_keys(duckdb_reader, contract.table_name, key_cols, duckdb_keys)
    snowflake_rows = sql_checks.fetch_rows_by_keys(
        snowflake_reader, contract.table_name, key_cols, snowflake_keys_for_cohort
    )

    duckdb_only_count = 0
    snowflake_only_count = 0
    if scope_mode == "key_intersection":
        duckdb_only_count = len(duckdb_set - snowflake_set)
        snowflake_only_count = len(snowflake_set - duckdb_set)

    duckdb_key_digest = sorted_key_set_digest([tuple(row[c] for c in key_cols) for row in duckdb_rows])
    snowflake_key_digest = sorted_key_set_digest([tuple(row[c] for c in key_cols) for row in snowflake_rows])
    duckdb_semantic_digest = sorted_semantic_row_digest(
        duckdb_rows, key_columns=key_cols, exclude_columns=contract.semantic_exclude_columns
    )
    snowflake_semantic_digest = sorted_semantic_row_digest(
        snowflake_rows, key_columns=key_cols, exclude_columns=contract.semantic_exclude_columns
    )

    status: CheckStatus = (
        "pass"
        if duckdb_key_digest == snowflake_key_digest and duckdb_semantic_digest == snowflake_semantic_digest
        else "fail"
    )

    return SemanticDigestResult(
        scope_mode=scope_mode,
        cohort_size=cohort_size,
        compared_key_count=len(duckdb_keys),
        out_of_scope_count=out_of_scope_count,
        duckdb_only_count=duckdb_only_count,
        snowflake_only_count=snowflake_only_count,
        duckdb_key_digest=duckdb_key_digest,
        snowflake_key_digest=snowflake_key_digest,
        duckdb_semantic_digest=duckdb_semantic_digest,
        snowflake_semantic_digest=snowflake_semantic_digest,
        status=status,
        cohort_keys_digest=sorted_key_set_digest(duckdb_keys),
    )


def reconcile_table(
    duckdb_reader: Reader,
    snowflake_reader: Reader,
    contract: TableContract,
    *,
    cohort_size: int = _DEFAULT_COHORT_SIZE,
) -> TableReconciliationResult:
    bronze_result = _integrity_result(duckdb_reader, contract.bronze_anchor) if contract.bronze_anchor else None
    if contract.logical_parent is None or contract.logical_parent == contract.bronze_anchor:
        parent_result = bronze_result
    else:
        parent_result = _integrity_result(duckdb_reader, contract.logical_parent)

    pk_result = _pk_uniqueness_result(duckdb_reader, contract)
    semantic_result = _semantic_digest_result(
        duckdb_reader, snowflake_reader, contract, cohort_size=cohort_size
    )

    legitimate_zero_note = (
        f"{contract.table_name} is declared cardinality={contract.cardinality!r} -- "
        + (
            "zero child rows for any given parent key is a legitimate outcome, not a defect."
            if contract.cardinality == "optional_or_many"
            else "every parent-key row is expected to produce at least one row here."
        )
    )

    statuses = [
        r.status
        for r in (bronze_result, parent_result, pk_result, semantic_result)
        if r is not None
    ]
    overall: CheckStatus = "fail" if any(s == "fail" for s in statuses) else "pass"

    return TableReconciliationResult(
        table_name=contract.table_name,
        cardinality=contract.cardinality,
        bronze_to_silver=bronze_result,
        required_parent=parent_result,
        pk_uniqueness=pk_result,
        semantic_digest=semantic_result,
        legitimate_zero_note=legitimate_zero_note,
        overall_status=overall,
    )
