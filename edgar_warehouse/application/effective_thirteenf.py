"""Form 13F amendment-effective filing-set rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class ThirteenFFiling:
    accession_number: str
    manager_cik: int
    period_of_report: date
    filing_date: date
    form: str
    amendment_type: str | None = None
    confidential_omission: bool = False


@dataclass(frozen=True)
class EffectiveThirteenFSet:
    effective: tuple[ThirteenFFiling, ...]
    superseded: dict[str, str]


def effective_filing_set(filings: Iterable[ThirteenFFiling]) -> EffectiveThirteenFSet:
    """Apply restatement replacement and added-holdings supplement semantics."""
    groups: dict[tuple[int, date], list[ThirteenFFiling]] = {}
    for filing in filings:
        if filing.form.upper().endswith("/A") and filing.amendment_type not in {
            "restatement", "added_holdings"
        }:
            raise ValueError(f"13F amendment {filing.accession_number} requires amendment_type")
        groups.setdefault((filing.manager_cik, filing.period_of_report), []).append(filing)

    effective: list[ThirteenFFiling] = []
    superseded: dict[str, str] = {}
    for rows in groups.values():
        rows.sort(key=lambda row: (row.filing_date, row.accession_number))
        base: ThirteenFFiling | None = None
        additions: list[ThirteenFFiling] = []
        for row in rows:
            if row.form.upper().endswith("/A") and row.amendment_type == "added_holdings":
                additions.append(row)
                continue
            if base is not None:
                superseded[base.accession_number] = row.accession_number
            for addition in additions:
                superseded[addition.accession_number] = row.accession_number
            additions = []
            base = row
        if base is None:
            raise ValueError("added-holdings amendment has no base or restatement filing")
        effective.extend([base, *additions])
    effective.sort(key=lambda row: (row.manager_cik, row.period_of_report,
                                    row.filing_date, row.accession_number))
    return EffectiveThirteenFSet(tuple(effective), superseded)
