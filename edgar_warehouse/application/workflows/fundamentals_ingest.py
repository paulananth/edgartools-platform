"""Branch B bootstrap workflow — fundamentals silver namespace.

Handles three distinct processing modes:

per-filing
----------
Fetches primary document for 8-K (earnings releases) and DEF 14A (proxy
compensation) filings whose form type is in BRANCH_B_FORMS.  Dispatches through
``edgar_warehouse.parsers.get_parser()`` (same mechanism as bootstrap-batch).
Writes to: sec_earnings_release, sec_executive_record.

entity-facts
------------
Calls the SEC ``/api/xbrl/companyfacts/CIK{cik:010}.json`` endpoint for each
CIK in the batch.  Dispatches through ``parse_entity_facts``.
Writes to: sec_financial_fact, sec_accounting_flag.
Then calls ``compute_derived_for_accession()`` per accession to populate
sec_financial_derived, and ``backfill_accounting_flags()`` to add forensic scores.

thirteenf
---------
For each 13F-HR filing in bronze, fetches the INFORMATION TABLE XML attachment
and dispatches through ``parse_thirteenf``.
Writes to: sec_thirteenf_holding.

Relationship to bootstrap-batch (Branch A)
------------------------------------------
Branch B writes fundamentals tables into the same SEC silver DuckDB database as
Branch A. Per-filing and 13F modes use the same connection as their source so
filing metadata and fundamentals rows remain application-consistent.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError

# Branch B form types handled by the per-filing path
BRANCH_B_FILING_FORMS = frozenset({
    "8-K", "8-K/A",
    "DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A",
})

# 13F forms handled by the thirteenf path
BRANCH_B_13F_FORMS = frozenset({"13F-HR", "13F-HR/A"})


def _emit(event: str, **kwargs: Any) -> None:
    doc = {"event": event, "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"), **kwargs}
    print(json.dumps(doc, sort_keys=True), file=sys.stderr, flush=True)


def run_bootstrap_fundamentals_per_filing(
    *,
    cik_list: list[int],
    source,                # SilverDatabase | None — Branch A metadata source
    db,                    # SilverDatabase instance — write target
    sync_run_id: str,
    release_mode: bool = False,
    candidate_accessions: set[str] | None = None,
) -> dict[str, Any]:
    """Process 8-K earnings + DEF 14A proxy filings from bronze for the given CIKs.

    Filing/attachment/raw-object metadata is read from ``source`` — Branch A's
    silver tables, produced by bootstrap-next/bootstrap-batch. In the unified
    silver layout ``source`` is normally the same ``SilverDatabase`` instance as
    ``db``. ``source`` may still be None in direct unit tests or ad-hoc local
    calls; this is treated as zero available filings rather than an error.

    Returns row counts per table written.
    """
    from edgar_warehouse.parsers import get_parser
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    metrics: dict[str, Any] = {
        "filings_scanned": 0,
        "filings_parsed": 0,
        "filings_skipped": 0,
        "rows_earnings_release": 0,
        "rows_executive_record": 0,
        "rows_employment_event": 0,
        "candidate_outcomes": [],
    }

    if source is None:
        if release_mode:
            raise WarehouseRuntimeError("release relationship source is unavailable")
        _emit("fundamentals_source_unavailable", cik_count=len(cik_list))
        return metrics

    form_list = ", ".join(f"'{f}'" for f in BRANCH_B_FILING_FORMS)
    cik_placeholder = ", ".join("?" * len(cik_list))

    filings = source.fetch(
        f"""
        SELECT f.accession_number, f.cik, f.form, f.filing_date, f.items
        FROM sec_company_filing f
        WHERE f.cik IN ({cik_placeholder})
          AND f.form IN ({form_list})
        ORDER BY f.cik, f.filing_date DESC
        """,
        [int(c) for c in cik_list],
    )
    metrics["filings_scanned"] = len(filings)

    if candidate_accessions is not None:
        filings = [row for row in filings if row["accession_number"] in candidate_accessions]
        observed = {row["accession_number"] for row in filings}
        missing = sorted(candidate_accessions - observed)
        if release_mode and missing:
            raise WarehouseRuntimeError(f"required candidates missing from filing manifest: {missing}")
        metrics["filings_scanned"] = len(filings)

    for filing in filings:
        accession_number = filing["accession_number"]
        cik = filing["cik"]
        form_type = str(filing.get("form") or "").strip()
        filing_date = filing.get("filing_date")

        try:
            parser = get_parser(form_type)
        except ValueError:
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required candidate {accession_number} has no configured parser"
                )
            metrics["filings_skipped"] += 1
            continue

        try:
            attachments = source.fetch(
                "SELECT * FROM sec_filing_attachment WHERE accession_number = ?",
                [accession_number],
            )
            primary = next((r for r in attachments if r.get("is_primary")), None)
            if primary is None or not primary.get("raw_object_id"):
                if release_mode:
                    raise WarehouseRuntimeError(
                        f"required candidate {accession_number} is missing its primary artifact"
                    )
                metrics["filings_skipped"] += 1
                continue
            raw_rows = source.fetch(
                "SELECT * FROM sec_raw_object WHERE raw_object_id = ?",
                [str(primary["raw_object_id"])],
            )
            raw_object = raw_rows[0] if raw_rows else None
            if raw_object is None:
                if release_mode:
                    raise WarehouseRuntimeError(
                        f"required candidate {accession_number} primary raw object is missing"
                    )
                metrics["filings_skipped"] += 1
                continue
            content = read_bytes(str(raw_object["storage_path"])).decode(
                "utf-8", errors="replace"
            )
        except Exception as exc:
            if release_mode:
                if isinstance(exc, WarehouseRuntimeError):
                    raise
                raise WarehouseRuntimeError(
                    f"required candidate {accession_number} artifact read failed"
                ) from exc
            _emit("fundamentals_artifact_error", accession=accession_number, error=str(exc))
            metrics["filings_skipped"] += 1
            continue

        try:
            if form_type in ("8-K", "8-K/A"):
                parsed = parser(accession_number, content, form_type, cik,
                                filing_date=str(filing_date) if filing_date else None)
            else:
                parsed = parser(accession_number, content, form_type, cik)
        except Exception as exc:
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required candidate {accession_number} parse failed"
                ) from exc
            _emit("fundamentals_parse_error", accession=accession_number,
                  form=form_type, error=str(exc))
            metrics["filings_skipped"] += 1
            continue

        metrics["rows_earnings_release"] += db.merge_earnings_releases(
            parsed.get("sec_earnings_release", []), sync_run_id
        )
        metrics["rows_executive_record"] += db.merge_executive_records(
            parsed.get("sec_executive_record", []), sync_run_id
        )
        terminal_status = "not_applicable"
        terminal_reason = "no_relationship_rows"
        if parsed.get("sec_executive_record"):
            terminal_status = "applicable_loaded"
            terminal_reason = "executive_records_loaded"
        if form_type in ("8-K", "8-K/A") and (
            "5.02" in str(filing.get("items") or "") or not str(filing.get("items") or "").strip()
        ):
            from datetime import date as _date
            from edgar_warehouse.parsers.item_502 import PARSER_VERSION, parse_item_502

            result = parse_item_502(
                accession_number=accession_number,
                cik=int(cik),
                filing_date=(filing_date if isinstance(filing_date, _date)
                             else _date.fromisoformat(str(filing_date)[:10])),
                content=content,
            )
            # Release-Owner-accepted Item 5.02 unresolved exception (see
            # docs/release-readiness/required-relationship-bulk-load-completion-gate.md).
            # An unresolved parse is recorded as the bounded "unresolved_accepted"
            # terminal status instead of hard-failing the whole batch; the
            # aggregate rate is enforced fail-closed at evidence time
            # (build_required_relationship_bulk_load_evidence), where exceeding
            # the accepted threshold still yields NO_GO. Only this specific
            # parse-ambiguity path is accepted — artifact/manifest failures
            # above still raise.
            unresolved_item502 = release_mode and result.applicability == "unresolved"
            if unresolved_item502:
                metrics.setdefault("unresolved_item502", []).append(accession_number)
                _emit(
                    "item_502_unresolved_accepted",
                    accession=accession_number,
                    cik=int(cik),
                )
            event_rows = [
                {
                    "accession_number": event.accession_number,
                    "event_index": index,
                    "cik": event.cik,
                    "event_type": event.event_type,
                    "person_name": event.person_name,
                    "exec_role": event.role,
                    "previous_role": event.previous_role,
                    "compensation_amount": event.compensation_amount,
                    "effective_date": event.effective_date,
                    "parser_version": PARSER_VERSION,
                }
                for index, event in enumerate(result.events, start=1)
            ]
            metrics["rows_employment_event"] += db.merge_employment_events(
                event_rows, sync_run_id
            )
            if unresolved_item502:
                terminal_status = "unresolved_accepted"
                terminal_reason = "item_502_unresolved_ambiguous_verb"
            elif event_rows:
                terminal_status = "applicable_loaded"
                terminal_reason = "employment_events_loaded"
            else:
                terminal_status = "not_applicable"
                terminal_reason = f"item_502_{result.applicability}"
        if release_mode:
            metrics["candidate_outcomes"].append({
                "accession_number": accession_number,
                "status": terminal_status,
                "reason": terminal_reason,
            })
        metrics["filings_parsed"] += 1

    return metrics


def run_bootstrap_entity_facts(
    *,
    cik_list: list[int],
    db,                     # SilverDatabase instance
    identity: str,          # SEC User-Agent string
    sync_run_id: str,
    force: bool = False,
) -> dict[str, int]:
    """Fetch SEC companyfacts JSON for each CIK and write to silver.

    Ticket 07: companyfacts network uses the edgartools-backed gateway (not the
    parallel ``sec_client`` HTTP stack).

    Ticket 04: when ``force`` is false and silver already has financial facts for
    the CIK at the current facts parser_version, skip the companyfacts network call.

    Returns row counts per table written plus network_fetches / silver_skips.
    """
    from edgar_warehouse.infrastructure.edgartools_sec_gateway import fetch_companyfacts_json
    from edgar_warehouse.infrastructure.silver_once import has_companyfacts_at_version
    from edgar_warehouse.parsers.financials import PARSER_VERSION as FACTS_PARSER_VERSION
    from edgar_warehouse.parsers.financials import parse_entity_facts
    from edgar_warehouse.parsers.financials_derived import compute_derived_for_accession

    metrics: dict[str, int] = {
        "ciks_processed": 0,
        "ciks_failed": 0,
        "ciks_skipped": 0,
        "network_fetches": 0,
        "silver_skips": 0,
        "rows_financial_fact": 0,
        "rows_financial_derived": 0,
        "rows_accounting_flag": 0,
    }

    for cik in cik_list:
        if not force and has_companyfacts_at_version(
            db, cik=int(cik), facts_parser_version=str(FACTS_PARSER_VERSION)
        ):
            metrics["ciks_skipped"] += 1
            metrics["silver_skips"] += 1
            _emit(
                "entity_facts_silver_skip",
                cik=cik,
                facts_parser_version=str(FACTS_PARSER_VERSION),
            )
            continue

        try:
            facts_json = fetch_companyfacts_json(int(cik), identity)
            metrics["network_fetches"] += 1
        except Exception as exc:
            _emit("entity_facts_fetch_error", cik=cik, error=str(exc))
            metrics["ciks_failed"] += 1
            continue

        try:
            parsed = parse_entity_facts(cik=cik, facts_json=facts_json)
        except Exception as exc:
            _emit("entity_facts_parse_error", cik=cik, error=str(exc))
            metrics["ciks_failed"] += 1
            continue

        metrics["rows_financial_fact"] += db.merge_financial_facts(
            parsed.get("sec_financial_fact", []), sync_run_id
        )
        metrics["rows_accounting_flag"] += db.merge_accounting_flags(
            parsed.get("sec_accounting_flag", []), sync_run_id
        )

        # Compute derived metrics per (accession, fiscal_period) group
        fact_rows = parsed.get("sec_financial_fact", [])
        accession_groups: dict[tuple, list[dict]] = {}
        for row in fact_rows:
            key = (
                row["accession_number"],
                row.get("fiscal_period", "FY"),
                row.get("fiscal_year"),
                row.get("period_end"),
                row.get("form_type", ""),
            )
            accession_groups.setdefault(key, []).append(row)

        for (accn, fp, fy, pe, ft), group in accession_groups.items():
            try:
                derived = compute_derived_for_accession(
                    cik=cik, accession_number=accn, fiscal_year=fy,
                    fiscal_period=fp, period_end=pe, form_type=ft,
                    fact_rows=group,
                )
                metrics["rows_financial_derived"] += db.merge_financial_derived(
                    derived.get("sec_financial_derived", []), sync_run_id
                )
            except Exception as exc:
                _emit("derived_compute_error", cik=cik, accession=accn,
                      fiscal_period=fp, error=str(exc))

        metrics["ciks_processed"] += 1

    return metrics


def run_bootstrap_thirteenf(
    *,
    cik_list: list[int],
    source,                 # SilverDatabase | None — Branch A metadata source
    db,                      # SilverDatabase instance — write target
    sync_run_id: str,
    release_mode: bool = False,
    candidate_accessions: set[str] | None = None,
) -> dict[str, Any]:
    """Parse 13F-HR INFORMATION TABLE XML attachments for the given CIKs.

    The infotable XML lives in a filing attachment with document_type matching
    '13F-HR' or 'INFORMATION TABLE'.  The primary document is the cover XML;
    the attachment is identified by matching document descriptions.

    Filing/attachment/raw-object metadata is read from ``source`` (Branch A's
    ownership silver) — see run_bootstrap_fundamentals_per_filing for why.

    Returns row counts per table written.
    """
    from edgar_warehouse.infrastructure.object_storage import read_bytes
    from edgar_warehouse.parsers.thirteenf import parse_thirteenf

    metrics: dict[str, Any] = {
        "filings_scanned": 0,
        "filings_parsed": 0,
        "filings_skipped": 0,
        "rows_thirteenf_holding": 0,
        "rows_thirteenf_filing": 0,
        "candidate_outcomes": [],
    }

    if source is None:
        if release_mode:
            raise WarehouseRuntimeError("release 13F source is unavailable")
        _emit("fundamentals_source_unavailable", cik_count=len(cik_list))
        return metrics

    cik_placeholder = ", ".join("?" * len(cik_list))
    filings = source.fetch(
        f"""
        SELECT f.accession_number, f.cik, f.report_date, f.filing_date, f.form
        FROM sec_company_filing f
        WHERE f.cik IN ({cik_placeholder})
          AND f.form IN ('13F-HR', '13F-HR/A')
        ORDER BY f.cik, f.report_date DESC
        """,
        [int(c) for c in cik_list],
    )
    metrics["filings_scanned"] = len(filings)

    if candidate_accessions is not None:
        filings = [row for row in filings if row["accession_number"] in candidate_accessions]
        observed = {row["accession_number"] for row in filings}
        missing = sorted(candidate_accessions - observed)
        if release_mode and missing:
            raise WarehouseRuntimeError(f"required 13F candidates missing from filing manifest: {missing}")
        metrics["filings_scanned"] = len(filings)

    for filing in filings:
        accession_number = filing["accession_number"]
        cik = filing["cik"]
        period_of_report = filing.get("report_date")

        # Find the INFORMATION TABLE attachment
        try:
            attachments = source.fetch(
                "SELECT * FROM sec_filing_attachment WHERE accession_number = ?",
                [accession_number],
            )
        except Exception:
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} attachment lookup failed"
                )
            metrics["filings_skipped"] += 1
            continue

        infotable_attachment = None
        primary_attachment = next((att for att in attachments if att.get("is_primary")), None)
        for att in attachments:
            desc = str(att.get("description") or att.get("document_type") or "").upper()
            filename = str(att.get("filename") or "").upper()
            if "INFORMATION TABLE" in desc or "INFOTABLE" in filename:
                infotable_attachment = att
                break

        if infotable_attachment is None:
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} is missing its information table"
                )
            _emit("thirteenf_no_infotable", accession=accession_number, cik=cik)
            metrics["filings_skipped"] += 1
            continue

        if primary_attachment is None or not primary_attachment.get("raw_object_id"):
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} is missing its cover page"
                )
            metrics["filings_skipped"] += 1
            continue

        try:
            raw_rows = source.fetch(
                "SELECT * FROM sec_raw_object WHERE raw_object_id = ?",
                [str(infotable_attachment["raw_object_id"])],
            )
            raw_object = raw_rows[0] if raw_rows else None
            if raw_object is None:
                if release_mode:
                    raise WarehouseRuntimeError(
                        f"required 13F candidate {accession_number} information-table raw object is missing"
                    )
                metrics["filings_skipped"] += 1
                continue
            infotable_xml = read_bytes(str(raw_object["storage_path"])).decode(
                "utf-8", errors="replace"
            )
            cover_rows = source.fetch(
                "SELECT * FROM sec_raw_object WHERE raw_object_id = ?",
                [str(primary_attachment["raw_object_id"])],
            )
            cover_object = cover_rows[0] if cover_rows else None
            if cover_object is None:
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} cover raw object is missing"
                )
            cover_xml = read_bytes(str(cover_object["storage_path"])).decode(
                "utf-8", errors="replace"
            )
        except Exception as exc:
            if release_mode:
                if isinstance(exc, WarehouseRuntimeError):
                    raise
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} artifact read failed"
                ) from exc
            _emit("thirteenf_artifact_error", accession=accession_number,
                  cik=cik, error=str(exc))
            metrics["filings_skipped"] += 1
            continue

        try:
            parsed = parse_thirteenf(
                infotable_xml=infotable_xml,
                cik=int(cik),
                accession_number=accession_number,
                period_of_report=str(period_of_report) if period_of_report else "",
            )
        except Exception as exc:
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} parse failed"
                ) from exc
            _emit("thirteenf_parse_error", accession=accession_number,
                  cik=cik, error=str(exc))
            metrics["filings_skipped"] += 1
            continue

        if release_mode and not parsed.get("sec_thirteenf_holding"):
            raise WarehouseRuntimeError(
                f"required 13F candidate {accession_number} produced zero holding rows"
            )

        from edgar_warehouse.parsers.thirteenf_cover import parse_thirteenf_cover
        try:
            cover = parse_thirteenf_cover(cover_xml)
        except Exception as exc:
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required 13F candidate {accession_number} cover parse failed"
                ) from exc
            metrics["filings_skipped"] += 1
            continue

        metrics["rows_thirteenf_filing"] += db.merge_thirteenf_filings([{
            "accession_number": accession_number,
            "cik": int(cik),
            "period_of_report": str(period_of_report) if period_of_report else "",
            "filing_date": str(filing.get("filing_date"))[:10],
            "form": str(filing.get("form") or "13F-HR"),
            "amendment_type": cover["amendment_type"],
            "confidential_omission": cover["confidential_omission"],
            "parser_version": "1",
        }], sync_run_id)

        metrics["rows_thirteenf_holding"] += db.merge_thirteenf_holdings(
            parsed.get("sec_thirteenf_holding", []), sync_run_id
        )
        if release_mode:
            metrics["candidate_outcomes"].append({
                "accession_number": accession_number,
                "status": "applicable_loaded",
                "reason": "effective_holdings_loaded",
            })
        metrics["filings_parsed"] += 1

    return metrics
