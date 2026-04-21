"""Loaders for SEC submissions JSON payloads."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.loaders.common import parse_date, safe_int, safe_str


def stage_company_loader(
    payload: dict[str, Any],
    cik: int,
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
) -> list[dict[str, Any]]:
    return [
        {
            "cik": cik,
            "entity_name": payload.get("name"),
            "entity_type": payload.get("entityType"),
            "sic": payload.get("sic"),
            "sic_description": payload.get("sicDescription"),
            "state_of_incorporation": payload.get("stateOfIncorporation"),
            "state_of_incorporation_desc": payload.get("stateOfIncorporationDescription"),
            "fiscal_year_end": payload.get("fiscalYearEnd"),
            "ein": payload.get("ein"),
            "description": payload.get("description"),
            "category": payload.get("category"),
            "sync_run_id": sync_run_id,
            "raw_object_id": raw_object_id,
            "load_mode": load_mode,
        }
    ]


def stage_address_loader(
    payload: dict[str, Any],
    cik: int,
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
) -> list[dict[str, Any]]:
    addresses = payload.get("addresses", {})
    rows: list[dict[str, Any]] = []
    for address_type, addr in addresses.items():
        if not isinstance(addr, dict):
            continue
        rows.append(
            {
                "cik": cik,
                "address_type": address_type,
                "street1": addr.get("street1"),
                "street2": addr.get("street2"),
                "city": addr.get("city"),
                "state_or_country": addr.get("stateOrCountry"),
                "zip_code": addr.get("zipCode"),
                "country": addr.get("stateOrCountryDescription"),
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "load_mode": load_mode,
            }
        )
    return rows


def stage_former_name_loader(
    payload: dict[str, Any],
    cik: int,
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
) -> list[dict[str, Any]]:
    former_names = payload.get("formerNames", [])
    if not isinstance(former_names, list):
        return []
    rows: list[dict[str, Any]] = []
    for idx, entry in enumerate(former_names, start=1):
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "cik": cik,
                "former_name": entry.get("name"),
                "date_changed": parse_date(entry.get("date")),
                "ordinal": idx,
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "load_mode": load_mode,
            }
        )
    return rows


def stage_manifest_loader(
    payload: dict[str, Any],
    cik: int,
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
) -> list[dict[str, Any]]:
    filings = payload.get("filings", {})
    if not isinstance(filings, dict):
        return []
    files = filings.get("files", [])
    if not isinstance(files, list):
        return []
    rows: list[dict[str, Any]] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        file_name = entry.get("name", "")
        if not file_name:
            continue
        rows.append(
            {
                "cik": cik,
                "file_name": file_name,
                "filing_count": entry.get("filingCount"),
                "filing_from": parse_date(entry.get("filingFrom")),
                "filing_to": parse_date(entry.get("filingTo")),
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "load_mode": load_mode,
            }
        )
    return rows


def stage_recent_filing_loader(
    payload: dict[str, Any],
    cik: int,
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
    recent_limit: int | None = None,
) -> list[dict[str, Any]]:
    filings = payload.get("filings", {})
    if not isinstance(filings, dict):
        return []
    recent = filings.get("recent", {})
    if not isinstance(recent, dict):
        return []

    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    acceptance_datetimes = recent.get("acceptanceDateTime", [])
    acts = recent.get("act", [])
    forms = recent.get("form", [])
    file_numbers = recent.get("fileNumber", [])
    film_numbers = recent.get("filmNumber", [])
    items = recent.get("items", [])
    sizes = recent.get("size", [])
    is_xbrl_list = recent.get("isXBRL", [])
    is_inline_xbrl_list = recent.get("isInlineXBRL", [])
    primary_documents = recent.get("primaryDocument", [])
    primary_doc_descs = recent.get("primaryDocDescription", [])

    count = len(accession_numbers)
    if recent_limit is not None:
        count = min(count, recent_limit)

    rows: list[dict[str, Any]] = []
    for i in range(count):
        rows.append(
            {
                "accession_number": safe_str(accession_numbers, i),
                "cik": cik,
                "form": safe_str(forms, i),
                "filing_date": parse_date(safe_str(filing_dates, i)),
                "report_date": parse_date(safe_str(report_dates, i)),
                "acceptance_datetime": safe_str(acceptance_datetimes, i),
                "act": safe_str(acts, i),
                "file_number": safe_str(file_numbers, i),
                "film_number": safe_str(film_numbers, i),
                "items": safe_str(items, i),
                "size": safe_int(sizes, i),
                "is_xbrl": bool(safe_int(is_xbrl_list, i)),
                "is_inline_xbrl": bool(safe_int(is_inline_xbrl_list, i)),
                "primary_document": safe_str(primary_documents, i),
                "primary_doc_desc": safe_str(primary_doc_descs, i),
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "load_mode": load_mode,
            }
        )
    return rows


def stage_pagination_filing_loader(
    payload: dict[str, Any],
    cik: int,
    sync_run_id: str,
    raw_object_id: str,
    load_mode: str,
) -> list[dict[str, Any]]:
    filings = payload.get("filings", {})
    if not isinstance(filings, dict):
        return []

    accession_numbers = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])
    report_dates = filings.get("reportDate", [])
    acceptance_datetimes = filings.get("acceptanceDateTime", [])
    acts = filings.get("act", [])
    forms = filings.get("form", [])
    file_numbers = filings.get("fileNumber", [])
    film_numbers = filings.get("filmNumber", [])
    items = filings.get("items", [])
    sizes = filings.get("size", [])
    is_xbrl_list = filings.get("isXBRL", [])
    is_inline_xbrl_list = filings.get("isInlineXBRL", [])
    primary_documents = filings.get("primaryDocument", [])
    primary_doc_descs = filings.get("primaryDocDescription", [])

    rows: list[dict[str, Any]] = []
    for i in range(len(accession_numbers)):
        rows.append(
            {
                "accession_number": safe_str(accession_numbers, i),
                "cik": cik,
                "form": safe_str(forms, i),
                "filing_date": parse_date(safe_str(filing_dates, i)),
                "report_date": parse_date(safe_str(report_dates, i)),
                "acceptance_datetime": safe_str(acceptance_datetimes, i),
                "act": safe_str(acts, i),
                "file_number": safe_str(file_numbers, i),
                "film_number": safe_str(film_numbers, i),
                "items": safe_str(items, i),
                "size": safe_int(sizes, i),
                "is_xbrl": bool(safe_int(is_xbrl_list, i)),
                "is_inline_xbrl": bool(safe_int(is_inline_xbrl_list, i)),
                "primary_document": safe_str(primary_documents, i),
                "primary_doc_desc": safe_str(primary_doc_descs, i),
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "load_mode": load_mode,
            }
        )
    return rows
