"""Multi-shard silver reader via DuckDB ATTACH + UNION ALL views.

ShardedSilverReader opens N shard DuckDB files in a single in-memory connection
via ATTACH (READ_ONLY) and creates a UNION ALL view for every table in _TABLES.
Callers can query unioned data through the .fetch() helper method.

Duck-typing compatibility
--------------------------
``edgar_warehouse.silver_support.access.get_connection(...)`` can use this
reader through the same connection-bearing interface as ``SilverDatabase``.

gold.py compatibility
----------------------
``build_gold(...)`` calls ``get_connection(...)``.
ShardedSilverReader satisfies this via duck typing; no signature change needed.

MDM pipeline compatibility
---------------------------
``MDMPipeline`` and ``_require_silver_reader`` call ``silver.fetch(sql, params)``.
ShardedSilverReader provides that method so MDM callers work unchanged.

Pitfalls
--------
1. File handle conflict: ATTACH raises "Binder Error: Unique file handle conflict"
   if the shard file is already open by another DuckDB connection in the same
   process. Construct ShardedSilverReader only AFTER SilverDatabase.close() has
   been called on the same shard paths.

2. UNION ALL (not UNION): UNION performs sort+dedup — expensive on large tables.
   UNION ALL is correct because primary keys enforce no duplicates within a shard.

3. Always ATTACH with (READ_ONLY): prevents accidental writes to shard files.

4. In-memory connection (":memory:"): avoids conflicts from persisting views.

5. Wrap each CREATE VIEW in try/except: older shards may lack tables added by
   later schema evolutions.
"""

from __future__ import annotations

import duckdb


class ShardedSilverReader:
    """Read-only multi-shard silver database reader using DuckDB ATTACH + UNION ALL.

    Parameters
    ----------
    shard_paths:
        List of local filesystem paths to shard DuckDB files (e.g.,
        ["/tmp/silver/shards/shard-0.duckdb", "/tmp/silver/shards/shard-1.duckdb"]).
        All listed shard files must be closed by their writers before this reader
        is constructed (see Pitfall 1 in module docstring).
    """

    _TABLES = [
        "sec_company",
        "sec_company_address",
        "sec_company_former_name",
        "sec_company_submission_file",
        "sec_company_filing",
        "sec_company_ticker",
        "sec_current_filing_feed",
        "sec_ownership_reporting_owner",
        "sec_ownership_non_derivative_txn",
        "sec_ownership_derivative_txn",
        "sec_adv_filing",
        "sec_adv_office",
        "sec_adv_disclosure_event",
        "sec_adv_private_fund",
        "sec_subsidiary_evidence",
        "sec_auditor_report_evidence",
        "stg_daily_index_filing",
        "sec_daily_index_checkpoint",
        "sec_raw_object",
        "sec_filing_attachment",
        "sec_filing_text",
        "sec_parse_run",
        "sec_sync_run",
        "sec_source_checkpoint",
        "sec_company_sync_state",
        "sec_reconcile_finding",
        "sec_tracked_universe",  # legacy table; best-effort
        # Fundamentals namespace (Branch B) — absent in older ownership-only shards;
        # CREATE VIEW failures are silently ignored by the try/except in __init__.
        "sec_financial_fact",
        "sec_financial_derived",
        "sec_earnings_release",
        "sec_accounting_flag",
        "sec_executive_record",
        "sec_thirteenf_holding",
    ]

    def __init__(self, shard_paths: list[str]) -> None:
        self._shard_paths = shard_paths
        self._conn = duckdb.connect(":memory:")
        aliases = []
        for i, path in enumerate(shard_paths):
            alias = f"s{i}"
            self._conn.execute(f"ATTACH '{path}' AS {alias} (READ_ONLY)")
            aliases.append(alias)

        # Per-shard table membership: a UNION ALL across aliases that DO contain
        # the table. Required for mixed historical/current mounts where table
        # sets differ between files. Without per-shard detection, the UNION ALL
        # would reference a non-existent table in one of the aliases and DuckDB
        # would fail the entire CREATE VIEW.
        for table in self._TABLES:
            aliases_with_table = []
            for alias in aliases:
                try:
                    self._conn.execute(f"SELECT 1 FROM {alias}.{table} LIMIT 0")
                    aliases_with_table.append(alias)
                except Exception:
                    pass  # table doesn't exist in this shard
            if not aliases_with_table:
                continue  # table doesn't exist in any mounted shard

            parts = " UNION ALL ".join(
                f"SELECT * FROM {alias}.{table}" for alias in aliases_with_table
            )
            try:
                self._conn.execute(f"CREATE VIEW {table} AS {parts}")
            except Exception:
                pass  # schema mismatch (column drift) — skip with best effort

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        """Execute a SQL query and return results as a list of dicts.

        This method provides API compatibility with the ``_DuckReader`` used by
        MDMPipeline and ``_require_silver_reader`` in ``mdm/cli.py``.

        Parameters
        ----------
        sql:
            SQL query string. Must use only table names exposed as UNION ALL views
            (i.e., those in _TABLES) for cross-shard reads.
        params:
            Optional list of positional query parameters.
        """
        rows = self._conn.execute(sql, params or []).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        """Close the in-memory DuckDB connection."""
        self._conn.close()

    def __repr__(self) -> str:
        return f"ShardedSilverReader({len(self._shard_paths)} shards)"
