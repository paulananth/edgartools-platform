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

Separation from bootstrap-batch (Branch A)
------------------------------------------
Branch B uses a separate ``silver/fundamentals/`` DuckDB namespace (AD-05) so
DuckDB's single-writer constraint is never violated.  The orchestrator mounts
both namespaces in the ShardedSilverReader for MDM.
"""

from __future__ import annotations

import json
import sys
import uuid
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
    source,                # ShardedSilverReader | None — read-only Branch A ownership silver
    db,                    # SilverDatabase instance (fundamentals namespace) — write target
    sync_run_id: str,
) -> dict[str, int]:
    """Process 8-K earnings + DEF 14A proxy filings from bronze for the given CIKs.

    Filing/attachment/raw-object metadata is read from ``source`` — Branch A's
    ownership silver, produced by bootstrap-next/bootstrap-batch — NOT from ``db``,
    which is Branch B's isolated fundamentals-only shard and never contains those
    tables. ``source`` is None when Branch A's silver hasn't been published yet
    (e.g. local dev before any bootstrap run); this is treated as zero available
    filings rather than an error (AD-13: Branch B is best-effort).

    Returns row counts per table written.
    """
    from edgar_warehouse.parsers import get_parser
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    metrics: dict[str, int] = {
        "filings_scanned": 0,
        "filings_parsed": 0,
        "filings_skipped": 0,
        "rows_earnings_release": 0,
        "rows_executive_record": 0,
    }

    if source is None:
        _emit("fundamentals_source_unavailable", cik_count=len(cik_list))
        return metrics

    form_list = ", ".join(f"'{f}'" for f in BRANCH_B_FILING_FORMS)
    cik_placeholder = ", ".join("?" * len(cik_list))

    filings = source.fetch(
        f"""
        SELECT f.accession_number, f.cik, f.form, f.filing_date
        FROM sec_company_filing f
        WHERE f.cik IN ({cik_placeholder})
          AND f.form IN ({form_list})
        ORDER BY f.cik, f.filing_date DESC
        """,
        [int(c) for c in cik_list],
    )
    metrics["filings_scanned"] = len(filings)

    for filing in filings:
        accession_number = filing["accession_number"]
        cik = filing["cik"]
        form_type = str(filing.get("form") or "").strip()
        filing_date = filing.get("filing_date")

        try:
            parser = get_parser(form_type)
        except ValueError:
            metrics["filings_skipped"] += 1
            continue

        try:
            attachments = source.fetch(
                "SELECT * FROM sec_filing_attachment WHERE accession_number = ?",
                [accession_number],
            )
            primary = next((r for r in attachments if r.get("is_primary")), None)
            if primary is None or not primary.get("raw_object_id"):
                metrics["filings_skipped"] += 1
                continue
            raw_rows = source.fetch(
                "SELECT * FROM sec_raw_object WHERE raw_object_id = ?",
                [str(primary["raw_object_id"])],
            )
            raw_object = raw_rows[0] if raw_rows else None
            if raw_object is None:
                metrics["filings_skipped"] += 1
                continue
            content = read_bytes(str(raw_object["storage_path"])).decode(
                "utf-8", errors="replace"
            )
        except Exception as exc:
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
        metrics["filings_parsed"] += 1

    return metrics


def run_bootstrap_entity_facts(
    *,
    cik_list: list[int],
    db,                     # SilverDatabase instance (fundamentals namespace)
    identity: str,          # SEC User-Agent string
    sync_run_id: str,
) -> dict[str, int]:
    """Fetch SEC companyfacts JSON for each CIK and write to silver.

    Uses the shared SEC client (edgar_warehouse.infrastructure.sec_client) so this
    direct SEC traffic follows the same host allowlist, rate limit, retry, and
    response-size-limit contract as the rest of the warehouse runtime.

    Returns row counts per table written.
    """
    from edgar_warehouse.infrastructure.sec_client import build_companyfacts_url, download_sec_bytes
    from edgar_warehouse.parsers.financials import parse_entity_facts
    from edgar_warehouse.parsers.financials_derived import compute_derived_for_accession

    metrics: dict[str, int] = {
        "ciks_processed": 0,
        "ciks_failed": 0,
        "rows_financial_fact": 0,
        "rows_financial_derived": 0,
        "rows_accounting_flag": 0,
    }

    for cik in cik_list:
        url = build_companyfacts_url(int(cik))
        try:
            payload = download_sec_bytes(url, identity)
            facts_json = json.loads(payload.decode("utf-8"))
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
    source,                 # ShardedSilverReader | None — read-only Branch A ownership silver
    db,                      # SilverDatabase instance (fundamentals namespace) — write target
    sync_run_id: str,
) -> dict[str, int]:
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

    metrics: dict[str, int] = {
        "filings_scanned": 0,
        "filings_parsed": 0,
        "filings_skipped": 0,
        "rows_thirteenf_holding": 0,
    }

    if source is None:
        _emit("fundamentals_source_unavailable", cik_count=len(cik_list))
        return metrics

    cik_placeholder = ", ".join("?" * len(cik_list))
    filings = source.fetch(
        f"""
        SELECT f.accession_number, f.cik, f.report_date, f.filing_date
        FROM sec_company_filing f
        WHERE f.cik IN ({cik_placeholder})
          AND f.form IN ('13F-HR', '13F-HR/A')
        ORDER BY f.cik, f.report_date DESC
        """,
        [int(c) for c in cik_list],
    )
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
            metrics["filings_skipped"] += 1
            continue

        infotable_attachment = None
        for att in attachments:
            desc = str(att.get("description") or att.get("document_type") or "").upper()
            filename = str(att.get("filename") or "").upper()
            if "INFORMATION TABLE" in desc or "INFOTABLE" in filename:
                infotable_attachment = att
                break

        if infotable_attachment is None:
            _emit("thirteenf_no_infotable", accession=accession_number, cik=cik)
            metrics["filings_skipped"] += 1
            continue

        try:
            raw_rows = source.fetch(
                "SELECT * FROM sec_raw_object WHERE raw_object_id = ?",
                [str(infotable_attachment["raw_object_id"])],
            )
            raw_object = raw_rows[0] if raw_rows else None
            if raw_object is None:
                metrics["filings_skipped"] += 1
                continue
            infotable_xml = read_bytes(str(raw_object["storage_path"])).decode(
                "utf-8", errors="replace"
            )
        except Exception as exc:
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
            _emit("thirteenf_parse_error", accession=accession_number,
                  cik=cik, error=str(exc))
            metrics["filings_skipped"] += 1
            continue

        metrics["rows_thirteenf_holding"] += db.merge_thirteenf_holdings(
            parsed.get("sec_thirteenf_holding", []), sync_run_id
        )
        metrics["filings_parsed"] += 1

    return metrics
