"""MDM pipeline orchestrator.

Runs resolvers in the correct dependency order:
  1. Company   (no dependencies)
  2. Adviser   (links to Company via CIK)
  3. Security  (links to Company as issuer)
  4. Person    (links to Company via ownership filings)
  5. Fund      (links to Adviser)

Each phase reads from silver, resolves/creates MDM entities, and commits.
Graph sync runs last.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.mdm.database import get_session
from edgar_warehouse.mdm.graph import GraphSyncEngine
from edgar_warehouse.mdm.match import MatchAction
from edgar_warehouse.mdm.observability import elapsed_ms, emit_mdm_event
from edgar_warehouse.mdm.resolvers import (
    CompanyResolver,
    PersonResolver,
    SecurityResolver,
)
from edgar_warehouse.mdm.resolvers.base import ResolverContext, SilverReader
from edgar_warehouse.mdm.rules import MDMRuleEngine

# All three per-row resolve loops (run_companies, run_securities,
# run_persons) are network-round-trip-bound against MDM's Postgres store
# (~68ms/call measured live, us-east-1 ECS tasks against a us-west-2
# Snowflake Postgres endpoint -- see pipeline-throughput-architecture map's
# MDM addendum), not CPU-bound, so bounded thread concurrency hides that
# latency instead of fighting it. Shared default of 16 (mdm-run-throughput
# map); each domain can override independently. database.py's connection
# pool budget (MDM_DB_POOL_SIZE/MDM_DB_MAX_OVERFLOW) is sized to cover this
# default plus the pipeline's own primary session -- raise both together.
_RESOLVE_MAX_WORKERS = int(os.environ.get("MDM_RESOLVE_CONCURRENCY", "16"))
_COMPANY_RESOLVE_MAX_WORKERS = int(
    os.environ.get("MDM_COMPANY_RESOLVE_CONCURRENCY", str(_RESOLVE_MAX_WORKERS))
)
_SECURITY_RESOLVE_MAX_WORKERS = int(
    os.environ.get("MDM_SECURITY_RESOLVE_CONCURRENCY", str(_RESOLVE_MAX_WORKERS))
)
_PERSON_RESOLVE_MAX_WORKERS = int(
    os.environ.get("MDM_PERSON_RESOLVE_CONCURRENCY", str(_RESOLVE_MAX_WORKERS))
)

# derive_relationships() concurrency -- one worker per relationship *type*
# (11 today, RELATIONSHIP_TYPES below), each on its own session, mirroring
# the per-row worker-session pattern above. Deliberately a smaller default
# than the row-level pools: type-level tasks are much coarser-grained (one
# task can be a single-digit-millions-row derivation, e.g. INSTITUTIONAL_HOLDS)
# and this pool runs *after* every run_all() entity-resolution step has
# finished (derive_relationships()'s trigger is unchanged by
# mdm-run-step-parallelism ticket 02 below -- still waits for all 5), so it
# doesn't need to share connection-pool headroom with those pools at the
# same time.
_RELATIONSHIP_DERIVE_MAX_WORKERS = int(os.environ.get("MDM_RELATIONSHIP_CONCURRENCY", "4"))

# mdm-run-step-parallelism wayfinder map, ticket 02
# (.scratch/mdm-run-step-parallelism/issues/02-decide-parallelism-shape.md):
# run_all()'s five entity-resolution steps (company/adviser/security/person/
# fund) now launch as concurrent top-level futures instead of running
# sequentially -- each on its own fresh MDMPipeline instance/session (the
# same "worker gets its own session" pattern derive_relationships() already
# uses above), never sharing self.session across steps. company + security
# dominate wall-clock time (2h14m / 1h50m measured live, ticket 01); the
# other three are collectively under 3 minutes, but fold into the same
# concurrent batch anyway since special-casing them out buys nothing.
# Exactly 5 steps exist, so this rarely needs tuning, but exposed for
# consistency with every other concurrency knob in this file.
_RUN_STEP_MAX_WORKERS = int(os.environ.get("MDM_RUN_STEP_CONCURRENCY", "5"))

# Progress-log cadence for the per-row resolve loops below (run_companies,
# run_securities, run_persons). A fixed interval is too chatty for large
# domains (62,190 companies emitted 124 log lines at the old hardcoded-500
# default) and too sparse for small ones -- scale with the domain's own row
# count instead, floored at a configurable minimum so short runs (tests,
# --limit smoke checks) still get periodic progress signal.
_PROGRESS_LOG_MIN_INTERVAL = int(os.environ.get("MDM_PROGRESS_LOG_INTERVAL", "1000"))


def _progress_log_interval(total_rows: int) -> int:
    """Row interval between mdm_progress log events for a resolve loop.

    ``max(configured minimum, total_rows // 8)`` -- roughly 8 progress log
    lines per domain regardless of size, never below the configured floor.
    Override the floor with ``MDM_PROGRESS_LOG_INTERVAL``.
    """
    return max(_PROGRESS_LOG_MIN_INTERVAL, total_rows // 8) if total_rows else _PROGRESS_LOG_MIN_INTERVAL

RELATIONSHIP_TYPES = (
    # ── Existing (ownership + ADV) ────────────────────────────────────────────
    "IS_INSIDER",
    "HOLDS",
    "COMPANY_HOLDS",
    "ISSUED_BY",
    "IS_ENTITY_OF",
    "HAS_PARENT_COMPANY",
    "MANAGES_FUND",
    "IS_PERSON_OF",
    # ── New (fundamentals research) ───────────────────────────────────────────
    "EMPLOYED_BY",          # Person → Company     (DEF 14A proxy)
    "AUDITED_BY",           # Company → AuditFirm  (10-K dei_AuditorFirmId XBRL)
    "INSTITUTIONAL_HOLDS",  # Adviser → Security   (13F holdings)
)

_RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER = 50
_RELATIONSHIP_SOURCE_LIMIT_MINIMUM = 100

# INSTITUTIONAL_HOLDS reads sec_thirteenf_holding -- the largest silver table
# (large fund managers report tens of thousands of positions per quarter) --
# in CIK-range chunks rather than one unbounded silver.fetch() (D-03, TODOS.md).
_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE = 1000

# MANAGES_FUND priming an adviser CRD at a time (rather than the whole type
# unconditionally) -- mdm-oom-manages-fund fix. Measured live 2026-08-21:
# unscoped prime_relationship_type("MANAGES_FUND") materializes ~2GB of ORM
# rows for a table that's only 390MB on disk, and one adviser alone (a
# large fund-administration platform, same outlier already flagged in
# CLAUDE.md's schema-conventions section) holds 89,108 of the 563,631 active
# rows -- 16% from a single CRD. Batched by CRD (not row count) so a single
# oversized adviser's batch is bounded by that adviser's own relationship
# count, not the whole universe's.
_MANAGES_FUND_CRD_BATCH_SIZE = 1000

# _derive_relationship_type's uniform dispatcher prime (below) is skipped for
# these types -- they manage their own (batch-scoped) priming instead of one
# unscoped whole-type load. See _derive_manages_fund.
_SELF_PRIMING_RELATIONSHIP_TYPES = frozenset({"MANAGES_FUND"})


@dataclass
class PipelineStats:
    companies_processed: int = 0
    advisers_processed: int = 0
    persons_processed: int = 0
    securities_processed: int = 0
    funds_processed: int = 0
    graph_nodes_synced: int = 0
    graph_edges_synced: int = 0
    quarantined: int = 0
    sent_to_review: int = 0
    relationships_written: int = 0
    relationship_counts_by_type: dict[str, dict[str, int | None]] = field(default_factory=dict)


def _first_per_key(rows: list[dict], key_field: str) -> dict[Any, dict]:
    """Bulk-prefetch helper: keep only the first row seen per key_field value.

    Used to replicate a per-row ``ORDER BY ... LIMIT 1`` query's semantics
    (first-seen-wins for a given key) against a single bulk-fetched,
    pre-sorted row set instead of one query per key.
    """
    out: dict[Any, dict] = {}
    for row in rows:
        key = row[key_field]
        if key not in out:
            out[key] = row
    return out


def _derive_role(row: dict) -> str:
    if row.get("is_director"):
        return "director"
    if row.get("is_officer"):
        return "officer"
    if row.get("is_ten_percent_owner"):
        return "10pct_owner"
    return "other"


@dataclass
class MDMPipeline:
    session: Session
    silver: SilverReader
    engine: MDMRuleEngine = field(init=False)
    run_id: str = ""

    def __post_init__(self) -> None:
        self.engine = MDMRuleEngine.load(self.session)

    def _ctx(self) -> ResolverContext:
        return ResolverContext(
            session=self.session,
            engine=self.engine,
            silver=self.silver,
            run_id=self.run_id,
        )

    @staticmethod
    def _bounded_relationship_sql(sql: str, remaining: Optional[int], existing: int = 0) -> str:
        """Append a LIMIT that grows with `existing` so the source window keeps
        advancing past already-converted rows on repeat runs.

        Without `existing` in the limit, every run re-reads the same leading
        slice of the (unordered-by-default) source query: rows already turned
        into relationships come back as `skipped_existing` and the run never
        reaches fresh rows further down the table — repeat invocations with the
        same `--limit` plateau at whatever the first run produced. Growing the
        window by `existing` guarantees it always extends past the previously
        converted prefix into unconverted territory, given a stable ORDER BY.
        """
        if remaining is None:
            return sql
        source_limit = int(existing) + max(
            int(remaining) * _RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER,
            _RELATIONSHIP_SOURCE_LIMIT_MINIMUM,
        )
        return f"{sql.rstrip()} LIMIT {source_limit}"

    def _fetch_optional_relationship_rows(
        self,
        sql: str,
        remaining: Optional[int],
        *,
        rel_type_name: str,
        source_table: str | tuple[str, ...],
        existing: int = 0,
    ) -> list[dict]:
        try:
            return self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))
        except Exception as exc:
            missing_table = self._find_missing_source_table(exc, source_table)
            if missing_table is None:
                raise
            print(json.dumps({
                "event": "mdm_relationship_skip",
                "rel_type": rel_type_name,
                "reason": "missing_source_table",
                "source_table": missing_table,
                "ts": datetime.now(timezone.utc).isoformat(),
            }), file=sys.stderr, flush=True)
            return []

    @staticmethod
    def _find_missing_source_table(exc: Exception, table_names: str | tuple[str, ...]) -> str | None:
        # A relationship-derivation query can join more than one source table
        # (e.g. sec_thirteenf_holding JOIN sec_thirteenf_filing for
        # INSTITUTIONAL_HOLDS) -- any one of them can legitimately be absent
        # (no filings of that type loaded yet) and should trigger the same
        # graceful skip, not just the first-declared table. Checking only one
        # name left a real "table not created yet" error on the second table
        # uncaught, crashing the whole mdm run instead of skipping that
        # relationship type.
        message = str(exc).lower()
        missing_markers = ("does not exist", "not found", "catalog error", "binder error")
        if not any(marker in message for marker in missing_markers):
            return None
        names = (table_names,) if isinstance(table_names, str) else table_names
        for name in names:
            if name.lower() in message:
                return name
        return None

    def run_companies(
        self,
        limit: Optional[int] = None,
        *,
        issuer_ciks: Optional[Iterable[int]] = None,
        resume_ledger_run_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> int:
        """Resolve companies from silver.

        Full-universe loads leave ``issuer_ciks`` unset. Ticket 21 insider path
        only needs missing **issuer** shells for the CIKs under test — pass
        those CIKs here; never re-walk the whole sec_company table for insiders.

        Each row resolves on its own worker thread and its own SQLAlchemy
        session (bounded by ``_COMPANY_RESOLVE_MAX_WORKERS``), committing
        independently. This is safe here specifically because
        ``CompanyResolver._existing_candidates`` scopes its match-candidate
        lookup to the row's own CIK (``MdmCompany.cik == cik``) -- concurrent
        rows never share mutable match state, and CIK-exact re-matching makes
        a resumed/retried run idempotent (an already-resolved CIK reuses its
        existing entity_id instead of duplicating it). Ticker/tracking lookups
        are prefetched in bulk up front instead of two extra per-row silver
        reads inside the loop.

        pipeline-resumability ticket 02: ``resume_ledger_run_id`` (mirrors
        bootstrap-batch's own ``--resume-ledger-run-id``) resumes a prior
        full-universe attempt instead of re-resolving all ~62K companies from
        scratch -- a frozen CIK snapshot (written once, at the first attempt
        under ``run_id``) plus batched succeeded-CIK outcome flushes let a
        resumed call skip already-done CIKs. Only valid for the unscoped,
        unlimited full-universe path (``issuer_ciks``/``limit`` both unset)
        -- combining resume with either has undefined semantics (does
        ``limit`` bound the frozen set or the remaining set?) so both are
        rejected together with ``resume_ledger_run_id``. Fails closed
        (``ResumeRunNotFoundError``) when ``resume_ledger_run_id`` is
        explicitly given but no snapshot exists for it -- distinct from a
        first attempt under ``run_id`` alone, which creates the snapshot.
        """
        from edgar_warehouse.mdm.company_resume import (
            ResumeRunNotFoundError,
            read_snapshot,
            read_succeeded_ciks,
            write_outcome_batch,
            write_snapshot,
        )

        resolver = CompanyResolver()
        ciks = self._normalize_issuer_ciks(issuer_ciks)

        explicit_resume_id = str(resume_ledger_run_id or "").strip()
        own_run_id = str(run_id or "").strip()
        effective_run_id = explicit_resume_id or own_run_id

        if explicit_resume_id and (limit or ciks is not None):
            raise WarehouseRuntimeError(
                "run_companies: resume_ledger_run_id is only supported for the "
                "full-universe run (no limit, no issuer_ciks scoping)"
            )

        bronze_root = os.environ.get("WAREHOUSE_BRONZE_ROOT", "").strip()
        resumable = bool(effective_run_id) and ciks is None and not limit and bool(bronze_root)
        if explicit_resume_id and not bronze_root:
            raise WarehouseRuntimeError(
                "run_companies: resume_ledger_run_id requires WAREHOUSE_BRONZE_ROOT to be set"
            )

        already_succeeded: set[int] = set()
        if resumable:
            if explicit_resume_id:
                snapshot_ciks = read_snapshot(bronze_root=bronze_root, run_id=effective_run_id)
                already_succeeded = read_succeeded_ciks(
                    bronze_root=bronze_root, run_id=effective_run_id
                )
            else:
                try:
                    snapshot_ciks = read_snapshot(bronze_root=bronze_root, run_id=effective_run_id)
                    already_succeeded = read_succeeded_ciks(
                        bronze_root=bronze_root, run_id=effective_run_id
                    )
                except ResumeRunNotFoundError:
                    # First attempt under this run_id: query live, freeze the
                    # candidate set now so any later resume reuses it verbatim.
                    snapshot_rows = self.silver.fetch("SELECT cik FROM sec_company")
                    snapshot_ciks = [int(row["cik"]) for row in snapshot_rows]
                    write_snapshot(
                        bronze_root=bronze_root, run_id=effective_run_id, ciks=snapshot_ciks
                    )
            remaining_ciks = [cik for cik in snapshot_ciks if cik not in already_succeeded]
            if remaining_ciks:
                placeholders = ", ".join("?" for _ in remaining_ciks)
                rows = self.silver.fetch(
                    f"SELECT * FROM sec_company WHERE cik IN ({placeholders})", remaining_ciks
                )
            else:
                rows = []
        elif ciks is not None:
            sql = "SELECT * FROM sec_company WHERE cik IN ({})".format(
                ", ".join("?" for _ in ciks)
            )
            if limit:
                sql += f" LIMIT {int(limit)}"
            rows = self.silver.fetch(sql, list(ciks))
        elif limit:
            # release-readiness ticket 94: a bounded (no resume, no
            # issuer_ciks) full-universe call previously plateaued on the
            # same first `limit` rows on every call -- "SELECT * FROM
            # sec_company LIMIT N" has no ORDER BY and no WHERE excluding
            # already-resolved CIKs, so a resolver that idempotently
            # skips/reuses already-resolved CIKs (see this method's own
            # docstring) never advanced past the first N rows in whatever
            # order the table scan happened to return. Confirmed live via a
            # real SilverDatabase-backed repro: 3 successive limit=2 calls
            # against a 5-company universe never resolved past the same
            # first 2 CIKs. This is the identical plateau shape already
            # documented and fixed for relationship-derivation's own source
            # query (_bounded_relationship_sql's docstring above) -- ported
            # here: over-fetch a growing window past the already-resolved
            # prefix (stable ORDER BY cik + the existing-count-scaled LIMIT
            # that helper already computes), exclude already-resolved CIKs,
            # then cap at `limit` genuinely-new candidates -- same
            # bounded-cost-per-call contract as before (at most `limit` real
            # MDM resolutions happen), but the window now actually advances
            # on repeat calls instead of plateauing.
            already_resolved = self._company_cik_set()
            fetch_sql = self._bounded_relationship_sql(
                "SELECT * FROM sec_company ORDER BY cik", limit, len(already_resolved)
            )
            candidate_rows = self.silver.fetch(fetch_sql)
            rows = [
                row for row in candidate_rows if row["cik"] not in already_resolved
            ][: int(limit)]
        else:
            rows = self.silver.fetch("SELECT * FROM sec_company")

        ticker_rows = self.silver.fetch(
            "SELECT cik, ticker, exchange FROM sec_company_ticker "
            "ORDER BY cik, source_rank NULLS LAST"
        )
        ticker_by_cik = _first_per_key(ticker_rows, "cik")
        try:
            tracking_rows = self.silver.fetch(
                "SELECT cik, tracking_status FROM sec_company_sync_state"
            )
        except Exception as exc:
            # sec_company_sync_state is a bookkeeping table with no analog
            # in EDGARTOOLS_SILVER (silver-snowflake-migration map, Ticket
            # 09's table-coverage check -- 8 operational/lease tables never
            # landed in the dbt-managed schema, deliberately: they're
            # destined for MDM's own Postgres store, not Snowflake silver).
            # Under MDM_SILVER_READ_TARGET=snowflake this table genuinely
            # doesn't exist; degrade the same way _fetch_optional_
            # relationship_rows already does for a missing source table --
            # tracking_by_cik empty means every row's `tracking` argument
            # below is None, which resolve_one already handles.
            missing_table = self._find_missing_source_table(exc, "sec_company_sync_state")
            if missing_table is None:
                raise
            print(json.dumps({
                "event": "mdm_relationship_skip",
                "rel_type": "company_tracking_status",
                "reason": "missing_source_table",
                "source_table": missing_table,
                "ts": datetime.now(timezone.utc).isoformat(),
            }), file=sys.stderr, flush=True)
            tracking_rows = []
        tracking_by_cik = {row["cik"]: row for row in tracking_rows}

        rule_engine = self.engine
        sql_engine = self.session.get_bind()
        silver = self.silver
        pipeline_run_id = self.run_id
        processed = 0
        skipped_unchanged = 0
        lock = threading.Lock()
        started_at = time.monotonic()
        log_interval = _progress_log_interval(len(rows))
        pending_flush: list[int] = []

        # SQLite (test/stub backend only -- MDM production is always Postgres,
        # see database.py's MDM_DATABASE_URL) doesn't support genuinely
        # concurrent connections the way Postgres does: SQLAlchemy's SQLite
        # dialect commonly binds every session in-process to the same
        # underlying DBAPI connection (StaticPool, used for :memory: fixtures
        # so all sessions see the same data), and that one connection cannot
        # run two simultaneous transactions -- concurrent worker sessions
        # deadlock against it. Real per-worker connection concurrency is a
        # property Postgres provides that SQLite here does not, so cap workers
        # at 1 (still runs through the same worker-thread code path, just
        # strictly one task at a time) whenever the bound engine is SQLite.
        max_workers = (
            1 if sql_engine.dialect.name == "sqlite" else _COMPANY_RESOLVE_MAX_WORKERS
        )

        def _resolve_row(row: dict) -> tuple[int, bool]:
            worker_session = get_session(sql_engine)
            try:
                worker_ctx = ResolverContext(
                    session=worker_session,
                    engine=rule_engine,
                    silver=silver,
                    run_id=pipeline_run_id,
                )
                ticker = ticker_by_cik.get(row["cik"])
                tracking = tracking_by_cik.get(row["cik"])
                outcome = resolver.resolve_one(worker_ctx, "edgar_cik", row, ticker, tracking)
                worker_session.commit()
                return int(row["cik"]), outcome.action == MatchAction.SKIPPED_UNCHANGED
            finally:
                worker_session.close()

        def _flush_pending() -> None:
            if resumable and pending_flush:
                write_outcome_batch(
                    bronze_root=bronze_root,
                    run_id=effective_run_id,
                    batch_id=uuid.uuid4().hex,
                    ciks=pending_flush,
                )
                pending_flush.clear()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_resolve_row, row) for row in rows]
            try:
                for future in as_completed(futures):
                    resolved_cik, was_skipped = future.result()
                    with lock:
                        processed += 1
                        if was_skipped:
                            skipped_unchanged += 1
                        if resumable:
                            pending_flush.append(resolved_cik)
                        if processed % log_interval == 0:
                            emit_mdm_event(
                                "mdm_progress",
                                domain="company",
                                processed=processed,
                                skipped_unchanged=skipped_unchanged,
                                elapsed_ms=elapsed_ms(started_at),
                            )
                            _flush_pending()
            except Exception:
                for f in futures:
                    f.cancel()
                with lock:
                    _flush_pending()
                raise
            with lock:
                _flush_pending()
        emit_mdm_event(
            "mdm_company_resolution_completed",
            processed=processed,
            skipped_unchanged=skipped_unchanged,
            elapsed_ms=elapsed_ms(started_at),
        )
        return processed

    def run_advisers(self, limit: Optional[int] = None) -> int:
        from edgar_warehouse.mdm.adv_bulk import resolve_advisers_bulk

        return resolve_advisers_bulk(
            self.session,
            self.silver,
            self.engine,
            limit=limit,
        )

    def _run_grouped_concurrent(
        self,
        keyed_rows: list[tuple[Any, dict]],
        process_row_fn,
        *,
        domain: str,
        max_workers: int,
        log_interval: int,
    ) -> int:
        """Partition rows into groups by their caller-supplied key; each
        group's rows resolve sequentially on one worker (its own session),
        while different groups run concurrently across a bounded thread
        pool -- the same shape as run_companies' per-row concurrency, just
        applied per-group instead of per-row.

        Correctness depends entirely on the caller's key capturing the
        FULL set of shared match state a resolver's ``_existing_candidates``
        touches: two rows that could ever race on the same underlying
        entity MUST land in the same group. See run_securities/run_persons
        for the specific groupings and why they're safe.

        Mirrors run_companies' session-per-worker pattern (never touches
        ``self.session`` from a worker thread -- Session objects are not
        thread-safe) and its SQLite StaticPool guard (worker sessions can't
        get genuine connection concurrency there, so cap at 1).
        """
        groups: dict[Any, list[dict]] = defaultdict(list)
        for key, row in keyed_rows:
            groups[key].append(row)

        sql_engine = self.session.get_bind()
        rule_engine = self.engine
        silver = self.silver
        pipeline_run_id = self.run_id
        processed = 0
        lock = threading.Lock()
        started_at = time.monotonic()

        effective_max_workers = (
            1 if sql_engine.dialect.name == "sqlite" else max_workers
        )

        def _process_group(group_rows: list[dict]) -> None:
            nonlocal processed
            worker_session = get_session(sql_engine)
            try:
                worker_ctx = ResolverContext(
                    session=worker_session,
                    engine=rule_engine,
                    silver=silver,
                    run_id=pipeline_run_id,
                )
                for row in group_rows:
                    process_row_fn(worker_ctx, row)
                    with lock:
                        processed += 1
                        if processed % log_interval == 0:
                            emit_mdm_event(
                                "mdm_progress",
                                domain=domain,
                                processed=processed,
                                elapsed_ms=elapsed_ms(started_at),
                            )
                worker_session.commit()
            finally:
                worker_session.close()

        with ThreadPoolExecutor(max_workers=effective_max_workers) as executor:
            futures = [
                executor.submit(_process_group, group_rows)
                for group_rows in groups.values()
            ]
            try:
                for future in as_completed(futures):
                    future.result()
            except Exception:
                for f in futures:
                    f.cancel()
                raise
        return processed

    def run_securities(self, limit: Optional[int] = None) -> int:
        """Resolve ownership-transaction security titles into MDM entities.

        Runs on a bounded thread pool, grouped by (issuer_entity_id,
        canonical_title) -- NOT canonical_title alone (mdm-run-throughput
        map's original design, revised 2026-08-21 after live production
        data showed why title-only grouping doesn't scale).
        ``SecurityResolver._existing_candidates`` always scopes its exact
        match to ``canonical_title`` -- issuer-scoped when the issuer is
        known, NULL-issuer-scoped otherwise -- and ``resolve_one`` also has
        an "upgrade a NULL-issuer security" path that lets two *different*
        issuers sharing the same title interact (the second issuer's row
        can claim/upgrade an entity the first created). That upgrade path
        is only reachable through a NULL-``issuer_entity_id`` security, so
        the real concurrency boundary is per title: rows sharing a title
        can safely resolve on different workers UNLESS at least one row for
        that title has ``issuer_entity_id is None`` (no ``MdmCompany`` match
        for its ``issuer_cik``) -- only then must every row sharing that
        title stay serialized, since a shared NULL-issuer entity could exist
        for them to race on upgrading. Verified empirically, not assumed:
        live production data (all 4 silver shards, ~15K ownership-txn rows,
        2026-08-21) has zero rows with a NULL issuer_entity_id, and prod
        MDM Postgres has zero NULL-issuer ``mdm_security`` rows out of 2,985
        total -- so today this optimization applies to every title, but the
        conditional guard is real safety, not a shortcut: a handful of
        titles like "Common Stock" and "Class A Common Stock" concentrated
        53%/27% of one shard's rows into ONE sequential group each under the
        old title-only grouping, collapsing effective concurrency from
        16-way to ~1-way for the vast majority of the run as smaller groups
        exhausted (measured live: throughput decayed 17.05 -> 14.97 -> 5.23
        -> 1.81 records/sec across four progress checkpoints on the same
        stuck production run this fix was written to unblock). Rows with no
        title never dedup at all (an empty canonical title always creates a
        brand-new entity), so each gets its own singleton group instead of
        serializing behind a shared key that carries no real match risk.
        """
        resolver = SecurityResolver()
        # mdm-ownership-resolver-filing-join-gap ticket 01: LEFT JOIN, not INNER --
        # sec_company_filing is only populated for tracked companies' bulk-fetched
        # submission history. An ownership filing's issuer is not necessarily a
        # tracked company (e.g. an insider's Form 4 for an issuer that was never
        # bootstrapped), so an INNER JOIN here silently and permanently drops those
        # rows from every future run. issuer_cik is genuinely optional downstream --
        # SecurityResolver already has a NULL-issuer-scoped matching path.
        sql = """
            SELECT DISTINCT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, f.cik AS issuer_cik, FALSE AS is_derivative
            FROM sec_ownership_non_derivative_txn t
            LEFT JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            UNION ALL
            SELECT DISTINCT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, f.cik AS issuer_cik, TRUE AS is_derivative
            FROM sec_ownership_derivative_txn t
            LEFT JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql)

        # Companies are fully resolved before run_securities executes
        # (run_all's dependency order) and never mutated again during this
        # phase, so a single bulk prefetch is a stable, safe substitute for
        # a live self.session query -- which worker threads below must
        # never issue, since Session objects aren't thread-safe.
        issuer_ciks = {
            row.get("issuer_cik") for row in rows if row.get("issuer_cik") is not None
        }
        company_entity_id_by_cik = self._company_entity_ids(issuer_ciks)

        # Two passes: first determine, per canonical title, whether ANY row
        # has a null issuer_entity_id (the only condition under which
        # different-issuer rows sharing that title can race -- see
        # docstring above); second, build the actual grouping key using
        # that per-title safety determination.
        canonical_titles: list[str] = []
        issuer_entity_ids: list[Optional[str]] = []
        for row in rows:
            title = row.get("security_title") or ""
            # Must match SecurityResolver.resolve_one's own canonicalization
            # exactly, or grouping stops matching the resolver's real match
            # boundary and the concurrency safety argument above breaks.
            canonical_titles.append(
                " ".join(w.capitalize() for w in title.split()) if title else ""
            )
            issuer_entity_ids.append(company_entity_id_by_cik.get(row.get("issuer_cik")))

        titles_needing_serialization = {
            canonical_titles[i]
            for i in range(len(rows))
            if canonical_titles[i] and issuer_entity_ids[i] is None
        }

        keyed_rows: list[tuple[Any, dict]] = []
        for i, row in enumerate(rows):
            canonical = canonical_titles[i]
            if not canonical:
                key: Any = f"__no_title__{i}"
            elif canonical in titles_needing_serialization:
                key = canonical
            else:
                key = (issuer_entity_ids[i], canonical)
            keyed_rows.append((key, row))

        def _process(ctx: ResolverContext, row: dict) -> None:
            issuer_entity_id = company_entity_id_by_cik.get(row.get("issuer_cik"))
            resolver.resolve_one(ctx, "ownership_filing", row, issuer_entity_id)

        return self._run_grouped_concurrent(
            keyed_rows,
            _process,
            domain="security",
            max_workers=_SECURITY_RESOLVE_MAX_WORKERS,
            log_interval=_progress_log_interval(len(rows)),
        )

    def run_persons(
        self,
        limit: Optional[int] = None,
        *,
        issuer_ciks: Optional[Iterable[int]] = None,
    ) -> int:
        """Resolve Form 3/4/5 reporting owners into MDM person entities.

        Ticket 21: persons are the only entity load needed for IS_INSIDER —
        companies are assumed already resolved and are never re-run here.
        Optional ``issuer_ciks`` scopes to ownership rows for those issuers only.

        Rows with a real ``owner_cik`` run on a bounded thread pool, grouped
        by ``owner_cik`` -- ``PersonResolver._existing_candidates`` scopes
        strictly to ``owner_cik`` when present, the same true natural-key
        shape as company, so different CIKs never share match state.
        Multiple rows for the *same* CIK still run on one worker/session so
        they can't race and create duplicate entities for that person.

        Rows with ``owner_cik IS NULL`` fall back to an UNSCOPED fuzzy name
        match across the entire mdm_person table (no CIK filter is applied
        at all in that case) -- concurrent workers there could each miss a
        sibling's still-uncommitted near-duplicate and create duplicates a
        sequential run would have merged. These rows are NOT safe to
        parallelize; they run single-threaded, strictly after the
        CIK-scoped batch has fully committed, so the full-table scan sees a
        stable, complete snapshot instead of racing in-flight writes.
        """
        ctx = self._ctx()
        resolver = PersonResolver()
        ciks = self._normalize_issuer_ciks(issuer_ciks)
        # mdm-ownership-resolver-filing-join-gap ticket 01: LEFT JOIN, not INNER --
        # sec_company_filing is only populated for tracked companies' bulk-fetched
        # submission history. An ownership filing's issuer is not necessarily a
        # tracked company (e.g. an insider's Form 4 for an issuer that was never
        # bootstrapped), so an INNER JOIN here silently and permanently drops those
        # rows from every future run. issuer_cik is genuinely optional downstream
        # (PersonResolver.resolve_one defaults it to None). The explicit
        # `--cik`/issuer_ciks filter below still works correctly under LEFT JOIN --
        # f.cik is NULL for an unmatched row, and NULL never satisfies `IN (...)`,
        # so a caller-scoped run still excludes untracked issuers as intended; only
        # the unscoped (issuer_ciks=None) default run picks them up.
        sql = """
            SELECT DISTINCT o.owner_cik, o.owner_name, o.officer_title,
                   o.is_director, o.is_officer, o.is_ten_percent_owner, o.is_other,
                   o.accession_number, o.owner_index, f.cik AS issuer_cik
            FROM sec_ownership_reporting_owner o
            LEFT JOIN sec_company_filing f ON o.accession_number = f.accession_number
            WHERE o.owner_name IS NOT NULL
        """
        params: list[Any] = []
        if ciks is not None:
            placeholders = ", ".join("?" for _ in ciks)
            sql += f" AND f.cik IN ({placeholders})"
            params.extend(ciks)
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql, params or None)
        company_ciks = self._company_cik_set()

        eligible_rows = [r for r in rows if r.get("owner_cik") not in company_ciks]
        cik_rows = [r for r in eligible_rows if r.get("owner_cik") is not None]
        unscoped_rows = [r for r in eligible_rows if r.get("owner_cik") is None]

        log_interval = _progress_log_interval(len(rows))

        def _process(worker_ctx: ResolverContext, row: dict) -> None:
            resolver.resolve_one(worker_ctx, "ownership_filing", row,
                                  issuer_cik=row.get("issuer_cik"))

        keyed_rows = [(row.get("owner_cik"), row) for row in cik_rows]
        processed = self._run_grouped_concurrent(
            keyed_rows,
            _process,
            domain="person",
            max_workers=_PERSON_RESOLVE_MAX_WORKERS,
            log_interval=log_interval,
        )

        started_at = time.monotonic()
        for row in unscoped_rows:
            resolver.resolve_one(ctx, "ownership_filing", row,
                                 issuer_cik=row.get("issuer_cik"))
            processed += 1
            if processed % log_interval == 0:
                emit_mdm_event("mdm_progress", domain="person", processed=processed, elapsed_ms=elapsed_ms(started_at))
        self.session.commit()
        return processed

    def run_funds(self, limit: Optional[int] = None) -> int:
        from edgar_warehouse.mdm.adv_bulk import resolve_funds_bulk

        return resolve_funds_bulk(
            self.session,
            self.silver,
            self.engine,
            limit=limit,
        )

    def run_relationships(self, limit: Optional[int] = None) -> int:
        summary = self.derive_relationships(target_per_type=limit)
        return sum(int(item["inserted"] or 0) for item in summary.values())

    def derive_relationships(
        self,
        *,
        target_per_type: Optional[int] = None,
        relationship_types: Optional[Iterable[str]] = None,
        issuer_ciks: Optional[Iterable[int]] = None,
    ) -> dict[str, dict[str, int | None]]:
        """Create relationship instances until each requested type reaches target_per_type.

        Existing active relationships count toward the target. Returned counts
        are per type so operators can see source shortfalls without inspecting
        MDM tables directly.

        ``issuer_ciks`` scopes ownership-sourced types (IS_INSIDER, HOLDS,
        COMPANY_HOLDS) to Form 3/4/5 rows for those issuers only — Ticket 21
        insider smoke does not re-walk the full universe.

        Each relationship type resolves on its own worker thread and its own
        SQLAlchemy session (bounded by ``_RELATIONSHIP_DERIVE_MAX_WORKERS``),
        committing independently, mirroring run_companies' worker-session
        pattern. This is safe because every ``_derive_*`` method only ever
        writes ``mdm_relationship_instance`` rows scoped to its own
        rel_type_id (``relationship_id`` is a deterministic hash of
        ``(rel_type_id, source, target)``, so two types can never collide on
        the same row) and any stub entity a type creates (e.g.
        HAS_PARENT_COMPANY's subsidiary stubs, EMPLOYED_BY's proxy-person
        stubs) is read by other types only as a best-effort, already-
        idempotent lookup that quietly retries on the next `mdm run` when
        unresolved this run -- the exact same fallback the old strictly-
        sequential ordering already relied on (a type earlier in
        RELATIONSHIP_TYPES never saw a later type's stubs either). Falls
        back to a single worker whenever the bound engine is SQLite (see
        run_companies' identical guard -- the StaticPool test fixture shares
        one physical connection and cannot run concurrent transactions).
        """
        requested_types = self._relationship_type_names(relationship_types)
        ciks = self._normalize_issuer_ciks(issuer_ciks)
        started_at = time.monotonic()

        # Read-only, so safe to precompute for every type up front rather
        # than interleaved with each type's own work as the old sequential
        # loop did -- counts are per rel_type_id and never interact across
        # types.
        existing_by_type: dict[str, int] = {
            name: self._relationship_count(name) for name in requested_types
        }
        remaining_by_type: dict[str, Optional[int]] = {}
        for name in requested_types:
            if target_per_type is None:
                remaining_by_type[name] = None
            else:
                remaining_by_type[name] = max(int(target_per_type) - existing_by_type[name], 0)

        sql_engine = self.session.get_bind()
        max_workers = (
            1 if sql_engine.dialect.name == "sqlite"
            else min(_RELATIONSHIP_DERIVE_MAX_WORKERS, len(requested_types) or 1)
        )
        silver = self.silver
        pipeline_run_id = self.run_id

        def _derive_one(rel_type_name: str) -> tuple[int, int, int, int, int]:
            remaining = remaining_by_type[rel_type_name]
            if remaining is not None and remaining <= 0:
                return (0, 0, 0, 0, 0)
            worker_session = get_session(sql_engine)
            try:
                worker_pipeline = MDMPipeline(
                    session=worker_session, silver=silver, run_id=pipeline_run_id
                )
                worker_sync_engine = GraphSyncEngine.build(worker_session)
                result = worker_pipeline._derive_relationship_type(
                    worker_sync_engine, rel_type_name, remaining, issuer_ciks=ciks
                )
                worker_session.commit()
                return result
            finally:
                worker_session.close()

        summary: dict[str, dict[str, int | None]] = {}
        total_inserted = 0
        completed = 0
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_derive_one, name): name for name in requested_types
            }
            for future in as_completed(futures):
                rel_type_name = futures[future]
                (inserted, skipped_corporate, skipped_unresolved_source,
                 skipped_unresolved_target, skipped_existing) = future.result()
                existing = existing_by_type[rel_type_name]
                with lock:
                    total_inserted += inserted
                    completed += 1
                    type_summary = {
                        "existing":                  existing,
                        "inserted":                  inserted,
                        "skipped":                   (skipped_corporate + skipped_unresolved_source
                                                      + skipped_unresolved_target + skipped_existing),
                        "skipped_corporate":         skipped_corporate,
                        "skipped_unresolved_source": skipped_unresolved_source,
                        "skipped_unresolved_target": skipped_unresolved_target,
                        "skipped_existing":          skipped_existing,
                        "target":                    target_per_type,
                        "total":                     existing + inserted,
                    }
                    summary[rel_type_name] = type_summary
                    emit_mdm_event(
                        "mdm_progress",
                        domain="relationships",
                        rel_type=rel_type_name,
                        types_done=completed,
                        types_total=len(requested_types),
                        inserted=inserted,
                        total_inserted=total_inserted,
                        elapsed_ms=elapsed_ms(started_at),
                        **{k: v for k, v in type_summary.items() if k not in ("inserted",)},
                    )
        return summary

    def _normalize_issuer_ciks(
        self, issuer_ciks: Optional[Iterable[int]]
    ) -> Optional[list[int]]:
        if issuer_ciks is None:
            return None
        normalized = sorted({int(c) for c in issuer_ciks if c is not None})
        return normalized or None

    def _derive_relationship_type(
        self,
        sync_engine: GraphSyncEngine,
        rel_type_name: str,
        remaining: Optional[int],
        *,
        issuer_ciks: Optional[list[int]] = None,
    ) -> tuple[int, int, int, int, int]:
        # Prime + defer-flush once per type here, for every type uniformly,
        # rather than leaving each _derive_* method to opt in individually
        # (only MANAGES_FUND did, before this). Without it, ensure_relationship
        # pays one existing-version SELECT plus one session.flush() round
        # trip per row -- confirmed live via CloudWatch overlap-counting
        # during a real prod mdm run (max concurrently-open SQL calls == 1,
        # strictly sequential, unlike company/security/person resolution's
        # proven 16-way concurrency) that this per-row I/O is exactly what
        # made relationship derivation the slow, single-threaded tail of the
        # command. prime_relationship_type is idempotent (see graph.py), so
        # this is safe even for MANAGES_FUND's own internal call -- except
        # self-priming types (mdm-oom-manages-fund fix) are skipped here
        # deliberately: an unscoped prime here would run BEFORE the deriver
        # gets a chance to scope its own batches, defeating the whole point
        # (idempotency means the deriver's own scoped call would then be a
        # silent no-op against the already-fully-primed cache).
        if rel_type_name not in _SELF_PRIMING_RELATIONSHIP_TYPES:
            sync_engine.prime_relationship_type(rel_type_name, defer_flush=True)
        try:
            if rel_type_name == "IS_INSIDER":
                return self._derive_is_insider(sync_engine, remaining, issuer_ciks=issuer_ciks)
            if rel_type_name == "HOLDS":
                return self._derive_holds(sync_engine, remaining)
            if rel_type_name == "COMPANY_HOLDS":
                return self._derive_company_holds(sync_engine, remaining)
            if rel_type_name == "ISSUED_BY":
                return self._derive_issued_by(sync_engine, remaining)
            if rel_type_name == "IS_ENTITY_OF":
                return self._derive_is_entity_of(sync_engine, remaining)
            if rel_type_name == "HAS_PARENT_COMPANY":
                return self._derive_has_parent_company(sync_engine, remaining)
            if rel_type_name == "MANAGES_FUND":
                return self._derive_manages_fund(sync_engine, remaining)
            if rel_type_name == "IS_PERSON_OF":
                return self._derive_is_person_of(sync_engine, remaining)
            if rel_type_name == "EMPLOYED_BY":
                return self._derive_employed_by(sync_engine, remaining)
            if rel_type_name == "AUDITED_BY":
                return self._derive_audited_by(sync_engine, remaining)
            if rel_type_name == "INSTITUTIONAL_HOLDS":
                return self._derive_institutional_holds(sync_engine, remaining)
            raise KeyError(f"Unknown relationship type '{rel_type_name}'")
        finally:
            sync_engine.flush_pending()

    def _derive_is_insider(
        self,
        sync_engine: GraphSyncEngine,
        remaining: Optional[int],
        *,
        issuer_ciks: Optional[list[int]] = None,
    ) -> tuple[int, int, int, int, int]:
        """Derive IS_INSIDER from Form 3/4/5 reporting owners.

        Does not create or refresh company entities — issuer CIKs must already
        resolve in MDM (Ticket 21: companies do not change on an insider load).
        """
        sql = """
            SELECT o.accession_number, o.owner_index, o.owner_cik, o.owner_name,
                   o.is_director, o.is_officer, o.is_ten_percent_owner, o.is_other,
                   o.officer_title,
                   f.cik AS issuer_cik, f.report_date AS period_of_report
            FROM sec_ownership_reporting_owner o
            JOIN sec_company_filing f ON o.accession_number = f.accession_number
        """
        params: list[Any] = []
        if issuer_ciks is not None:
            placeholders = ", ".join("?" for _ in issuer_ciks)
            sql += f" WHERE f.cik IN ({placeholders})"
            params.extend(issuer_ciks)
        sql += " ORDER BY o.accession_number, o.owner_index"
        company_ciks = self._company_cik_set()
        existing = self._relationship_count("IS_INSIDER")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        # When scoping to issuer CIKs, do not use the global existing-count LIMIT
        # short-circuit SQL: existing universe totals are unrelated to this slice.
        if issuer_ciks is not None:
            fetch_sql = sql
            fetch_params: list[Any] | None = params
        else:
            fetch_sql = self._bounded_relationship_sql(sql, remaining, existing)
            fetch_params = None
        rows = self.silver.fetch(fetch_sql, fetch_params)
        # Bulk-prefetch owner_cik -> entity_id once for the whole batch
        # instead of a fresh per-row MdmPerson round-trip inside
        # _person_entity_id for every row (same rationale as
        # _derive_company_holds/_derive_holds -- owner CIKs repeat heavily
        # across a person's many filings). Rows with no CIK match (rare:
        # owner_cik missing entirely) still fall back to _person_entity_id's
        # per-row name-match branch below.
        owner_ciks = {row.get("owner_cik") for row in rows if row.get("owner_cik") is not None}
        person_id_by_cik = self._person_entity_ids(owner_ciks)
        # Same rationale for the issuer side: a well-followed issuer's CIK
        # repeats across every one of its own reporting owners' rows.
        issuer_ciks_seen = {row.get("issuer_cik") for row in rows if row.get("issuer_cik") is not None}
        issuer_id_by_cik = self._company_entity_ids(issuer_ciks_seen)
        for row in rows:
            owner_cik = row.get("owner_cik")
            if owner_cik in company_ciks:
                skipped_corporate += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "corporate",
                    "owner_cik": owner_cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            person_id = (
                person_id_by_cik.get(int(owner_cik)) if owner_cik is not None else None
            ) or self._person_entity_id(owner_cik, row.get("owner_name"))
            if person_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "unresolved_source",
                    "owner_cik": owner_cik,
                    "owner_name": row.get("owner_name"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            issuer_cik = row.get("issuer_cik")
            issuer_id = issuer_id_by_cik.get(int(issuer_cik)) if issuer_cik is not None else None
            if issuer_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "unresolved_target",
                    "issuer_cik": row.get("issuer_cik"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="IS_INSIDER",
                source_entity_id=person_id,
                target_entity_id=issuer_id,
                properties={"role": _derive_role(row), "title": row.get("officer_title") or ""},
                effective_from=row.get("period_of_report"),
                source_system="ownership_filing",
                source_accession=row.get("accession_number"),
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "existing",
                    "source_entity_id": person_id,
                    "target_entity_id": issuer_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_holds(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        sql = """
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   FALSE AS is_derivative,
                   NULL AS conversion_or_exercise_price,
                   NULL AS exercise_date,
                   NULL AS expiration_date,
                   NULL AS underlying_security_title,
                   NULL AS underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            UNION ALL
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   TRUE AS is_derivative,
                   t.conversion_or_exercise_price,
                   t.exercise_date,
                   t.expiration_date,
                   t.underlying_security_title,
                   t.underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            ORDER BY accession_number, owner_index, txn_index
        """
        company_ciks = self._company_cik_set()
        existing = self._relationship_count("HOLDS")
        rows = self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))
        # Bulk-prefetch issuer_cik -> entity_id once for the whole batch
        # instead of a fresh per-row round-trip inside _security_entity_id's
        # issuer fallback lookup for every row (see _derive_company_holds
        # for the identical rationale -- issuer CIKs repeat heavily here too).
        issuer_ciks = {row.get("issuer_cik") for row in rows if row.get("issuer_cik") is not None}
        company_entity_id_by_cik = self._company_entity_ids(issuer_ciks)
        # Same bulk-prefetch rationale as _derive_is_insider: owner CIKs
        # repeat heavily across a person's many transactions.
        owner_ciks = {row.get("owner_cik") for row in rows if row.get("owner_cik") is not None}
        person_id_by_cik = self._person_entity_ids(owner_ciks)
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in rows:
            owner_cik = row.get("owner_cik")
            if owner_cik in company_ciks:
                skipped_corporate += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "corporate",
                    "owner_cik": owner_cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            person_id = (
                person_id_by_cik.get(int(owner_cik)) if owner_cik is not None else None
            ) or self._person_entity_id(owner_cik, row.get("owner_name"))
            if person_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "unresolved_source",
                    "owner_cik": owner_cik,
                    "owner_name": row.get("owner_name"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            security_id = self._security_entity_id(row, company_entity_id_by_cik)
            if security_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "unresolved_target",
                    "security_title": row.get("security_title"),
                    "issuer_cik": row.get("issuer_cik"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            properties = {
                "shares_owned": self._json_property(row.get("shares_owned_after")),
                "direct_indirect": row.get("ownership_direct_indirect"),
                "as_of_date": self._json_property(row.get("transaction_date")),
                "is_derivative": bool(row.get("is_derivative")),
                "conversion_or_exercise_price": self._json_property(row.get("conversion_or_exercise_price")),
                "exercise_date": self._json_property(row.get("exercise_date")),
                "expiration_date": self._json_property(row.get("expiration_date")),
                "underlying_security_title": row.get("underlying_security_title"),
                "underlying_security_shares": self._json_property(row.get("underlying_security_shares")),
            }
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="HOLDS",
                source_entity_id=person_id,
                target_entity_id=security_id,
                properties={k: v for k, v in properties.items() if v is not None},
                effective_from=row.get("transaction_date"),
                source_system="ownership_filing",
                source_accession=row.get("accession_number"),
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "existing",
                    "source_entity_id": person_id,
                    "target_entity_id": security_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_company_holds(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        sql = """
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   FALSE AS is_derivative,
                   NULL AS conversion_or_exercise_price,
                   NULL AS exercise_date,
                   NULL AS expiration_date,
                   NULL AS underlying_security_title,
                   NULL AS underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            UNION ALL
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   TRUE AS is_derivative,
                   t.conversion_or_exercise_price,
                   t.exercise_date,
                   t.expiration_date,
                   t.underlying_security_title,
                   t.underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            ORDER BY accession_number, owner_index, txn_index
        """
        company_ciks = self._company_cik_set()
        existing = self._relationship_count("COMPANY_HOLDS")
        rows = self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))
        # Bulk-prefetch owner_cik/issuer_cik -> entity_id once for the whole
        # batch instead of a fresh per-row round-trip for each (both the
        # top-level owner lookup below and _security_entity_id's own issuer
        # fallback lookup used to each cost one network round-trip per row;
        # CIKs repeat heavily across a corporate insider's many filings, so
        # this collapses what was O(rows) round-trips into O(1)).
        wanted_ciks = {
            cik
            for row in rows
            for cik in (row.get("owner_cik"), row.get("issuer_cik"))
            if cik is not None
        }
        company_entity_id_by_cik = self._company_entity_ids(wanted_ciks)
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in rows:
            owner_cik = row.get("owner_cik")
            if owner_cik not in company_ciks:
                # skipped_corporate here means non-corporate owner (inverse of
                # IS_INSIDER/HOLDS — COMPANY_HOLDS wants corporate owners only)
                skipped_corporate += 1
                continue
            company_id = company_entity_id_by_cik.get(int(owner_cik))
            if company_id is None:
                skipped_unresolved_source += 1
                continue
            security_id = self._security_entity_id(row, company_entity_id_by_cik)
            if security_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "COMPANY_HOLDS",
                    "reason": "unresolved_target",
                    "security_title": row.get("security_title"),
                    "issuer_cik": row.get("issuer_cik"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            properties = {
                "shares_owned": self._json_property(row.get("shares_owned_after")),
                "direct_indirect": row.get("ownership_direct_indirect"),
                "as_of_date": self._json_property(row.get("transaction_date")),
                "is_derivative": bool(row.get("is_derivative")),
                "conversion_or_exercise_price": self._json_property(row.get("conversion_or_exercise_price")),
                "exercise_date": self._json_property(row.get("exercise_date")),
                "expiration_date": self._json_property(row.get("expiration_date")),
                "underlying_security_title": row.get("underlying_security_title"),
                "underlying_security_shares": self._json_property(row.get("underlying_security_shares")),
            }
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="COMPANY_HOLDS",
                source_entity_id=company_id,
                target_entity_id=security_id,
                properties={k: v for k, v in properties.items() if v is not None},
                effective_from=row.get("transaction_date"),
                source_system="ownership_filing",
                source_accession=row.get("accession_number"),
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_is_entity_of(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for adviser_id, company_id in self._adviser_company_pairs():
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="IS_ENTITY_OF",
                source_entity_id=adviser_id,
                target_entity_id=company_id,
                source_system="adv_filing",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_has_parent_company(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        from edgar_warehouse.mdm.database import MdmCompany

        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        source_rows = self._fetch_optional_relationship_rows(
            """
            SELECT accession_number, registrant_cik, document_name, row_ordinal,
                   legal_name, jurisdiction, parent_scope, immediate_parent_known,
                   effective_date, source_sha256
            FROM sec_subsidiary_evidence
            ORDER BY registrant_cik, accession_number, document_name, row_ordinal
            """,
            remaining,
            rel_type_name="HAS_PARENT_COMPANY",
            source_table="sec_subsidiary_evidence",
            existing=self._relationship_count("HAS_PARENT_COMPANY"),
        )
        # Bulk-prefetch registrant_cik -> parent entity_id once for the whole
        # batch instead of a fresh per-row round-trip (same rationale as
        # _derive_holds/_derive_company_holds -- registrant CIKs repeat
        # heavily, one registrant can disclose many subsidiaries). Child
        # subsidiary resolution (_ensure_disclosed_subsidiary) stays per-row:
        # it's a create-if-absent write, not a pure lookup, so it isn't safe
        # to collapse the same way.
        registrant_ciks = {
            row.get("registrant_cik") for row in source_rows if row.get("registrant_cik") is not None
        }
        parent_id_by_cik = self._company_entity_ids(registrant_ciks)
        for row in source_rows:
            registrant_cik = row.get("registrant_cik")
            parent_id = (
                parent_id_by_cik.get(int(registrant_cik)) if registrant_cik is not None else None
            )
            child_id = self._ensure_disclosed_subsidiary(row)
            if child_id is None:
                skipped_unresolved_source += 1
                continue
            if parent_id is None or child_id == parent_id:
                skipped_unresolved_target += 1
                continue
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="HAS_PARENT_COMPANY",
                source_entity_id=child_id,
                target_entity_id=parent_id,
                properties={
                    "parent_scope": row.get("parent_scope") or "registrant_disclosed",
                    "immediate_parent_known": bool(row.get("immediate_parent_known")),
                    "jurisdiction": row.get("jurisdiction"),
                    "evidence_fingerprint": row.get("source_sha256"),
                },
                effective_from=row.get("effective_date"),
                source_system="sec_exhibit_subsidiaries",
                source_accession=row.get("accession_number"),
                date_provenance="reported",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        if source_rows:
            return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

        for company in self.session.scalars(
            select(MdmCompany)
            .where(MdmCompany.parent_company_entity_id.isnot(None))
            .order_by(MdmCompany.cik)
        ):
            if company.entity_id == company.parent_company_entity_id:
                skipped_unresolved_target += 1
                continue
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="HAS_PARENT_COMPANY",
                source_entity_id=company.entity_id,
                target_entity_id=company.parent_company_entity_id,
                source_system="derived",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _ensure_disclosed_subsidiary(self, row: dict) -> Optional[str]:
        import uuid as _uuid
        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity, MdmSourceRef

        legal_name = " ".join(str(row.get("legal_name") or "").split())
        registrant_cik = row.get("registrant_cik")
        jurisdiction = " ".join(str(row.get("jurisdiction") or "").split())
        if not legal_name or registrant_cik is None:
            return None
        source_key = f"{int(registrant_cik)}:{legal_name.casefold()}:{jurisdiction.casefold()}"
        entity_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"sec:subsidiary:{source_key}"))
        if self.session.get(MdmEntity, entity_id) is None:
            self.session.add(MdmEntity(
                entity_id=entity_id,
                entity_type="company",
                resolution_method="sec_exhibit_name_jurisdiction",
                confidence=1.0,
            ))
            # See _ensure_thirteenf_manager: MdmEntity must flush before its
            # FK-dependent rows -- no relationship() links them, so the ORM
            # won't auto-order the inserts.
            self.session.flush()
            self.session.add(MdmCompany(
                entity_id=entity_id,
                cik=None,
                canonical_name=legal_name,
                state_of_incorporation=jurisdiction or None,
            ))
            self.session.add(MdmSourceRef(
                entity_id=entity_id,
                source_system="sec_exhibit_subsidiaries",
                source_id=source_key,
                source_priority=10,
                confidence=1.0,
            ))
            self._log_stub_entity_created(
                entity_id,
                "company",
                {
                    "resolution_method": "sec_exhibit_name_jurisdiction",
                    "source_system": "sec_exhibit_subsidiaries",
                },
            )
            self.session.flush()
        return entity_id

    def _derive_is_person_of(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for adviser_id, person_id in self._adviser_person_pairs():
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="IS_PERSON_OF",
                source_entity_id=adviser_id,
                target_entity_id=person_id,
                source_system="adv_filing",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_manages_fund(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        """Derive MANAGES_FUND edges, batched by adviser CRD (mdm-oom-manages-fund fix).

        Prior version primed the WHOLE type unconditionally (every active
        MANAGES_FUND row, universe-wide) before it knew which advisers this
        run would even touch. Measured live 2026-08-21: that single query
        materializes ~2GB of ORM rows for a table that's 390MB on disk, and
        one adviser (a large fund-administration platform, the same outlier
        flagged in CLAUDE.md's schema-conventions section) holds 89,108 of
        the 563,631 active rows -- 16% from a single CRD. Concurrent with
        derive_relationships()'s other worker threads, that pushed
        edgartools-prod-mdm-medium (4096MB) over its ceiling.

        Advisers are resolved first, then CRDs are processed in
        ``_MANAGES_FUND_CRD_BATCH_SIZE`` batches -- each batch primes,
        reads, and closes/inserts relationships for only its own advisers,
        then discards that batch's cache before moving on
        (``GraphSyncEngine.unprime_relationship_type``). Peak memory is
        bounded by one batch's data (worst case: whichever batch contains
        the outlier adviser) instead of the whole type.
        """
        from edgar_warehouse.mdm.database import MdmAdviser, MdmFund

        adviser_ids_by_crd = {
            str(crd_number): entity_id
            for entity_id, crd_number in self.session.execute(
                select(MdmAdviser.entity_id, MdmAdviser.crd_number).where(
                    MdmAdviser.crd_number.isnot(None)
                )
            )
        }
        fund_ids_by_pfid = {
            str(private_fund_id): entity_id
            for entity_id, private_fund_id in self.session.execute(
                select(MdmFund.entity_id, MdmFund.private_fund_id).where(
                    MdmFund.private_fund_id.isnot(None)
                )
            )
        }

        # Cheap existence probe -- if there's no ADV filing/private-fund
        # data at all (fresh/degenerate universe), skip straight to the
        # MdmFund-based fallback below instead of iterating CRD batches
        # that would all come back empty. Both queries are LIMIT 1 -- this
        # is not the memory-heavy read the batching below guards against.
        existing_count = self._relationship_count("MANAGES_FUND")
        probe_filing = self._fetch_optional_relationship_rows(
            "SELECT 1 AS probe FROM sec_adv_filing WHERE crd_number IS NOT NULL LIMIT 1",
            None, rel_type_name="MANAGES_FUND", source_table="sec_adv_filing",
            existing=existing_count,
        )
        probe_source = self._fetch_optional_relationship_rows(
            """
            SELECT 1 AS probe FROM sec_adv_private_fund
            WHERE adviser_crd_number IS NOT NULL AND private_fund_id IS NOT NULL LIMIT 1
            """,
            None, rel_type_name="MANAGES_FUND", source_table="sec_adv_private_fund",
            existing=existing_count,
        )

        if not probe_filing and not probe_source:
            sync_engine.prime_relationship_type("MANAGES_FUND", defer_flush=True)
            inserted = skipped_existing = 0
            for fund in self.session.scalars(
                select(MdmFund).where(MdmFund.adviser_entity_id.isnot(None))
            ):
                _rel, created = sync_engine.ensure_relationship(
                    rel_type_name="MANAGES_FUND",
                    source_entity_id=fund.adviser_entity_id,
                    target_entity_id=fund.entity_id,
                    source_system="mdm_backfill",
                )
                inserted += 1 if created else 0
                skipped_existing += 0 if created else 1
                if remaining is not None and inserted >= remaining:
                    break
            sync_engine.flush_pending()
            return inserted, 0, 0, 0, skipped_existing

        totals = [0, 0, 0, 0, 0]  # inserted, skipped_corporate, skipped_unresolved_source/target, skipped_existing
        sorted_crds = sorted(adviser_ids_by_crd.keys())
        for start in range(0, len(sorted_crds), _MANAGES_FUND_CRD_BATCH_SIZE):
            batch_crds = sorted_crds[start:start + _MANAGES_FUND_CRD_BATCH_SIZE]
            batch_remaining = None if remaining is None else max(remaining - totals[0], 0)
            if batch_remaining == 0:
                break
            batch_result = self._derive_manages_fund_batch(
                sync_engine, batch_remaining, batch_crds, adviser_ids_by_crd, fund_ids_by_pfid,
            )
            for i, value in enumerate(batch_result):
                totals[i] += value
            if remaining is not None and totals[0] >= remaining:
                break
        return tuple(totals)

    def _derive_manages_fund_batch(
        self,
        sync_engine: GraphSyncEngine,
        remaining: Optional[int],
        batch_crds: list[str],
        adviser_ids_by_crd: dict[str, str],
        fund_ids_by_pfid: dict[str, str],
    ) -> tuple[int, int, int, int, int]:
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        batch_adviser_ids = [
            adviser_ids_by_crd[crd] for crd in batch_crds if crd in adviser_ids_by_crd
        ]
        sync_engine.prime_relationship_type(
            "MANAGES_FUND", defer_flush=True, source_entity_ids=batch_adviser_ids,
        )
        try:
            placeholders = ", ".join(["?"] * len(batch_crds))
            filing_rows = self.silver.fetch(
                f"""
                SELECT accession_number, crd_number, effective_date, filing_action
                FROM sec_adv_filing
                WHERE crd_number IN ({placeholders})
                ORDER BY crd_number, effective_date, accession_number
                """,
                params=list(batch_crds),
            )
            source_rows = self.silver.fetch(
                f"""
                SELECT accession_number, adviser_crd_number, private_fund_id,
                       filing_id, schedule_section, reporting_role, effective_date,
                       filing_action, source_sha256
                FROM sec_adv_private_fund
                WHERE adviser_crd_number IN ({placeholders}) AND private_fund_id IS NOT NULL
                ORDER BY filing_id, private_fund_id, schedule_section
                """,
                params=list(batch_crds),
            )

            current_by_adviser: dict[str, list] = {}
            for current in sync_engine.current_relationships("MANAGES_FUND"):
                current_by_adviser.setdefault(current.source_entity_id, []).append(current)

            latest_by_crd: dict[str, dict] = {}
            if filing_rows:
                for filing in filing_rows:
                    crd = str(filing.get("crd_number") or "")
                    effective = filing.get("effective_date")
                    if effective and not isinstance(effective, date):
                        effective = date.fromisoformat(str(effective)[:10])
                    accession = str(filing.get("accession_number") or "")
                    filing_id = accession.rsplit(":", 1)[-1]
                    key = (effective or date.min, int(filing_id) if filing_id.isdecimal() else 0,
                           accession)
                    prior = latest_by_crd.get(crd)
                    if prior is None or key > prior["_key"]:
                        latest_by_crd[crd] = {**filing, "_key": key}
                active_accessions = {
                    str(filing.get("accession_number"))
                    for filing in latest_by_crd.values()
                    if not any(
                        marker in str(filing.get("filing_action") or "").lower()
                        for marker in ("final", "withdraw")
                    )
                }
                source_rows = [
                    row for row in source_rows
                    if str(row.get("accession_number")) in active_accessions
                ]
                from edgar_warehouse.mdm.graph import close_relationship_version

                expected_targets_by_adviser: dict[str, set[str]] = {}
                for row in source_rows:
                    adviser_id = adviser_ids_by_crd.get(
                        str(row.get("adviser_crd_number"))
                    )
                    fund_id = fund_ids_by_pfid.get(str(row.get("private_fund_id")))
                    if adviser_id and fund_id:
                        expected_targets_by_adviser.setdefault(adviser_id, set()).add(fund_id)
                for crd, filing in latest_by_crd.items():
                    adviser_id = adviser_ids_by_crd.get(str(crd))
                    if adviser_id is None:
                        continue
                    effective = filing["_key"][0]
                    expected_targets = expected_targets_by_adviser.get(adviser_id, set())
                    current_versions = current_by_adviser.get(adviser_id, [])
                    for current in current_versions:
                        if (
                            current.valid_to_date is None
                            and current.target_entity_id not in expected_targets
                        ):
                            close_relationship_version(
                                self.session, current.instance_id, effective
                            )
            for row in source_rows:
                adviser_id = adviser_ids_by_crd.get(str(row.get("adviser_crd_number")))
                fund_id = fund_ids_by_pfid.get(str(row.get("private_fund_id")))
                if adviser_id is None:
                    skipped_unresolved_source += 1
                    continue
                if fund_id is None:
                    skipped_unresolved_target += 1
                    continue
                _rel, created = sync_engine.ensure_relationship(
                    rel_type_name="MANAGES_FUND",
                    source_entity_id=adviser_id,
                    target_entity_id=fund_id,
                    properties={
                        "private_fund_id": row.get("private_fund_id"),
                        "source_filing_id": row.get("filing_id"),
                        "source_section": row.get("schedule_section"),
                        "reporting_role": row.get("reporting_role"),
                        "evidence_fingerprint": row.get("source_sha256"),
                    },
                    effective_from=row.get("effective_date"),
                    source_system="iapd_adv_bulk",
                    source_accession=row.get("accession_number"),
                    date_provenance="reported",
                )
                inserted += 1 if created else 0
                skipped_existing += 0 if created else 1
                if remaining is not None and inserted >= remaining:
                    break
            sync_engine.flush_pending()
        finally:
            sync_engine.unprime_relationship_type("MANAGES_FUND")
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_issued_by(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        from edgar_warehouse.mdm.database import MdmSecurity

        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for security in self.session.scalars(
            select(MdmSecurity).where(MdmSecurity.issuer_entity_id.isnot(None))
        ):
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="ISSUED_BY",
                source_entity_id=security.entity_id,
                target_entity_id=security.issuer_entity_id,
                source_system="mdm_backfill",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def backfill_security_issuers(self) -> int:
        """Repair mdm_security rows where issuer_entity_id is NULL but the company is now in MDM.

        5-why root cause: run_companies(limit=100) processes at most 100 of 5400 companies per
        run, so when run_securities() creates a security its issuer may not yet exist in
        mdm_company.  On subsequent runs the resolver finds the existing NULL-issuer row and
        returns it unchanged.  This method does one full scan of silver to patch those rows.

        Returns the number of rows updated.
        """
        from edgar_warehouse.mdm.database import MdmSecurity

        # canonical_title normalisation must match run_securities()
        def _canonical(raw: str) -> str:
            return " ".join(w.capitalize() for w in (raw or "").split())

        sql = """
            SELECT DISTINCT t.security_title, f.cik AS issuer_cik
            FROM   sec_ownership_non_derivative_txn t
            JOIN   sec_company_filing f ON f.accession_number = t.accession_number
            WHERE  t.security_title IS NOT NULL
            UNION
            SELECT DISTINCT t.security_title, f.cik AS issuer_cik
            FROM   sec_ownership_derivative_txn t
            JOIN   sec_company_filing f ON f.accession_number = t.accession_number
            WHERE  t.security_title IS NOT NULL
        """
        rows = self.silver.fetch(sql)

        updated = 0
        for row in rows:
            canonical = _canonical(row.get("security_title") or "")
            issuer_cik = row.get("issuer_cik")
            if not canonical or issuer_cik is None:
                continue

            issuer_entity_id = self._company_entity_id(issuer_cik)
            if not issuer_entity_id:
                continue

            result = self.session.execute(
                update(MdmSecurity)
                .where(MdmSecurity.canonical_title == canonical)
                .where(MdmSecurity.issuer_entity_id.is_(None))
                .values(issuer_entity_id=issuer_entity_id)
            )
            updated += result.rowcount

        if updated:
            self.session.commit()
        return updated

    def run_all(
        self,
        limit: Optional[int] = None,
        *,
        resume_ledger_run_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> PipelineStats:
        """Resolve all 5 entity types, then derive relationships.

        mdm-run-step-parallelism wayfinder map, ticket 02: the 5
        entity-resolution steps run as concurrent top-level futures instead
        of sequentially. Each step gets its own fresh MDMPipeline
        instance/session (mirroring derive_relationships()'s own
        per-relationship-type worker-session pattern below) -- self.session
        is never touched from more than one thread. This matters because
        run_advisers/run_funds (edgar_warehouse/mdm/adv_bulk.py) write
        through whatever session they're given directly, and run_persons'
        unscoped-name-match fallback also writes through self.session
        directly (see its own docstring) -- none of the 5 steps is safe to
        launch concurrently against one shared session, only against 5
        independent ones.

        derive_relationships() still runs after all 5 steps finish (its own
        trigger is unchanged -- ticket 02 explicitly kept this), so it never
        shares connection-pool headroom with the 5-way concurrent phase.

        Fail-fast on any step's exception: cancels the remaining futures and
        propagates immediately, matching run_companies' own
        cancel-on-exception pattern for its per-row worker futures (ticket
        02's explicit choice over letting already-launched steps finish
        best-effort).
        """
        stats = PipelineStats()
        # pipeline-resumability ticket 02: only the company step supports
        # resume today -- resume_ledger_run_id/run_id are scoped to
        # run_companies alone, not threaded to the other steps. Securities
        # and persons now run concurrently too (mdm-run-throughput map,
        # grouped by canonical_title / owner_cik respectively -- see
        # run_securities/run_persons docstrings), but neither writes a
        # resumable CIK snapshot/outcome ledger the way company does, so a
        # restart still re-resolves them from scratch (idempotently safe,
        # just not skip-ahead).
        sql_engine = self.session.get_bind()
        silver = self.silver
        pipeline_run_id = self.run_id
        max_workers = 1 if sql_engine.dialect.name == "sqlite" else _RUN_STEP_MAX_WORKERS

        # (stats field, runner) pairs rather than a step-name string dispatched
        # through an if/elif ladder elsewhere: the field a step's result gets
        # assigned to and the method that produces it are declared in the same
        # place, so the two can't silently drift apart (e.g. a copy-paste
        # swapping which branch feeds which PipelineStats attribute).
        step_runners: tuple[tuple[str, Callable[[MDMPipeline], int]], ...] = (
            (
                "companies_processed",
                lambda wp: wp.run_companies(
                    limit=limit, resume_ledger_run_id=resume_ledger_run_id, run_id=run_id
                ),
            ),
            ("advisers_processed", lambda wp: wp.run_advisers(limit=limit)),
            ("securities_processed", lambda wp: wp.run_securities(limit=limit)),
            ("persons_processed", lambda wp: wp.run_persons(limit=limit)),
            ("funds_processed", lambda wp: wp.run_funds(limit=limit)),
        )

        def _run_step(run_fn: Callable[[MDMPipeline], int]) -> int:
            worker_session = get_session(sql_engine)
            try:
                worker_pipeline = MDMPipeline(
                    session=worker_session, silver=silver, run_id=pipeline_run_id
                )
                result = run_fn(worker_pipeline)
                worker_session.commit()
                return result
            finally:
                worker_session.close()
        # Not a `with ThreadPoolExecutor(...) as executor:` block deliberately:
        # its __exit__ always calls shutdown(wait=True), which would block
        # this except-clause's re-raise until every already-running sibling
        # step finished -- with exactly 5 futures and max_workers defaulting
        # to 5, all 5 start immediately, so that wait is never short. That
        # would silently turn "propagates immediately" (ticket 02's Answer)
        # into "propagates after the slowest still-running step," up to the
        # ~2h14m company/~1h50m security durations measured in ticket 01.
        # shutdown(wait=False, cancel_futures=True) below returns without
        # waiting; already-running worker threads keep running to their own
        # completion in the background (Python can't preempt a thread), so
        # the caller (this method's own exception propagation) sees the
        # error immediately instead of blocking on them -- confirmed via a
        # standalone repro script (pool of 2, one sleeping, one raising):
        # the raise reaches the caller at ~0s, not after the sleep. Caller-
        # level only, though: the process itself does NOT exit that fast --
        # CPython's concurrent.futures.thread atexit hook still joins every
        # pool thread before interpreter shutdown, so an ECS task running
        # this still waits out the slowest sibling step before its process
        # actually terminates, even though run_all() itself has already
        # raised and any caller-side error handling/logging runs right away.
        executor = ThreadPoolExecutor(max_workers=max_workers)
        futures = {
            executor.submit(_run_step, run_fn): stat_field
            for stat_field, run_fn in step_runners
        }
        try:
            for future in as_completed(futures):
                setattr(stats, futures[future], future.result())
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        executor.shutdown(wait=True)

        # Cross-connection visibility check (traced, not assumed): the 5
        # steps above wrote their entities through their own committed
        # worker sessions -- self.session (this outer pipeline's own
        # connection) never touched those rows. derive_relationships()
        # itself only reads self.session for _relationship_count(), a
        # COUNT over pre-existing mdm_relationship_instance rows unrelated
        # to what the 5 steps just wrote; every actual relationship-
        # derivation worker below opens its own brand-new
        # get_session(sql_engine) connection with an empty identity map,
        # which sees all committed writes under Postgres's default READ
        # COMMITTED isolation (no isolation_level override in
        # database.py's get_engine()) regardless of self.session's state.
        # rollback() here is a cheap belt-and-suspenders: nothing on
        # self.session was written in this method, so there's nothing to
        # lose, and it makes that visibility contract explicit rather than
        # incidental for any future caller who does write through
        # self.session before calling run_all().
        self.session.rollback()
        stats.relationship_counts_by_type = self.derive_relationships(target_per_type=limit)
        stats.relationships_written = sum(
            int(item["inserted"] or 0) for item in stats.relationship_counts_by_type.values()
        )
        return stats

    def _relationship_type_names(self, relationship_types: Optional[Iterable[str]]) -> list[str]:
        if relationship_types is None:
            return list(RELATIONSHIP_TYPES)
        requested = [name.strip().upper() for name in relationship_types if name and name.strip()]
        unknown = sorted(set(requested) - set(RELATIONSHIP_TYPES))
        if unknown:
            raise KeyError(f"Unknown relationship type(s): {', '.join(unknown)}")
        return requested

    def _relationship_count(self, rel_type_name: str) -> int:
        from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType

        return int(
            self.session.scalar(
                select(func.count(MdmRelationshipInstance.instance_id))
                .join(MdmRelationshipType)
                .where(
                    MdmRelationshipType.rel_type_name == rel_type_name,
                    MdmRelationshipInstance.is_active.is_(True),
                )
            )
            or 0
        )

    def _company_cik_set(self) -> set:
        from edgar_warehouse.mdm.database import MdmCompany
        from sqlalchemy import select
        return set(self.session.scalars(
            select(MdmCompany.cik).where(MdmCompany.cik.isnot(None))
        ))

    def _company_entity_id(self, cik) -> Optional[str]:
        if cik is None:
            return None
        from edgar_warehouse.mdm.database import MdmCompany
        from sqlalchemy import select
        return self.session.scalar(
            select(MdmCompany.entity_id).where(MdmCompany.cik == int(cik))
        )

    def _company_entity_ids(self, ciks: Iterable[Any]) -> dict[int, str]:
        """Bulk cik->entity_id prefetch -- the multi-row counterpart to
        ``_company_entity_id``, used by callers (run_securities) that must
        avoid a live ``self.session`` query from a worker thread."""
        ciks_int = {int(c) for c in ciks if c is not None}
        if not ciks_int:
            return {}
        from edgar_warehouse.mdm.database import MdmCompany
        from sqlalchemy import select
        rows = self.session.execute(
            select(MdmCompany.cik, MdmCompany.entity_id).where(MdmCompany.cik.in_(ciks_int))
        ).all()
        return {int(cik): entity_id for cik, entity_id in rows}

    def _person_entity_id(self, owner_cik, owner_name) -> Optional[str]:
        from edgar_warehouse.mdm.database import MdmPerson
        from sqlalchemy import select
        if owner_cik is not None:
            result = self.session.scalar(
                select(MdmPerson.entity_id).where(MdmPerson.owner_cik == int(owner_cik))
            )
            if result:
                return result
        if owner_name:
            return self.session.scalar(
                select(MdmPerson.entity_id).where(MdmPerson.canonical_name == owner_name)
            )
        return None

    def _person_entity_ids(self, owner_ciks: Iterable[Any]) -> dict[int, str]:
        """Bulk owner_cik->entity_id prefetch -- the multi-row counterpart to
        ``_person_entity_id``'s CIK branch, used by callers (IS_INSIDER,
        HOLDS) that would otherwise pay one MdmPerson SELECT per row. Callers
        still fall back to ``_person_entity_id``'s per-row name-match branch
        for any CIK this misses (rare: only reporting owners with no
        owner_cik at all)."""
        ciks_int = {int(c) for c in owner_ciks if c is not None}
        if not ciks_int:
            return {}
        from edgar_warehouse.mdm.database import MdmPerson
        from sqlalchemy import select
        rows = self.session.execute(
            select(MdmPerson.owner_cik, MdmPerson.entity_id).where(MdmPerson.owner_cik.in_(ciks_int))
        ).all()
        return {int(cik): entity_id for cik, entity_id in rows}

    def _security_entity_id(
        self,
        txn_row: dict,
        company_entity_id_by_cik: Optional[dict[int, str]] = None,
    ) -> Optional[str]:
        """Resolve a security's entity_id for an ownership transaction row.

        ``company_entity_id_by_cik``, when provided, is consulted instead of
        issuing a fresh ``_company_entity_id`` round-trip for the issuer CIK
        fallback lookup -- callers that already bulk-prefetched company
        entity IDs for a batch of rows (see ``_derive_company_holds``/
        ``_derive_holds``) pass it through to avoid re-fetching the same CIK
        over and over across rows that share an issuer. Defaults to None,
        which preserves the original per-row lookup for any other caller.
        """
        from edgar_warehouse.mdm.database import MdmEntity, MdmSecurity, MdmSourceRef

        source_id = _ownership_security_source_id(txn_row)
        source_match = self.session.scalar(
            select(MdmSourceRef.entity_id)
            .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
            .where(MdmSourceRef.source_system == "ownership_filing")
            .where(MdmSourceRef.source_id == source_id)
            .where(MdmEntity.entity_type == "security")
        )
        if source_match:
            return source_match
        issuer_cik = txn_row.get("issuer_cik")
        if company_entity_id_by_cik is not None:
            issuer_entity_id = (
                company_entity_id_by_cik.get(int(issuer_cik)) if issuer_cik is not None else None
            )
        else:
            issuer_entity_id = self._company_entity_id(issuer_cik)
        title = txn_row.get("security_title")
        if not title:
            return None
        canonical = " ".join(word.capitalize() for word in str(title).split())
        stmt = select(MdmSecurity.entity_id).where(MdmSecurity.canonical_title == canonical)
        if issuer_entity_id:
            stmt = stmt.where(MdmSecurity.issuer_entity_id == issuer_entity_id)
        return self.session.scalar(stmt)

    def _adviser_entity_id(self, accession_number) -> Optional[str]:
        if accession_number is None:
            return None
        from edgar_warehouse.mdm.database import MdmEntity, MdmSourceRef
        from sqlalchemy import select
        return self.session.scalar(
            select(MdmSourceRef.entity_id)
            .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
            .where(MdmSourceRef.source_system == "adv_filing")
            .where(MdmSourceRef.source_id == accession_number)
            .where(MdmEntity.entity_type == "adviser")
        )

    def _adviser_entity_id_by_crd(self, crd_number) -> Optional[str]:
        if crd_number is None:
            return None
        from edgar_warehouse.mdm.database import MdmAdviser
        return self.session.scalar(
            select(MdmAdviser.entity_id).where(MdmAdviser.crd_number == str(crd_number))
        )

    def _fund_entity_id_by_pfid(self, private_fund_id) -> Optional[str]:
        if private_fund_id is None:
            return None
        from edgar_warehouse.mdm.database import MdmFund
        return self.session.scalar(
            select(MdmFund.entity_id).where(
                MdmFund.private_fund_id == str(private_fund_id)
            )
        )

    def _adviser_entity_id_by_cik(self, cik) -> Optional[str]:
        """Look up an adviser entity_id by CIK.

        Used for 13F filers, which are identified by CIK in the SEC 13F filer
        list rather than by an ADV accession number.
        """
        if cik is None:
            return None
        from edgar_warehouse.mdm.database import MdmAdviser
        from sqlalchemy import select
        return self.session.scalar(
            select(MdmAdviser.entity_id).where(MdmAdviser.cik == int(cik))
        )

    def _ensure_thirteenf_manager(self, cik) -> Optional[str]:
        """Resolve or deterministically create the adviser source entity for a 13F manager."""
        existing = self._adviser_entity_id_by_cik(cik)
        if existing or cik is None:
            return existing
        import uuid as _uuid
        from edgar_warehouse.mdm.database import MdmAdviser, MdmEntity, MdmSourceRef

        normalized_cik = int(cik)
        entity_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"sec:13f-manager:{normalized_cik}"))
        company_rows = self.silver.fetch(
            "SELECT entity_name FROM sec_company WHERE cik = ? LIMIT 1",
            [normalized_cik],
        )
        canonical_name = (
            str(company_rows[0].get("entity_name") or "").strip()
            if company_rows else ""
        ) or f"13F Manager CIK {normalized_cik}"
        if self.session.get(MdmEntity, entity_id) is None:
            self.session.add(MdmEntity(
                entity_id=entity_id,
                entity_type="adviser",
                resolution_method="sec_13f_manager_cik",
                confidence=1.0,
            ))
            # MdmEntity must be flushed before its dependents (MdmAdviser,
            # MdmSourceRef, MdmChangeLog) are inserted: no ORM relationship()
            # links these tables to MdmEntity, only a plain-column
            # ForeignKey, so SQLAlchemy's unit-of-work has no dependency
            # edge to auto-order the inserts by and may emit the child
            # insert before the parent's. SQLite (this file's test suite)
            # doesn't enforce FKs by default and stayed silent; real
            # Postgres (prod MDM) raised ForeignKeyViolation.
            self.session.flush()
            self.session.add(MdmAdviser(
                entity_id=entity_id,
                cik=normalized_cik,
                canonical_name=canonical_name,
                adviser_type="13f_manager",
            ))
            self.session.add(MdmSourceRef(
                entity_id=entity_id,
                source_system="thirteenf_manager",
                source_id=str(normalized_cik),
                source_priority=20,
                confidence=1.0,
            ))
            self._log_stub_entity_created(
                entity_id,
                "adviser",
                {
                    "resolution_method": "sec_13f_manager_cik",
                    "source_system": "thirteenf_manager",
                    "cik": normalized_cik,
                },
            )
            self.session.flush()
        return entity_id

    def _audit_firm_entity_id(
        self, pcaob_id: Optional[str], firm_name: Optional[str]
    ) -> Optional[str]:
        """Resolve an audit firm, creating valid long-tail PCAOB identities."""
        import uuid as _uuid

        from edgar_warehouse.mdm.database import (
            MdmAuditFirm, MdmEntity, MdmSourceRef,
        )
        from sqlalchemy import select
        # Primary: match on PCAOB registration number (authoritative identifier)
        if pcaob_id:
            result = self.session.scalar(
                select(MdmAuditFirm.entity_id).where(MdmAuditFirm.pcaob_firm_id == str(pcaob_id))
            )
            if result:
                return result
        # Fallback: case-insensitive name match
        if firm_name:
            from sqlalchemy import func as sqlfunc
            result = self.session.scalar(
                select(MdmAuditFirm.entity_id).where(
                    sqlfunc.lower(MdmAuditFirm.canonical_name) == firm_name.lower().strip()
                )
            )
            if result:
                return result
        normalized_id = str(pcaob_id or "").strip()
        canonical_name = " ".join(str(firm_name or "").split())
        if normalized_id.isdecimal() and canonical_name:
            normalized_id = str(int(normalized_id))
            entity_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"pcaob:firm:{normalized_id}"))
            if self.session.get(MdmEntity, entity_id) is None:
                self.session.add(MdmEntity(
                    entity_id=entity_id,
                    entity_type="audit_firm",
                    resolution_method="pcaob_firm_id",
                    confidence=1.0,
                ))
                # See _ensure_thirteenf_manager: MdmEntity must flush before
                # its FK-dependent rows -- no relationship() links them, so
                # the ORM won't auto-order the inserts.
                self.session.flush()
                self.session.add(MdmAuditFirm(
                    entity_id=entity_id,
                    firm_name=canonical_name,
                    canonical_name=canonical_name,
                    pcaob_firm_id=normalized_id,
                    big4=False,
                ))
                self.session.add(MdmSourceRef(
                    entity_id=entity_id,
                    source_system="pcaob_firm_registry",
                    source_id=normalized_id,
                    source_priority=5,
                    confidence=1.0,
                ))
                self._log_stub_entity_created(
                    entity_id,
                    "audit_firm",
                    {
                        "resolution_method": "pcaob_firm_id",
                        "source_system": "pcaob_firm_registry",
                        "pcaob_firm_id": normalized_id,
                    },
                )
                self.session.flush()
            return entity_id
        return None

    def _log_stub_entity_created(
        self,
        entity_id: str,
        entity_type: str,
        changed_fields: Optional[dict] = None,
    ) -> None:
        """Write mdm_change_log so stub entities drain through mdm export.

        Relationship instances track export via graph_synced_at independently
        of mdm_change_log. Without a change-log row, stub persons/securities
        never reach the Snowflake MDM mirror and graph verify fails with
        missing_graph_edge_endpoints (Ticket 20 EMPLOYED_BY source persons).
        """
        from edgar_warehouse.mdm.database import MdmChangeLog

        self.session.add(
            MdmChangeLog(
                entity_id=entity_id,
                entity_type=entity_type,
                changed_fields=changed_fields or {"created": True},
            )
        )

    def _ensure_proxy_person(
        self, exec_name: str, company_cik: int, accession_number: str
    ) -> Optional[str]:
        """Return entity_id for a proxy executive, creating a stub if not found.

        Resolution order (AD-06 hybrid CIK crosswalk + UUID5 fallback):
        1. Exact CIK match via _person_entity_id (Form 4 anchor)
        2. Canonical name match via _person_entity_id
        3. UUID5(NAMESPACE_DNS, f"{company_cik}:{normalized_name}") — deterministic stub

        IMPORTANT: UUID5 deduplication is intentionally per-company (AD-06).
        An exec named "John Smith" at AAPL (cik=320193) and at MSFT (cik=789019)
        will receive two different entity_ids.  MDM merge pass (Splink) may later
        link them, but that is a separate pipeline step outside this derivation.

        Source ref: source_priority=50, confidence=0.5 — lower than Form 4 anchor
        (priority=10) so the Form 4 record wins on survivorship if the person is
        later resolved to a canonical entity.
        """
        import unicodedata
        import uuid as _uuid

        if not exec_name:
            return None

        # Step 1 + 2: Check existing MDM person records (Form 4 anchor path)
        existing = self._person_entity_id(None, exec_name)
        if existing:
            return existing

        # Step 3: Create UUID5 stub — deterministic so re-runs are idempotent
        normalized = unicodedata.normalize("NFKD", exec_name.strip().lower())
        stub_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"{company_cik}:{normalized}"))

        # Check whether the stub already exists (idempotency guard)
        from edgar_warehouse.mdm.database import MdmEntity, MdmPerson, MdmSourceRef
        from sqlalchemy import select
        already = self.session.scalar(
            select(MdmPerson.entity_id).where(MdmPerson.entity_id == stub_id)
        )
        if already:
            return already

        # Create MdmEntity + MdmPerson + MdmSourceRef + change-log (export drain)
        entity = MdmEntity(
            entity_id=stub_id,
            entity_type="person",
            resolution_method="uuid5_proxy_stub",
            confidence=0.5,
        )
        self.session.add(entity)
        person = MdmPerson(
            entity_id=stub_id,
            canonical_name=exec_name.strip(),
            name_variants=[exec_name.strip()],
        )
        self.session.add(person)
        # Source ref provides audit trail back to the DEF 14A filing
        source_ref = MdmSourceRef(
            entity_id=stub_id,
            source_system="proxy_filing",
            source_id=accession_number,
            source_priority=50,
            confidence=0.5,
        )
        self.session.add(source_ref)
        self._log_stub_entity_created(
            stub_id,
            "person",
            {
                "resolution_method": "uuid5_proxy_stub",
                "source_system": "proxy_filing",
                "source_id": accession_number,
            },
        )
        self.session.flush()
        return stub_id

    def _ensure_security_by_cusip(
        self,
        cusip: str,
        issuer_name: Optional[str],
        security_class: Optional[str],
    ) -> Optional[str]:
        """Return entity_id for a security identified by CUSIP, auto-creating if absent.

        13F holdings reference securities overwhelmingly outside the Form 4-derived
        mdm_security universe, so auto-creation is required (unlike AUDITED_BY which
        is lookup-only).  UUID5(NAMESPACE_DNS, f"cusip:{cusip}") ensures idempotency
        across multiple bootstrap runs.
        """
        import uuid as _uuid

        if not cusip:
            return None

        # Check existing by CUSIP (fastest path — indexed)
        from edgar_warehouse.mdm.database import MdmEntity, MdmSecurity, MdmSourceRef
        from sqlalchemy import select
        existing = self.session.scalar(
            select(MdmSecurity.entity_id).where(MdmSecurity.cusip == cusip)
        )
        if existing:
            # Opportunistically set security_class if still NULL
            if security_class:
                rec = self.session.get(MdmSecurity, existing)
                if rec and rec.security_class is None:
                    rec.security_class = security_class
                    self.session.flush()
            return existing

        # Auto-create new security stub
        stub_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"cusip:{cusip}"))

        # Idempotency guard — could exist in entity table without security row
        already = self.session.scalar(
            select(MdmSecurity.entity_id).where(MdmSecurity.entity_id == stub_id)
        )
        if already:
            return already

        canonical = issuer_name.strip() if issuer_name else f"CUSIP:{cusip}"
        entity = MdmEntity(
            entity_id=stub_id,
            entity_type="security",
            resolution_method="cusip_stub",
            confidence=0.7,
        )
        self.session.add(entity)
        security = MdmSecurity(
            entity_id=stub_id,
            canonical_title=canonical,
            cusip=cusip,
            security_class=security_class,
        )
        self.session.add(security)
        source_ref = MdmSourceRef(
            entity_id=stub_id,
            source_system="thirteenf_filing",
            source_id=f"cusip:{cusip}",
            source_priority=60,
            confidence=0.7,
        )
        self.session.add(source_ref)
        self._log_stub_entity_created(
            stub_id,
            "security",
            {
                "resolution_method": "cusip_stub",
                "source_system": "thirteenf_filing",
                "cusip": cusip,
            },
        )
        self.session.flush()
        return stub_id

    # ── New derivation methods ────────────────────────────────────────────────

    def _derive_employed_by(
        self, sync_engine: GraphSyncEngine, remaining: Optional[int]
    ) -> tuple[int, int, int, int, int]:
        """Derive EMPLOYED_BY edges from sec_executive_record (DEF 14A proxy filings).

        Person resolution order (AD-06):
        1. Exact Form 4 anchor via _person_entity_id
        2. UUID5 proxy stub via _ensure_proxy_person (creates if absent)

        Dedup key: (source_entity_id, target_entity_id, fiscal_year).
        One EMPLOYED_BY edge per person-company-year combination.
        """
        sql = """
            SELECT cik, accession_number, fiscal_year, exec_name, exec_role,
                   total_comp, base_salary, bonus, stock_awards,
                   option_awards, non_equity_incentive
            FROM sec_executive_record
            WHERE exec_name IS NOT NULL
            ORDER BY cik, fiscal_year, accession_number, exec_name
        """
        existing = self._relationship_count("EMPLOYED_BY")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        exec_rows = self._fetch_optional_relationship_rows(
            sql,
            remaining,
            rel_type_name="EMPLOYED_BY",
            source_table="sec_executive_record",
            existing=existing,
        )
        # Bulk-prefetch cik -> entity_id once for the whole batch instead of
        # a fresh per-row round-trip -- same rationale as the other
        # deriver methods (a company reports many executives across many
        # fiscal years). The person side (_ensure_proxy_person) stays
        # per-row: it creates a stub entity when no exact match exists, so
        # it isn't a pure lookup this fix can safely collapse.
        exec_ciks = {row.get("cik") for row in exec_rows if row.get("cik") is not None}
        company_id_by_cik = self._company_entity_ids(exec_ciks)
        for row in exec_rows:
            cik = row.get("cik")
            exec_name = row.get("exec_name") or ""
            accession_number = row.get("accession_number") or ""
            fiscal_year = row.get("fiscal_year")

            company_id = company_id_by_cik.get(int(cik)) if cik is not None else None
            if company_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "unresolved_target",
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            person_id = self._ensure_proxy_person(exec_name, int(cik), accession_number)
            if person_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "unresolved_source",
                    "exec_name": exec_name,
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            effective_from = date(int(fiscal_year), 1, 1) if fiscal_year else None
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="EMPLOYED_BY",
                source_entity_id=person_id,
                target_entity_id=company_id,
                properties={
                    "role":               row.get("exec_role"),
                    "title":              row.get("exec_role"),
                    "fiscal_year":        fiscal_year,
                    "total_compensation": row.get("total_comp"),
                    "stock_awards":       row.get("stock_awards"),
                    "option_awards":      row.get("option_awards"),
                    "non_equity_incentive": row.get("non_equity_incentive"),
                    "source_accession":   accession_number,
                },
                effective_from=effective_from,
                source_system="proxy_filing",
                source_accession=accession_number,
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "existing",
                    "source_entity_id": person_id,
                    "target_entity_id": company_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break

        # Item 5.02 events are applied after proxy baselines in effective-date
        # order. Appointments open a version; role changes close the prior open
        # version before opening the replacement; departures only close.
        event_sql = """
            SELECT accession_number, cik, event_type, person_name, exec_role,
                   previous_role, compensation_amount, effective_date
            FROM sec_employment_event
            ORDER BY effective_date, accession_number, event_index
        """
        event_rows = self._fetch_optional_relationship_rows(
            event_sql,
            None,
            rel_type_name="EMPLOYED_BY",
            source_table="sec_employment_event",
        )
        # Bulk-prefetch company lookups only (this loop's version open/close
        # sequencing genuinely depends on processing event_rows in the
        # already-materialized effective_date order above -- that ordering
        # is unaffected by prefetching, only the per-row lookup mechanism).
        event_ciks = {event.get("cik") for event in event_rows if event.get("cik") is not None}
        event_company_id_by_cik = self._company_entity_ids(event_ciks)
        for event in event_rows:
            cik = event.get("cik")
            accession_number = event.get("accession_number") or ""
            person_name = event.get("person_name") or ""
            effective_date = event.get("effective_date")
            if effective_date and not isinstance(effective_date, date):
                effective_date = date.fromisoformat(str(effective_date)[:10])
            company_id = event_company_id_by_cik.get(int(cik)) if cik is not None else None
            if company_id is None:
                skipped_unresolved_target += 1
                continue
            # Prefer Form 3/4/5 ownership identity (owner_cik / canonical_name).
            # If the person is not yet known from ownership filings, still
            # identify them via a deterministic UUID5 stub so Item 5.02 events
            # do not disappear when 3/4/5 has not named them yet.
            person_id = self._person_entity_id(None, person_name)
            if person_id is None and person_name and event.get("event_type") in {
                "appointment",
                "role_change",
                "compensation_change",
                "departure",
            }:
                person_id = self._ensure_proxy_person(person_name, int(cik), accession_number)
            if person_id is None:
                skipped_unresolved_source += 1
                continue

            current = self._current_employment_versions(person_id, company_id)
            if event.get("event_type") == "departure":
                if len(current) != 1:
                    skipped_unresolved_source += 1
                    continue
                if current[0].effective_from is not None and effective_date is not None \
                        and current[0].effective_from >= effective_date:
                    # Item 5.02 events are walked in effective_date order, but proxy
                    # baselines (source_system="proxy_filing") are all inserted up
                    # front with effective_from = Jan 1 of the DEF 14A fiscal year --
                    # a coarse placeholder, not a true start date. When that baseline's
                    # placeholder date lands on or after this event's real
                    # effective_date, closing it here would set effective_to <=
                    # effective_from -- ck_rel_instance_valid_interval requires a
                    # strictly positive interval (valid_to_date > valid_from_date), so
                    # even an equal-date close (two same-day events) is invalid. Skip
                    # rather than corrupt/crash.
                    skipped_unresolved_source += 1
                    print(json.dumps({
                        "event": "mdm_relationship_skip",
                        "rel_type": "EMPLOYED_BY",
                        "reason": "event_predates_open_version",
                        "source_entity_id": person_id,
                        "target_entity_id": company_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }), file=sys.stderr, flush=True)
                    continue
                from edgar_warehouse.mdm.graph import close_relationship_version
                close_relationship_version(self.session, current[0].instance_id, effective_date)
                continue
            if event.get("event_type") not in {
                "appointment", "role_change", "compensation_change"
            }:
                skipped_unresolved_source += 1
                continue
            if len(current) > 1:
                skipped_unresolved_source += 1
                continue
            if current and current[0].effective_from is not None and effective_date is not None \
                    and current[0].effective_from >= effective_date:
                # Same out-of-order/same-day guard as the departure branch above.
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "event_predates_open_version",
                    "source_entity_id": person_id,
                    "target_entity_id": company_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            if current:
                from edgar_warehouse.mdm.graph import close_relationship_version
                close_relationship_version(self.session, current[0].instance_id, effective_date)
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="EMPLOYED_BY",
                source_entity_id=person_id,
                target_entity_id=company_id,
                properties={
                    "role": event.get("exec_role") or (
                        (current[0].properties or {}).get("role") if current else None
                    ),
                    "title": event.get("exec_role") or (
                        (current[0].properties or {}).get("title") if current else None
                    ),
                    "previous_role": event.get("previous_role"),
                    "compensation_amount": event.get("compensation_amount"),
                    "source_accession": accession_number,
                    "event_type": event.get("event_type"),
                },
                effective_from=effective_date,
                source_system="item_502_filing",
                source_accession=accession_number,
                date_provenance="reported",
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1

        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _current_employment_versions(self, person_id: str, company_id: str):
        from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType

        return list(self.session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType,
                  MdmRelationshipType.rel_type_id == MdmRelationshipInstance.rel_type_id)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
            .where(MdmRelationshipInstance.source_entity_id == person_id)
            .where(MdmRelationshipInstance.target_entity_id == company_id)
            .where(MdmRelationshipInstance.is_active.is_(True))
            .where(MdmRelationshipInstance.quarantined.is_(False))
            .where(MdmRelationshipInstance.superseded_by_version_id.is_(None))
            .where(MdmRelationshipInstance.valid_to_date.is_(None))
        ))

    def _derive_audited_by(
        self, sync_engine: GraphSyncEngine, remaining: Optional[int]
    ) -> tuple[int, int, int, int, int]:
        """Derive report-date AUDITED_BY edges from direct annual-filing evidence.

        Audit firm resolution (AD-08):
        1. PCAOB firm ID — authoritative (dei_AuditorFirmId XBRL concept)
        2. Firm name fuzzy match — fallback for FY2020 filings predating mandatory DEI

        auditor_changed is computed as TRUE when the firm_name differs from the
        immediately prior fiscal year's row for the same CIK.
        """
        direct_sql = """
            SELECT registrant_cik AS cik, accession_number,
                   EXTRACT(YEAR FROM audited_period_end) AS fiscal_year,
                   audited_period_end AS period_end, report_date,
                   pcaob_firm_id AS auditor_pcaob_id,
                   principal_firm_name AS auditor_name,
                   evidence_source, evidence_fingerprint,
                   form_ap_filing_id, NULL AS icfr_attestation
            FROM sec_auditor_report_evidence
            ORDER BY registrant_cik, audited_period_end, report_date, accession_number
        """
        rows = self._fetch_optional_relationship_rows(
            direct_sql, remaining, rel_type_name="AUDITED_BY",
            source_table="sec_auditor_report_evidence",
            existing=self._relationship_count("AUDITED_BY"),
        )
        if not rows:
            legacy_sql = """
            SELECT cik, accession_number, fiscal_year, period_end,
                   NULL AS report_date, auditor_pcaob_id, auditor_name,
                   NULL AS evidence_source, NULL AS evidence_fingerprint,
                   NULL AS form_ap_filing_id, icfr_attestation
            FROM sec_accounting_flag
            WHERE auditor_name IS NOT NULL OR auditor_pcaob_id IS NOT NULL
            ORDER BY cik, fiscal_year
            """
            rows = self._fetch_optional_relationship_rows(
                legacy_sql, remaining, rel_type_name="AUDITED_BY",
                source_table="sec_accounting_flag",
                existing=self._relationship_count("AUDITED_BY"),
            )
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        # Bulk-prefetch cik -> entity_id once for the whole batch (same
        # rationale as the other deriver methods). The auditor-change
        # detection below still walks `rows` sequentially in its original
        # cik/fiscal_year order -- prefetching only replaces the lookup, not
        # the ordering it depends on.
        audited_ciks = {row.get("cik") for row in rows if row.get("cik") is not None}
        audited_company_id_by_cik = self._company_entity_ids(audited_ciks)

        prev_cik: Optional[int] = None
        prev_auditor_name: Optional[str] = None

        for row in rows:
            cik = row.get("cik")
            pcaob_id = row.get("auditor_pcaob_id")
            auditor_name = row.get("auditor_name")
            fiscal_year = row.get("fiscal_year")
            accession_number = row.get("accession_number") or ""
            icfr_attestation = row.get("icfr_attestation")

            # Detect auditor change vs prior fiscal year (same CIK, ORDER BY cik, fiscal_year)
            if cik == prev_cik and prev_auditor_name is not None and auditor_name:
                auditor_changed = (auditor_name.lower().strip() != prev_auditor_name.lower().strip())
            else:
                auditor_changed = False
            prev_cik = cik
            prev_auditor_name = auditor_name

            company_id = audited_company_id_by_cik.get(int(cik)) if cik is not None else None
            if company_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "AUDITED_BY",
                    "reason": "unresolved_source",
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            audit_firm_id = self._audit_firm_entity_id(pcaob_id, auditor_name)
            if audit_firm_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "AUDITED_BY",
                    "reason": "unresolved_target",
                    "cik": cik,
                    "auditor_pcaob_id": pcaob_id,
                    "auditor_name": auditor_name,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            effective_from = row.get("report_date") or (
                date(int(fiscal_year), 1, 1) if fiscal_year else None
            )
            if auditor_changed and effective_from is not None:
                from edgar_warehouse.mdm.database import (
                    MdmRelationshipInstance,
                    MdmRelationshipType,
                )
                from edgar_warehouse.mdm.graph import close_relationship_version

                prior_versions = self.session.scalars(
                    select(MdmRelationshipInstance)
                    .join(MdmRelationshipType)
                    .where(MdmRelationshipType.rel_type_name == "AUDITED_BY")
                    .where(MdmRelationshipInstance.source_entity_id == company_id)
                    .where(MdmRelationshipInstance.target_entity_id != audit_firm_id)
                    .where(MdmRelationshipInstance.is_active.is_(True))
                    .where(MdmRelationshipInstance.quarantined.is_(False))
                    .where(MdmRelationshipInstance.superseded_by_version_id.is_(None))
                    .where(MdmRelationshipInstance.valid_to_date.is_(None))
                ).all()
                for prior_version in prior_versions:
                    close_relationship_version(
                        self.session, prior_version.instance_id, effective_from
                    )
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="AUDITED_BY",
                source_entity_id=company_id,
                target_entity_id=audit_firm_id,
                properties={
                    "fiscal_year":      fiscal_year,
                    "pcaob_firm_id":    pcaob_id,
                    "icfr_attestation": icfr_attestation,
                    "auditor_changed":  auditor_changed,
                    "source_accession": accession_number,
                    "audited_period_end": (
                        row.get("period_end").isoformat()
                        if hasattr(row.get("period_end"), "isoformat")
                        else row.get("period_end")
                    ),
                    "report_date": (
                        row.get("report_date").isoformat()
                        if hasattr(row.get("report_date"), "isoformat")
                        else row.get("report_date")
                    ),
                    "evidence_source": row.get("evidence_source") or "legacy_companyfacts",
                    "evidence_fingerprint": row.get("evidence_fingerprint"),
                    "form_ap_filing_id": row.get("form_ap_filing_id"),
                },
                effective_from=effective_from,
                source_system=row.get("evidence_source") or "tenk_filing",
                source_accession=accession_number,
                date_provenance="reported" if row.get("report_date") else "filing_date_proxy",
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "AUDITED_BY",
                    "reason": "existing",
                    "source_entity_id": company_id,
                    "target_entity_id": audit_firm_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break

        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_institutional_holds(
        self, sync_engine: GraphSyncEngine, remaining: Optional[int]
    ) -> tuple[int, int, int, int, int]:
        """Derive INSTITUTIONAL_HOLDS edges from sec_thirteenf_holding (13F-HR filings).

        Source entity: Adviser (filing manager CIK → mdm_adviser.cik)
        Target entity: Security (CUSIP → mdm_security.cusip, auto-created if absent)

        Security auto-creation rationale: 13F holdings overwhelmingly reference
        securities outside the Form 4-derived mdm_security universe.  Auto-creating
        via _ensure_security_by_cusip is necessary to capture institutional coverage.
        The UUID5 key (f"cusip:{cusip}") guarantees idempotency across runs.

        Rows without a CUSIP are skipped — security identity cannot be established.
        Filing managers resolve by SEC CIK. If the CIK is not already represented
        by an ADV-derived adviser, a deterministic 13F-manager adviser source entity
        is created so the complete manager universe is not restricted to IARD filers.

        CIK-range batching (D-03, EDGE-11, T-06-01, T-06-02): sec_thirteenf_holding
        is the largest silver table — a single unbounded silver.fetch() risks OOM
        on ECS at full-universe scale. A cheap MIN(cik)/MAX(cik) bounds query
        (still governed by the standard missing-source-table graceful skip) is
        issued once, then rows are read in `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE`
        CIK-wide chunks via a parameterized `WHERE ... AND cik BETWEEN ? AND ?`
        query — CIK bounds are always bound params, never string-formatted into
        the SQL. Adviser-entity resolution is per-CIK, so batch ordering carries
        no correctness risk (TODOS.md). Counters and the `remaining` early-exit
        accumulate across all batches, not per batch.
        """
        base_sql = """
            SELECT h.cik, h.accession_number, h.period_of_report, h.cusip,
                   h.issuer_name, h.security_title, h.shares_held, h.market_value,
                   h.put_call, h.discretion_type, h.security_class
            FROM sec_thirteenf_holding h
            JOIN sec_thirteenf_filing f ON f.accession_number = h.accession_number
            WHERE h.cusip IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM sec_thirteenf_filing later
                  WHERE later.cik = f.cik
                    AND later.period_of_report = f.period_of_report
                    AND later.amendment_type = 'restatement'
                    AND (later.filing_date, later.accession_number) >
                        (f.filing_date, f.accession_number)
              )
        """
        bounds_sql = """
            SELECT MIN(cik) AS min_cik, MAX(cik) AS max_cik
            FROM (
                SELECT h.cik
                FROM sec_thirteenf_holding h
                JOIN sec_thirteenf_filing f ON f.accession_number = h.accession_number
                WHERE h.cusip IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM sec_thirteenf_filing later
                      WHERE later.cik = f.cik
                        AND later.period_of_report = f.period_of_report
                        AND later.amendment_type = 'restatement'
                        AND (later.filing_date, later.accession_number) >
                            (f.filing_date, f.accession_number)
                  )
            ) effective_holdings
        """
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        # Single cheap bounds lookup — the missing-source-table graceful skip
        # (one mdm_relationship_skip event) fires here if either
        # sec_thirteenf_holding or sec_thirteenf_filing (both joined in
        # bounds_sql/base_sql above) is absent, before any batch loop is
        # entered.
        bounds_rows = self._fetch_optional_relationship_rows(
            bounds_sql,
            None,
            rel_type_name="INSTITUTIONAL_HOLDS",
            source_table=("sec_thirteenf_holding", "sec_thirteenf_filing"),
        )
        if not bounds_rows or bounds_rows[0].get("min_cik") is None:
            return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

        min_cik = int(bounds_rows[0]["min_cik"])
        max_cik = int(bounds_rows[0]["max_cik"])
        batch_sql = f"{base_sql.rstrip()} AND h.cik BETWEEN ? AND ? ORDER BY h.cik, h.accession_number, h.cusip"

        # A manager CIK's rows repeat thousands of times across this table
        # (one row per holding, all sharing the same filer) -- CIK-range
        # batching already bounds memory, but every row still re-ran
        # _ensure_thirteenf_manager's own lookup query before this cache.
        # _ensure_thirteenf_manager has no per-call side effect beyond the
        # first (create-if-absent, then a pure return thereafter), so
        # memoizing it here is safe -- unlike _ensure_security_by_cusip
        # below, which opportunistically backfills security_class on every
        # call and is deliberately left unmemoized so a later row with a
        # non-NULL security_class can still backfill an earlier NULL one.
        adviser_id_by_cik: dict[int, Optional[str]] = {}

        cik_lo = min_cik
        while cik_lo <= max_cik:
            cik_hi = min(cik_lo + _INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE - 1, max_cik)

            for row in self.silver.fetch(batch_sql, params=[cik_lo, cik_hi]):
                cik = row.get("cik")
                cusip = row.get("cusip") or ""
                accession_number = row.get("accession_number") or ""
                period_of_report = row.get("period_of_report")
                security_class = row.get("security_class")
                issuer_name = row.get("issuer_name")

                if not cusip:
                    skipped_unresolved_target += 1
                    continue

                if cik not in adviser_id_by_cik:
                    adviser_id_by_cik[cik] = self._ensure_thirteenf_manager(cik)
                adviser_id = adviser_id_by_cik[cik]
                if adviser_id is None:
                    skipped_unresolved_source += 1
                    print(json.dumps({
                        "event": "mdm_relationship_skip",
                        "rel_type": "INSTITUTIONAL_HOLDS",
                        "reason": "unresolved_source",
                        "cik": cik,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }), file=sys.stderr, flush=True)
                    continue

                security_id = self._ensure_security_by_cusip(cusip, issuer_name, security_class)
                if security_id is None:
                    skipped_unresolved_target += 1
                    print(json.dumps({
                        "event": "mdm_relationship_skip",
                        "rel_type": "INSTITUTIONAL_HOLDS",
                        "reason": "unresolved_target",
                        "cusip": cusip,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }), file=sys.stderr, flush=True)
                    continue

                _rel, created = sync_engine.ensure_relationship(
                    rel_type_name="INSTITUTIONAL_HOLDS",
                    source_entity_id=adviser_id,
                    target_entity_id=security_id,
                    properties={
                        "quarter_end":      str(period_of_report) if period_of_report else None,
                        "shares_held":      row.get("shares_held"),
                        "market_value":     row.get("market_value"),
                        "ownership_pct":    None,   # computed by gold layer (shares / shares_outstanding)
                        "put_call":         row.get("put_call"),
                        "discretion_type":  row.get("discretion_type"),
                        "source_accession": accession_number,
                    },
                    effective_from=date.fromisoformat(str(period_of_report)) if period_of_report else None,
                    source_system="thirteenf_filing",
                    source_accession=accession_number,
                )
                if created:
                    inserted += 1
                else:
                    skipped_existing += 1
                    print(json.dumps({
                        "event": "mdm_relationship_skip",
                        "rel_type": "INSTITUTIONAL_HOLDS",
                        "reason": "existing",
                        "source_entity_id": adviser_id,
                        "target_entity_id": security_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }), file=sys.stderr, flush=True)
                if remaining is not None and inserted >= remaining:
                    # Early exit across both the inner row loop and the outer
                    # CIK-range batch loop — counters accumulated so far are final.
                    return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

            cik_lo = cik_hi + 1

        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _adviser_company_pairs(self):
        from edgar_warehouse.mdm.database import MdmAdviser
        from sqlalchemy import select
        return self.session.execute(
            select(MdmAdviser.entity_id, MdmAdviser.linked_company_entity_id)
            .where(MdmAdviser.linked_company_entity_id.isnot(None))
        ).all()

    def _adviser_person_pairs(self):
        from edgar_warehouse.mdm.database import MdmAdviser, MdmPerson
        from sqlalchemy import select
        return self.session.execute(
            select(MdmAdviser.entity_id, MdmPerson.entity_id)
            .join(MdmPerson, MdmPerson.owner_cik == MdmAdviser.cik)
            .where(MdmAdviser.cik.isnot(None))
            .where(MdmAdviser.linked_company_entity_id.is_(None))
        ).all()

    @staticmethod
    def _first(rows: list[dict]) -> Optional[dict]:
        return rows[0] if rows else None

    @staticmethod
    def _json_property(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "__float__") and value.__class__.__module__ == "decimal":
            return float(value)
        return value


