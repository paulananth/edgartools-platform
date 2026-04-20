"""Minimal ADV-family parser for XML, HTML, and text filings."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

PARSER_NAME = "adv_v1"
PARSER_VERSION = "1"

_DATE_PATTERNS = (
    re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b"),
    re.compile(r"\b(20\d{2}/\d{2}/\d{2})\b"),
    re.compile(r"\b(\d{2}/\d{2}/20\d{2})\b"),
)
_SEC_FILE_NUMBER_PATTERN = re.compile(r"\b801-\d+\b")
_CRD_PATTERN = re.compile(r"\b(?:CRD|IARD)\s*(?:No\.?|Number)?[:#]?\s*([0-9]{3,})\b", re.IGNORECASE)
_EFFECTIVE_PATTERN = re.compile(
    r"\b(?:effective|filed|filing)\s+date[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4})\b",
    re.IGNORECASE,
)
_STATUS_PATTERN = re.compile(
    r"\b(status|amendment|withdrawal|registration)\b[:\s]+([A-Za-z][A-Za-z /-]{2,80})",
    re.IGNORECASE,
)


def parse_adv(
    accession_number: str,
    content: bytes | str,
    form_type: str,
    cik: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
    source_format = _detect_source_format(text)
    soup = BeautifulSoup(text, "xml" if source_format == "xml" else "html.parser")
    adviser_name = _extract_adviser_name(soup, text)
    sec_file_number = _extract_first_text(soup, ("secFileNumber", "fileNumber")) or _extract_pattern(
        _SEC_FILE_NUMBER_PATTERN,
        text,
    )
    crd_number = _extract_first_text(soup, ("crdNumber", "iardNumber")) or _extract_pattern(_CRD_PATTERN, text)
    effective_date = _extract_date(
        _extract_first_text(soup, ("effectiveDate", "dateFiled", "filingDate")) or _extract_pattern(_EFFECTIVE_PATTERN, text)
    )
    filing_status = _extract_status(soup, text)

    filing_row = {
        "accession_number": accession_number,
        "cik": cik,
        "form": form_type,
        "adviser_name": adviser_name,
        "sec_file_number": sec_file_number,
        "crd_number": crd_number,
        "effective_date": effective_date,
        "filing_status": filing_status,
        "source_format": source_format,
        "parser_version": PARSER_VERSION,
    }
    office_rows = _extract_offices(accession_number, soup, text)
    disclosure_rows = _extract_disclosures(accession_number, soup, text)
    fund_rows = _extract_private_funds(accession_number, soup, text)
    return {
        "sec_adv_filing": [filing_row],
        "sec_adv_office": office_rows,
        "sec_adv_disclosure_event": disclosure_rows,
        "sec_adv_private_fund": fund_rows,
    }


def _detect_source_format(text: str) -> str:
    lowered = text.lower()
    if "<xml" in lowered or "<edgarsubmission" in lowered or "<advfiling" in lowered:
        return "xml"
    if "<html" in lowered or "<body" in lowered or "<table" in lowered:
        return "html"
    if "%pdf" in lowered[:1024]:
        return "pdf"
    if lowered.strip():
        return "text"
    return "unknown"


def _extract_adviser_name(soup: BeautifulSoup, text: str) -> str | None:
    for tag_name in (
        "primaryBusinessName",
        "registrantName",
        "adviserName",
        "companyName",
        "name",
    ):
        value = _extract_first_text(soup, (tag_name,))
        if value:
            return value
    pattern = re.compile(
        r"\b(?:adviser|advisor|registrant|investment adviser)\s+(?:name)?[:\s]+([A-Z0-9][A-Z0-9 ,.'&/-]{3,120})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        return _clean_value(match.group(1))
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    return _clean_value(title)


def _extract_status(soup: BeautifulSoup, text: str) -> str | None:
    for tag_name in ("filingStatus", "submissionType", "amendmentType", "status"):
        value = _extract_first_text(soup, (tag_name,))
        if value:
            return value
    match = _STATUS_PATTERN.search(text)
    return _clean_value(match.group(2)) if match else None


def _extract_offices(
    accession_number: str,
    soup: BeautifulSoup,
    text: str,
) -> list[dict[str, Any]]:
    offices: list[dict[str, Any]] = []
    office_tags = _find_tags(soup, ("office", "mainOffice", "principalOffice"))
    for office_index, tag in enumerate(office_tags, start=1):
        office_name = _extract_nested_text(tag, ("officeName", "name"))
        city = _extract_nested_text(tag, ("city",))
        state = _extract_nested_text(tag, ("state", "stateOrCountry"))
        country = _extract_nested_text(tag, ("country", "countryName"))
        if not any((office_name, city, state, country)):
            continue
        headquarters_value = _extract_nested_text(tag, ("isHeadquarters", "principalOffice"))
        offices.append(
            {
                "accession_number": accession_number,
                "office_index": office_index,
                "office_name": office_name,
                "city": city,
                "state_or_country": state,
                "country": country,
                "is_headquarters": _parse_bool(headquarters_value),
                "parser_version": PARSER_VERSION,
            }
        )
    if offices:
        return offices

    address_pattern = re.compile(
        r"\b(?:principal office|main office|headquarters)\b[:\s]+([A-Za-z0-9 .,'&/-]+?),\s*([A-Za-z .'-]+),\s*([A-Z]{2}|[A-Za-z ]{3,30})",
        re.IGNORECASE,
    )
    match = address_pattern.search(text)
    if not match:
        return []
    return [
        {
            "accession_number": accession_number,
            "office_index": 1,
            "office_name": "Principal Office",
            "city": _clean_value(match.group(1)),
            "state_or_country": _clean_value(match.group(2)),
            "country": _clean_value(match.group(3)),
            "is_headquarters": True,
            "parser_version": PARSER_VERSION,
        }
    ]


def _extract_disclosures(
    accession_number: str,
    soup: BeautifulSoup,
    text: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    event_tags = _find_tags(soup, ("disclosureEvent", "disclosure"))
    for event_index, tag in enumerate(event_tags, start=1):
        category = _extract_nested_text(tag, ("category", "disclosureCategory", "caption"))
        description = _clean_value(tag.get_text(" ", strip=True))
        if not category and not description:
            continue
        rows.append(
            {
                "accession_number": accession_number,
                "event_index": event_index,
                "disclosure_category": category or "general",
                "event_date": _extract_date(_extract_nested_text(tag, ("date", "eventDate"))),
                "is_reported": True,
                "description": description,
                "parser_version": PARSER_VERSION,
            }
        )
    if rows:
        return rows[:25]

    categories = (
        "criminal",
        "civil",
        "regulatory",
        "judicial",
        "bonding",
        "financial",
    )
    lowered = text.lower()
    for event_index, category in enumerate(categories, start=1):
        if category not in lowered:
            continue
        rows.append(
            {
                "accession_number": accession_number,
                "event_index": len(rows) + 1,
                "disclosure_category": category,
                "event_date": None,
                "is_reported": True,
                "description": None,
                "parser_version": PARSER_VERSION,
            }
        )
    return rows


def _extract_private_funds(
    accession_number: str,
    soup: BeautifulSoup,
    text: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fund_tags = _find_tags(soup, ("privateFund", "fund"))
    for fund_index, tag in enumerate(fund_tags, start=1):
        fund_name = _extract_nested_text(tag, ("fundName", "name"))
        fund_type = _extract_nested_text(tag, ("fundType", "type"))
        jurisdiction = _extract_nested_text(tag, ("jurisdiction", "domicile"))
        aum_amount = _parse_amount(_extract_nested_text(tag, ("aum", "aumAmount", "grossAssetValue")))
        if not any((fund_name, fund_type, jurisdiction, aum_amount is not None)):
            continue
        rows.append(
            {
                "accession_number": accession_number,
                "fund_index": fund_index,
                "fund_name": fund_name,
                "fund_type": fund_type,
                "jurisdiction": jurisdiction,
                "aum_amount": aum_amount,
                "parser_version": PARSER_VERSION,
            }
        )
    if rows:
        return rows[:100]

    fund_pattern = re.compile(
        r"\bprivate fund\b[:\s]+([A-Za-z0-9 .,'&/-]{3,120})",
        re.IGNORECASE,
    )
    match = fund_pattern.search(text)
    if not match:
        return []
    return [
        {
            "accession_number": accession_number,
            "fund_index": 1,
            "fund_name": _clean_value(match.group(1)),
            "fund_type": None,
            "jurisdiction": None,
            "aum_amount": None,
            "parser_version": PARSER_VERSION,
        }
    ]


def _extract_first_text(soup: BeautifulSoup, tag_names: tuple[str, ...]) -> str | None:
    for tag_name in tag_names:
        tag = soup.find(tag_name)
        if tag:
            value = _clean_value(tag.get_text(" ", strip=True))
            if value:
                return value
    return None


def _extract_nested_text(tag: Any, names: tuple[str, ...]) -> str | None:
    for name in names:
        nested = tag.find(name)
        if nested:
            value = _clean_value(nested.get_text(" ", strip=True))
            if value:
                return value
    return None


def _extract_pattern(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    group = match.group(1) if match.lastindex else match.group(0)
    return _clean_value(group)


def _find_tags(soup: BeautifulSoup, names: tuple[str, ...]) -> list[Any]:
    target_names = {name.lower() for name in names}
    return [
        tag
        for tag in soup.find_all(True)
        if getattr(tag, "name", "").lower() in target_names
    ]


def _extract_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = value.strip().replace("/", "-")
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", cleaned):
        month, day_value, year = cleaned.split("-")
        cleaned = f"{year}-{month}-{day_value}"
    for pattern in _DATE_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        candidate = match.group(1).replace("/", "-")
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", candidate):
            month, day_value, year = candidate.split("-")
            candidate = f"{year}-{month}-{day_value}"
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError:
        return None


def _parse_amount(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    return None


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" :\n\t")
    return cleaned or None
