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

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import duckdb

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.silver_store import _DDL as _SILVER_SCHEMA_DDL


def _connect_bounded() -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with an explicit memory_limit.

    Without one, DuckDB sizes its default buffer pool from what it detects as
    total system memory, which is not guaranteed to respect an ECS/Fargate
    task's cgroup memory limit -- the observed failure mode is a silent
    OutOfMemoryError container kill (exit 137) with no DuckDB-level error to
    catch or log. A conservative explicit ceiling, well under the task's
    declared memory (4096MB for the warehouse-medium task definition as of
    this writing), leaves headroom for the Python process's own overhead
    (candidate row lists, etc.) and the container OS.
    """
    conn = duckdb.connect(":memory:")
    limit_gb = os.environ.get("WAREHOUSE_SILVER_MERGE_MEMORY_LIMIT_GB", "2").strip()
    conn.execute(f"SET memory_limit = '{int(limit_gb)}GB'")
    return conn


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
    # Columns that record *where this row was first/most-recently observed*
    # rather than the row's own business data -- excluded from same-key
    # conflict detection for this table only (unlike the global
    # _PROVENANCE_COLUMNS, which would be wrong to apply broadly: the same
    # column name can be load-bearing business data on one table and pure
    # provenance on another). Declared per-table because "is this column
    # identity or provenance" depends on the table's own key semantics, not
    # the column name alone.
    provenance_columns: frozenset[str] = frozenset()


# Reviewed, fail-closed registry of every canonical domain table in the
# silver_store.py DDL (edgar_warehouse/silver_store.py:_DDL). Business keys
# and authority columns mirror each table's declared PRIMARY KEY and its
# existing last_synced_at/ingested_at/fetched_at provenance timestamp.
PROTECTED_TABLE_REGISTRY: dict[str, ProtectedTablePolicy] = {
    "sec_company": ProtectedTablePolicy(
        "sec_company",
        ("cik",),
        authority_column="last_synced_at",
        # mdm-ahead-of-silver map, ticket 02/05: written NULL at parse time,
        # backfilled by an independent sweep -- never business data, and
        # without this exclusion an authority-column win on this table
        # overwrites every non-key column from the candidate side (silver_
        # protection.py's _update_row), which would silently regress an
        # already-backfilled mdm_entity_id back to NULL on the next ordinary
        # re-sync of the same CIK.
        provenance_columns=frozenset({"mdm_entity_id"}),
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
        "sec_ownership_reporting_owner",
        ("accession_number", "owner_index"),
        # mdm-ahead-of-silver map, ticket 02/05: see sec_company's comment.
        # This table has no authority_column, so without this exclusion a
        # stale parse-time NULL re-presented by any later candidate would
        # abort the merge outright, not just silently regress a value.
        provenance_columns=frozenset({"mdm_entity_id"}),
    ),
    "sec_ownership_non_derivative_txn": ProtectedTablePolicy(
        "sec_ownership_non_derivative_txn",
        ("accession_number", "owner_index", "txn_index"),
        provenance_columns=frozenset({"mdm_entity_id"}),
    ),
    "sec_ownership_derivative_txn": ProtectedTablePolicy(
        "sec_ownership_derivative_txn",
        ("accession_number", "owner_index", "txn_index"),
        provenance_columns=frozenset({"mdm_entity_id"}),
    ),
    "sec_adv_filing": ProtectedTablePolicy(
        "sec_adv_filing",
        ("accession_number",),
        provenance_columns=frozenset({"mdm_entity_id"}),
    ),
    "sec_adv_office": ProtectedTablePolicy(
        "sec_adv_office", ("accession_number", "office_index")
    ),
    "sec_adv_disclosure_event": ProtectedTablePolicy(
        "sec_adv_disclosure_event", ("accession_number", "event_index")
    ),
    "sec_adv_private_fund": ProtectedTablePolicy(
        "sec_adv_private_fund",
        ("accession_number", "fund_index"),
        # mdm-ahead-of-silver map, ticket 02/05: see sec_company's comment.
        provenance_columns=frozenset({"mdm_entity_id"}),
    ),
    "sec_adv_firm_roster": ProtectedTablePolicy(
        "sec_adv_firm_roster", ("adviser_crd_number", "dataset_period")
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
        "sec_raw_object",
        ("raw_object_id",),
        authority_column="fetched_at",
        # raw_object_id IS the sha256 of the fetched bytes (silver_store.py) --
        # identical byte content legitimately recurs across different filings
        # (shared boilerplate/exhibit templates, common XBRL taxonomy files),
        # fetched under different accessions/forms/URLs. The real
        # content<->filing linkage lives in sec_filing_attachment
        # (accession_number, document_name -> raw_object_id), independent of
        # this table. Because the key is content-derived, the *only* columns
        # that can legitimately differ-and-should-halt a merge are ones
        # intrinsic to the bytes themselves (sha256, byte_size -- and those
        # can only differ on a genuine hash collision); every other column
        # here just records *how/where this particular fetch observed it* and
        # is provenance. Regression (2026-07-22, Ticket 20): first hit on
        # cik/accession_number/source_url/storage_path (10 rows, same content
        # refetched under a different accession than canonical's first-seen
        # record); a follow-up run then hit the identical class on `form`
        # alone (4 rows) because that first fix listed columns by hand instead
        # of deriving the set structurally -- fetched_at authority never
        # resolves either class (both sides carry the same original
        # first-fetch timestamp), so without exclusion every such recurrence
        # is a permanent, unresolvable ambiguous conflict. Fixed for good by
        # whitelisting the content-derived columns as checked and treating
        # every remaining fetch-context column (including content_type/
        # content_encoding, which are server-declared per-fetch labels, not
        # facts about the bytes) as provenance.
        provenance_columns=frozenset(
            {
                "cik",
                "accession_number",
                "form",
                "source_url",
                "storage_path",
                "source_type",
                "content_type",
                "content_encoding",
                "http_status",
                "source_last_modified",
                "source_etag",
            }
        ),
    ),
    "sec_filing_attachment": ProtectedTablePolicy(
        "sec_filing_attachment",
        ("accession_number", "document_name"),
        # raw_object_id is a content hash (sha256) pointing at externally-
        # fetched bytes -- the same class of drift sec_raw_object's own
        # provenance_columns comment documents (SEC serves slightly
        # different bytes on refetch of "the same" document over time).
        # This table declares no authority_column at all (no timestamp
        # column exists in the DDL to add one to without a schema
        # migration), so any raw_object_id difference was unconditionally
        # ambiguous -- confirmed live (Ticket 97): a 20-CIK sample backfill
        # retry produced 147 such conflicts, 100% on this one column.
        # raw_object_id is not otherwise consumed downstream (no gold/
        # serving/mdm reads it; the real content<->hash identity work
        # happens in sec_raw_object, keyed by the hash itself), so
        # canonical's first-observed value can safely stay authoritative
        # without contest, the same way sec_raw_object's own recurrence
        # class is handled.
        #
        # document_url is the same class of drift, confirmed live
        # (2026-08-06): accession 0001137439-25-001001 (a DEFA14A jointly
        # associated with 18 CIKs) produced 51 conflicts, 100% on this
        # column. bronze_filing_artifacts.py resolves each accession via
        # get_filing_by_cik_and_accession(cik, accession_number) using
        # whichever CIK the current candidate's own sec_filing row
        # associates with the accession -- and SEC serves a distinct SGML
        # header (and therefore a distinct document_url, which embeds the
        # querying CIK's own path segment) per associated CIK for a
        # multi-registrant filing. Verified directly against live SEC data:
        # fetching the same document via edgar.Company(cik) for 4 different
        # CIKs associated with this accession returned 4 different
        # document_url strings differing only in the CIK path segment,
        # while every other attachment field (sequence_number,
        # document_type, description, is_primary) and the actual byte
        # content (raw_object_id) were identical. Not a data-integrity
        # issue -- the content-identity signal (raw_object_id) is
        # unaffected and already provenance above.
        provenance_columns=frozenset({"raw_object_id", "document_url"}),
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
    "sec_guidance_fact": ProtectedTablePolicy(
        "sec_guidance_fact",
        (
            "cik", "metric", "fiscal_year", "fiscal_quarter", "as_of",
            "accession_number", "is_non_gaap", "source_system",
        ),
        authority_column="ingested_at",
    ),
    # A run-level concurrency record, not an expendable execution log.  It
    # must survive publication so the daily identity-refresh/backstop lease
    # remains exclusive across successive canonical silver databases.
    "pipeline_run_lease": ProtectedTablePolicy(
        "pipeline_run_lease", ("lease_name",), authority_column="updated_at"
    ),
}

# Write-provenance columns (record which run last touched a row, not business
# data) that never participate in same-key conflict detection, regardless of
# whether a table declares an authority_column. A row whose only difference
# is which run re-affirmed it is unchanged for every business purpose --
# flagging that as an ambiguous conflict blocked every idempotent re-sync of
# sec_company_former_name (the one table with no authority_column, so any
# raw column difference -- including this bookkeeping field -- aborted the
# merge). Tables that use last_synced_at/ingested_at/etc. as an authority
# column are unaffected: that column is still compared, just via
# _resolve_conflict rather than the plain-equality check here.
_PROVENANCE_COLUMNS = frozenset({"last_sync_run_id"})

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
        "pipeline_run_lease",
        "gold_manifest",
        "sec_source_checkpoint",
        "sec_company_sync_state",
        "sec_reconcile_finding",
        # ERDP-02 D6: append-only quarantine log for rejected guidance-fact
        # candidates -- no natural key (rows accumulate, never conflict).
        "sec_guidance_fact_reject",
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


def _emit_table_merge_started_event(table_name: str) -> None:
    """Paired with ``_emit_table_merge_event`` (the completion event) to give
    ``merge_candidate_into_canonical`` the same started/completed symmetry as
    source_dimensional_export.py's gold_table_started/completed. Before this, a table whose
    merge took a long time (the schema reconciliation, the anti-join delta
    query, or the per-row Python loop below) was silently invisible for its
    entire duration -- only the *previous* table's completion and the *next*
    table's completion bracketed the gap, so a slow or stuck table could only
    be narrowed down after the fact, never named directly while it was
    happening. Fired for every table the candidate has data for, regardless
    of whether the merge ultimately writes anything (mirrors
    ``_emit_table_merge_event``'s scope for the provenance-filtered-only
    fast path, which does emit a completion event).
    """
    print(
        json.dumps({"event": "silver_table_merge_started", "table": table_name}),
        file=sys.stderr,
        flush=True,
    )


def _emit_table_merge_event(table_name: str, *, inserted: int, updated: int, unchanged: int) -> None:
    """One structured line per table merged, matching this codebase's
    event-keyed JSON logging convention (e.g. source_dimensional_export.py's
    gold_table_started/completed). merge_candidate_into_canonical previously
    emitted nothing at all -- a table taking minutes for zero real writes
    (the sec_company_filing authority-column incident) was invisible in
    CloudWatch until reproduced locally against a downloaded copy of prod
    data. This does not identify the run -- callers with a run/task id log
    that context separately; this is purely per-table merge accounting.
    """
    print(
        json.dumps(
            {
                "event": "silver_table_merged",
                "table": table_name,
                "rows_inserted": inserted,
                "rows_updated": updated,
                "rows_unchanged": unchanged,
            }
        ),
        file=sys.stderr,
        flush=True,
    )


def _comparable_columns(policy: "ProtectedTablePolicy", all_columns: list[str]) -> list[str]:
    """Columns whose values determine whether two same-key rows are
    *meaningfully* different -- excludes business keys, the global and
    per-table provenance columns, and the table's own declared
    ``authority_column``.

    The authority column exists to tiebreak an already-real conflict, not to
    manufacture one: it is a sync/ingestion timestamp that changes on every
    re-sync regardless of whether the row's actual content changed. Treating
    it as a comparable column means a full-history re-sync flags every
    previously-seen row as "different" forever, even when nothing about the
    row itself changed (see the sec_company_filing incident: a 500-CIK
    identity-refresh batch produced a 452,996-row delta where 100% of rows
    differed only on last_synced_at/last_sync_run_id -- confirmed live
    against production data).
    """
    excluded = set(policy.business_keys) | _PROVENANCE_COLUMNS | policy.provenance_columns
    if policy.authority_column is not None:
        excluded.add(policy.authority_column)
    return [c for c in all_columns if c not in excluded]


def _merge_chunk_size() -> int:
    """Row-chunk size for the existing-key-diff merge path (see
    ``_iter_existing_key_diff_row_chunks``).

    Bounds Python-side memory for that path regardless of how large a
    same-key delta is. See ticket 20
    (.scratch/ecs-cost-sizing/issues/20-fix-stage1b-entity-facts-oom-on-medium-profile.md):
    an earlier, unchunked version of this merge OOM-killed
    Stage1BEntityFacts and Stage1BPerFiling on a `medium` (4096MB) ECS task
    by materializing an entire cold-start table's delta (~5M rows, ~2.3GB)
    into a Python list of dicts in one ``.fetchall()``.
    """
    raw = os.environ.get("WAREHOUSE_SILVER_MERGE_CHUNK_SIZE", "50000").strip()
    return int(raw)


def _merge_sql_fragments(
    business_keys: tuple[str, ...], compare_columns: list[str]
) -> tuple[str, str]:
    """Return ``(key_eq_sql, match_sql)`` fragments shared by the merge's
    new-key-insert and existing-key-diff queries, so both definitions of
    "same business key" / "same business key and content" stay in sync.

    IS NOT DISTINCT FROM is used for content comparison instead of plain
    equality for null-safety (a NULL-vs-NULL comparable column must not
    register as a difference). A prior version of this comparison included
    the authority column -- wrong, since it treated a same-key row whose
    real data is byte-identical as a genuine delta purely because its sync
    timestamp advanced; ``compare_columns`` (via ``_comparable_columns``)
    already excludes it.
    """
    key_eq_sql = " AND ".join(f"c.{_quote_ident(k)} = o.{_quote_ident(k)}" for k in business_keys)
    compare_eq_sql = " AND ".join(
        f"c.{_quote_ident(c)} IS NOT DISTINCT FROM o.{_quote_ident(c)}" for c in compare_columns
    )
    match_sql = " AND ".join(part for part in (key_eq_sql, compare_eq_sql) if part)
    return key_eq_sql, match_sql


def _bulk_insert_new_key_rows(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
    business_keys: tuple[str, ...],
) -> int:
    """Insert every candidate row whose business key doesn't exist in
    canonical at all, via one SQL ``INSERT ... SELECT`` executed entirely
    inside DuckDB -- no candidate row is ever materialized into a Python
    dict for this case.

    This is the case that dominates a cold-start table (canonical starts
    ~empty, so ~every candidate row's key is "new" -- see ticket 20, linked
    on ``_merge_chunk_size``). A row whose key already exists in canonical,
    even if its content is identical, never matches this WHERE clause and is
    left for ``_iter_existing_key_diff_row_chunks`` to evaluate.

    Returns the count of rows inserted, via ``COUNT(*)`` against the same
    predicate evaluated *before* the INSERT mutates ``out`` -- the predicate
    is re-evaluated fresh on every execution, so counting afterward would
    always read back zero.
    """
    quoted_table = _quote_ident(table_name)
    key_eq_sql = " AND ".join(f"c.{_quote_ident(k)} = o.{_quote_ident(k)}" for k in business_keys)
    where_sql = f"NOT EXISTS (SELECT 1 FROM out.main.{quoted_table} o WHERE {key_eq_sql})"
    count = conn.execute(
        f"SELECT COUNT(*) FROM cand.main.{quoted_table} c WHERE {where_sql}"
    ).fetchone()[0]
    if count:
        cols_sql = ", ".join(_quote_ident(c) for c in columns)
        select_cols_sql = ", ".join(f"c.{_quote_ident(c)}" for c in columns)
        conn.execute(
            f"INSERT INTO out.main.{quoted_table} ({cols_sql}) "
            f"SELECT {select_cols_sql} FROM cand.main.{quoted_table} c WHERE {where_sql}"
        )
    return count


def _iter_existing_key_diff_row_chunks(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
    business_keys: tuple[str, ...],
    compare_columns: list[str],
    chunk_size: int,
) -> Iterator[list[dict[str, Any]]]:
    """Yield chunks of candidate rows whose business key exists in canonical
    but whose comparable-column content differs, ``chunk_size`` rows at a
    time -- the only rows that need Python-side conflict resolution
    (authority-column tiebreak / ambiguous-conflict reporting).

    Bounded via DuckDB's own ``fetchmany`` cursor rather than one
    ``.fetchall()`` (see ticket 20, linked on ``_merge_chunk_size``). A
    cold-start table never reaches this path for its new rows at all --
    those are handled by ``_bulk_insert_new_key_rows`` without a Python
    round-trip -- but a genuinely large same-key delta (e.g. an
    authority-column-driven full-history re-sync) still needs a memory
    bound.

    Executed on a dedicated ``conn.cursor()`` rather than ``conn`` itself:
    the caller runs other queries (canonical lookups, row updates) on
    ``conn`` for each chunk this generator yields, and a DuckDB connection
    keeps only one statement's result live at a time -- interleaving another
    ``conn.execute()`` on the same connection between two ``fetchmany()``
    calls silently redirects subsequent fetches to that other statement's
    results instead of continuing this one (confirmed empirically: without
    an isolated cursor, a mid-loop lookup query corrupted the next chunk's
    rows). A cursor shares the parent connection's attached databases
    (``out``/``cand``), so no separate ATTACH is needed here.
    """
    quoted_table = _quote_ident(table_name)
    select_cols_sql = ", ".join(f"c.{_quote_ident(c)}" for c in columns)
    key_eq_sql, match_sql = _merge_sql_fragments(business_keys, compare_columns)
    cursor = conn.cursor()
    result = cursor.execute(
        f"SELECT {select_cols_sql} FROM cand.main.{quoted_table} c "
        f"WHERE EXISTS (SELECT 1 FROM out.main.{quoted_table} o WHERE {key_eq_sql}) "
        f"AND NOT EXISTS (SELECT 1 FROM out.main.{quoted_table} o WHERE {match_sql})"
    )
    try:
        while True:
            batch = result.fetchmany(chunk_size)
            if not batch:
                return
            yield [dict(zip(columns, row)) for row in batch]
    finally:
        cursor.close()


def _key_tuple(row: dict[str, Any], business_keys: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[k] for k in business_keys)


def _matching_canonical_rows_as_dicts(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    business_keys: tuple[str, ...],
    columns: list[str],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch only canonical ('out') rows whose business key also appears in
    ``candidate_rows`` -- a targeted lookup, not a full table scan.

    A canonical row whose key is absent from the candidate can never be
    looked up by the merge loop below (it only ever queries keys drawn from
    candidate_rows), so loading it was always wasted work. For a table the
    size of sec_company_filing (2M+ rows in production), unconditionally
    loading the full table into Python dicts on every publish -- regardless
    of how small the candidate is -- risks OOM in the bounded-memory
    ECS/Fargate task that runs this merge (observed: a 4-CIK
    company-identity candidate silently killed the container with an
    OutOfMemoryError).

    Deliberately built as an explicit ``WHERE (keys) IN (VALUES ...)`` against
    Python-side candidate keys -- already read into memory here since
    candidate_rows is always small -- rather than a SQL JOIN against the
    attached candidate table. An attached read-only database may not carry
    fresh statistics for DuckDB's optimizer, and this avoids depending on it
    picking canonical's 2M+-row table as the join's probe side rather than
    its build side.
    """
    if not candidate_rows:
        return []
    quoted_table = _quote_ident(table_name)
    cols_sql = ", ".join(_quote_ident(c) for c in columns)
    key_tuple_sql = "(" + ", ".join(_quote_ident(k) for k in business_keys) + ")"
    placeholder_row = "(" + ", ".join("?" for _ in business_keys) + ")"
    values_sql = ", ".join(placeholder_row for _ in candidate_rows)
    params = [
        value
        for row in candidate_rows
        for value in _key_tuple(row, business_keys)
    ]
    result = conn.execute(
        f"SELECT {cols_sql} FROM out.main.{quoted_table} "
        f"WHERE {key_tuple_sql} IN (VALUES {values_sql})",
        params,
    )
    return [dict(zip(columns, row)) for row in result.fetchall()]


