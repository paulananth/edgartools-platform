"""Loader for SEC daily form index files."""

from __future__ import annotations

import hashlib
import re
from datetime import date

_DAILY_IDX_FULL_PATTERN = re.compile(
    r"^(?P<form>\S[\S ]*?)\s{2,}(?P<company>.+?)\s{2,}(?P<cik>\d{4,10})\s+(?P<date>\d{8}|\d{4}-\d{2}-\d{2})\s+(?P<filename>edgar/data/\S+)"
)
_ACCESSION_PATTERN = re.compile(r"edgar/data/\d+/([0-9-]+)-index\.")


def stage_daily_index_filing_loader(
    payload: bytes,
    business_date: date,
    sync_run_id: str,
    raw_object_id: str,
    source_url: str,
) -> list[dict[str, object]]:
    source_year = business_date.year
    source_quarter = ((business_date.month - 1) // 3) + 1
    text = payload.decode("utf-8", errors="replace")
    rows: list[dict[str, object]] = []
    ordinal = 0
    for line in text.splitlines():
        if "edgar/data/" not in line:
            continue
        match = _DAILY_IDX_FULL_PATTERN.match(line)
        if not match:
            continue
        ordinal += 1
        form_value = match.group("form").strip()
        company_value = match.group("company").strip()
        cik_value = int(match.group("cik"))
        date_str = match.group("date")
        try:
            if len(date_str) == 8:
                filing_date_value = date.fromisoformat(date_str[:4] + "-" + date_str[4:6] + "-" + date_str[6:])
            else:
                filing_date_value = date.fromisoformat(date_str)
        except ValueError:
            continue
        file_name_value = match.group("filename")
        accession_match = _ACCESSION_PATTERN.search(file_name_value)
        accession_number_value = accession_match.group(1) if accession_match else file_name_value
        filing_txt_url_value = "https://www.sec.gov/Archives/" + file_name_value
        record_hash_value = hashlib.sha256(
            f"{form_value}|{company_value}|{cik_value}|{filing_date_value}|{file_name_value}".encode()
        ).hexdigest()
        rows.append(
            {
                "sync_run_id": sync_run_id,
                "raw_object_id": raw_object_id,
                "source_name": "daily_form_index",
                "source_url": source_url,
                "business_date": business_date,
                "source_year": source_year,
                "source_quarter": source_quarter,
                "row_ordinal": ordinal,
                "form": form_value,
                "company_name": company_value,
                "cik": cik_value,
                "filing_date": filing_date_value,
                "file_name": file_name_value,
                "accession_number": accession_number_value,
                "filing_txt_url": filing_txt_url_value,
                "record_hash": record_hash_value,
            }
        )
    return rows
