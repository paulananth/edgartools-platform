"""Helpers for building and updating reconcile findings."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.loaders import (
    stage_address_loader,
    stage_company_loader,
    stage_former_name_loader,
    stage_manifest_loader,
    stage_recent_filing_loader,
)


def build_reconcile_findings(
    *,
    db: Any,
    cik: int,
    sync_run_id: str,
    submissions_payload: dict[str, Any],
    load_mode: str = "full_reconcile",
) -> list[dict[str, Any]]:
    raw_object_id = f"reconcile:{cik}"
    now = datetime.now(UTC)
    live_company = stage_company_loader(submissions_payload, cik, sync_run_id, raw_object_id, load_mode)[0]
    live_addresses = stage_address_loader(submissions_payload, cik, sync_run_id, raw_object_id, load_mode)
    live_former_names = stage_former_name_loader(submissions_payload, cik, sync_run_id, raw_object_id, load_mode)
    live_manifest = stage_manifest_loader(submissions_payload, cik, sync_run_id, raw_object_id, load_mode)
    live_recent = stage_recent_filing_loader(submissions_payload, cik, sync_run_id, raw_object_id, load_mode)

    findings: list[dict[str, Any]] = []

    company_hash = _hash_value(_project_row(live_company, COMPANY_FIELDS))
    current_company = db.get_company(cik)
    current_company_hash = _hash_value(_project_row(current_company, COMPANY_FIELDS)) if current_company else None
    if company_hash != current_company_hash:
        findings.append(
            _finding(
                reconcile_run_id=sync_run_id,
                cik=cik,
                scope_type="cik",
                object_type="company",
                object_key=str(cik),
                drift_type="company_mismatch",
                expected_value_hash=company_hash,
                actual_value_hash=current_company_hash,
                severity="high",
                recommended_action="cik_resync",
                status="detected",
                detected_at=now,
            )
        )

    findings.extend(
        _compare_sets(
            reconcile_run_id=sync_run_id,
            cik=cik,
            object_type="address",
            scope_type="cik",
            live_rows=live_addresses,
            current_rows=db.get_addresses(cik),
            key_fields=("address_type",),
            compare_fields=ADDRESS_FIELDS,
            recommended_action="cik_resync",
            detected_at=now,
        )
    )
    findings.extend(
        _compare_sets(
            reconcile_run_id=sync_run_id,
            cik=cik,
            object_type="former_name",
            scope_type="cik",
            live_rows=live_former_names,
            current_rows=db.get_former_names(cik),
            key_fields=("ordinal",),
            compare_fields=FORMER_NAME_FIELDS,
            recommended_action="cik_resync",
            detected_at=now,
        )
    )
    findings.extend(
        _compare_sets(
            reconcile_run_id=sync_run_id,
            cik=cik,
            object_type="manifest",
            scope_type="cik",
            live_rows=live_manifest,
            current_rows=db.get_submission_files(cik),
            key_fields=("file_name",),
            compare_fields=MANIFEST_FIELDS,
            recommended_action="cik_resync",
            detected_at=now,
        )
    )
    findings.extend(
        _compare_sets(
            reconcile_run_id=sync_run_id,
            cik=cik,
            object_type="filing",
            scope_type="accession",
            live_rows=live_recent,
            current_rows=db.get_filings_for_cik(cik),
            key_fields=("accession_number",),
            compare_fields=FILING_FIELDS,
            recommended_action="accession_resync",
            detected_at=now,
        )
    )
    return findings


def mark_findings_for_resync(rows: list[dict[str, Any]], resync_run_id: str | None = None) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    updated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["status"] = "queued_for_resync"
        item["resync_run_id"] = resync_run_id
        item["resolved_at"] = now
        updated.append(item)
    return updated


def mark_findings_resolved(rows: list[dict[str, Any]], resync_run_id: str | None = None) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    updated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["status"] = "resolved"
        item["resync_run_id"] = resync_run_id
        item["resolved_at"] = now
        updated.append(item)
    return updated


def _compare_sets(
    *,
    reconcile_run_id: str,
    cik: int,
    object_type: str,
    scope_type: str,
    live_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    compare_fields: tuple[str, ...],
    recommended_action: str,
    detected_at: datetime,
) -> list[dict[str, Any]]:
    live_map = {_row_key(row, key_fields): _project_row(row, compare_fields) for row in live_rows}
    current_map = {_row_key(row, key_fields): _project_row(row, compare_fields) for row in current_rows}

    findings: list[dict[str, Any]] = []
    for object_key in sorted(set(live_map) | set(current_map)):
        live_hash = _hash_value(live_map.get(object_key))
        current_hash = _hash_value(current_map.get(object_key))
        if live_hash == current_hash:
            continue
        severity = "medium" if object_type in {"manifest", "address", "former_name"} else "high"
        findings.append(
            _finding(
                reconcile_run_id=reconcile_run_id,
                cik=cik,
                scope_type=scope_type,
                object_type=object_type,
                object_key=object_key,
                drift_type=f"{object_type}_mismatch",
                expected_value_hash=live_hash,
                actual_value_hash=current_hash,
                severity=severity,
                recommended_action=recommended_action,
                status="detected",
                detected_at=detected_at,
            )
        )
    return findings


def _finding(**kwargs: Any) -> dict[str, Any]:
    return dict(kwargs)


def _row_key(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    values = [str(_normalize_scalar(row.get(field))) for field in fields]
    return "|".join(values)


def _project_row(row: dict[str, Any] | None, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if row is None:
        return None
    return {field: _normalize_scalar(row.get(field)) for field in fields}


def _normalize_scalar(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _hash_value(value: Any) -> str | None:
    if value is None:
        return None
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


COMPANY_FIELDS = (
    "cik",
    "entity_name",
    "entity_type",
    "sic",
    "sic_description",
    "state_of_incorporation",
    "state_of_incorporation_desc",
    "fiscal_year_end",
    "ein",
    "description",
    "category",
)

ADDRESS_FIELDS = (
    "cik",
    "address_type",
    "street1",
    "street2",
    "city",
    "state_or_country",
    "zip_code",
    "country",
)

FORMER_NAME_FIELDS = (
    "cik",
    "former_name",
    "date_changed",
    "ordinal",
)

MANIFEST_FIELDS = (
    "cik",
    "file_name",
    "filing_count",
    "filing_from",
    "filing_to",
)

FILING_FIELDS = (
    "accession_number",
    "cik",
    "form",
    "filing_date",
    "report_date",
    "acceptance_datetime",
    "act",
    "file_number",
    "film_number",
    "items",
    "size",
    "is_xbrl",
    "is_inline_xbrl",
    "primary_document",
    "primary_doc_desc",
)
