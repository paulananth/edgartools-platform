"""Native parser for the SEC Firm Roster CSV (full-universe monthly snapshot).

Unlike `adv_bulk_ingest.py`'s `advFilingData` feed (a rolling delta of filing
activity, ~17% of firms per month), the Firm Roster CSV is a true
full-universe point-in-time snapshot published monthly by sec.gov. It only
carries aggregate private-fund counts per firm, not per-fund identity, so it
is ingested as a narrow independent completeness cross-check -- see
`.scratch/adv-firm-roster-crosscheck/spec.md`. Only the ~8 documented
aggregate private-fund columns are parsed; the remaining ~440 (registered) /
~163 (exempt) undocumented columns have no current consumer and no SEC data
dictionary.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from edgar_warehouse.application.errors import WarehouseRuntimeError

# Confirmed live against a real July-2026 Firm Roster CSV (both the
# registered, 448-column, and exempt, 171-column, variants) -- column names
# are identical across both variants despite differing column *counts* and
# *positions*, so DictReader-by-name works unmodified for either.
_CRD_COLUMN = "Organization CRD#"


@dataclass(frozen=True)
class AdvFirmRosterRow:
    adviser_crd_number: str
    private_funds_reported: bool
    private_fund_count_7b1: int
    any_hedge_funds: bool
    hedge_fund_count: int | None
    any_pe_funds: bool
    pe_fund_count: int | None
    total_gross_assets_private_funds: Decimal | None
    private_fund_count_7b2: int
    # Named plainly, unlike sibling parsers' source_dataset_period: for this
    # table dataset_period is a business key column (PRIMARY KEY (adviser_crd_
    # number, dataset_period)), not pure lineage metadata -- see the spec's
    # Implementation Decisions.
    dataset_period: str
    source_sha256: str


@dataclass(frozen=True)
class AdvFirmRosterParseResult:
    rows: tuple[AdvFirmRosterRow, ...]


def _rows(bundle: zipfile.ZipFile, pattern: str) -> list[dict[str, str]]:
    names = sorted(name for name in bundle.namelist() if re.search(pattern, name, re.I))
    result: list[dict[str, str]] = []
    for name in names:
        with bundle.open(name) as source:
            payload = source.read()
        # Same cp1252 rationale as adv_bulk_ingest.py's _rows(): confirmed live
        # against a real Firm Roster CSV, which fails utf-8 decoding on
        # accented adviser/office names.
        reader = csv.DictReader(io.StringIO(payload.decode("cp1252")))
        result.extend({str(k): str(v or "").strip() for k, v in row.items()} for row in reader)
    return result


def _flag(value: str) -> bool:
    return value.strip().upper() == "Y"


def _count(value: str) -> int | None:
    # Real Firm Roster count columns are right-padded with whitespace inside
    # the CSV cell (e.g. "                   3") and are empty when the
    # corresponding "Any ... Funds" flag is "N" -- confirmed live.
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return int(candidate)
    except ValueError as exc:
        raise WarehouseRuntimeError(f"invalid Firm Roster count: {value!r}") from exc


def _required_count(value: str, *, column: str) -> int:
    # Unlike the hedge/PE fund counts (legitimately blank when their "Any ..."
    # flag is "N"), the 7B(1)/7B(2) counts are documented as always populated,
    # including an explicit "0" -- confirmed live against a real July-2026
    # roster. A blank here is a genuine anomaly, not an expected case, so this
    # fails closed rather than silently collapsing to 0 and risking a false
    # negative in ticket 04's downstream count-mismatch reconciliation.
    count = _count(value)
    if count is None:
        raise WarehouseRuntimeError(f"Firm Roster row is missing required count: {column}")
    return count


def _amount(value: str) -> Decimal | None:
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return Decimal(candidate.replace(",", ""))
    except InvalidOperation as exc:
        raise WarehouseRuntimeError(f"invalid Firm Roster amount: {value!r}") from exc


def parse_firm_roster_archive(
    content: bytes,
    *,
    dataset_period: str,
    source_sha256: str,
) -> AdvFirmRosterParseResult:
    """Parse a Firm Roster CSV archive (registered or exempt variant), fail closed."""
    if not dataset_period or not source_sha256:
        raise WarehouseRuntimeError("Firm Roster lineage requires dataset period and SHA-256")
    try:
        bundle = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise WarehouseRuntimeError("invalid Firm Roster ZIP archive") from exc

    with bundle:
        raw_rows = _rows(bundle, r"FIRM_ROSTER_FOIA_DOWNLOAD[^/]*\.csv$")
    if not raw_rows:
        raise WarehouseRuntimeError("Firm Roster archive is missing roster rows")

    rows_by_crd: dict[str, AdvFirmRosterRow] = {}
    for raw in raw_rows:
        crd = raw.get(_CRD_COLUMN, "")
        if not crd:
            raise WarehouseRuntimeError("Firm Roster row is missing Organization CRD#")
        row = AdvFirmRosterRow(
            adviser_crd_number=crd,
            private_funds_reported=_flag(raw.get("7B", "")),
            private_fund_count_7b1=_required_count(
                raw.get("Count of Private Funds - 7B(1)", ""),
                column="Count of Private Funds - 7B(1)",
            ),
            any_hedge_funds=_flag(raw.get("Any Hedge Funds", "")),
            hedge_fund_count=_count(raw.get("Total number of Hedge funds", "")),
            any_pe_funds=_flag(raw.get("Any PE Funds", "")),
            pe_fund_count=_count(raw.get("Total number of PE funds", "")),
            total_gross_assets_private_funds=_amount(
                raw.get("Total Gross Assets of Private Funds", "")
            ),
            private_fund_count_7b2=_required_count(
                raw.get("Count of Private Funds - 7B(2)", ""),
                column="Count of Private Funds - 7B(2)",
            ),
            dataset_period=dataset_period,
            source_sha256=source_sha256,
        )
        prior = rows_by_crd.get(crd)
        if prior is not None and prior != row:
            raise WarehouseRuntimeError(f"conflicting duplicate Firm Roster CRD: {crd}")
        rows_by_crd[crd] = row

    return AdvFirmRosterParseResult(
        rows=tuple(rows_by_crd[key] for key in sorted(rows_by_crd, key=int))
    )


def ingest_firm_roster_archive(
    db,
    content: bytes,
    *,
    dataset_period: str,
    source_sha256: str,
    sync_run_id: str,
) -> dict[str, int]:
    """Parse and transactionally upsert a Firm Roster CSV archive into silver."""
    parsed = parse_firm_roster_archive(
        content, dataset_period=dataset_period, source_sha256=source_sha256
    )
    rows = [
        {
            "adviser_crd_number": row.adviser_crd_number,
            "dataset_period": row.dataset_period,
            "private_funds_reported": row.private_funds_reported,
            "private_fund_count_7b1": row.private_fund_count_7b1,
            "any_hedge_funds": row.any_hedge_funds,
            "hedge_fund_count": row.hedge_fund_count,
            "any_pe_funds": row.any_pe_funds,
            "pe_fund_count": row.pe_fund_count,
            "total_gross_assets_private_funds": row.total_gross_assets_private_funds,
            "private_fund_count_7b2": row.private_fund_count_7b2,
            "source_sha256": row.source_sha256,
            "parser_version": "firm_roster_v1",
        }
        for row in parsed.rows
    ]
    return {"firm_roster": db.merge_adv_firm_roster(rows, sync_run_id)}
