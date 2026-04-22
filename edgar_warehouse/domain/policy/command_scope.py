"""Pure helpers for command scope and run semantics."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError


def dedupe_ints(values: list[int]) -> list[int]:
    deduped: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def latest_filing_date(rows: list[dict[str, Any]]) -> date | None:
    values = [row.get("filing_date") for row in rows if row.get("filing_date") is not None]
    if not values:
        return None
    normalized = [value if isinstance(value, date) else date.fromisoformat(str(value)) for value in values]
    return max(normalized)


def latest_acceptance_datetime(rows: list[dict[str, Any]]) -> datetime | None:
    values = [parse_acceptance_datetime(row.get("acceptance_datetime")) for row in rows]
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def parse_acceptance_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text[: len(fmt.replace("%", ""))], fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def sync_mode_for_command(command_name: str) -> str:
    if command_name in {"bootstrap-full", "bootstrap-recent-10", "bootstrap-batch"}:
        return "bootstrap"
    if command_name in {"daily-incremental", "load-daily-form-index-for-date", "catch-up-daily-form-index"}:
        return "incremental"
    if command_name == "targeted-resync":
        return "resync"
    if command_name == "full-reconcile":
        return "reconcile"
    return "incremental"


def sync_scope_type_for_command(command_name: str, scope: dict[str, Any]) -> str:
    if command_name in {"daily-incremental", "load-daily-form-index-for-date", "catch-up-daily-form-index"}:
        return "daily_index"
    if command_name in {"bootstrap-full", "bootstrap-recent-10", "bootstrap-batch"}:
        return "submissions"
    if command_name == "seed-universe":
        return "reference"
    if command_name == "targeted-resync":
        scope_type = str(scope.get("scope_type", "")).strip()
        if scope_type == "cik":
            return "submissions"
        if scope_type == "accession":
            return "artifact_fetch"
        return "reference"
    if command_name == "full-reconcile":
        return "reconcile"
    return "submissions"


def sync_scope_key_for_command(command_name: str, scope: dict[str, Any]) -> str | None:
    if command_name == "daily-incremental":
        return f"{scope['business_date_start']}:{scope['business_date_end']}"
    if command_name == "load-daily-form-index-for-date":
        return str(scope["target_date"])
    if command_name == "catch-up-daily-form-index":
        return str(scope["end_date"])
    if command_name == "targeted-resync":
        return str(scope.get("scope_key") or "")
    if command_name == "seed-universe":
        return "company_tickers_exchange"
    cik_list = scope.get("cik_list") or []
    return ",".join(str(value) for value in cik_list) or None


def resolve_export_business_date(command_name: str, scope: dict[str, Any], now: datetime) -> str:
    if command_name == "daily-incremental":
        return str(scope["business_date_end"])
    if command_name == "load-daily-form-index-for-date":
        return str(scope["target_date"])
    if command_name == "catch-up-daily-form-index":
        return str(scope["end_date"])
    return now.date().isoformat()


def parse_date(value: Any, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise WarehouseRuntimeError(f"{field_name} must be a date string in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise WarehouseRuntimeError(f"{field_name} must be a date string in YYYY-MM-DD format") from exc


def parse_cik(value: Any) -> int:
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise WarehouseRuntimeError(f"Invalid CIK value: {value}") from exc
