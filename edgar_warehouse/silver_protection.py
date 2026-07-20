"""Fail-closed protected-table registry and semantic silver merge (07-06, ARTF-01/ARTF-02).

Ordinary silver publication must never let a partial or stale local candidate
regress canonical state. Every canonical domain table is classified here with
its business key and a deterministic same-key conflict rule; anything not
classified (a new table, or an explicitly-excluded operational/staging table)
is either rejected (unclassified) or ignored (excluded) by the merge -- there
is no default "just overwrite" path.

``merge_candidate_into_canonical`` never deletes a row that exists only in
canonical (a partial candidate is expected and must not regress coverage) and
never silently picks a side on an ambiguous same-key conflict (no declared
authority column, or the authority column ties/is null on either side) --
those abort the whole merge with a row-level report instead.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from edgar_warehouse.application.errors import WarehouseRuntimeError


class SilverPublicationError(WarehouseRuntimeError):
    """Raised when a silver candidate cannot be safely merged or published."""


@dataclass(frozen=True)
class ProtectedTablePolicy:
    """Declared merge policy for one canonical silver domain table."""

    table_name: str
    business_keys: tuple[str, ...]
    # Column compared to break a same-key value conflict: the row with the
    # greater (non-null) value is authoritative. None means this table has no
    # declared tiebreak column -- any same-key value difference is always
    # ambiguous and aborts the merge for manual review.
    authority_column: str | None = None


# Reviewed, fail-closed registry of every canonical domain table in the
# silver_store.py DDL (edgar_warehouse/silver_store.py:_DDL). Business keys
# and authority columns mirror each table's declared PRIMARY KEY and its
# existing last_synced_at/ingested_at/fetched_at provenance timestamp.
PROTECTED_TABLE_REGISTRY: dict[str, ProtectedTablePolicy] = {
    "sec_company": ProtectedTablePolicy(
        "sec_company", ("cik",), authority_column="last_synced_at"
    ),
    "sec_company_address": ProtectedTablePolicy(
        "sec_company_address", ("cik", "address_type"), authority_column="last_synced_at"
    ),
    "sec_company_former_name": ProtectedTablePolicy(
        "sec_company_former_name", ("cik", "ordinal")
    ),
    "sec_company_submission_file": ProtectedTablePolicy(
        "sec_company_submission_file", ("cik", "file_name"), authority_column="last_synced_at"
    ),
    "sec_company_filing": ProtectedTablePolicy(
        "sec_company_filing", ("accession_number",), authority_column="last_synced_at"
    ),
    "sec_company_ticker": ProtectedTablePolicy(
        "sec_company_ticker",
        ("cik", "ticker", "source_name"),
        authority_column="last_synced_at",
    ),
    "sec_current_filing_feed": ProtectedTablePolicy(
        "sec_current_filing_feed", ("accession_number",), authority_column="last_synced_at"
    ),
    "sec_ownership_reporting_owner": ProtectedTablePolicy(
        "sec_ownership_reporting_owner", ("accession_number", "owner_index")
    ),
    "sec_ownership_non_derivative_txn": ProtectedTablePolicy(
        "sec_ownership_non_derivative_txn",
        ("accession_number", "owner_index", "txn_index"),
    ),
    "sec_ownership_derivative_txn": ProtectedTablePolicy(
        "sec_ownership_derivative_txn",
        ("accession_number", "owner_index", "txn_index"),
    ),
    "sec_adv_filing": ProtectedTablePolicy("sec_adv_filing", ("accession_number",)),
    "sec_adv_office": ProtectedTablePolicy(
        "sec_adv_office", ("accession_number", "office_index")
    ),
    "sec_adv_disclosure_event": ProtectedTablePolicy(
        "sec_adv_disclosure_event", ("accession_number", "event_index")
    ),
    "sec_adv_private_fund": ProtectedTablePolicy(
        "sec_adv_private_fund", ("accession_number", "fund_index")
    ),
    "sec_subsidiary_evidence": ProtectedTablePolicy(
        "sec_subsidiary_evidence", ("accession_number", "document_name", "row_ordinal")
    ),
    "sec_auditor_report_evidence": ProtectedTablePolicy(
        "sec_auditor_report_evidence", ("accession_number", "evidence_fingerprint")
    ),
    "sec_pcaob_firm_identity": ProtectedTablePolicy(
        "sec_pcaob_firm_identity", ("pcaob_firm_id", "snapshot_sha256")
    ),
    "sec_raw_object": ProtectedTablePolicy(
        "sec_raw_object", ("raw_object_id",), authority_column="fetched_at"
    ),
    "sec_filing_attachment": ProtectedTablePolicy(
        "sec_filing_attachment", ("accession_number", "document_name")
    ),
    "sec_filing_text": ProtectedTablePolicy(
        "sec_filing_text", ("accession_number", "text_version"), authority_column="extracted_at"
    ),
    "sec_financial_fact": ProtectedTablePolicy(
        "sec_financial_fact",
        ("cik", "accession_number", "concept", "fiscal_period", "segment", "period_end", "period_start"),
        authority_column="ingested_at",
    ),
    "sec_financial_derived": ProtectedTablePolicy(
        "sec_financial_derived",
        ("cik", "accession_number", "fiscal_period", "period_end"),
        authority_column="ingested_at",
    ),
    "sec_earnings_release": ProtectedTablePolicy(
        "sec_earnings_release", ("cik", "accession_number"), authority_column="ingested_at"
    ),
    "sec_accounting_flag": ProtectedTablePolicy(
        "sec_accounting_flag", ("cik", "accession_number"), authority_column="ingested_at"
    ),
    "sec_executive_record": ProtectedTablePolicy(
        "sec_executive_record", ("cik", "accession_number", "exec_name"), authority_column="ingested_at"
    ),
    "sec_thirteenf_holding": ProtectedTablePolicy(
        "sec_thirteenf_holding",
        ("cik", "accession_number", "holding_index"),
        authority_column="ingested_at",
    ),
    "sec_thirteenf_filing": ProtectedTablePolicy(
        "sec_thirteenf_filing", ("accession_number",), authority_column="ingested_at"
    ),
    "sec_employment_event": ProtectedTablePolicy(
        "sec_employment_event",
        ("accession_number", "event_index"),
        authority_column="ingested_at",
    ),
}

# Ephemeral/operational tables explicitly excluded from semantic merge
# protection: checkpoints, run-tracking, staging, and manifests. These are
# operator/orchestrator bookkeeping, not canonical domain data -- a candidate
# is always free to overwrite them, and merge conflicts on them are not
# reported.
EXCLUDED_OPERATIONAL_TABLES = frozenset(
    {
        "schema_migration",
        "stg_daily_index_filing",
        "sec_daily_index_checkpoint",
        "discovery_checkpoint",
        "sec_parse_run",
        "sec_sync_run",
        "pipeline_run",
        "gold_manifest",
        "sec_source_checkpoint",
        "sec_company_sync_state",
        "sec_reconcile_finding",
    }
)


@dataclass(frozen=True)
class RowConflict:
    """One ambiguous same-key row conflict, reported not resolved."""

    table_name: str
    business_key: dict[str, Any]
    canonical_values: dict[str, Any]
    candidate_values: dict[str, Any]
    differing_columns: tuple[str, ...]


class SemanticMergeConflictError(SilverPublicationError):
    """Raised when one or more same-key rows differ with no way to resolve them."""

    def __init__(self, conflicts: list[RowConflict]):
        self.conflicts = conflicts
        preview = "; ".join(
            f"{c.table_name}{c.business_key}: {list(c.differing_columns)}"
            for c in conflicts[:5]
        )
        more = f" (+{len(conflicts) - 5} more)" if len(conflicts) > 5 else ""
        super().__init__(
            f"{len(conflicts)} ambiguous same-key conflict(s) block publication: {preview}{more}"
        )


@dataclass(frozen=True)
class MergeResult:
    merged_path: Path
    tables_merged: tuple[str, ...]
    rows_inserted: dict[str, int]
    rows_updated: dict[str, int]
    rows_unchanged: dict[str, int]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_names(conn: duckdb.DuckDBPyConnection, catalog: str) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_catalog = ? AND table_schema = 'main'",
        [catalog],
    ).fetchall()
    return {row[0] for row in rows}


def _columns(conn: duckdb.DuckDBPyConnection, catalog: str, table_name: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
        "ORDER BY ordinal_position",
        [catalog, table_name],
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _rows_as_dicts(conn: duckdb.DuckDBPyConnection, catalog: str, table_name: str, columns: list[str]) -> list[dict[str, Any]]:
    cols_sql = ", ".join(_quote_ident(c) for c in columns)
    result = conn.execute(f"SELECT {cols_sql} FROM {catalog}.main.{_quote_ident(table_name)}")
    return [dict(zip(columns, row)) for row in result.fetchall()]


def _key_tuple(row: dict[str, Any], business_keys: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[k] for k in business_keys)


def _matching_canonical_rows_as_dicts(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    business_keys: tuple[str, ...],
    columns: list[str],
) -> list[dict[str, Any]]:
    """Fetch only canonical ('out') rows whose business key also exists in the
    candidate ('cand') table -- a semi-join, not a full table scan.

    A canonical row whose key is absent from the candidate can never be
    looked up by the merge loop below (it only ever queries keys drawn from
    candidate_rows), so loading it was always wasted work. For a table the
    size of sec_company_filing (2M+ rows in production), unconditionally
    loading the full table into Python dicts on every publish -- regardless
    of how small the candidate is -- risks OOM in the bounded-memory
    ECS/Fargate task that runs this merge (observed: a 4-CIK
    company-identity candidate silently killed the container here). The
    join below returns at most as many rows as the candidate has, never
    canonical's full size.
    """
    quoted_table = _quote_ident(table_name)
    cols_sql = ", ".join(f"out.{_quote_ident(c)}" for c in columns)
    join_sql = " AND ".join(
        f"out.{_quote_ident(k)} IS NOT DISTINCT FROM cand.{_quote_ident(k)}"
        for k in business_keys
    )
    result = conn.execute(
        f"SELECT {cols_sql} FROM out.main.{quoted_table} AS out "
        f"JOIN cand.main.{quoted_table} AS cand ON {join_sql}"
    )
    return [dict(zip(columns, row)) for row in result.fetchall()]


def merge_candidate_into_canonical(
    candidate_path: Path,
    canonical_path: Path,
    output_path: Path,
) -> MergeResult:
    """Merge a partial candidate silver DuckDB into a copy of canonical.

    The output starts as an exact copy of ``canonical_path`` (so any table the
    candidate doesn't mention, and any row a partial candidate omits, is
    preserved unchanged). For every table classified in
    ``PROTECTED_TABLE_REGISTRY`` that the candidate also has data for: new
    business keys are inserted, identical same-key rows are left alone, and
    differing same-key rows are resolved only via the table's declared
    ``authority_column`` (candidate wins iff its value is strictly greater);
    anything else is an ambiguous conflict that aborts the whole merge.

    A table present in either database that is neither classified nor
    explicitly excluded fails closed (raises ``SilverPublicationError``) --
    a new domain table must be reviewed and registered before it can be
    published through this path. A protected table whose candidate schema
    drops a canonical column, or changes a shared column's declared type,
    also fails closed (only additive schema evolution is permitted here).
    """
    if not candidate_path.exists():
        raise SilverPublicationError(f"Candidate silver database not found: {candidate_path}")
    if not canonical_path.exists():
        raise SilverPublicationError(f"Canonical silver database not found: {canonical_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical_path, output_path)

    conn = duckdb.connect(":memory:")
    try:
        conn.execute(f"ATTACH '{output_path}' AS out")
        conn.execute(f"ATTACH '{candidate_path}' AS cand (READ_ONLY)")

        cand_tables = _table_names(conn, "cand")
        out_tables = _table_names(conn, "out")

        unclassified = {
            t
            for t in (cand_tables | out_tables)
            if t not in PROTECTED_TABLE_REGISTRY and t not in EXCLUDED_OPERATIONAL_TABLES
        }
        if unclassified:
            raise SilverPublicationError(
                "Unclassified silver table(s) block publication (add a "
                f"ProtectedTablePolicy or exclude explicitly): {sorted(unclassified)}"
            )

        conflicts: list[RowConflict] = []
        tables_merged: list[str] = []
        rows_inserted: dict[str, int] = {}
        rows_updated: dict[str, int] = {}
        rows_unchanged: dict[str, int] = {}

        for table_name, policy in PROTECTED_TABLE_REGISTRY.items():
            if table_name not in cand_tables:
                continue  # candidate has no data for this table; canonical copy stands.

            cand_columns = _columns(conn, "cand", table_name)
            if table_name in out_tables:
                out_columns = _columns(conn, "out", table_name)
                missing = set(out_columns) - set(cand_columns)
                if missing:
                    raise SilverPublicationError(
                        f"Candidate silver database drops canonical column(s) on "
                        f"{table_name!r}: {sorted(missing)} (destructive schema change; "
                        "use the explicit repair workflow instead)"
                    )
                type_mismatches = {
                    c
                    for c in out_columns
                    if c in cand_columns and out_columns[c] != cand_columns[c]
                }
                if type_mismatches:
                    raise SilverPublicationError(
                        f"Candidate silver database changes column type(s) on "
                        f"{table_name!r}: {sorted(type_mismatches)} (destructive schema "
                        "change; use the explicit repair workflow instead)"
                    )
                # Additive: candidate may declare extra columns beyond canonical.
                for extra_col in set(cand_columns) - set(out_columns):
                    conn.execute(
                        f"ALTER TABLE out.main.{_quote_ident(table_name)} "
                        f"ADD COLUMN IF NOT EXISTS {_quote_ident(extra_col)} {cand_columns[extra_col]}"
                    )
            else:
                # New classified domain table, first time it's being published.
                conn.execute(
                    f"CREATE TABLE out.main.{_quote_ident(table_name)} AS "
                    f"SELECT * FROM cand.main.{_quote_ident(table_name)} WHERE 1=0"
                )

            all_columns = list(_columns(conn, "out", table_name).keys())
            candidate_rows = _rows_as_dicts(conn, "cand", table_name, all_columns)
            if not candidate_rows:
                continue

            canonical_by_key: dict[tuple[Any, ...], dict[str, Any]] = {
                _key_tuple(row, policy.business_keys): row
                for row in _matching_canonical_rows_as_dicts(
                    conn, table_name, policy.business_keys, all_columns
                )
            }

            inserted = updated = unchanged = 0
            for cand_row in candidate_rows:
                key = _key_tuple(cand_row, policy.business_keys)
                canon_row = canonical_by_key.get(key)

                if canon_row is None:
                    _insert_row(conn, table_name, all_columns, cand_row)
                    inserted += 1
                    continue

                differing = tuple(
                    c
                    for c in all_columns
                    if c not in policy.business_keys and canon_row.get(c) != cand_row.get(c)
                )
                if not differing:
                    unchanged += 1
                    continue

                winner = _resolve_conflict(policy, canon_row, cand_row)
                if winner is None:
                    conflicts.append(
                        RowConflict(
                            table_name=table_name,
                            business_key=dict(zip(policy.business_keys, key)),
                            canonical_values=canon_row,
                            candidate_values=cand_row,
                            differing_columns=differing,
                        )
                    )
                elif winner == "candidate":
                    _update_row(conn, table_name, all_columns, policy.business_keys, cand_row)
                    updated += 1
                else:
                    unchanged += 1  # canonical remains authoritative; no-op.

            tables_merged.append(table_name)
            rows_inserted[table_name] = inserted
            rows_updated[table_name] = updated
            rows_unchanged[table_name] = unchanged

        if conflicts:
            raise SemanticMergeConflictError(conflicts)

        return MergeResult(
            merged_path=output_path,
            tables_merged=tuple(tables_merged),
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_unchanged=rows_unchanged,
        )
    finally:
        conn.close()


def _resolve_conflict(
    policy: ProtectedTablePolicy,
    canonical_row: dict[str, Any],
    candidate_row: dict[str, Any],
) -> str | None:
    """Return 'candidate', 'canonical', or None (ambiguous) for a same-key conflict."""
    if policy.authority_column is None:
        return None
    canon_value = canonical_row.get(policy.authority_column)
    cand_value = candidate_row.get(policy.authority_column)
    if canon_value is None or cand_value is None:
        return None
    if cand_value > canon_value:
        return "candidate"
    if canon_value > cand_value:
        return "canonical"
    return None  # exact tie on the authority column is still ambiguous.


def _insert_row(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
    row: dict[str, Any],
) -> None:
    cols_sql = ", ".join(_quote_ident(c) for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO out.main.{_quote_ident(table_name)} ({cols_sql}) VALUES ({placeholders})",
        [row[c] for c in columns],
    )


def _primary_key_columns(conn: duckdb.DuckDBPyConnection, catalog: str, table_name: str) -> tuple[str, ...]:
    row = conn.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE database_name = ? AND table_name = ? AND constraint_type = 'PRIMARY KEY'",
        [catalog, table_name],
    ).fetchone()
    if row is None:
        return ()
    return tuple(row[0])


@dataclass(frozen=True)
class SchemaDiff:
    table_name: str
    dropped_columns: tuple[str, ...]
    type_changed_columns: tuple[str, ...]
    business_key_before: tuple[str, ...]
    business_key_after: tuple[str, ...]

    @property
    def business_key_changed(self) -> bool:
        return self.business_key_before != self.business_key_after

    @property
    def is_destructive(self) -> bool:
        return bool(self.dropped_columns) or bool(self.type_changed_columns) or self.business_key_changed


@dataclass(frozen=True)
class SilverRepairAuditRecord:
    table_name: str
    operator: str
    reason: str
    dry_run: bool
    diff: SchemaDiff
    applied: bool


class SilverRepairRequiresReasonError(SilverPublicationError):
    """Raised when a destructive repair is attempted without an operator reason."""


def plan_silver_repair(candidate_path: Path, canonical_path: Path, table_name: str) -> SchemaDiff:
    """Compute the destructive schema diff for one table between candidate and canonical.

    This is the dry-run diff half of the repair contract -- safe to call at
    any time, never mutates either database.
    """
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(f"ATTACH '{candidate_path}' AS cand (READ_ONLY)")
        conn.execute(f"ATTACH '{canonical_path}' AS canon (READ_ONLY)")
        canon_columns = _columns(conn, "canon", table_name)
        cand_columns = _columns(conn, "cand", table_name)
        dropped = tuple(sorted(set(canon_columns) - set(cand_columns)))
        type_changed = tuple(
            sorted(
                c
                for c in canon_columns
                if c in cand_columns and canon_columns[c] != cand_columns[c]
            )
        )
        key_before = _primary_key_columns(conn, "canon", table_name)
        key_after = _primary_key_columns(conn, "cand", table_name)
        return SchemaDiff(
            table_name=table_name,
            dropped_columns=dropped,
            type_changed_columns=type_changed,
            business_key_before=key_before,
            business_key_after=key_after,
        )
    finally:
        conn.close()


def execute_silver_repair(
    candidate_path: Path,
    canonical_path: Path,
    output_path: Path,
    *,
    table_name: str,
    operator: str,
    reason: str,
    dry_run: bool = True,
) -> SilverRepairAuditRecord:
    """Apply a destructive schema/business-key change to one table.

    This is the only path permitted to drop a canonical column, change a
    shared column's type, or replace a table's business key -- ordinary
    ``merge_candidate_into_canonical`` publication fails closed on all three.
    Requires a non-empty operator reason (there is no ``--force`` bypass: a
    reason is mandatory even when ``dry_run=False``). Always computes and
    returns the schema diff; ``dry_run=True`` (the default) stops there
    without touching ``output_path``.
    """
    if not operator or not operator.strip():
        raise SilverRepairRequiresReasonError("Destructive silver repair requires an operator identity")
    if not reason or not reason.strip():
        raise SilverRepairRequiresReasonError("Destructive silver repair requires a non-empty reason")

    diff = plan_silver_repair(candidate_path, canonical_path, table_name)
    if dry_run:
        return SilverRepairAuditRecord(
            table_name=table_name, operator=operator, reason=reason, dry_run=True, diff=diff, applied=False
        )

    if not output_path.exists():
        shutil.copy2(canonical_path, output_path)
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(f"ATTACH '{output_path}' AS out")
        conn.execute(f"ATTACH '{candidate_path}' AS cand (READ_ONLY)")
        conn.execute(f"DROP TABLE IF EXISTS out.main.{_quote_ident(table_name)}")
        conn.execute(
            f"CREATE TABLE out.main.{_quote_ident(table_name)} AS "
            f"SELECT * FROM cand.main.{_quote_ident(table_name)}"
        )
    finally:
        conn.close()
    return SilverRepairAuditRecord(
        table_name=table_name, operator=operator, reason=reason, dry_run=False, diff=diff, applied=True
    )


def _update_row(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
    business_keys: tuple[str, ...],
    row: dict[str, Any],
) -> None:
    non_key_columns = [c for c in columns if c not in business_keys]
    set_sql = ", ".join(f"{_quote_ident(c)} = ?" for c in non_key_columns)
    where_sql = " AND ".join(f"{_quote_ident(k)} = ?" for k in business_keys)
    conn.execute(
        f"UPDATE out.main.{_quote_ident(table_name)} SET {set_sql} WHERE {where_sql}",
        [row[c] for c in non_key_columns] + [row[k] for k in business_keys],
    )
