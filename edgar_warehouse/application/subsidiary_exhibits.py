"""Deterministic SEC Exhibit 21 / Form 20-F Exhibit 8 subsidiary parser."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date

from bs4 import BeautifulSoup

from edgar_warehouse.application.errors import WarehouseRuntimeError


@dataclass(frozen=True)
class SubsidiaryEvidenceRow:
    accession_number: str
    registrant_cik: int
    document_name: str
    document_type: str
    row_ordinal: int
    legal_name: str
    jurisdiction: str | None
    parent_scope: str
    immediate_parent_known: bool
    effective_date: date
    row_locator: str
    source_sha256: str


@dataclass(frozen=True)
class SubsidiaryParseResult:
    outcome: str
    reason: str | None
    rows: tuple[SubsidiaryEvidenceRow, ...]


_EXPLICIT_ZERO = re.compile(
    r"(?:has|have)\s+no\s+subsidiar(?:y|ies).{0,100}(?:required|item\s+601|listed)",
    re.I | re.S,
)


def _clean(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).replace("\xa0", " ").split())


def parse_subsidiary_exhibit(
    *,
    accession_number: str,
    registrant_cik: int,
    document_name: str,
    document_type: str,
    content: bytes | str,
    report_date: date,
    source_sha256: str,
) -> SubsidiaryParseResult:
    """Parse one authoritative subsidiary-list artifact without inferred hierarchy."""
    normalized_type = document_type.strip().upper()
    if not re.fullmatch(r"EX-(?:21|8)(?:\..+)?", normalized_type):
        raise WarehouseRuntimeError(f"unsupported subsidiary exhibit type: {document_type}")
    if not accession_number or registrant_cik <= 0 or not source_sha256 or report_date is None:
        raise WarehouseRuntimeError("subsidiary evidence is missing required lineage")
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
    plain = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    if _EXPLICIT_ZERO.search(plain):
        return SubsidiaryParseResult(
            "not_applicable",
            "explicit_no_disclosable_subsidiaries_601_b21_ii",
            (),
        )

    soup = BeautifulSoup(text, "html.parser")
    candidates: list[tuple[str, str | None, str]] = []
    for table_index, table in enumerate(soup.find_all("table"), start=1):
        table_rows = [
            [_clean(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
            for tr in table.find_all("tr")
        ]
        header_index = next(
            (
                index for index, cells in enumerate(table_rows)
                if any("subsidiar" in cell.casefold() for cell in cells)
            ),
            None,
        )
        if header_index is None:
            continue
        header = [cell.casefold() for cell in table_rows[header_index]]
        name_index = next(
            index for index, cell in enumerate(header) if "subsidiar" in cell
        )
        jurisdiction_index = next(
            (
                index for index, cell in enumerate(header)
                if any(marker in cell for marker in ("jurisdiction", "organized", "country", "state"))
            ),
            None,
        )
        for row_index, cells in enumerate(table_rows[header_index + 1:], start=header_index + 2):
            if name_index >= len(cells) or not cells[name_index]:
                continue
            jurisdiction = (
                cells[jurisdiction_index]
                if jurisdiction_index is not None and jurisdiction_index < len(cells)
                else None
            )
            candidates.append((cells[name_index], jurisdiction,
                               f"table[{table_index}]/row[{row_index}]"))

    if not candidates and "<" not in text:
        for line_number, line in enumerate(text.splitlines(), start=1):
            parts = [_clean(part) for part in re.split(r"\t|\s{2,}|\|", line) if _clean(part)]
            if not parts or "subsidiary" in parts[0].lower():
                continue
            candidates.append((parts[0], parts[1] if len(parts) > 1 else None,
                               f"line[{line_number}]"))

    rows: list[SubsidiaryEvidenceRow] = []
    seen: set[tuple[str, str]] = set()
    for legal_name, jurisdiction, locator in candidates:
        key = (_clean(legal_name).casefold(), _clean(jurisdiction or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append(SubsidiaryEvidenceRow(
            accession_number=accession_number,
            registrant_cik=registrant_cik,
            document_name=document_name,
            document_type=normalized_type,
            row_ordinal=len(rows) + 1,
            legal_name=_clean(legal_name),
            jurisdiction=_clean(jurisdiction) if jurisdiction else None,
            parent_scope="registrant_disclosed",
            immediate_parent_known=False,
            effective_date=report_date,
            row_locator=locator,
            source_sha256=source_sha256,
        ))
    if not rows:
        return SubsidiaryParseResult("unresolved", "empty_or_unsupported_exhibit", ())
    return SubsidiaryParseResult("applicable_loaded", None, tuple(rows))


def ingest_subsidiary_parse_result(
    db: object, result: SubsidiaryParseResult, *, sync_run_id: str
) -> int:
    """Persist only evidence-bearing rows; terminal zero/unresolved remains in the ledger."""
    if not result.rows:
        return 0
    return db.merge_subsidiary_evidence(
        [asdict(row) for row in result.rows], sync_run_id
    )
