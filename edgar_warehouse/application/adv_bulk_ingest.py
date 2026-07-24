"""Native parser for official IAPD Form ADV Part 1 relational bulk archives."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from edgar_warehouse.application.errors import WarehouseRuntimeError


@dataclass(frozen=True)
class AdvBulkFiling:
    accession_number: str
    filing_id: str
    adviser_name: str
    adviser_crd_number: str
    sec_file_number: str | None
    effective_date: date
    private_funds_reported: bool
    filing_action: str
    source_dataset_period: str
    source_sha256: str


@dataclass(frozen=True)
class AdvBulkFund:
    accession_number: str
    filing_id: str
    adviser_crd_number: str
    private_fund_id: str
    reference_id: str | None
    schedule_section: str
    reporting_role: str
    filing_action: str
    fund_name: str
    fund_type: str | None
    jurisdiction: str | None
    aum_amount: Decimal | None
    effective_date: date
    source_dataset_period: str
    source_sha256: str


@dataclass(frozen=True)
class AdvBulkParseResult:
    filings: tuple[AdvBulkFiling, ...]
    funds: tuple[AdvBulkFund, ...]


def _rows(bundle: zipfile.ZipFile, pattern: str) -> list[dict[str, str]]:
    names = sorted(name for name in bundle.namelist() if re.search(pattern, name, re.I))
    result: list[dict[str, str]] = []
    for name in names:
        with bundle.open(name) as source:
            payload = source.read()
        # SEC/FINRA's monthly advFilingData archives are not consistently UTF-8 --
        # older months (e.g. 2025-06, 2025-07) contain cp1252-encoded accented
        # characters (0xC0-0xD6 range) in adviser/fund names that raise
        # UnicodeDecodeError under utf-8-sig. cp1252 is ASCII-compatible, so this
        # is safe for months that happen to be pure-ASCII too.
        reader = csv.DictReader(io.StringIO(payload.decode("cp1252")))
        result.extend({str(k): str(v or "").strip() for k, v in row.items()} for row in reader)
    return result


def _submitted_date(value: str) -> date:
    candidate = value.strip()
    # Real advFilingData archives mix at least three DateSubmitted shapes across
    # months: 12-hour with seconds and AM/PM ("09/03/2025 09:31:51 AM"), date-only
    # ("6/24/2025"), and 24-hour with no seconds ("6/24/2025 7:44") -- confirmed by
    # scanning every IA_ADV_Base_A/B file across the full 2025-06..2026-06 window,
    # not just one sample.
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            pass
    raise WarehouseRuntimeError(f"invalid IAPD DateSubmitted: {value!r}")


def _amount(value: str) -> Decimal | None:
    if not value.strip():
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise WarehouseRuntimeError(f"invalid IAPD amount: {value!r}") from exc


def parse_adv_bulk_archive(
    content: bytes,
    *,
    dataset_period: str,
    source_sha256: str,
) -> AdvBulkParseResult:
    """Parse official IA/ERA base and Schedule D 7.B tables, fail closed."""
    if not dataset_period or not source_sha256:
        raise WarehouseRuntimeError("ADV bulk lineage requires dataset period and SHA-256")
    try:
        bundle = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise WarehouseRuntimeError("invalid IAPD ADV bulk ZIP archive") from exc

    with bundle:
        base_rows = _rows(bundle, r"(?:IA|ERA)_ADV_Base(?:_A)?_[^/]*\.csv$")
        section_7b1 = _rows(bundle, r"(?:IA|ERA)_Schedule_D_7B1_[^/]*\.csv$")
        section_7b2 = _rows(bundle, r"(?:IA|ERA)_Schedule_D_7B2_[^/]*\.csv$")
        filing_type_rows = _rows(bundle, r"ADV_Filing_Types_[^/]*\.csv$")
    if not base_rows:
        raise WarehouseRuntimeError("IAPD archive is missing ADV base rows")

    filing_actions: dict[str, str] = {}
    for row in filing_type_rows:
        filing_id = row.get("FilingID", "")
        actions = [
            re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            for key, value in row.items()
            if key != "FilingID" and value.strip().upper() in {"Y", "YES", "TRUE", "1"}
        ]
        if filing_id and actions:
            filing_actions[filing_id] = "+".join(actions)

    filings_by_id: dict[str, AdvBulkFiling] = {}
    for row in base_rows:
        filing_id = row.get("FilingID", "")
        crd = row.get("1E1", "")
        if not filing_id or not crd:
            raise WarehouseRuntimeError("IAPD base row is missing FilingID or adviser CRD")
        filing = AdvBulkFiling(
            accession_number=f"iapd-adv:{filing_id}",
            filing_id=filing_id,
            adviser_name=row.get("1A", "") or row.get("1B1", ""),
            adviser_crd_number=crd,
            sec_file_number=row.get("1D", "") or None,
            effective_date=_submitted_date(row.get("DateSubmitted", "")),
            private_funds_reported=row.get("7B", "").upper() == "Y",
            filing_action=filing_actions.get(filing_id, "current_compilation"),
            source_dataset_period=dataset_period,
            source_sha256=source_sha256,
        )
        prior = filings_by_id.get(filing_id)
        if prior is not None and prior != filing:
            raise WarehouseRuntimeError(f"conflicting duplicate IAPD FilingID: {filing_id}")
        filings_by_id[filing_id] = filing

    funds: dict[tuple[str, str, str], AdvBulkFund] = {}
    for section, rows in (("7B1", section_7b1), ("7B2", section_7b2)):
        for row in rows:
            filing_id = row.get("FilingID", "")
            pfid = row.get("Fund ID", "")
            filing = filings_by_id.get(filing_id)
            if filing is None or not pfid:
                raise WarehouseRuntimeError(
                    f"IAPD {section} row has unresolved FilingID/PFID: {filing_id!r}/{pfid!r}"
                )
            key = (filing_id, pfid, section)
            fund = AdvBulkFund(
                accession_number=filing.accession_number,
                filing_id=filing_id,
                adviser_crd_number=filing.adviser_crd_number,
                private_fund_id=pfid,
                reference_id=row.get("ReferenceID") or None,
                schedule_section=section,
                reporting_role="detailed_reporter" if section == "7B1" else "relying_reporter",
                filing_action=filing.filing_action,
                fund_name=row.get("Fund Name", ""),
                fund_type=row.get("Fund Type") or None,
                jurisdiction=" / ".join(
                    value for value in (row.get("State", ""), row.get("Country", "")) if value
                ) or None,
                aum_amount=_amount(row.get("Gross Asset Value", "")),
                effective_date=filing.effective_date,
                source_dataset_period=dataset_period,
                source_sha256=source_sha256,
            )
            prior = funds.get(key)
            if prior is not None and prior != fund:
                raise WarehouseRuntimeError(f"conflicting duplicate IAPD fund assertion: {key}")
            funds[key] = fund

    for filing in filings_by_id.values():
        if filing.private_funds_reported and not any(
            row.filing_id == filing.filing_id for row in funds.values()
        ):
            raise WarehouseRuntimeError(
                f"IAPD filing {filing.filing_id} reports Item 7.B=Y but has no fund rows"
            )
    return AdvBulkParseResult(
        filings=tuple(filings_by_id[key] for key in sorted(filings_by_id, key=int)),
        funds=tuple(funds[key] for key in sorted(funds, key=lambda item: (int(item[0]), item[1], item[2]))),
    )


def ingest_adv_bulk_archive(
    db,
    content: bytes,
    *,
    dataset_period: str,
    source_sha256: str,
    sync_run_id: str,
) -> dict[str, int]:
    """Parse and transactionally upsert an official ADV bulk archive into silver."""
    parsed = parse_adv_bulk_archive(
        content, dataset_period=dataset_period, source_sha256=source_sha256
    )
    filing_rows = [
        {
            "accession_number": row.accession_number,
            "cik": None,
            "form": "ADV",
            "adviser_name": row.adviser_name,
            "sec_file_number": row.sec_file_number,
            "crd_number": row.adviser_crd_number,
            "effective_date": row.effective_date,
            "filing_status": "effective",
            "filing_action": row.filing_action,
            "source_format": "iapd_bulk_csv",
            "parser_version": "iapd_bulk_v1",
        }
        for row in parsed.filings
    ]
    fund_rows = [
        {
            "accession_number": row.accession_number,
            "fund_index": index,
            "filing_id": row.filing_id,
            "adviser_crd_number": row.adviser_crd_number,
            "private_fund_id": row.private_fund_id,
            "reference_id": row.reference_id,
            "schedule_section": row.schedule_section,
            "reporting_role": row.reporting_role,
            "filing_action": row.filing_action,
            "fund_name": row.fund_name,
            "fund_type": row.fund_type,
            "jurisdiction": row.jurisdiction,
            "aum_amount": row.aum_amount,
            "effective_date": row.effective_date,
            "source_dataset_period": row.source_dataset_period,
            "source_sha256": row.source_sha256,
            "parser_version": "iapd_bulk_v1",
        }
        for index, row in enumerate(parsed.funds, start=1)
    ]
    return {
        "filings": db.merge_adv_filings(filing_rows, sync_run_id),
        "funds": db.merge_adv_private_funds(fund_rows, sync_run_id),
    }


def reconstruct_effective_adv_set(
    snapshots: list[AdvBulkParseResult] | tuple[AdvBulkParseResult, ...],
) -> AdvBulkParseResult:
    """Select the latest filing per CRD and its exact linked 7.B assertions."""
    latest: dict[str, AdvBulkFiling] = {}
    funds_by_filing: dict[str, list[AdvBulkFund]] = {}
    for snapshot in snapshots:
        for fund in snapshot.funds:
            funds_by_filing.setdefault(fund.filing_id, []).append(fund)
        for filing in snapshot.filings:
            prior = latest.get(filing.adviser_crd_number)
            key = (filing.effective_date, int(filing.filing_id))
            prior_key = (prior.effective_date, int(prior.filing_id)) if prior else None
            if prior_key is None or key > prior_key:
                latest[filing.adviser_crd_number] = filing
    effective_filings = tuple(
        latest[crd] for crd in sorted(latest, key=lambda value: (int(value), value))
    )
    effective_funds: list[AdvBulkFund] = []
    for filing in effective_filings:
        terminal = any(word in filing.filing_action for word in ("final", "withdraw"))
        if not terminal:
            effective_funds.extend(funds_by_filing.get(filing.filing_id, ()))
    return AdvBulkParseResult(
        effective_filings,
        tuple(sorted(effective_funds, key=lambda row: (
            int(row.filing_id), row.private_fund_id, row.schedule_section,
        ))),
    )
