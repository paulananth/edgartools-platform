"""BookkeepingStore: SQLAlchemy-backed store for the 11 operational tables.

Ported 1:1 from edgar_warehouse.silver_store.SilverDatabase's equivalent
methods (DuckDB Retirement Cutover Ticket 02). Method names and signatures
match the originals so Ticket 03's caller repointing is close to mechanical.
Two methods from the original surface are deliberately NOT ported here:
`get_all_filing_texts` (queries sec_filing_text, not one of these 11 tables)
and `get_company_identity_ciks` (a cross-store join against sec_company/
sec_company_ticker) -- both are Ticket 03's territory, see that ticket and
Ticket 02's own file for the full reasoning. `get_table_counts` here is a
narrowed, 11-table-only reimplementation; the original's whole-database
contract is also Ticket 03's job (merging this store's counts with DuckDB's
remaining content-table counts).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import String, case, cast, func, literal, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from edgar_warehouse.bookkeeping.database import Base
from edgar_warehouse.bookkeeping.models import (
    BOOKKEEPING_TABLES,
    DiscoveryCheckpoint,
    GoldManifest,
    PipelineRun,
    PipelineRunLease,
    SecCompanySyncState,
    SecDailyIndexCheckpoint,
    SecParseRun,
    SecReconcileFinding,
    SecSourceCheckpoint,
    SecSyncRun,
    StgDailyIndexFiling,
)


class BookkeepingStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        """Durably commit every write issued through this store so far.

        Every ``upsert_*``/``start_*``/``complete_*`` method below issues
        exactly one ``self._session.execute()`` and relies on the caller to
        commit -- mirroring ``edgar_warehouse.mdm``'s explicit
        ``session.commit()`` convention (this store's own module docstring
        says it is "ported 1:1" from that codebase's equivalent methods),
        not a per-statement autocommit engine. Without an explicit call to
        this method, every write made through this store is silently rolled
        back when the owning process exits -- confirmed live 2026-09-01:
        a checkpoint write logged as "status: succeeded" was unreadable by
        both a separate task and a fresh rerun of the same command minutes
        later, because nothing had ever called commit() on this store's
        session in its whole call graph.
        """
        self._session.commit()

    # -- internal helpers ---------------------------------------------------

    def _insert_factory(self):
        dialect_name = self._session.get_bind().dialect.name
        return sqlite_insert if dialect_name == "sqlite" else postgresql_insert

    @staticmethod
    def _to_dict(instance: Any) -> dict[str, Any]:
        mapper = sa_inspect(instance).mapper
        return {attr.key: getattr(instance, attr.key) for attr in mapper.column_attrs}

    @staticmethod
    def _json_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value, default=str, sort_keys=True)

    @staticmethod
    def _as_date(value: Any) -> Any:
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

    @staticmethod
    def _chunks(items: list, size: int):
        for i in range(0, len(items), size):
            yield items[i : i + size]

    @staticmethod
    def _as_utc_date(value: datetime) -> date:
        """Every caller in this codebase writes timestamps as tz-aware UTC
        (the ``datetime.now(UTC)`` convention) -- but SQLite (this store's
        test/dev dialect) has no real ``TIMESTAMP(timezone=True)`` support
        and silently drops tzinfo on round trip, unlike Postgres (prod),
        which always returns a tz-aware value. ``.astimezone()`` on a naive
        datetime assumes *local system time*, which would misconvert an
        already-UTC value read back from SQLite and shift its date --
        reproduced live in this module's own test suite. Treat a naive value
        as already-UTC instead of guessing; only convert when a real
        timezone is attached.
        """
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(timezone.utc).date()

    # -- stg_daily_index_filing / sec_daily_index_checkpoint ----------------

    def merge_daily_index_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        if not rows:
            return 0
        staged_at = datetime.now(timezone.utc)
        deduped: dict[tuple[Any, str], dict[str, Any]] = {}
        for row in rows:
            key = (self._as_date(row.get("business_date")), row.get("accession_number"))
            deduped[key] = row
        values = []
        for row in deduped.values():
            values.append(
                {
                    "sync_run_id": sync_run_id,
                    "raw_object_id": row.get("raw_object_id"),
                    "source_name": row.get("source_name"),
                    "source_url": row.get("source_url"),
                    "business_date": self._as_date(row.get("business_date")),
                    "source_year": row.get("source_year"),
                    "source_quarter": row.get("source_quarter"),
                    "row_ordinal": row.get("row_ordinal"),
                    "form": row.get("form"),
                    "company_name": row.get("company_name"),
                    "cik": row.get("cik"),
                    "filing_date": self._as_date(row.get("filing_date")),
                    "file_name": row.get("file_name"),
                    "accession_number": row.get("accession_number"),
                    "filing_txt_url": row.get("filing_txt_url"),
                    "record_hash": row.get("record_hash"),
                    "staged_at": staged_at,
                }
            )
        insert_factory = self._insert_factory()
        stmt = insert_factory(StgDailyIndexFiling).values(values)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[StgDailyIndexFiling.business_date, StgDailyIndexFiling.accession_number],
            set_={
                "sync_run_id": excluded.sync_run_id,
                "raw_object_id": excluded.raw_object_id,
                "source_name": excluded.source_name,
                "source_url": excluded.source_url,
                "source_year": excluded.source_year,
                "source_quarter": excluded.source_quarter,
                "row_ordinal": excluded.row_ordinal,
                "form": excluded.form,
                "company_name": excluded.company_name,
                "cik": excluded.cik,
                "filing_date": excluded.filing_date,
                "file_name": excluded.file_name,
                "filing_txt_url": excluded.filing_txt_url,
                "record_hash": excluded.record_hash,
                "staged_at": excluded.staged_at,
            },
        )
        self._session.execute(stmt)
        return len(rows)

    def get_daily_index_filings(self, business_date: str) -> list[dict[str, Any]]:
        stmt = (
            select(StgDailyIndexFiling)
            .where(StgDailyIndexFiling.business_date == self._as_date(business_date))
            .order_by(StgDailyIndexFiling.row_ordinal)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_dict(r) for r in rows]

    def upsert_daily_index_checkpoint(self, row: dict[str, Any]) -> None:
        insert_factory = self._insert_factory()
        stmt = insert_factory(SecDailyIndexCheckpoint).values(
            business_date=self._as_date(row["business_date"]),
            source_name=row.get("source_name", "daily_form_index"),
            source_key=row["source_key"],
            source_url=row["source_url"],
            expected_available_at=row["expected_available_at"],
            first_attempt_at=row.get("first_attempt_at"),
            last_attempt_at=row.get("last_attempt_at"),
            attempt_count=row.get("attempt_count", 1),
            raw_object_id=row.get("raw_object_id"),
            last_sha256=row.get("last_sha256"),
            row_count=row.get("row_count"),
            distinct_cik_count=row.get("distinct_cik_count"),
            distinct_accession_count=row.get("distinct_accession_count"),
            status=row.get("status", "pending"),
            error_message=row.get("error_message"),
            finalized_at=row.get("finalized_at"),
            last_success_at=row.get("last_success_at"),
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[SecDailyIndexCheckpoint.business_date],
            set_={
                "first_attempt_at": func.coalesce(
                    SecDailyIndexCheckpoint.first_attempt_at,
                    excluded.first_attempt_at,
                    SecDailyIndexCheckpoint.last_attempt_at,
                    excluded.last_attempt_at,
                ),
                "last_attempt_at": excluded.last_attempt_at,
                "attempt_count": SecDailyIndexCheckpoint.attempt_count + 1,
                "raw_object_id": excluded.raw_object_id,
                "last_sha256": excluded.last_sha256,
                "row_count": excluded.row_count,
                "distinct_cik_count": excluded.distinct_cik_count,
                "distinct_accession_count": excluded.distinct_accession_count,
                "status": excluded.status,
                "error_message": excluded.error_message,
                "finalized_at": excluded.finalized_at,
                "last_success_at": excluded.last_success_at,
            },
        )
        self._session.execute(stmt)

    def get_daily_index_checkpoint(self, business_date: str) -> Optional[dict[str, Any]]:
        row = self._session.get(SecDailyIndexCheckpoint, self._as_date(business_date))
        return self._to_dict(row) if row else None

    def get_last_successful_checkpoint_date(self) -> Optional[str]:
        stmt = (
            select(SecDailyIndexCheckpoint.business_date)
            .where(SecDailyIndexCheckpoint.status == "succeeded")
            .order_by(SecDailyIndexCheckpoint.business_date.desc())
            .limit(1)
        )
        row = self._session.execute(stmt).first()
        return None if row is None else str(row[0])

    def get_pending_checkpoint_dates(self, up_to_date: str) -> list[str]:
        stmt = (
            select(SecDailyIndexCheckpoint.business_date)
            .where(
                SecDailyIndexCheckpoint.status.in_(("pending", "failed_retryable")),
                SecDailyIndexCheckpoint.business_date <= self._as_date(up_to_date),
            )
            .order_by(SecDailyIndexCheckpoint.business_date.asc())
        )
        rows = self._session.execute(stmt).all()
        return [str(r[0]) for r in rows]

    # -- discovery_checkpoint -------------------------------------------------

    def get_discovery_checkpoint(self, scope_type: str, scope_key: str) -> Optional[dict[str, Any]]:
        row = self._session.get(DiscoveryCheckpoint, (scope_type, scope_key))
        return self._to_dict(row) if row else None

    # daily_incremental's own --recurring-index-lookback-days revalidation
    # (CLAUDE.md's "Daily accession-expansion 5-whys") deliberately re-claims
    # the same rolling-window CIK set across separate calendar days -- that
    # part is intentional (Ticket 45, release-readiness map: "force-recheck
    # the trailing seven calendar days on every run", to catch a late SEC
    # daily-index republish). It was NOT intentional for two runs on the SAME
    # calendar day: confirmed live 2026-09-03, two consecutive same-day
    # daily_incremental executions both emitted cik_count: 9205 for the
    # identical 5 business days -- the second run fully reprocessed CIKs the
    # first had already succeeded on minutes earlier. At that scale the
    # original per-CIK loop below (one SELECT + one INSERT per CIK, no
    # batching) cost ~30 minutes of pure Postgres round-trip latency every
    # single run, confirmed via CloudWatch: a ~36-minute silent gap between
    # the last SEC daily-index download and the first bronze_capture_progress
    # log line, with zero log output in between. Batched into one chunked
    # SELECT (existing in_progress-under-another-run rows, plus a same-day
    # succeeded-under-this-source check added as a follow-up fix, see
    # claim_discovery_ciks' own inline comment) plus one chunked bulk upsert
    # -- O(2 * ceil(N/chunk_size)) round trips instead of O(2N). Chunk size
    # bounds bind-parameter count per statement (each upserted row is 9
    # columns; Postgres' ~65535-parameter-per-statement ceiling would
    # otherwise be exceeded well before N=9205).
    _DISCOVERY_CLAIM_CHUNK_SIZE = 1000

    def claim_discovery_ciks(
        self, ciks: list[int], *, discovery_source: str, run_id: str, claimed_at: datetime
    ) -> list[int]:
        deduped: list[int] = []
        seen: set[int] = set()
        for raw_cik in ciks:
            cik = int(raw_cik)
            if cik in seen:
                continue
            seen.add(cik)
            deduped.append(cik)
        if not deduped:
            return []

        scope_keys = [str(cik) for cik in deduped]
        claimed_at_date = self._as_utc_date(claimed_at)
        blocked: set[str] = set()
        for chunk in self._chunks(scope_keys, self._DISCOVERY_CLAIM_CHUNK_SIZE):
            stmt = select(
                DiscoveryCheckpoint.scope_key,
                DiscoveryCheckpoint.status,
                DiscoveryCheckpoint.run_id,
                DiscoveryCheckpoint.discovery_source,
                DiscoveryCheckpoint.finished_at,
            ).where(
                DiscoveryCheckpoint.scope_type == "cik",
                DiscoveryCheckpoint.scope_key.in_(chunk),
            )
            for (
                scope_key,
                status,
                existing_run_id,
                existing_source,
                finished_at,
            ) in self._session.execute(stmt).all():
                if status == "in_progress" and existing_run_id != run_id:
                    blocked.add(scope_key)
                elif (
                    status == "succeeded"
                    and existing_run_id != run_id
                    and existing_source == discovery_source
                    and finished_at is not None
                    and self._as_utc_date(finished_at) == claimed_at_date
                ):
                    # daily_incremental follow-up (change-propagation map),
                    # confirmed live 2026-09-04: without this, a CIK that
                    # already succeeded earlier *today* under this same
                    # discovery_source was reclaimed and fully reprocessed by
                    # the very next run, no matter how recently it finished --
                    # two same-day daily_incremental runs both claimed the
                    # identical 8,699 CIKs. Scoped to same discovery_source and
                    # same UTC calendar day only: a different source (e.g.
                    # bootstrap_next) is unaffected, and Ticket 45's deliberate
                    # 7-day-recheck design is untouched for any CIK not
                    # already succeeded today -- it is reclaimed normally on
                    # the next calendar day, still catching late SEC
                    # daily-index republishes exactly as before.
                    #
                    # existing_run_id != run_id preserves this method's
                    # original, pre-existing invariant (this docstring's own
                    # class-level comment above always said "allow the same
                    # run_id to reclaim") -- a run resuming/retrying under its
                    # own run_id must never be blocked by its own prior
                    # success, only a *different* run's same-day success
                    # should suppress a reclaim. Not reachable via today's
                    # production callers (each execution gets a fresh
                    # run_id), but this is a real invariant worth keeping
                    # explicit and tested, not silently dropped.
                    blocked.add(scope_key)

        claimed = [cik for cik, scope_key in zip(deduped, scope_keys) if scope_key not in blocked]
        if not claimed:
            return []

        insert_factory = self._insert_factory()
        claimed_scope_keys = [str(cik) for cik in claimed]
        for chunk in self._chunks(claimed_scope_keys, self._DISCOVERY_CLAIM_CHUNK_SIZE):
            values = [
                {
                    "scope_type": "cik",
                    "scope_key": scope_key,
                    "discovery_source": discovery_source,
                    "status": "in_progress",
                    "run_id": run_id,
                    "claimed_at": claimed_at,
                    "finished_at": None,
                    "updated_at": claimed_at,
                    "metadata_json": None,
                }
                for scope_key in chunk
            ]
            stmt = insert_factory(DiscoveryCheckpoint).values(values)
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=[DiscoveryCheckpoint.scope_type, DiscoveryCheckpoint.scope_key],
                set_={
                    "discovery_source": excluded.discovery_source,
                    "status": excluded.status,
                    "run_id": excluded.run_id,
                    "claimed_at": excluded.claimed_at,
                    "finished_at": excluded.finished_at,
                    "updated_at": excluded.updated_at,
                    "metadata_json": excluded.metadata_json,
                },
            )
            self._session.execute(stmt)
        return claimed

    def finish_discovery_ciks(
        self,
        ciks: list[int],
        *,
        discovery_source: str,
        run_id: str,
        status: str,
        finished_at: datetime,
    ) -> None:
        seen: set[int] = set()
        insert_factory = self._insert_factory()
        for raw_cik in ciks:
            cik = int(raw_cik)
            if cik in seen:
                continue
            seen.add(cik)
            scope_key = str(cik)
            stmt = insert_factory(DiscoveryCheckpoint).values(
                scope_type="cik",
                scope_key=scope_key,
                discovery_source=discovery_source,
                status=status,
                run_id=run_id,
                claimed_at=finished_at,
                finished_at=finished_at,
                updated_at=finished_at,
                metadata_json=None,
            )
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=[DiscoveryCheckpoint.scope_type, DiscoveryCheckpoint.scope_key],
                set_={
                    "discovery_source": excluded.discovery_source,
                    "status": excluded.status,
                    "run_id": excluded.run_id,
                    "finished_at": excluded.finished_at,
                    "updated_at": excluded.updated_at,
                },
            )
            self._session.execute(stmt)

    # -- pipeline_run_lease ---------------------------------------------------

    def acquire_pipeline_run_lease(
        self,
        *,
        lease_name: str,
        run_id: str,
        mode: str,
        acquired_at: datetime,
        stale_after_seconds: int = 20 * 3600,
    ) -> bool:
        stale_cutoff = acquired_at - timedelta(seconds=stale_after_seconds)
        insert_factory = self._insert_factory()
        stmt = insert_factory(PipelineRunLease).values(
            lease_name=lease_name,
            status="held",
            run_id=run_id,
            mode=mode,
            acquired_at=acquired_at,
            released_at=None,
            updated_at=acquired_at,
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[PipelineRunLease.lease_name],
            set_={
                "status": "held",
                "run_id": excluded.run_id,
                "mode": excluded.mode,
                "acquired_at": excluded.acquired_at,
                "released_at": None,
                "updated_at": excluded.updated_at,
            },
            where=(
                (PipelineRunLease.status != "held") | (PipelineRunLease.acquired_at < stale_cutoff)
            ),
        )
        self._session.execute(stmt)
        row = self.get_pipeline_run_lease(lease_name)
        return bool(row and row.get("run_id") == run_id and row.get("status") == "held")

    def release_pipeline_run_lease(self, *, lease_name: str, run_id: str, released_at: datetime) -> None:
        stmt = (
            update(PipelineRunLease)
            .where(
                PipelineRunLease.lease_name == lease_name,
                PipelineRunLease.run_id == run_id,
                PipelineRunLease.status == "held",
            )
            .values(
                status="idle",
                released_at=released_at,
                updated_at=released_at,
                backstop_overdue=case(
                    (PipelineRunLease.mode == "backstop", False),
                    else_=PipelineRunLease.backstop_overdue,
                ),
            )
        )
        self._session.execute(stmt)

    def mark_pipeline_run_lease_backstop_overdue(self, *, lease_name: str) -> None:
        stmt = (
            update(PipelineRunLease)
            .where(PipelineRunLease.lease_name == lease_name)
            .values(backstop_overdue=True)
        )
        self._session.execute(stmt)

    def get_pipeline_run_lease(self, lease_name: str) -> Optional[dict[str, Any]]:
        row = self._session.get(PipelineRunLease, lease_name)
        return self._to_dict(row) if row else None

    # -- sec_parse_run --------------------------------------------------------

    def start_parse_run(self, row: dict[str, Any]) -> None:
        for key in ("parse_run_id", "parser_name", "parser_version", "target_form_family"):
            if row.get(key) is None:
                raise ValueError(f"start_parse_run requires {key!r}")
        started_at = row.get("started_at") or datetime.now(timezone.utc)
        instance = SecParseRun(
            parse_run_id=row["parse_run_id"],
            accession_number=row.get("accession_number"),
            parser_name=row["parser_name"],
            parser_version=row["parser_version"],
            target_form_family=row["target_form_family"],
            status="running",
            started_at=started_at,
            rows_written=row.get("rows_written"),
        )
        self._session.add(instance)

    def complete_parse_run(
        self,
        parse_run_id: str,
        status: str = "succeeded",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        rows_written: Optional[int] = None,
    ) -> None:
        if not parse_run_id:
            raise ValueError("complete_parse_run requires parse_run_id")
        completed_at = datetime.now(timezone.utc)
        stmt = (
            update(SecParseRun)
            .where(SecParseRun.parse_run_id == parse_run_id)
            .values(
                status=status,
                completed_at=completed_at,
                error_code=error_code,
                error_message=error_message,
                rows_written=func.coalesce(rows_written, SecParseRun.rows_written),
            )
        )
        self._session.execute(stmt)

    def get_parse_run(self, parse_run_id: str) -> Optional[dict[str, Any]]:
        row = self._session.get(SecParseRun, parse_run_id)
        return self._to_dict(row) if row else None

    def has_successful_parse_run(
        self, *, accession_number: str, parser_name: str, parser_version: str
    ) -> bool:
        """True when a succeeded sec_parse_run row matches this natural key.

        Ticket 03: infrastructure/silver_once.py::has_successful_ownership_parse
        looks up by (accession_number, parser_name, parser_version), not by
        parse_run_id (get_parse_run's only key) -- no existing method covers
        this lookup shape.
        """
        stmt = select(SecParseRun.parse_run_id).where(
            SecParseRun.accession_number == accession_number,
            SecParseRun.parser_name == parser_name,
            SecParseRun.parser_version == parser_version,
            SecParseRun.status == "succeeded",
        ).limit(1)
        return self._session.execute(stmt).first() is not None

    # -- sec_sync_run -----------------------------------------------------------

    def start_sync_run(self, row: dict[str, Any]) -> None:
        for key in ("sync_run_id", "sync_mode", "scope_type"):
            if row.get(key) is None:
                raise ValueError(f"start_sync_run requires {key!r}")
        started_at = row.get("started_at") or datetime.now(timezone.utc)
        status = row.get("status", "running")
        insert_factory = self._insert_factory()
        stmt = insert_factory(SecSyncRun).values(
            sync_run_id=row["sync_run_id"],
            sync_mode=row["sync_mode"],
            scope_type=row["scope_type"],
            scope_key=row.get("scope_key"),
            started_at=started_at,
            status=status,
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[SecSyncRun.sync_run_id],
            set_={
                "sync_mode": excluded.sync_mode,
                "scope_type": excluded.scope_type,
                "scope_key": excluded.scope_key,
                "started_at": excluded.started_at,
                "status": excluded.status,
            },
        )
        self._session.execute(stmt)

    def complete_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str,
        rows_inserted: Optional[int] = None,
        rows_updated: Optional[int] = None,
        rows_deleted: Optional[int] = None,
        rows_skipped: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        stmt = (
            update(SecSyncRun)
            .where(SecSyncRun.sync_run_id == sync_run_id)
            .values(
                completed_at=completed_at,
                status=status,
                rows_inserted=rows_inserted,
                rows_updated=rows_updated,
                rows_deleted=rows_deleted,
                rows_skipped=rows_skipped,
                error_message=error_message,
            )
        )
        self._session.execute(stmt)

    def get_sync_run(self, sync_run_id: str) -> Optional[dict[str, Any]]:
        row = self._session.get(SecSyncRun, sync_run_id)
        return self._to_dict(row) if row else None

    # -- pipeline_run -------------------------------------------------------

    def start_pipeline_run(self, row: dict[str, Any]) -> None:
        insert_factory = self._insert_factory()
        stmt = insert_factory(PipelineRun).values(
            pipeline_run_id=row["pipeline_run_id"],
            command_name=row.get("command_name"),
            runtime_mode=row.get("runtime_mode"),
            environment_name=row.get("environment_name"),
            started_at=row.get("started_at"),
            status=row.get("status"),
            arguments_json=self._json_text(row.get("arguments")),
            scope_json=self._json_text(row.get("scope")),
            bronze_root=row.get("bronze_root"),
            storage_root=row.get("storage_root"),
            silver_root=row.get("silver_root"),
            serving_export_root=row.get("serving_export_root"),
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[PipelineRun.pipeline_run_id],
            set_={
                "command_name": excluded.command_name,
                "runtime_mode": excluded.runtime_mode,
                "environment_name": excluded.environment_name,
                "started_at": excluded.started_at,
                "status": excluded.status,
                "arguments_json": excluded.arguments_json,
                "scope_json": excluded.scope_json,
                "bronze_root": excluded.bronze_root,
                "storage_root": excluded.storage_root,
                "silver_root": excluded.silver_root,
                "serving_export_root": excluded.serving_export_root,
                "completed_at": None,
                "writes_json": None,
                "raw_writes_json": None,
                "metrics_json": None,
                "error_message": None,
                "verification_status": None,
                "last_verified_at": None,
                "verification_report_json": None,
            },
        )
        self._session.execute(stmt)

    def complete_pipeline_run(
        self,
        pipeline_run_id: str,
        *,
        status: str,
        writes: list[dict[str, Any]],
        raw_writes: list[dict[str, Any]],
        metrics: Optional[dict[str, Any]],
        error_message: Optional[str] = None,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        stmt = (
            update(PipelineRun)
            .where(PipelineRun.pipeline_run_id == pipeline_run_id)
            .values(
                completed_at=completed_at,
                status=status,
                writes_json=self._json_text(writes),
                raw_writes_json=self._json_text(raw_writes),
                metrics_json=self._json_text(metrics),
                error_message=error_message,
            )
        )
        self._session.execute(stmt)

    def record_pipeline_verification(
        self, pipeline_run_id: str, *, verification_status: str, report: dict[str, Any]
    ) -> None:
        last_verified_at = datetime.now(timezone.utc)
        stmt = (
            update(PipelineRun)
            .where(PipelineRun.pipeline_run_id == pipeline_run_id)
            .values(
                verification_status=verification_status,
                last_verified_at=last_verified_at,
                verification_report_json=self._json_text(report),
            )
        )
        self._session.execute(stmt)

    def get_pipeline_run(self, pipeline_run_id: str) -> Optional[dict[str, Any]]:
        row = self._session.get(PipelineRun, pipeline_run_id)
        return self._to_dict(row) if row else None

    def get_recent_successful_pipeline_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Recent succeeded/ok pipeline_run rows with metrics, most-recent-first.

        Ticket 03: replaces application/commands/validate_data_quality.py's
        _latest_previous_table_counts raw SQL: `SELECT pipeline_run_id,
        metrics_json FROM pipeline_run WHERE status IN ('succeeded', 'ok')
        AND metrics_json IS NOT NULL ORDER BY completed_at DESC NULLS LAST,
        started_at DESC LIMIT 10`. completed_at and metrics_json are always
        set together by complete_pipeline_run, so a NULL completed_at with
        non-NULL metrics_json can't arise through this store's own write
        path today -- the NULLS LAST ordering (and the started_at DESC
        tiebreak) is kept anyway to match the original query's defensive
        handling of that state exactly.
        """
        stmt = (
            select(PipelineRun)
            .where(
                PipelineRun.status.in_(("succeeded", "ok")),
                PipelineRun.metrics_json.is_not(None),
            )
            .order_by(PipelineRun.completed_at.desc().nulls_last(), PipelineRun.started_at.desc())
            .limit(limit)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_dict(r) for r in rows]

    # -- gold_manifest --------------------------------------------------------

    def _latest_gold_manifest_for_table(
        self, *, table_name: str, storage_layer: str, exclude_run_id: str
    ) -> Optional[dict[str, Any]]:
        stmt = (
            select(GoldManifest)
            .where(
                GoldManifest.table_name == table_name,
                GoldManifest.storage_layer == storage_layer,
                GoldManifest.run_id != exclude_run_id,
            )
            .order_by(GoldManifest.recorded_at.desc(), GoldManifest.run_id.desc())
            .limit(1)
        )
        row = self._session.execute(stmt).scalars().first()
        return self._to_dict(row) if row else None

    def record_gold_manifest(self, *, run_id: str, command_name: str, entries: list[dict[str, Any]]) -> None:
        insert_factory = self._insert_factory()
        for entry in entries:
            table_name = entry["table_name"]
            storage_layer = entry["storage_layer"]
            previous = self._latest_gold_manifest_for_table(
                table_name=table_name, storage_layer=storage_layer, exclude_run_id=run_id
            )
            previous_run_id = previous["run_id"] if previous else None
            previous_row_count = previous["row_count"] if previous else None
            previous_parquet_sha256 = previous["parquet_sha256"] if previous else None
            row_count = entry["row_count"]
            parquet_sha256 = entry["parquet_sha256"]
            row_count_delta = (
                row_count - previous_row_count if previous_row_count is not None else None
            )
            parquet_changed = previous_parquet_sha256 != parquet_sha256
            recorded_at = entry.get("recorded_at") or datetime.now(timezone.utc)
            stmt = insert_factory(GoldManifest).values(
                run_id=run_id,
                command_name=command_name,
                table_name=table_name,
                storage_layer=storage_layer,
                relative_path=entry["relative_path"],
                storage_path=entry.get("storage_path"),
                row_count=row_count,
                parquet_sha256=parquet_sha256,
                byte_size=entry.get("byte_size"),
                previous_run_id=previous_run_id,
                previous_row_count=previous_row_count,
                previous_parquet_sha256=previous_parquet_sha256,
                row_count_delta=row_count_delta,
                parquet_changed=parquet_changed,
                recorded_at=recorded_at,
            )
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=[GoldManifest.run_id, GoldManifest.storage_layer, GoldManifest.table_name],
                set_={
                    "command_name": excluded.command_name,
                    "relative_path": excluded.relative_path,
                    "storage_path": excluded.storage_path,
                    "row_count": excluded.row_count,
                    "parquet_sha256": excluded.parquet_sha256,
                    "byte_size": excluded.byte_size,
                    "previous_run_id": excluded.previous_run_id,
                    "previous_row_count": excluded.previous_row_count,
                    "previous_parquet_sha256": excluded.previous_parquet_sha256,
                    "row_count_delta": excluded.row_count_delta,
                    "parquet_changed": excluded.parquet_changed,
                    "recorded_at": excluded.recorded_at,
                },
            )
            self._session.execute(stmt)

    def get_gold_manifest(self, run_id: Optional[str] = None) -> list[dict[str, Any]]:
        stmt = select(GoldManifest)
        if run_id is None:
            stmt = stmt.order_by(
                GoldManifest.recorded_at, GoldManifest.run_id, GoldManifest.storage_layer, GoldManifest.table_name
            )
        else:
            stmt = stmt.where(GoldManifest.run_id == run_id).order_by(
                GoldManifest.storage_layer, GoldManifest.table_name
            )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_dict(r) for r in rows]

    # -- sec_source_checkpoint --------------------------------------------------

    def upsert_source_checkpoint(self, row: dict[str, Any]) -> None:
        insert_factory = self._insert_factory()
        stmt = insert_factory(SecSourceCheckpoint).values(
            source_name=row["source_name"],
            source_key=row["source_key"],
            raw_object_id=row.get("raw_object_id"),
            last_success_at=row.get("last_success_at"),
            last_sha256=row.get("last_sha256"),
            last_etag=row.get("last_etag"),
            last_modified_at=row.get("last_modified_at"),
            last_acceptance_datetime_seen=row.get("last_acceptance_datetime_seen"),
            last_accession_number_seen=row.get("last_accession_number_seen"),
            bronze_path=row.get("bronze_path"),
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[SecSourceCheckpoint.source_name, SecSourceCheckpoint.source_key],
            set_={
                "raw_object_id": excluded.raw_object_id,
                "last_success_at": excluded.last_success_at,
                "last_sha256": excluded.last_sha256,
                "last_etag": excluded.last_etag,
                "last_modified_at": excluded.last_modified_at,
                "last_acceptance_datetime_seen": excluded.last_acceptance_datetime_seen,
                "last_accession_number_seen": excluded.last_accession_number_seen,
                "bronze_path": excluded.bronze_path,
            },
        )
        self._session.execute(stmt)

    def get_source_checkpoint(self, source_name: str, source_key: str) -> Optional[dict[str, Any]]:
        row = self._session.get(SecSourceCheckpoint, (source_name, source_key))
        return self._to_dict(row) if row else None

    # -- sec_company_sync_state --------------------------------------------------

    def upsert_company_sync_state(self, row: dict[str, Any]) -> None:
        insert_factory = self._insert_factory()
        stmt = insert_factory(SecCompanySyncState).values(
            cik=row["cik"],
            tracking_status=row["tracking_status"],
            bootstrap_completed_at=row.get("bootstrap_completed_at"),
            last_main_sync_at=row.get("last_main_sync_at"),
            last_main_raw_object_id=row.get("last_main_raw_object_id"),
            last_main_sha256=row.get("last_main_sha256"),
            latest_filing_date_seen=self._as_date(row.get("latest_filing_date_seen")),
            latest_acceptance_datetime_seen=row.get("latest_acceptance_datetime_seen"),
            pagination_files_expected=row.get("pagination_files_expected"),
            pagination_files_loaded=row.get("pagination_files_loaded"),
            pagination_completed_at=row.get("pagination_completed_at"),
            next_sync_after=row.get("next_sync_after"),
            last_error_message=row.get("last_error_message"),
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[SecCompanySyncState.cik],
            set_={
                "tracking_status": excluded.tracking_status,
                "bootstrap_completed_at": func.coalesce(
                    excluded.bootstrap_completed_at, SecCompanySyncState.bootstrap_completed_at
                ),
                "last_main_sync_at": func.coalesce(
                    excluded.last_main_sync_at, SecCompanySyncState.last_main_sync_at
                ),
                "last_main_raw_object_id": func.coalesce(
                    excluded.last_main_raw_object_id, SecCompanySyncState.last_main_raw_object_id
                ),
                "last_main_sha256": func.coalesce(
                    excluded.last_main_sha256, SecCompanySyncState.last_main_sha256
                ),
                "latest_filing_date_seen": func.coalesce(
                    excluded.latest_filing_date_seen, SecCompanySyncState.latest_filing_date_seen
                ),
                "latest_acceptance_datetime_seen": func.coalesce(
                    excluded.latest_acceptance_datetime_seen,
                    SecCompanySyncState.latest_acceptance_datetime_seen,
                ),
                "pagination_files_expected": func.coalesce(
                    excluded.pagination_files_expected, SecCompanySyncState.pagination_files_expected
                ),
                "pagination_files_loaded": func.coalesce(
                    excluded.pagination_files_loaded, SecCompanySyncState.pagination_files_loaded
                ),
                "pagination_completed_at": func.coalesce(
                    excluded.pagination_completed_at, SecCompanySyncState.pagination_completed_at
                ),
                "next_sync_after": func.coalesce(
                    excluded.next_sync_after, SecCompanySyncState.next_sync_after
                ),
                "last_error_message": excluded.last_error_message,
            },
        )
        self._session.execute(stmt)

    def get_company_sync_state(self, cik: int) -> Optional[dict[str, Any]]:
        row = self._session.get(SecCompanySyncState, cik)
        return self._to_dict(row) if row else None

    def seed_company_sync_state_bulk(self, ciks: list[int]) -> int:
        deduped = list(dict.fromkeys(int(cik) for cik in ciks))
        if not deduped:
            return 0
        values = [
            {"cik": cik, "tracking_status": "bootstrap_pending", "last_error_message": None}
            for cik in deduped
        ]
        insert_factory = self._insert_factory()
        stmt = insert_factory(SecCompanySyncState).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SecCompanySyncState.cik],
            set_={"last_error_message": None},
        )
        self._session.execute(stmt)
        return len(deduped)

    # Sibling of _DISCOVERY_CLAIM_CHUNK_SIZE's bug (found live 2026-09-03,
    # same daily_incremental investigation, same /diagnosing-bugs session):
    # _seed_silver_tracking_status/_demote_deregistered_ciks
    # (warehouse_orchestrator.py) looped one SELECT+INSERT (seed) or one
    # INSERT (demote) per CIK, no batching -- at daily_incremental's real
    # ~9,205 impacted-CIK scale this was a second, independent multi-minute
    # stall sitting immediately BEFORE claim_discovery_ciks in the same
    # call chain, confirmed live via CloudWatch after the
    # claim_discovery_ciks fix alone did not close the observed gap.
    _COMPANY_SYNC_STATE_BULK_CHUNK_SIZE = 1000

    def seed_company_sync_state_bulk_if_missing(
        self, ciks: list[int], *, tracking_status: str
    ) -> int:
        """Bulk-insert sec_company_sync_state rows for CIKs with no existing
        row, leaving any already-tracked CIK's row completely untouched --
        not even last_error_message, unlike seed_company_sync_state_bulk
        above (which hardcodes tracking_status='bootstrap_pending' and
        always clears last_error_message on conflict; a genuinely different
        caller/contract, seed-universe's own initial seeding, not this
        one). ON CONFLICT DO NOTHING is the correct primitive for "insert
        only if truly new" -- preserves _seed_silver_tracking_status's
        existing "existing rows keep their current status" contract
        (tests/unit/test_pipeline_tracking_state.py) while batching what
        was previously one SELECT + one conditional INSERT per CIK into
        chunked bulk statements.
        """
        deduped = list(dict.fromkeys(int(cik) for cik in ciks))
        if not deduped:
            return 0
        insert_factory = self._insert_factory()
        for chunk in self._chunks(deduped, self._COMPANY_SYNC_STATE_BULK_CHUNK_SIZE):
            values = [
                {"cik": cik, "tracking_status": tracking_status, "last_error_message": None}
                for cik in chunk
            ]
            stmt = insert_factory(SecCompanySyncState).values(values)
            stmt = stmt.on_conflict_do_nothing(index_elements=[SecCompanySyncState.cik])
            self._session.execute(stmt)
        return len(deduped)

    def demote_company_sync_state_bulk(self, ciks: list[int], *, demoted_at: datetime) -> int:
        """Bulk-set tracking_status='deregistered' for CIKs with a Form 15
        deregistration filing (seed-universe ticket 03) -- unconditional
        overwrite (a company filing Form 15 was, by definition, already
        tracked), mirroring upsert_company_sync_state's own ON CONFLICT
        semantics for exactly the 3 fields _demote_deregistered_ciks sets,
        just batched. Unspecified columns (bootstrap_completed_at, etc.)
        are omitted from the INSERT the same way the original per-row
        upsert_company_sync_state({"cik":..., "tracking_status":...,
        "last_main_sync_at":..., "last_error_message": None}) call left
        them as None -- functionally identical, not merely similar.
        """
        deduped = list(dict.fromkeys(int(cik) for cik in ciks))
        if not deduped:
            return 0
        insert_factory = self._insert_factory()
        for chunk in self._chunks(deduped, self._COMPANY_SYNC_STATE_BULK_CHUNK_SIZE):
            values = [
                {
                    "cik": cik,
                    "tracking_status": "deregistered",
                    "last_main_sync_at": demoted_at,
                    "last_error_message": None,
                }
                for cik in chunk
            ]
            stmt = insert_factory(SecCompanySyncState).values(values)
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=[SecCompanySyncState.cik],
                set_={
                    "tracking_status": excluded.tracking_status,
                    "last_main_sync_at": excluded.last_main_sync_at,
                    "last_error_message": excluded.last_error_message,
                },
            )
            self._session.execute(stmt)
        return len(deduped)

    def get_tracked_ciks(self, tracking_status_filter: str = "active") -> list[int]:
        stmt = select(SecCompanySyncState.cik)
        tokens = [t.strip() for t in (tracking_status_filter or "").split(",") if t.strip()]
        if tokens and "all" not in tokens:
            stmt = stmt.where(SecCompanySyncState.tracking_status.in_(tokens))
        stmt = stmt.order_by(SecCompanySyncState.cik)
        return [row[0] for row in self._session.execute(stmt).all()]

    def get_all_company_sync_states(self) -> list[dict[str, Any]]:
        """Every sec_company_sync_state row, unfiltered.

        Ticket 03: callers doing a bulk cik -> tracking_status lookup
        (mdm/pipeline.py::run_companies, mdm/cli.py::_seed_mdm_from_silver's
        fallback branches) previously ran an unfiltered
        `SELECT cik, tracking_status FROM sec_company_sync_state` directly
        against DuckDB -- no existing method returns every row.
        """
        stmt = select(SecCompanySyncState).order_by(SecCompanySyncState.cik)
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_dict(r) for r in rows]

    def get_ciks_with_bronze(self, tracking_status_filter: str = "all") -> list[dict[str, Any]]:
        key_expr = literal("cik:").concat(cast(SecCompanySyncState.cik, String))
        exists_clause = (
            select(1)
            .where(
                SecSourceCheckpoint.source_name == "submissions_main",
                SecSourceCheckpoint.source_key == key_expr,
            )
            .exists()
        )
        stmt = select(SecCompanySyncState.cik).distinct().where(exists_clause)
        if tracking_status_filter and tracking_status_filter != "all":
            stmt = stmt.where(SecCompanySyncState.tracking_status == tracking_status_filter)
        stmt = stmt.order_by(SecCompanySyncState.cik)
        rows = self._session.execute(stmt).all()
        return [{"cik": r[0]} for r in rows]

    # -- sec_reconcile_finding -----------------------------------------------

    def insert_reconcile_findings(self, rows: list[dict[str, Any]]) -> int:
        insert_factory = self._insert_factory()
        count = 0
        for row in rows:
            detected_at = row.get("detected_at") or datetime.now(timezone.utc)
            stmt = insert_factory(SecReconcileFinding).values(
                reconcile_run_id=row["reconcile_run_id"],
                cik=row["cik"],
                scope_type=row["scope_type"],
                object_type=row["object_type"],
                object_key=row["object_key"],
                drift_type=row["drift_type"],
                expected_value_hash=row.get("expected_value_hash"),
                actual_value_hash=row.get("actual_value_hash"),
                severity=row.get("severity", "medium"),
                recommended_action=row.get("recommended_action", "manual_review"),
                status=row.get("status", "detected"),
                detected_at=detected_at,
                resolved_at=row.get("resolved_at"),
                resync_run_id=row.get("resync_run_id"),
            )
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    SecReconcileFinding.reconcile_run_id,
                    SecReconcileFinding.cik,
                    SecReconcileFinding.scope_type,
                    SecReconcileFinding.object_type,
                    SecReconcileFinding.object_key,
                    SecReconcileFinding.drift_type,
                ],
                set_={
                    "expected_value_hash": excluded.expected_value_hash,
                    "actual_value_hash": excluded.actual_value_hash,
                    "severity": excluded.severity,
                    "recommended_action": excluded.recommended_action,
                    "status": excluded.status,
                    "detected_at": excluded.detected_at,
                    "resolved_at": excluded.resolved_at,
                    "resync_run_id": excluded.resync_run_id,
                },
            )
            self._session.execute(stmt)
            count += 1
        return count

    def get_reconcile_findings(self, reconcile_run_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(SecReconcileFinding)
            .where(SecReconcileFinding.reconcile_run_id == reconcile_run_id)
            .order_by(
                SecReconcileFinding.cik,
                SecReconcileFinding.scope_type,
                SecReconcileFinding.object_type,
                SecReconcileFinding.object_key,
            )
        )
        rows = self._session.execute(stmt).scalars().all()
        return [self._to_dict(r) for r in rows]

    # -- narrowed get_table_counts (11 tables only; see module docstring) ----

    def get_table_counts(self) -> dict[str, int]:
        # Looks up the Core Table straight from Base.metadata (keyed by the
        # same table_name strings BOOKKEEPING_TABLES already lists) rather
        # than a separately hand-kept table_name -> model class dict, so
        # the two can't silently desync if a table is ever added/renamed.
        counts: dict[str, int] = {}
        for table_name in BOOKKEEPING_TABLES:
            table = Base.metadata.tables[table_name]
            count = self._session.execute(select(func.count()).select_from(table)).scalar_one()
            counts[table_name] = count
        return counts
