"""release-readiness Ticket 101: ledger-driven sweep that keeps
``sec_filing_text`` current for genuine periodic-reporting companies, and
surfaces (without deleting) every already-extracted exact text identity that
is no longer required.

Resolved via `/grilling` (2026-09-07, see
`.scratch/release-readiness/issues/101-automate-filing-text-capture-end-to-end.md`):
this is deliberately NOT a live/on-demand feature -- the one stated
consumer (`initiating-coverage`) fetches SEC directly and never touches
this platform's data -- so there is no request path to hook. Instead this
is a scheduled background sweep, invoked as its own command
(``sweep-filing-text``) folded into ``daily_incremental`` as a Step
Functions state after the main silver-publish state.

``required`` (computed fresh every sweep, no explicit transition
tracking -- recomputing is cheap and reuses joins the sweep needs anyway):

1. CIK has ever filed a real periodic disclosure form (``10-K``,
   ``10-K405``, ``10KSB``, ``10KSB40``). This automatically satisfies
   Ticket 01's individual-reporting-owner exclusion too -- a CIK whose
   *entire* filing history is ownership-forms-only (Ticket 01's
   discriminator) can never have filed one of these forms, so there is no
   need to separately call ``exclude_individual_reporting_owners_sql``
   here.
2. That CIK's most recent such filing is within the trailing 2 years --
   ages a company out of ``required`` automatically once it stops filing
   annual reports (delisted, acquired, went private, bankrupt).
3. CIK has a real ticker in ``sec_company_ticker`` -- tighter than
   periodic-filing history alone.

``processed`` = a ``sec_filing_text`` row already exists for that CIK's
current latest qualifying accession (``text_version="generic_text_v1"``,
matching ``filing_text_projection.extract_text_for_accession``'s own
default).

For every required-and-unprocessed CIK, this stages that CIK's filing
metadata via the existing ``submissions_orchestrator`` (a real SEC fetch --
canonical local silver.duckdb starts empty every run per DuckDB
Retirement Cutover Ticket 10, so nothing is locally known about a CIK
until this run captures it) then extracts text for its latest qualifying
accession via the existing ``extract_filing_text``. One CIK's failure
(a transient SEC error, a delisted CIK whose target accession fell out of
its own recent-submissions window, etc.) is isolated and logged, not
allowed to abort the whole sweep -- this runs against the full active
CIK universe, the same "one bad row shouldn't fail the batch" reasoning
already applied elsewhere in this pipeline (e.g. `_run_accession_resync`'s
immutable-object-conflict isolation).

Any known ``(accession_number, text_version)`` with an existing
``sec_filing_text`` row that is NOT in the exact required set is emitted as a
structured cleanup-candidate event. This includes an older projection for a
CIK whose newer filing is required. Unknown text versions are classified but
blocked. The sweep also writes a complete immutable retention manifest;
deletion remains a separately reviewed cost-optimizer operation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

_PERIODIC_FORMS = ("10-K", "10-K405", "10KSB", "10KSB40")
_TEXT_VERSION = "generic_text_v1"
_REQUIRED_RECENCY_YEARS = 2


def _latest_previous_manifest(
    storage_root: Any, *, run_id: str, observed_at: datetime
) -> dict[str, Any] | None:
    """Load the immediately preceding immutable observation, if one exists."""
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    observed_at_utc = (
        observed_at.replace(tzinfo=UTC)
        if observed_at.tzinfo is None
        else observed_at.astimezone(UTC)
    )
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in storage_root.find_existing(
        "artifacts/filing_text_retention/observed_date=*/run_id=*/manifest.json"
    ):
        manifest = json.loads(read_bytes(path))
        if manifest.get("run_id") == run_id:
            continue
        raw_observed_at = str(manifest.get("observed_at") or "")
        try:
            candidate_at = datetime.fromisoformat(raw_observed_at)
        except ValueError as exc:
            raise RuntimeError(
                f"invalid prior filing-text retention manifest at {path}"
            ) from exc
        if candidate_at.tzinfo is None:
            raise RuntimeError(
                f"prior filing-text retention manifest has no timezone at {path}"
            )
        candidate_at = candidate_at.astimezone(UTC)
        if candidate_at < observed_at_utc:
            candidates.append((candidate_at, path, manifest))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]


def _required_ciks(reader: Any) -> list[dict[str, Any]]:
    """Return one row per required CIK: cik, latest qualifying accession_number,
    latest filing_date. See module docstring for the ``required`` definition."""
    placeholders = ", ".join("?" for _ in _PERIODIC_FORMS)
    rows = reader.fetch(
        f"""
        WITH periodic AS (
            SELECT cik, accession_number, filing_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY cik ORDER BY filing_date DESC, accession_number DESC
                   ) AS rn
            FROM sec_company_filing
            WHERE form IN ({placeholders})
        )
        SELECT cik, accession_number, filing_date
        FROM periodic
        WHERE rn = 1
          AND filing_date >= DATEADD(year, -{_REQUIRED_RECENCY_YEARS}, CURRENT_DATE())
          AND cik IN (SELECT DISTINCT cik FROM sec_company_ticker)
        """,
        list(_PERIODIC_FORMS),
    )
    return [
        {
            "cik": int(row["cik"]),
            "accession_number": str(row["accession_number"]),
            "filing_date": row["filing_date"],
        }
        for row in rows
    ]


def _processed_filing_text(reader: Any) -> list[dict[str, Any]]:
    """Return every exact filing-text identity and its derived object evidence."""
    rows = reader.fetch(
        """
        SELECT DISTINCT f.cik, sft.accession_number, sft.text_version,
                        sft.text_storage_path, sft.text_sha256
        FROM sec_filing_text sft
        LEFT JOIN sec_company_filing f ON f.accession_number = sft.accession_number
        """
    )
    return [
        {
            "cik": int(row["cik"]) if row.get("cik") is not None else None,
            "accession_number": str(row["accession_number"]),
            "text_version": str(row["text_version"]),
            "text_storage_path": str(row.get("text_storage_path") or ""),
            "text_sha256": str(row.get("text_sha256") or ""),
        }
        for row in rows
    ]


def run_filing_text_sweep(
    *,
    context: Any,
    db: Any,
    bookkeeping: Any,
    sync_run_id: str,
    now: datetime,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _emit_pipeline_event,
        submissions_orchestrator,
    )
    from edgar_warehouse.infrastructure.filing_artifact_service import (
        extract_filing_text,
    )
    from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader

    raw_writes: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {
        "rows_inserted": 0,
        "rows_skipped": 0,
        "sync_status": "succeeded",
        "cleanup_candidate_count": 0,
        "cik_error_count": 0,
    }

    reader = SnowflakeSilverReader.connect()
    try:
        required = _required_ciks(reader)
        processed_rows = _processed_filing_text(reader)
        required_identities = {
            (row["accession_number"], _TEXT_VERSION) for row in required
        }
        processed_accessions = {
            row["accession_number"]
            for row in processed_rows
            if row["text_version"] == _TEXT_VERSION
            and (row["accession_number"], row["text_version"])
            in required_identities
        }
        cleanup_candidates = [
            row
            for row in processed_rows
            if row["text_version"] == _TEXT_VERSION
            and (row["accession_number"], row["text_version"])
            not in required_identities
        ]
    finally:
        reader.close()

    _emit_pipeline_event(
        "filing_text_sweep_started",
        run_id=sync_run_id,
        required_count=len(required),
        already_processed_count=len(processed_accessions),
        cleanup_candidate_count=len(cleanup_candidates),
    )

    if cleanup_candidates:
        _emit_pipeline_event(
            "filing_text_sweep_cleanup_candidates",
            run_id=sync_run_id,
            count=len(cleanup_candidates),
            # Sampled, not exhaustive -- this is a visibility signal for an
            # operator to scope a future cleanup ticket, not a work queue.
            sample=cleanup_candidates[:50],
        )
    metrics["cleanup_candidate_count"] = len(cleanup_candidates)

    pending = [row for row in required if row["accession_number"] not in processed_accessions]
    if limit is not None:
        pending = pending[:limit]

    for index, row in enumerate(pending, start=1):
        cik = row["cik"]
        accession_number = row["accession_number"]
        try:
            submission_result = submissions_orchestrator(
                context=context,
                db=db,
                bookkeeping=bookkeeping,
                sync_run_id=sync_run_id,
                cik=cik,
                include_pagination=False,
                fetch_date=now.date() if isinstance(now, datetime) else now,
                force=False,
                load_mode="sweep_filing_text",
            )
            raw_writes.extend(submission_result["raw_writes"])

            if db.get_filing(accession_number) is None:
                # The target accession wasn't in this CIK's captured recent-
                # submissions window (e.g. a very old "latest" filing for an
                # otherwise-active CIK). Not an error -- log and move on;
                # a later sweep with a fresher submissions window may pick
                # it up, or the CIK will file something newer in the
                # meantime and become required against that instead.
                metrics["rows_skipped"] += 1
                _emit_pipeline_event(
                    "filing_text_sweep_accession_not_found",
                    run_id=sync_run_id,
                    cik=cik,
                    accession_number=accession_number,
                    index=index,
                    total=len(pending),
                )
                continue

            extract_filing_text(
                context=context,
                db=db,
                accession_number=accession_number,
                sync_run_id=sync_run_id,
            )
            metrics["rows_inserted"] += 1
            _emit_pipeline_event(
                "filing_text_sweep_progress",
                run_id=sync_run_id,
                cik=cik,
                accession_number=accession_number,
                index=index,
                total=len(pending),
            )
        except Exception as exc:  # noqa: BLE001 -- isolate one CIK's failure, see module docstring
            metrics["cik_error_count"] += 1
            _emit_pipeline_event(
                "filing_text_sweep_cik_error",
                run_id=sync_run_id,
                cik=cik,
                accession_number=accession_number,
                index=index,
                total=len(pending),
                error=repr(exc),
            )
            continue

    _emit_pipeline_event(
        "filing_text_sweep_completed",
        run_id=sync_run_id,
        required_count=len(required),
        pending_count=len(pending),
        rows_inserted=metrics["rows_inserted"],
        rows_skipped=metrics["rows_skipped"],
        cik_error_count=metrics["cik_error_count"],
    )

    from edgar_warehouse.application.filing_text_retention import (
        build_filing_text_sweep_manifest,
        filing_text_sweep_manifest_bytes,
        filing_text_sweep_manifest_path,
    )

    retention_status = (
        "succeeded"
        if metrics["cik_error_count"] == 0 and metrics["rows_skipped"] == 0
        else "incomplete"
    )
    manifest = build_filing_text_sweep_manifest(
        run_id=sync_run_id,
        observed_at=now,
        required_rows=[
            {**row, "text_version": _TEXT_VERSION} for row in required
        ],
        processed_rows=processed_rows,
        status=retention_status,
        previous_manifest=_latest_previous_manifest(
            context.storage_root,
            run_id=sync_run_id,
            observed_at=now,
        ),
    )
    manifest_relative_path = filing_text_sweep_manifest_path(
        run_id=sync_run_id, observed_at=now
    )
    manifest_path = context.storage_root.write_immutable_bytes(
        manifest_relative_path,
        filing_text_sweep_manifest_bytes(manifest),
    )
    metrics["retention_manifest_path"] = manifest_path
    metrics["retention_manifest_hash"] = manifest["manifest_hash"]
    metrics["retention_manifest_status"] = retention_status

    return raw_writes, metrics