def compute_silver_fingerprint(db_path: Path) -> dict[str, Any] | None:
    """Cheap, local-only fingerprint used to detect whether a silver DuckDB
    file has diverged from an earlier snapshot of itself, without touching
    remote storage or reproducing the full merge.

    Two parts, both required for a safe comparison (release-readiness
    ticket 79):

    - ``tables``: the full sorted table-name set in the file. A table that
      didn't exist in the earlier snapshot (including one not yet
      classified in ``PROTECTED_TABLE_REGISTRY``) changes this set, which
      forces a mismatch -- so an unregistered new table can never be
      silently skipped past ``merge_candidate_into_canonical``'s own
      fail-closed unclassified-table guard.
    - ``protected``: per-``PROTECTED_TABLE_REGISTRY`` table (only those
      present in the file), a ``(row_count, content_hash)`` pair covering
      every column. ``EXCLUDED_OPERATIONAL_TABLES`` bookkeeping writes
      (``pipeline_run``/``sec_sync_run``) are deliberately excluded, so a
      command that only ever writes those never registers as "changed"
      here. The hash is an order-independent ``BIT_XOR`` of each row's
      ``HASH()`` over every column, so a same-row-count in-place content
      update (e.g. an authority-column-resolved conflict) is still caught
      -- a row-count-only check would miss it.

    Returns ``None`` if ``db_path`` doesn't exist.
    """
    if not db_path.exists():
        return None
    conn = _connect_bounded()
    try:
        conn.execute(f"ATTACH '{db_path}' AS fp (READ_ONLY)")
        table_names = sorted(_table_names(conn, "fp"))
        table_name_set = set(table_names)
        protected: dict[str, list[Any]] = {}
        for table_name in sorted(PROTECTED_TABLE_REGISTRY):
            if table_name not in table_name_set:
                continue
            columns = sorted(_columns(conn, "fp", table_name).keys())
            col_list = ", ".join(_quote_ident(c) for c in columns)
            row_count, xor_hash = conn.execute(
                f"SELECT COUNT(*), COALESCE(BIT_XOR(HASH({col_list})), 0) "
                f"FROM fp.main.{_quote_ident(table_name)}"
            ).fetchone()
            protected[table_name] = [row_count, str(xor_hash)]
        return {"tables": table_names, "protected": protected}
    finally:
        conn.close()


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

    conn = _connect_bounded()
    try:
        conn.execute(f"ATTACH '{output_path}' AS out")
        conn.execute(f"ATTACH '{candidate_path}' AS cand (READ_ONLY)")

        cand_tables = _table_names(conn, "cand")
        out_tables = _table_names(conn, "out")

        # backup_<table>_<reason>_<timestamp> tables are created exclusively by
        # SilverDatabase's schema-migration backup-and-recreate helper (see
        # silver_store.py's period_end/period_start PK migrations and the
        # fund_index BIGINT migration) as an audit/rollback artifact -- never
        # canonical domain data, and their names are deliberately unpredictable
        # (a runtime timestamp), so they can never be pre-registered by exact
        # name the way EXCLUDED_OPERATIONAL_TABLES otherwise requires.
        # Discovered via a real production ingest-relationship-sources run:
        # the fund_index BIGINT migration fired against a stale pre-migration
        # silver.duckdb, and the immediately-following publish step failed
        # closed on its own backup table.
        unclassified = {
            t
            for t in (cand_tables | out_tables)
            if t not in PROTECTED_TABLE_REGISTRY
            and t not in EXCLUDED_OPERATIONAL_TABLES
            and not t.startswith("backup_")
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

            _emit_table_merge_started_event(table_name)

            cand_columns = _columns(conn, "cand", table_name)
            if table_name not in out_tables:
                # New classified domain table, first time it's being published.
                # Create it from the canonical schema DDL (every statement is
                # CREATE TABLE IF NOT EXISTS, so this is a no-op for tables
                # that already exist) rather than a schema-inferring CTAS --
                # CTAS only copies column names/types, not the PRIMARY
                # KEY/NOT NULL constraints declared in silver_store.py's
                # _DDL, which silently left canonical tables constraint-free
                # and later broke any ON CONFLICT merge against them.
                conn.execute("USE out")
                conn.execute(_SILVER_SCHEMA_DDL)
                conn.execute("USE memory")

            # Schema reconciliation applies identically whether the table
            # already existed or was just created above: a first-publish
            # candidate must satisfy the same DDL-declared columns as any
            # later publish, so an inconsistent candidate fails closed here
            # instead of crashing deep inside the delta query below.
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

            all_columns = list(_columns(conn, "out", table_name).keys())
            comparable_columns = _comparable_columns(policy, all_columns)

            # Rows the anti-join filters out before ever reaching Python:
            # same business key, identical on every comparable column, so
            # only a provenance/authority column (if anything) differed.
            # Computed via COUNT(*) below rather than fetched, so a
            # full-history re-sync candidate that touches nothing real still
            # reports an accurate rows_unchanged total without materializing
            # it.
            cand_total = conn.execute(
                f"SELECT COUNT(*) FROM cand.main.{_quote_ident(table_name)}"
            ).fetchone()[0]

            # Phase 1: candidate rows whose business key doesn't exist in
            # canonical at all -- one SQL INSERT, no Python row
            # materialization. Dominates a cold-start table (ticket 20: an
            # unchunked Python fetchall of this exact case OOM-killed
            # Stage1BEntityFacts and Stage1BPerFiling).
            inserted = _bulk_insert_new_key_rows(conn, table_name, all_columns, policy.business_keys)

            # Phase 2: candidate rows whose key exists in canonical but whose
            # content differs -- the only rows that need Python-side
            # conflict resolution, fetched in bounded chunks rather than all
            # at once.
            updated = 0
            unchanged = 0
            processed_diff = 0
            for chunk in _iter_existing_key_diff_row_chunks(
                conn,
                table_name,
                all_columns,
                policy.business_keys,
                comparable_columns,
                _merge_chunk_size(),
            ):
                processed_diff += len(chunk)
                canonical_by_key: dict[tuple[Any, ...], dict[str, Any]] = {
                    _key_tuple(row, policy.business_keys): row
                    for row in _matching_canonical_rows_as_dicts(
                        conn, table_name, policy.business_keys, all_columns, chunk
                    )
                }

                for cand_row in chunk:
                    key = _key_tuple(cand_row, policy.business_keys)
                    # canon_row is guaranteed present: the chunk query above
                    # only selects candidate rows whose key already exists
                    # in canonical.
                    canon_row = canonical_by_key[key]

                    differing = tuple(
                        c
                        for c in comparable_columns
                        if canon_row.get(c) != cand_row.get(c)
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
                        # A candidate win on some genuinely differing business
                        # column must not drag mdm_entity_id backwards.
                        # _update_row writes every non-key column from
                        # cand_row unconditionally; an authority-column win
                        # driven by an unrelated content correction (e.g. a
                        # fixed entity_name) must not silently regress an
                        # already-backfilled mdm_entity_id back to NULL
                        # (mdm-ahead-of-silver map, ticket 02/05). Only
                        # applies when the candidate's own value is None --
                        # a candidate that DOES carry a real mdm_entity_id
                        # still wins normally.
                        #
                        # Deliberately scoped to mdm_entity_id only, not to
                        # every provenance_columns entry generically: other
                        # tables' provenance sets (e.g. sec_raw_object's
                        # source_etag/content_encoding/etc.) are structurally
                        # derived and have their own, possibly-legitimate
                        # None semantics on a candidate win that were never
                        # audited for this preserve-canonical rule -- widen
                        # only after checking each such column's contract
                        # explicitly, per-table.
                        effective_row = dict(cand_row)
                        for prov_col in ("mdm_entity_id",) if "mdm_entity_id" in policy.provenance_columns else ():
                            if effective_row.get(prov_col) is None and canon_row.get(prov_col) is not None:
                                effective_row[prov_col] = canon_row[prov_col]
                        _update_row(conn, table_name, all_columns, policy.business_keys, effective_row)
                        updated += 1
                    else:
                        unchanged += 1  # canonical remains authoritative; no-op.

            provenance_filtered = cand_total - inserted - processed_diff
            if inserted == 0 and processed_diff == 0:
                if provenance_filtered:
                    tables_merged.append(table_name)
                    rows_inserted[table_name] = 0
                    rows_updated[table_name] = 0
                    rows_unchanged[table_name] = provenance_filtered
                    _emit_table_merge_event(
                        table_name, inserted=0, updated=0, unchanged=provenance_filtered
                    )
                continue

            unchanged += provenance_filtered
            tables_merged.append(table_name)
            rows_inserted[table_name] = inserted
            rows_updated[table_name] = updated
            rows_unchanged[table_name] = unchanged
            _emit_table_merge_event(
                table_name, inserted=inserted, updated=updated, unchanged=unchanged
            )

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
    conn = _connect_bounded()
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
    conn = _connect_bounded()
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
