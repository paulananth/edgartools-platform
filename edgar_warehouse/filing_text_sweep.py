"""release-readiness Ticket 101: ledger-driven sweep that keeps
``sec_filing_text`` current for genuine periodic-reporting companies, and
surfaces (without deleting) any already-extracted text whose CIK no
longer qualifies.

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

Any CIK with an existing ``sec_filing_text`` row that is NOT in
``required`` (aged out past 2 years, lost its ticker, or turns out to be
an individual per Ticket 01's ongoing cleanup) is emitted as a structured
cleanup-candidate event -- identify only, never delete, matching this
repo's established Ticket 70/71 split between "decide/report" and
"actually remove."
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional

_PERIODIC_FORMS = ("10-K", "10-K405", "10KSB", "10KSB40")
_TEXT_VERSION = "generic_text_v1"
_REQUIRED_RECENCY_YEARS = 2
_CHUNK_SIZE = 1000


def _chunks(items: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


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


def _already_processed_accessions(reader: Any, accession_numbers: list[str]) -> set[str]:
    processed: set[str] = set()
    for chunk in _chunks(accession_numbers, _CHUNK_SIZE):
        if not chunk:
            continue
        placeholders = ", ".join("?" for _ in chunk)
        rows = reader.fetch(
            f"""
            SELECT DISTINCT accession_number
            FROM sec_filing_text
            WHERE text_version = ?
              AND accession_number IN ({placeholders})
            """,
            [_TEXT_VERSION, *chunk],
        )
        for row in rows:
            processed.add(str(row["accession_number"]))
    return processed


def _processed_ciks_with_owning_cik(reader: Any) -> list[dict[str, Any]]:
    """Every (cik, accession_number) pair with an existing sec_filing_text row,
    joined back to its owning CIK -- used to find cleanup candidates."""
    rows = reader.fetch(
        """
        SELECT DISTINCT f.cik, sft.accession_number
        FROM sec_filing_text sft
        JOIN sec_company_filing f ON f.accession_number = sft.accession_number
        WHERE sft.text_version = ?
        """,
        [_TEXT_VERSION],
    )
    return [{"cik": int(row["cik"]), "accession_number": str(row["accession_number"])} for row in rows]


def run_filing_text_sweep(
    *,
    context: Any,
    db: Any,
    bookkeeping: Any,
    sync_run_id: str,
    now: datetime,
    limit: Optional[int] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _emit_pipeline_event,
        submissions_orchestrator,
    )
    from edgar_warehouse.infrastructure.filing_artifact_service import extract_filing_text
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
        accession_numbers = [row["accession_number"] for row in required]
        processed_accessions = _already_processed_accessions(reader, accession_numbers)
        required_ciks = {row["cik"] for row in required}

        cleanup_candidates = [
            row for row in _processed_ciks_with_owning_cik(reader) if row["cik"] not in required_ciks
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

    return raw_writes, metrics