def _ownership_security_source_id(txn_row: dict) -> str:
    accession = txn_row.get("accession_number")
    owner_index = txn_row.get("owner_index")
    txn_index = txn_row.get("txn_index")
    if txn_row.get("is_derivative"):
        return f"{accession}:derivative:{owner_index}:{txn_index}"
    return f"{accession}:{owner_index}:{txn_index}"


def verify_insider_coverage(pipeline: "MDMPipeline", ciks=None) -> dict:
    """Ticket 21 slice 3: the concrete insider-coverage check.

    Builds the insider inventory from silver ownership rows and partitions it
    against MDM using the pipeline's own resolution (same person/company
    resolution _derive_is_insider uses) plus an IS_INSIDER pair-existence
    check. Fail-closed consumers require insider_unresolved == 0.
    """
    from sqlalchemy import func, select

    from edgar_warehouse.application.relationship_bulk_load import (
        insider_inventory,
        partition_insider_coverage,
    )
    from edgar_warehouse.mdm.database import (
        MdmRelationshipInstance,
        MdmRelationshipType,
    )

    inventory = insider_inventory(
        pipeline.silver, ciks,
        exclude_owner_ciks=pipeline._company_cik_set(),
    )

    def _has_insider_version(person_id: str, issuer_id: str) -> bool:
        return bool(pipeline.session.scalar(
            select(func.count(MdmRelationshipInstance.instance_id))
            .join(MdmRelationshipType)
            .where(
                MdmRelationshipType.rel_type_name == "IS_INSIDER",
                MdmRelationshipInstance.source_entity_id == person_id,
                MdmRelationshipInstance.target_entity_id == issuer_id,
                MdmRelationshipInstance.is_active.is_(True),
            )
        ))

    return partition_insider_coverage(
        inventory,
        resolve_person=pipeline._person_entity_id,
        resolve_issuer=pipeline._company_entity_id,
        has_insider_version=_has_insider_version,
    )
