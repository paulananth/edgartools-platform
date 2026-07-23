"""Fail-closed source inventory and completion-ledger contracts.

The release workflow uses these pure functions before it makes SEC requests.
They deliberately contain no network or database behavior, which makes the
frozen inventory reproducible and independently auditable.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable, Mapping


PROXY_FORMS = frozenset({"DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A"})
THIRTEENF_FORMS = frozenset({"13F-HR", "13F-HR/A"})
EIGHT_K_FORMS = frozenset({"8-K", "8-K/A"})
TERMINAL_STATUSES = frozenset(
    {"applicable_loaded", "not_applicable", "superseded", "unresolved_accepted"}
)
# Release-Owner-accepted Item 5.02 unresolved exception (2026-07-19 decision,
# docs/release-readiness/required-relationship-bulk-load-completion-gate.md,
# "Accepted Item 5.02 unresolved exception"). "unresolved_accepted" is terminal
# ONLY for Item 5.02 8-K candidates whose parse returned applicability
# "unresolved" (event verb found but no structured person/role/date). It is
# not a general escape hatch: artifact failures, missing manifests, and
# 13F/proxy candidates still fail closed, and the evidence builder rejects
# PASS when the accepted-unresolved rate exceeds the bounded threshold below
# (the parser's measured capability at the time the exception was accepted).
ITEM502_ACCEPTED_UNRESOLVED_STATUS = "unresolved_accepted"
ITEM502_ACCEPTED_UNRESOLVED_MAX_RATE = 0.095
# 13F XML information-table era floor (format correctness, not universal load start).
DEFAULT_COVERAGE_START = date(2013, 5, 20)
THIRTEENF_XML_FLOOR = DEFAULT_COVERAGE_START
# 2026-07-23 operator decision: historical 13F depth has no real value on its
# own (holdings go stale immediately; only the current snapshot + go-forward
# daily_incremental matter) -- narrowed from 1 year (PR #217, itself narrowed
# from the original 3-year lock) to a single quarter. Proxy/Item 502 lookbacks
# are unaffected.
THIRTEENF_AGENT_LOOKBACK_MONTHS = 3
PROXY_AGENT_LOOKBACK_YEARS = 5
ITEM_502_AGENT_LOOKBACK_YEARS = 2


class InventoryError(ValueError):
    pass


class LedgerError(ValueError):
    pass


def select_required_accessions(
    manifest: object,
    *,
    ciks: set[int] | None = None,
) -> set[str]:
    """Return the bounded artifact-required accessions for one CIK batch."""
    rows = manifest.get("candidates") if isinstance(manifest, Mapping) else manifest
    if not isinstance(rows, list) or not rows:
        raise InventoryError("candidate manifest must contain a non-empty candidates list")
    selected: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise InventoryError("candidate manifest rows must be objects")
        accession = str(row.get("accession_number") or "").strip()
        if not accession:
            raise InventoryError("candidate manifest row is missing accession_number")
        if accession in seen:
            raise InventoryError(f"duplicate candidate accession: {accession}")
        seen.add(accession)
        cik = int(row.get("cik") or 0)
        if ciks is not None and cik not in ciks:
            continue
        if bool(row.get("artifact_required", True)):
            selected.add(accession)
    return selected


def summarize_release_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    """Secret-safe inventory summary for operator preflight (no candidate dump)."""
    if not isinstance(manifest, Mapping):
        raise InventoryError("candidate manifest must be an object")
    watermark = _as_date(manifest.get("watermark"))
    coverage_start = _as_date(manifest.get("coverage_start"))
    fingerprint = str(manifest.get("fingerprint") or "").strip()
    rows = manifest.get("candidates")
    if not isinstance(rows, list):
        raise InventoryError("candidate manifest must contain candidates list")
    by_form: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    required = 0
    ciks: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        form = str(row.get("form") or "").strip().upper() or "?"
        reason = str(row.get("candidate_reason") or "").strip() or "?"
        by_form[form] = by_form.get(form, 0) + 1
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if bool(row.get("artifact_required", True)):
            required += 1
        cik = int(row.get("cik") or 0)
        if cik > 0:
            ciks.add(cik)
    batches = manifest.get("cik_batches")
    batch_count = len(batches) if isinstance(batches, list) else None
    return {
        "schema_version": int(manifest.get("schema_version") or 0) or None,
        "watermark": watermark.isoformat() if watermark else None,
        "coverage_start": coverage_start.isoformat() if coverage_start else None,
        "fingerprint": fingerprint or None,
        "has_coverage_by_document_type": isinstance(
            manifest.get("coverage_by_document_type"), Mapping
        )
        and bool(manifest.get("coverage_by_document_type")),
        "candidate_count": len(rows),
        "artifact_required_count": required,
        "candidate_cik_count": len(ciks),
        "batch_count": batch_count,
        "counts_by_form": dict(sorted(by_form.items())),
        "counts_by_reason": dict(sorted(by_reason.items())),
    }


def preflight_strict_release_manifest(manifest: object) -> dict[str, object]:
    """Validate agent-window freeze and return operator preflight report.

    Raises ``InventoryError`` when the freeze is not eligible for Ticket 20
    ``release_mode`` (missing type map, wrong windows, out-of-band candidates).
    """
    if not isinstance(manifest, Mapping):
        raise InventoryError("candidate manifest must be an object")
    windows = validate_strict_release_manifest(manifest)
    summary = summarize_release_manifest(manifest)
    summary["coverage_by_document_type"] = windows
    summary["strict_release_eligible"] = True
    summary["disposition"] = "READY_FOR_STRICT_LOAD"
    return summary


def validate_strict_release_manifest(manifest: Mapping[str, object]) -> dict[str, dict[str, str]]:
    """Fail closed for Ticket 20 ``release_mode`` loads.

    Requires ``coverage_by_document_type`` (post-rebuild freezes only). A legacy
    single-``coverage_start`` freeze without the type map is **not** agent GO —
    operators must rebuild under agent lookbacks.
    """
    raw_windows = manifest.get("coverage_by_document_type")
    if not isinstance(raw_windows, Mapping) or not raw_windows:
        raise InventoryError(
            "release candidate manifest is missing coverage_by_document_type; "
            "rebuild the freeze under locked agent lookbacks "
            "(post-filter of a 2013-era full-window freeze is not GO)"
        )
    windows = _normalize_coverage_by_document_type(raw_windows)
    watermark = _as_date(manifest.get("watermark"))
    if watermark is None:
        raise InventoryError("candidate manifest is missing watermark")
    expected = agent_coverage_by_document_type(watermark)
    for key in ("thirteenf", "proxy", "item_502_8k"):
        if windows[key]["start"] != expected[key]["start"] or windows[key]["end"] != expected[key]["end"]:
            raise InventoryError(
                f"coverage_by_document_type.{key} "
                f"({windows[key]['start']}..{windows[key]['end']}) does not match "
                f"locked agent window ({expected[key]['start']}..{expected[key]['end']}) "
                f"for watermark {watermark.isoformat()}; rebuild the freeze"
            )
    if windows["proxy"].get("baseline") != "latest_in_band_only":
        raise InventoryError(
            "coverage_by_document_type.proxy.baseline must be latest_in_band_only"
        )
    # Membership audit: no candidate may sit outside its form family's window.
    rows = manifest.get("candidates")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            form = str(row.get("form") or "").strip().upper()
            filing_date = _as_date(row.get("filing_date"))
            if filing_date is None or form not in PROXY_FORMS | EIGHT_K_FORMS | THIRTEENF_FORMS:
                continue
            if not filing_in_document_type_window(
                form, filing_date, windows, watermark=watermark
            ):
                accession = str(row.get("accession_number") or "")
                raise InventoryError(
                    f"release candidate {accession} ({form} {filing_date.isoformat()}) "
                    f"is outside locked agent windows; rebuild the freeze"
                )
            reason = str(row.get("candidate_reason") or "")
            if reason == "unrelated_8k_metadata":
                raise InventoryError(
                    f"release candidate {accession} is an unrelated 8-K; "
                    "unrelated 8-Ks must not appear in agent freezes"
                )
    return windows


def candidate_inventory_from_manifest(
    manifest: object,
    *,
    ciks: set[int] | None = None,
    require_strict_agent_windows: bool = False,
) -> CandidateInventory:
    """Restore a frozen inventory (or one CIK batch) from its release manifest.

    When ``require_strict_agent_windows`` is true (Ticket 20 release_mode), the
    manifest must carry locked ``coverage_by_document_type`` matching agent
    lookbacks for its watermark. Legacy freezes without that map are rejected.
    """
    if not isinstance(manifest, Mapping):
        raise InventoryError("candidate manifest must be an object")
    rows = manifest.get("candidates")
    if not isinstance(rows, list) or not rows:
        raise InventoryError("candidate manifest must contain a non-empty candidates list")
    coverage_start = _as_date(manifest.get("coverage_start"))
    watermark = _as_date(manifest.get("watermark"))
    inventory_fingerprint = str(manifest.get("fingerprint") or "").strip()
    if coverage_start is None or watermark is None or not inventory_fingerprint:
        raise InventoryError("candidate manifest is missing inventory identity")
    if require_strict_agent_windows:
        windows = validate_strict_release_manifest(manifest)
    else:
        raw_windows = manifest.get("coverage_by_document_type")
        if isinstance(raw_windows, Mapping) and raw_windows:
            windows = _normalize_coverage_by_document_type(raw_windows)
        else:
            # Legacy freezes (non-strict read): uniform windows from coverage_start.
            windows = uniform_coverage_by_document_type(coverage_start, watermark)
    candidates: list[RelationshipSourceCandidate] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise InventoryError("candidate manifest rows must be objects")
        cik = int(row.get("cik") or 0)
        if ciks is not None and cik not in ciks:
            continue
        filing_date = _as_date(row.get("filing_date"))
        if filing_date is None:
            raise InventoryError("candidate manifest row is missing filing_date")
        fingerprint = str(row.get("fingerprint") or "").strip()
        if not fingerprint:
            raise InventoryError("candidate manifest row is missing fingerprint")
        candidates.append(RelationshipSourceCandidate(
            accession_number=str(row.get("accession_number") or ""),
            cik=cik,
            form=str(row.get("form") or ""),
            filing_date=filing_date,
            report_date=_as_date(row.get("report_date")),
            relationship_type=str(row.get("relationship_type") or ""),
            candidate_reason=str(row.get("candidate_reason") or ""),
            artifact_required=bool(row.get("artifact_required", True)),
            source_index_identity=str(row.get("source_index_identity") or ""),
            source_manifest_fingerprint=str(row.get("source_manifest_fingerprint") or ""),
            fingerprint=fingerprint,
        ))
    if not candidates:
        raise InventoryError("candidate manifest has no candidates for this batch")
    quarters_raw = manifest.get("quarter_index_fingerprints") or manifest.get("quarters") or []
    quarters = tuple((str(row[0]), str(row[1])) for row in quarters_raw)
    return CandidateInventory(
        coverage_start,
        watermark,
        tuple(candidates),
        quarters,
        inventory_fingerprint,
        windows,
    )


def _sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def years_before(value: date, years: int) -> date:
    """Calendar lookback preserving month/day when possible (Feb 29 → Feb 28)."""
    if years < 0:
        raise InventoryError("lookback years must be non-negative")
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def months_before(value: date, months: int) -> date:
    """Calendar lookback by whole months, clamping the day into the target month."""
    if months < 0:
        raise InventoryError("lookback months must be non-negative")
    total_months = value.year * 12 + (value.month - 1) - months
    target_year, target_month = divmod(total_months, 12)
    target_month += 1
    last_day = calendar.monthrange(target_year, target_month)[1]
    return value.replace(year=target_year, month=target_month, day=min(value.day, last_day))


def agent_coverage_by_document_type(watermark: date) -> dict[str, dict[str, str]]:
    """Locked Ticket 20 agent windows (product truth for freeze membership)."""
    end = watermark.isoformat()
    thirteenf_start = max(
        months_before(watermark, THIRTEENF_AGENT_LOOKBACK_MONTHS),
        THIRTEENF_XML_FLOOR,
    )
    proxy_start = years_before(watermark, PROXY_AGENT_LOOKBACK_YEARS)
    item_502_start = years_before(watermark, ITEM_502_AGENT_LOOKBACK_YEARS)
    return {
        "thirteenf": {"start": thirteenf_start.isoformat(), "end": end},
        "proxy": {
            "start": proxy_start.isoformat(),
            "end": end,
            "baseline": "latest_in_band_only",
        },
        "item_502_8k": {"start": item_502_start.isoformat(), "end": end},
    }


def uniform_coverage_by_document_type(
    coverage_start: date, watermark: date
) -> dict[str, dict[str, str]]:
    """Legacy/test path: one start date applied to every Ticket 20 form family."""
    end = watermark.isoformat()
    start = coverage_start.isoformat()
    return {
        "thirteenf": {"start": start, "end": end},
        "proxy": {"start": start, "end": end, "baseline": "latest_in_band_only"},
        "item_502_8k": {"start": start, "end": end},
    }


def index_floor_coverage_start(
    coverage_by_document_type: Mapping[str, Mapping[str, object]],
) -> date:
    """Top-level inventory floor = min of per-type absolute starts (index identity)."""
    starts: list[date] = []
    for key in ("thirteenf", "proxy", "item_502_8k"):
        block = coverage_by_document_type.get(key)
        if not isinstance(block, Mapping):
            raise InventoryError(f"coverage_by_document_type missing {key}")
        start = _as_date(block.get("start"))
        if start is None:
            raise InventoryError(f"coverage_by_document_type.{key}.start is required")
        starts.append(start)
    return min(starts)


def _normalize_coverage_by_document_type(
    value: Mapping[str, object],
) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for key in ("thirteenf", "proxy", "item_502_8k"):
        block = value.get(key)
        if not isinstance(block, Mapping):
            raise InventoryError(f"coverage_by_document_type missing {key}")
        start = _as_date(block.get("start"))
        end = _as_date(block.get("end"))
        if start is None or end is None:
            raise InventoryError(f"coverage_by_document_type.{key} needs start and end")
        if start > end:
            raise InventoryError(f"coverage_by_document_type.{key} start is after end")
        entry: dict[str, str] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if key == "proxy":
            entry["baseline"] = str(block.get("baseline") or "latest_in_band_only")
        normalized[key] = entry
    return normalized


def resolve_coverage_policy(
    watermark: date,
    *,
    coverage_start: date | None = None,
    coverage_by_document_type: Mapping[str, object] | None = None,
) -> tuple[date, dict[str, dict[str, str]]]:
    """Return (index floor, per-type windows).

    - Explicit ``coverage_by_document_type`` is product truth; floor defaults to min start.
    - Explicit ``coverage_start`` without type map → uniform windows (tests / overrides).
    - Neither → locked agent lookbacks from watermark.
    """
    if coverage_by_document_type is not None:
        windows = _normalize_coverage_by_document_type(coverage_by_document_type)
        floor = coverage_start if coverage_start is not None else index_floor_coverage_start(windows)
        return floor, windows
    if coverage_start is not None:
        windows = uniform_coverage_by_document_type(coverage_start, watermark)
        return coverage_start, windows
    windows = agent_coverage_by_document_type(watermark)
    return index_floor_coverage_start(windows), windows


def _form_family_key(form: str) -> str | None:
    if form in THIRTEENF_FORMS:
        return "thirteenf"
    if form in PROXY_FORMS:
        return "proxy"
    if form in EIGHT_K_FORMS:
        return "item_502_8k"
    return None


def filing_in_document_type_window(
    form: str,
    filing_date: date,
    coverage_by_document_type: Mapping[str, Mapping[str, object]],
    *,
    watermark: date,
) -> bool:
    """True when filing_date is inside the agent window for this form family."""
    family = _form_family_key(form)
    if family is None:
        return False
    block = coverage_by_document_type.get(family)
    if not isinstance(block, Mapping):
        return False
    start = _as_date(block.get("start"))
    end = _as_date(block.get("end")) or watermark
    if start is None:
        return False
    return start <= filing_date <= end


def _quarter_key(value: date) -> str:
    return f"{value.year}Q{((value.month - 1) // 3) + 1}"


def expected_quarters(start: date, end: date) -> tuple[str, ...]:
    if start > end:
        raise InventoryError("coverage_start is after watermark")
    cursor = date(start.year, ((start.month - 1) // 3) * 3 + 1, 1)
    result: list[str] = []
    while cursor <= end:
        result.append(_quarter_key(cursor))
        month = cursor.month + 3
        cursor = date(cursor.year + (month > 12), ((month - 1) % 12) + 1, 1)
    return tuple(result)


def _has_item_502(items: object) -> bool:
    return bool(re.search(r"(?:^|[^0-9])5\s*\.\s*02(?:[^0-9]|$)", str(items or ""), re.I))


@dataclass(frozen=True)
class RelationshipSourceCandidate:
    accession_number: str
    cik: int
    form: str
    filing_date: date
    report_date: date | None
    relationship_type: str
    candidate_reason: str
    artifact_required: bool
    source_index_identity: str
    source_manifest_fingerprint: str
    fingerprint: str


@dataclass(frozen=True)
class CandidateInventory:
    coverage_start: date
    watermark: date
    candidates: tuple[RelationshipSourceCandidate, ...]
    quarter_index_fingerprints: tuple[tuple[str, str], ...]
    fingerprint: str
    coverage_by_document_type: dict[str, dict[str, str]]


def build_candidate_inventory(
    filings: Iterable[Mapping[str, object]],
    *,
    watermark: date,
    source_manifest_fingerprints: Mapping[str, str],
    quarter_index_fingerprints: Mapping[str, str],
    coverage_start: date | None = None,
    coverage_by_document_type: Mapping[str, object] | None = None,
) -> CandidateInventory:
    """Build a deterministic accession inventory and fail on source gaps.

    Membership is form-family specific: a filing is a candidate only when its
    filing_date falls in that family's window (Ticket 20 agent lookbacks by
    default). Unrelated 8-Ks (items prove no 5.02) never enter the freeze.
    """
    floor, windows = resolve_coverage_policy(
        watermark,
        coverage_start=coverage_start,
        coverage_by_document_type=coverage_by_document_type,
    )
    expected = expected_quarters(floor, watermark)
    missing_quarters = sorted(set(expected) - set(quarter_index_fingerprints))
    if missing_quarters:
        raise InventoryError(f"missing SEC quarter index fingerprints: {', '.join(missing_quarters)}")

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for filing in filings:
        accession = str(filing.get("accession_number") or "").strip()
        if not accession:
            raise InventoryError("filing is missing accession_number")
        if accession in seen:
            raise InventoryError(f"duplicate accession identity: {accession}")
        seen.add(accession)
        form = str(filing.get("form") or "").strip().upper()
        filing_date = _as_date(filing.get("filing_date"))
        if filing_date is None:
            continue
        if form not in PROXY_FORMS | EIGHT_K_FORMS | THIRTEENF_FORMS:
            continue
        if not filing_in_document_type_window(
            form, filing_date, windows, watermark=watermark
        ):
            continue
        normalized.append({**filing, "accession_number": accession, "form": form,
                           "filing_date": filing_date})

    candidates: list[RelationshipSourceCandidate] = []
    for filing in sorted(normalized, key=lambda row: str(row["accession_number"])):
        accession = str(filing["accession_number"])
        cik = int(filing.get("cik") or 0)
        if cik <= 0:
            raise InventoryError(f"candidate {accession} has invalid CIK")
        manifest_key = f"company:{cik}"
        manifest_fingerprint = source_manifest_fingerprints.get(manifest_key)
        if not manifest_fingerprint:
            raise InventoryError(f"missing submission manifest fingerprint: {manifest_key}")
        form = str(filing["form"])
        filing_date = filing["filing_date"]
        if not isinstance(filing_date, date):
            raise InventoryError(f"candidate {accession} has invalid filing_date")
        report_date = _as_date(filing.get("report_date"))
        if form in PROXY_FORMS:
            relationship_type, reason, artifact_required = "EMPLOYED_BY", "proxy_filing", True
        elif form in THIRTEENF_FORMS:
            relationship_type, reason, artifact_required = "INSTITUTIONAL_HOLDS", "thirteenf_filing", True
        elif _has_item_502(filing.get("items")):
            relationship_type, reason, artifact_required = "EMPLOYED_BY", "item_5_02_metadata", True
        elif not str(filing.get("items") or "").strip():
            relationship_type, reason, artifact_required = "EMPLOYED_BY", "ambiguous_8k_metadata", True
        else:
            # Items prove no Item 5.02 — out of Ticket 20 bulk-load membership.
            continue
        source_index_identity = _quarter_key(filing_date)
        if source_index_identity not in quarter_index_fingerprints:
            raise InventoryError(
                f"missing SEC quarter index fingerprint for {source_index_identity}"
            )
        raw = {
            "accession_number": accession,
            "cik": cik,
            "form": form,
            "filing_date": filing_date.isoformat(),
            "report_date": report_date.isoformat() if report_date else None,
            "relationship_type": relationship_type,
            "candidate_reason": reason,
            "artifact_required": artifact_required,
            "source_index_identity": source_index_identity,
            "source_manifest_fingerprint": manifest_fingerprint,
            "source_index_fingerprint": quarter_index_fingerprints[source_index_identity],
        }
        candidates.append(RelationshipSourceCandidate(
            accession_number=accession,
            cik=cik,
            form=form,
            filing_date=filing_date,
            report_date=report_date,
            relationship_type=relationship_type,
            candidate_reason=reason,
            artifact_required=artifact_required,
            source_index_identity=source_index_identity,
            source_manifest_fingerprint=manifest_fingerprint,
            fingerprint=_sha256(raw),
        ))

    quarters = tuple((key, quarter_index_fingerprints[key]) for key in expected)
    inventory_payload = {
        "coverage_start": floor.isoformat(),
        "coverage_by_document_type": windows,
        "watermark": watermark.isoformat(),
        "quarters": quarters,
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    return CandidateInventory(
        floor,
        watermark,
        tuple(candidates),
        quarters,
        _sha256(inventory_payload),
        windows,
    )


def build_frozen_candidate_manifest(
    quarter_indexes: Mapping[str, Iterable[Mapping[str, object]]],
    *,
    silver_filings: Iterable[Mapping[str, object]],
    release_ciks: set[int],
    source_manifest_fingerprints: Mapping[int, str] | None = None,
    watermark: date,
    coverage_start: date | None = None,
    coverage_by_document_type: Mapping[str, object] | None = None,
    batch_size: int = 100,
) -> dict[str, object]:
    """Freeze complete SEC quarter indexes into the release candidate manifest.

    Quarterly indexes are the authority for 13F coverage and for proving that
    every proxy/8-K accession in the bounded company universe was considered.
    Silver contributes submissions-only metadata such as 8-K item numbers.

    Default coverage is locked agent lookbacks (13F 3y/XML floor, proxy 5y,
    Item 5.02 8-K 2y). Top-level ``coverage_start`` is the index floor only.
    """
    if batch_size <= 0:
        raise InventoryError("batch_size must be positive")
    floor, windows = resolve_coverage_policy(
        watermark,
        coverage_start=coverage_start,
        coverage_by_document_type=coverage_by_document_type,
    )
    expected = expected_quarters(floor, watermark)
    missing = sorted(set(expected) - set(quarter_indexes))
    if missing:
        raise InventoryError(f"missing SEC quarter indexes: {', '.join(missing)}")

    silver_by_accession = {
        str(row.get("accession_number") or "").strip(): dict(row)
        for row in silver_filings
        if str(row.get("accession_number") or "").strip()
    }
    quarter_fingerprints: dict[str, str] = {}
    selected: list[dict[str, object]] = []
    source_rows_by_cik: dict[int, list[dict[str, object]]] = {}

    for quarter in expected:
        normalized_rows: list[dict[str, object]] = []
        for raw_row in quarter_indexes[quarter]:
            accession = str(raw_row.get("accession_number") or "").strip()
            filing_date = _as_date(raw_row.get("filing_date"))
            if not accession or filing_date is None:
                raise InventoryError(f"{quarter} index row is missing accession identity")
            # Index fingerprint includes all rows in the floor→W band; form
            # membership is applied below via per-type agent windows.
            if not floor <= filing_date <= watermark:
                continue
            normalized = {
                "accession_number": accession,
                "cik": int(raw_row.get("cik") or 0),
                "form": str(raw_row.get("form") or "").strip().upper(),
                "filing_date": filing_date.isoformat(),
            }
            normalized_rows.append(normalized)

        normalized_rows.sort(key=lambda row: str(row["accession_number"]))
        quarter_fingerprints[quarter] = _sha256(normalized_rows)
        for row in normalized_rows:
            form = str(row["form"])
            cik = int(row["cik"])
            filing_date = _as_date(row["filing_date"])
            if filing_date is None:
                raise InventoryError(
                    f"quarter index row missing filing_date for {row.get('accession_number')}"
                )
            if not filing_in_document_type_window(
                form, filing_date, windows, watermark=watermark
            ):
                continue
            in_company_scope = cik in release_ciks and form in PROXY_FORMS | EIGHT_K_FORMS
            if form not in THIRTEENF_FORMS and not in_company_scope:
                continue
            enriched = {**row, **silver_by_accession.get(str(row["accession_number"]), {})}
            enriched.update({
                "accession_number": row["accession_number"],
                "cik": cik,
                "form": form,
                "filing_date": row["filing_date"],
            })
            selected.append(enriched)
            source_rows_by_cik.setdefault(cik, []).append(row)

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in selected:
        grouped.setdefault(str(row["accession_number"]), []).append(row)
    canonical_rows: list[dict[str, object]] = []
    multi_registrant_accessions: list[dict[str, object]] = []
    for accession, rows in sorted(grouped.items()):
        identities = {(str(row["form"]), str(row["filing_date"])) for row in rows}
        if len(identities) != 1:
            raise InventoryError(f"conflicting SEC index identities for accession {accession}")
        indexed_ciks = sorted({int(row["cik"]) for row in rows})
        silver_cik = int(silver_by_accession.get(accession, {}).get("cik") or 0)
        canonical_cik = silver_cik if silver_cik in indexed_ciks else indexed_ciks[0]
        canonical_rows.append(next(row for row in rows if int(row["cik"]) == canonical_cik))
        if len(indexed_ciks) > 1:
            multi_registrant_accessions.append({
                "accession_number": accession,
                "canonical_cik": canonical_cik,
                "indexed_ciks": indexed_ciks,
            })

    computed_source_fingerprints = {
        f"company:{cik}": _sha256(sorted(rows, key=lambda row: str(row["accession_number"])))
        for cik, rows in source_rows_by_cik.items()
    }
    source_fingerprints = {
        key: str((source_manifest_fingerprints or {}).get(int(key.split(":", 1)[1])) or value)
        for key, value in computed_source_fingerprints.items()
    }
    inventory = build_candidate_inventory(
        canonical_rows,
        coverage_start=floor,
        coverage_by_document_type=windows,
        watermark=watermark,
        source_manifest_fingerprints=source_fingerprints,
        quarter_index_fingerprints=quarter_fingerprints,
    )
    candidate_rows = [
        {
            **asdict(candidate),
            "filing_date": candidate.filing_date.isoformat(),
            "report_date": candidate.report_date.isoformat() if candidate.report_date else None,
        }
        for candidate in inventory.candidates
    ]
    candidate_ciks = sorted({candidate.cik for candidate in inventory.candidates})
    index_only_candidates = [
        candidate
        for candidate in inventory.candidates
        if candidate.accession_number not in silver_by_accession
    ]
    cik_batches = [
        {"cik_list": ",".join(str(cik) for cik in candidate_ciks[offset:offset + batch_size])}
        for offset in range(0, len(candidate_ciks), batch_size)
    ]
    return {
        "schema_version": 1,
        "coverage_start": inventory.coverage_start.isoformat(),
        "coverage_by_document_type": inventory.coverage_by_document_type,
        "watermark": inventory.watermark.isoformat(),
        "fingerprint": inventory.fingerprint,
        "quarter_index_fingerprints": [list(row) for row in inventory.quarter_index_fingerprints],
        "candidate_count": len(candidate_rows),
        "candidate_cik_count": len(candidate_ciks),
        "index_only_candidate_count": len(index_only_candidates),
        "index_only_required_count": sum(
            candidate.artifact_required for candidate in index_only_candidates
        ),
        "candidates": candidate_rows,
        "cik_batches": cik_batches,
        "multi_registrant_accessions": multi_registrant_accessions,
    }


@dataclass(frozen=True)
class CandidateOutcome:
    generation_id: str
    accession_number: str
    candidate_fingerprint: str
    status: str
    evidence_fingerprint: str


@dataclass(frozen=True)
class LedgerReconciliation:
    generation_id: str
    inventory_fingerprint: str
    terminal_counts: dict[str, int]
    fingerprint: str


def format_ticket20_pass_claim(
    *,
    watermark: date,
    fingerprint: str,
    coverage_by_document_type: Mapping[str, Mapping[str, object]],
    accepted_unresolved_count: int = 0,
    item502_candidate_count: int | None = None,
) -> str:
    """Approved Ticket 20 PASS phrase (binds fingerprint, watermark, windows,
    and the accepted Item 5.02 unresolved count — never claims Item 5.02
    completeness without naming that count, per the revised gate doctrine)."""
    windows = _normalize_coverage_by_document_type(coverage_by_document_type)
    thirteenf = windows["thirteenf"]
    proxy = windows["proxy"]
    item_502 = windows["item_502_8k"]
    accepted = int(accepted_unresolved_count)
    if accepted > 0:
        if not item502_candidate_count or int(item502_candidate_count) <= 0:
            raise InventoryError(
                "item502_candidate_count is required to state the accepted "
                "unresolved rate in the PASS claim"
            )
        rate_pct = 100.0 * accepted / int(item502_candidate_count)
        item502_clause = (
            f"  Item 5.02 / ambiguous 8-K [{item_502['start']}, {item_502['end']}] "
            f"complete EXCEPT for {accepted} enumerated unresolved candidates "
            f"({rate_pct:.2f}% of the Item 5.02 8-K candidate inventory), accepted "
            "by the Release Owner as a known, bounded gap — not claimed complete."
        )
    else:
        item502_clause = (
            f"  Item 5.02 / ambiguous 8-K [{item_502['start']}, {item_502['end']}]."
        )
    return (
        "Required relationship sources for EMPLOYED_BY and INSTITUTIONAL_HOLDS are "
        f"bulk-load complete for agent windows at watermark {watermark.isoformat()} "
        f"(fingerprint {fingerprint}):\n"
        f"  13F [{thirteenf['start']}, {thirteenf['end']}];\n"
        f"  proxy [{proxy['start']}, {proxy['end']}] (latest-in-band baseline only);\n"
        f"{item502_clause}"
    )


REQUIRED_GATE_ATTESTATION_ROLES = (
    "warehouse",
    "mdm",
    "graph",
    "release_data_operator",
    "release_owner",
)


def normalize_s3_object_key(value: str, *, field_name: str = "key") -> str:
    """Accept an s3:// URI or bare key; return bucket-relative object key."""
    raw = str(value or "").strip()
    if not raw:
        raise InventoryError(f"{field_name} is empty")
    if raw.startswith("s3://"):
        without_scheme = raw[len("s3://") :]
        slash = without_scheme.find("/")
        if slash < 0 or slash == len(without_scheme) - 1:
            raise InventoryError(f"{field_name} is not a valid s3 object URI: {value!r}")
        return without_scheme[slash + 1 :]
    return raw.lstrip("/")


def build_ticket20_strict_execution_input(
    *,
    candidate_manifest_key: str,
    candidate_batches_key: str,
    attestations: Mapping[str, str] | object,
    batch_size: int = 100,
    watermark: str | date | None = None,
    fingerprint: str | None = None,
    ticket: int = 20,
) -> dict[str, object]:
    """Build Step Functions input for bronze_seed_silver_gold release_mode.

    Keys are bucket-relative (as required by the state machine ItemReader /
    StrictManifestCheck). Attestations must include all five named roles.
    """
    if int(batch_size) <= 0:
        raise InventoryError("batch_size must be positive")
    bound = normalize_gate_attestations(attestations)
    manifest_key = normalize_s3_object_key(
        candidate_manifest_key, field_name="candidate_manifest_key"
    )
    batches_key = normalize_s3_object_key(
        candidate_batches_key, field_name="candidate_batches_key"
    )
    payload: dict[str, object] = {
        "release_mode": True,
        "candidate_manifest_key": manifest_key,
        "candidate_batches_key": batches_key,
        "batch_size": int(batch_size),
        "attestations": bound,
        "ticket": int(ticket),
        "trigger": "operator",
        "workflow": "bronze_seed_silver_gold",
    }
    if watermark is not None:
        wm = watermark.isoformat() if isinstance(watermark, date) else str(watermark)
        payload["watermark"] = wm
    if fingerprint:
        payload["candidate_fingerprint"] = str(fingerprint).strip()
    return payload


def normalize_gate_attestations(attestations: object) -> dict[str, str]:
    """Require the five named Ticket 20 gate attestation roles (non-empty strings)."""
    if not isinstance(attestations, Mapping):
        raise InventoryError(
            "Ticket 20 evidence requires attestations object with five named roles"
        )
    normalized: dict[str, str] = {}
    missing: list[str] = []
    for role in REQUIRED_GATE_ATTESTATION_ROLES:
        value = str(attestations.get(role) or "").strip()
        if not value:
            missing.append(role)
        else:
            normalized[role] = value
    if missing:
        raise InventoryError(
            "Ticket 20 evidence missing attestations: " + ", ".join(missing)
        )
    return normalized


def parse_attestations_json(raw: object) -> dict[str, str]:
    """Parse CLI/SF ``--attestations-json`` payload into normalized role map."""
    if raw is None or raw == "":
        raise InventoryError("attestations-json is required for Ticket 20 evidence")
    if isinstance(raw, Mapping):
        return normalize_gate_attestations(raw)
    try:
        payload = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError) as exc:
        raise InventoryError("attestations-json must be valid JSON object") from exc
    return normalize_gate_attestations(payload)


def build_required_relationship_bulk_load_evidence(
    *,
    generation_id: str,
    inventory_fingerprint: str,
    watermark: date,
    coverage_start: date,
    coverage_by_document_type: Mapping[str, Mapping[str, object]],
    candidate_count: int,
    terminal_counts: Mapping[str, int],
    ledger_fingerprint: str,
    batch_ledger_count: int,
    attestations: Mapping[str, str] | object | None = None,
    image_digest: str | None = None,
    execution_arn: str | None = None,
    extra_checks: Mapping[str, object] | None = None,
    require_attestations: bool = True,
    accepted_unresolved_accessions: Iterable[str] | None = None,
    item502_candidate_count: int | None = None,
    accepted_unresolved_max_rate: float = ITEM502_ACCEPTED_UNRESOLVED_MAX_RATE,
    insider_coverage: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Secret-safe Ticket 20 gate evidence payload (completion gate shape).

    Disposition is PASS only when terminal counts sum to candidate_count,
    every status is a known terminal status, and (by default) all five named
    attestations are present. Nonterminal leftovers fail closed.

    ``unresolved_accepted`` (the Release-Owner-accepted Item 5.02 unresolved
    exception) is terminal but bounded: its count must exactly match the
    enumerated ``accepted_unresolved_accessions`` list, and the rate against
    ``item502_candidate_count`` must not exceed ``accepted_unresolved_max_rate``
    — otherwise this raises (fail closed) instead of emitting PASS evidence.
    """
    windows = _normalize_coverage_by_document_type(coverage_by_document_type)
    counts = {str(key): int(value) for key, value in terminal_counts.items()}
    unknown = sorted(set(counts) - TERMINAL_STATUSES)
    if unknown:
        raise InventoryError(
            f"terminal_counts contain nonterminal statuses: {', '.join(unknown)}"
        )
    total_terminal = sum(counts.values())
    if total_terminal != int(candidate_count):
        raise InventoryError(
            f"terminal_counts sum {total_terminal} != candidate_count {candidate_count}"
        )
    accepted_list = sorted(
        {str(a) for a in (accepted_unresolved_accessions or ()) if str(a).strip()}
    )
    accepted_count = counts.get(ITEM502_ACCEPTED_UNRESOLVED_STATUS, 0)
    if accepted_count != len(accepted_list):
        raise InventoryError(
            f"unresolved_accepted count {accepted_count} != enumerated accepted "
            f"accession list length {len(accepted_list)} — every accepted "
            "candidate must be enumerated in evidence, none silently"
        )
    accepted_rate = 0.0
    if accepted_count > 0:
        if not item502_candidate_count or int(item502_candidate_count) <= 0:
            raise InventoryError(
                "item502_candidate_count is required when any unresolved_accepted "
                "candidates exist"
            )
        accepted_rate = accepted_count / int(item502_candidate_count)
        if accepted_rate > float(accepted_unresolved_max_rate):
            raise InventoryError(
                f"accepted Item 5.02 unresolved rate {accepted_rate:.4f} exceeds "
                f"bounded threshold {float(accepted_unresolved_max_rate):.4f} "
                f"({accepted_count} of {int(item502_candidate_count)}) — NO_GO"
            )
    if require_attestations:
        bound_attestations = normalize_gate_attestations(attestations)
    elif attestations is None:
        bound_attestations = {}
    else:
        bound_attestations = normalize_gate_attestations(attestations)
    pass_claim = format_ticket20_pass_claim(
        watermark=watermark,
        fingerprint=inventory_fingerprint,
        coverage_by_document_type=windows,
        accepted_unresolved_count=accepted_count,
        item502_candidate_count=item502_candidate_count,
    )
    evidence: dict[str, object] = {
        "schema_version": 1,
        "artifact": "required_relationship_bulk_load_evidence",
        "disposition": "PASS",
        "generation_id": str(generation_id),
        "inventory_fingerprint": str(inventory_fingerprint),
        "ledger_fingerprint": str(ledger_fingerprint),
        "watermark": watermark.isoformat(),
        "coverage_start": coverage_start.isoformat(),
        "coverage_by_document_type": windows,
        "candidate_count": int(candidate_count),
        "batch_ledger_count": int(batch_ledger_count),
        "terminal_counts": counts,
        "pass_claim": pass_claim,
        "forbidden_overclaims": [
            "complete since 2013 for all relationship forms",
            "full history bulk-load for all forms",
            "Form 3/4/5 complete as Ticket 20",
            "CAGR/financials complete as Ticket 20",
            "Explore archive complete equals agent GO",
            "Item 5.02 / EMPLOYED_BY bulk-load complete without naming the accepted unresolved count",
        ],
    }
    if accepted_count > 0:
        evidence["accepted_unresolved"] = {
            "status": ITEM502_ACCEPTED_UNRESOLVED_STATUS,
            "count": accepted_count,
            "item502_candidate_count": int(item502_candidate_count or 0),
            "rate": round(accepted_rate, 6),
            "max_rate": float(accepted_unresolved_max_rate),
            "accessions": accepted_list,
        }
    if insider_coverage is not None:
        # Ticket 21: insider-scoped EMPLOYED_BY completeness. PASS requires
        # zero unresolved insiders — an unidentified Form 3/4/5 reporting
        # owner is a hard gate failure regardless of Item 5.02 acceptance.
        unresolved_insiders = int(insider_coverage.get("insider_unresolved") or 0)
        if unresolved_insiders > 0:
            raise InventoryError(
                f"insider coverage has {unresolved_insiders} unresolved "
                "insiders — every observed Form 3/4/5 reporting owner must "
                "be identified in MDM (NO_GO)"
            )
        evidence["insider_coverage"] = dict(insider_coverage)
    if bound_attestations:
        evidence["attestations"] = bound_attestations
    if image_digest:
        evidence["image_digest"] = str(image_digest)
    if execution_arn:
        evidence["execution_arn"] = str(execution_arn)
    if extra_checks:
        evidence["checks"] = dict(extra_checks)
    evidence["evidence_fingerprint"] = _sha256(
        {key: value for key, value in evidence.items() if key != "evidence_fingerprint"}
    )
    return evidence


def reconcile_completion_ledger(
    inventory: CandidateInventory,
    outcomes: Iterable[CandidateOutcome],
    *,
    generation_id: str,
) -> LedgerReconciliation:
    expected = {row.accession_number: row for row in inventory.candidates}
    actual: dict[str, CandidateOutcome] = {}
    for outcome in outcomes:
        if outcome.accession_number in actual:
            raise LedgerError(f"duplicate ledger outcome: {outcome.accession_number}")
        actual[outcome.accession_number] = outcome
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise LedgerError(f"ledger accession mismatch; missing={missing}, extra={extra}")
    counts: dict[str, int] = {}
    for accession, outcome in actual.items():
        if outcome.generation_id != generation_id:
            raise LedgerError(f"wrong generation for {accession}")
        if outcome.candidate_fingerprint != expected[accession].fingerprint:
            raise LedgerError(f"stale candidate outcome: {accession}")
        if outcome.status not in TERMINAL_STATUSES:
            raise LedgerError(f"nonterminal candidate outcome: {accession}={outcome.status}")
        if not outcome.evidence_fingerprint:
            raise LedgerError(f"missing evidence fingerprint: {accession}")
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    payload = [asdict(actual[key]) for key in sorted(actual)]
    return LedgerReconciliation(generation_id, inventory.fingerprint, counts, _sha256(payload))


def reconcile_completion_ledger_batches(
    inventory: CandidateInventory,
    batch_ledgers: Iterable[Mapping[str, object]],
    *,
    generation_id: str,
) -> LedgerReconciliation:
    """Fan in distributed batch ledgers and apply the exact global reconciliation."""
    outcomes: list[CandidateOutcome] = []
    for ledger in batch_ledgers:
        rows = ledger.get("outcomes")
        if not isinstance(rows, list):
            raise LedgerError("batch ledger is missing outcomes")
        for row in rows:
            if not isinstance(row, Mapping):
                raise LedgerError("batch ledger outcome must be an object")
            outcomes.append(CandidateOutcome(
                generation_id=str(row.get("generation_id") or ""),
                accession_number=str(row.get("accession_number") or ""),
                candidate_fingerprint=str(row.get("candidate_fingerprint") or ""),
                status=str(row.get("status") or ""),
                evidence_fingerprint=str(row.get("evidence_fingerprint") or ""),
            ))
    return reconcile_completion_ledger(inventory, outcomes, generation_id=generation_id)


def batch_identity_for_ciks(ciks: Iterable[int | str]) -> str:
    """Stable 16-hex identity for one StrictBatchSilver CIK batch."""
    normalized = sorted(str(int(cik)) for cik in ciks)
    return hashlib.sha256(",".join(normalized).encode("utf-8")).hexdigest()[:16]


def release_freeze_prefix_from_path(path: str) -> str:
    """Directory containing the frozen candidate_manifest / batches JSONL."""
    cleaned = str(path or "").strip().rstrip("/")
    if not cleaned:
        raise InventoryError("release freeze path is empty")
    if "://" in cleaned:
        parent = cleaned.rsplit("/", 1)[0]
        return parent + "/"
    from pathlib import Path

    return str(Path(cleaned).resolve().parent) + "/"


def batch_done_marker_path(freeze_prefix: str, batch_identity: str) -> str:
    """Absolute URI/path for a completed-batch marker under the freeze prefix."""
    prefix = freeze_prefix if freeze_prefix.endswith("/") else f"{freeze_prefix}/"
    identity = str(batch_identity or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{16}", identity):
        raise InventoryError(f"invalid batch identity: {batch_identity!r}")
    return f"{prefix}batch_done/{identity}.json"


def batch_identity_from_done_marker_name(name: str) -> str | None:
    """Parse ``{batch_identity}.json`` child names under batch_done/."""
    raw = str(name or "").strip()
    if not raw.endswith(".json"):
        return None
    identity = raw[: -len(".json")].lower()
    if not re.fullmatch(r"[0-9a-f]{16}", identity):
        return None
    return identity


def list_done_batch_identities(child_names: Iterable[str]) -> set[str]:
    """Extract completed batch identities from batch_done directory child names."""
    done: set[str] = set()
    for name in child_names:
        identity = batch_identity_from_done_marker_name(name)
        if identity is not None:
            done.add(identity)
    return done


def _ciks_from_batch_row(batch: Mapping[str, object]) -> list[int]:
    cik_list = batch.get("cik_list")
    if isinstance(cik_list, str):
        parts = [part.strip() for part in cik_list.split(",") if part.strip()]
        if not parts:
            raise InventoryError("cik_batches row has empty cik_list")
        return [int(part) for part in parts]
    if isinstance(cik_list, list):
        if not cik_list:
            raise InventoryError("cik_batches row has empty cik_list")
        return [int(part) for part in cik_list]
    raise InventoryError("cik_batches row is missing cik_list")


def parse_cik_batches_jsonl(text: str) -> list[dict[str, object]]:
    """Parse Distributed Map CIK batch JSONL into row objects."""
    rows: list[dict[str, object]] = []
    for line_no, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InventoryError(f"invalid cik_batches JSONL on line {line_no}") from exc
        if not isinstance(payload, dict):
            raise InventoryError(f"cik_batches JSONL line {line_no} must be an object")
        _ciks_from_batch_row(payload)  # validate
        rows.append(payload)
    return rows


def build_remaining_cik_batches(
    batches: Iterable[Mapping[str, object]],
    done_batch_identities: set[str],
) -> list[dict[str, object]]:
    """Drop batches whose identity already has a done marker (Ticket 20 P0 resume)."""
    remaining: list[dict[str, object]] = []
    done = {str(item).lower() for item in done_batch_identities}
    for batch in batches:
        identity = batch_identity_for_ciks(_ciks_from_batch_row(batch))
        if identity in done:
            continue
        remaining.append(dict(batch))
    return remaining


def build_batch_done_marker(
    *,
    batch_identity: str,
    ciks: Iterable[int | str],
    generation_id: str,
    inventory_fingerprint: str,
    ledger_path: str,
    ledger_fingerprint: str,
    terminal_counts: Mapping[str, int],
    candidate_count: int,
    completed_at: str,
) -> dict[str, object]:
    """Secret-safe done-marker payload written after a successful strict batch."""
    cik_values = [int(cik) for cik in ciks]
    computed = batch_identity_for_ciks(cik_values)
    expected = str(batch_identity or "").strip().lower()
    if expected and expected != computed:
        raise InventoryError(
            f"batch identity mismatch: expected {expected}, computed {computed}"
        )
    return {
        "schema_version": 1,
        "batch_identity": computed,
        "cik_list": ",".join(str(cik) for cik in sorted(cik_values)),
        "cik_count": len(cik_values),
        "candidate_count": int(candidate_count),
        "generation_id": str(generation_id),
        "inventory_fingerprint": str(inventory_fingerprint),
        "ledger_path": str(ledger_path),
        "ledger_fingerprint": str(ledger_fingerprint),
        "terminal_counts": {str(key): int(value) for key, value in terminal_counts.items()},
        "completed_at": str(completed_at),
    }


def sanitize_accession_for_path(accession_number: str) -> str:
    """Filesystem/S3-safe accession segment (keeps digits, letters, . _ -)."""
    raw = str(accession_number or "").strip()
    if not raw:
        raise InventoryError("accession_number is empty")
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", raw)
    if not safe or safe in {".", ".."}:
        raise InventoryError(f"invalid accession_number for path: {accession_number!r}")
    return safe


def accession_done_marker_path(freeze_prefix: str, accession_number: str) -> str:
    """Absolute URI/path for a per-accession terminal marker under the freeze prefix."""
    prefix = freeze_prefix if freeze_prefix.endswith("/") else f"{freeze_prefix}/"
    return f"{prefix}accession_done/{sanitize_accession_for_path(accession_number)}.json"


def build_accession_done_marker(
    *,
    accession_number: str,
    candidate_fingerprint: str,
    inventory_fingerprint: str,
    status: str,
    evidence_fingerprint: str,
    generation_id: str,
    completed_at: str,
) -> dict[str, object]:
    """Secret-safe terminal marker for one release candidate (Ticket 20 P1)."""
    status_value = str(status or "").strip()
    if status_value not in TERMINAL_STATUSES:
        raise InventoryError(f"nonterminal accession marker status: {status_value}")
    if not str(candidate_fingerprint or "").strip():
        raise InventoryError("accession marker missing candidate_fingerprint")
    if not str(inventory_fingerprint or "").strip():
        raise InventoryError("accession marker missing inventory_fingerprint")
    if not str(evidence_fingerprint or "").strip():
        raise InventoryError("accession marker missing evidence_fingerprint")
    return {
        "schema_version": 1,
        "accession_number": str(accession_number),
        "candidate_fingerprint": str(candidate_fingerprint),
        "inventory_fingerprint": str(inventory_fingerprint),
        "status": status_value,
        "evidence_fingerprint": str(evidence_fingerprint),
        "generation_id": str(generation_id),
        "completed_at": str(completed_at),
    }


def terminal_outcome_from_accession_marker(
    payload: Mapping[str, object],
    *,
    candidate: RelationshipSourceCandidate,
    inventory_fingerprint: str,
    generation_id: str,
) -> CandidateOutcome | None:
    """Return a reusable CandidateOutcome when the marker is still valid for this freeze."""
    if int(payload.get("schema_version") or 0) < 1:
        return None
    if str(payload.get("accession_number") or "") != candidate.accession_number:
        return None
    if str(payload.get("candidate_fingerprint") or "") != candidate.fingerprint:
        return None
    if str(payload.get("inventory_fingerprint") or "") != str(inventory_fingerprint):
        return None
    status = str(payload.get("status") or "").strip()
    evidence = str(payload.get("evidence_fingerprint") or "").strip()
    if status not in TERMINAL_STATUSES or not evidence:
        return None
    return CandidateOutcome(
        generation_id=str(generation_id),
        accession_number=candidate.accession_number,
        candidate_fingerprint=candidate.fingerprint,
        status=status,
        evidence_fingerprint=evidence,
    )


def load_terminal_accession_outcomes(
    *,
    freeze_prefix: str,
    candidates: Iterable[RelationshipSourceCandidate],
    inventory_fingerprint: str,
    generation_id: str,
    read_text,
) -> dict[str, CandidateOutcome]:
    """Load durable per-accession terminal markers for resume (Ticket 20 P1).

    ``read_text`` is injected (typically ``lambda path: read_bytes(path).decode()``)
    so unit tests do not need real S3.
    """
    outcomes: dict[str, CandidateOutcome] = {}
    for candidate in candidates:
        path = accession_done_marker_path(freeze_prefix, candidate.accession_number)
        try:
            raw = read_text(path)
        except (FileNotFoundError, OSError, ValueError, KeyError):
            continue
        except Exception:
            # Remote FS may raise provider-specific not-found errors.
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        outcome = terminal_outcome_from_accession_marker(
            payload,
            candidate=candidate,
            inventory_fingerprint=inventory_fingerprint,
            generation_id=generation_id,
        )
        if outcome is not None:
            outcomes[candidate.accession_number] = outcome
    return outcomes



# ── Ticket 21: insider-scoped EMPLOYED_BY completeness (slices 1-2) ──────────
#
# Release Owner decision (2026-07-19): the required identification universe
# is insiders — people appearing as reporting owners in Form 3/4/5 filings.
# Slice 1 builds the authoritative insider inventory from silver; slice 2
# partitions it into identified/unresolved against MDM via injected
# resolvers (no MDM import here — the concrete wiring lands with the
# evidence-block slice so this stays unit-testable with fakes).

@dataclass(frozen=True)
class InsiderObservation:
    owner_cik: int | None
    owner_name: str
    issuer_cik: int
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool


def insider_inventory(db, ciks: Iterable[int] | None = None,
                      *, exclude_owner_ciks: Iterable[int] | None = None,
                      ) -> tuple[InsiderObservation, ...]:
    """Distinct insiders observed in silver ownership rows (Ticket 21 slice 1).

    One row per (owner identity, issuer) pair, deduped across filings: an
    insider filing ten Form 4s for the same issuer is one observation. Owner
    identity is owner_cik when present, else casefolded owner_name.
    ``exclude_owner_ciks`` removes corporate reporting owners (funds filing
    Form 4), mirroring _derive_is_insider's corporate skip.
    """
    cik_list = sorted({int(c) for c in (ciks or ())})
    where = ""
    params: list[int] = []
    if cik_list:
        where = f"WHERE f.cik IN ({', '.join('?' * len(cik_list))})"
        params = cik_list
    rows = db.fetch(
        f"""
        SELECT o.owner_cik, o.owner_name, f.cik AS issuer_cik,
               MAX(CASE WHEN o.is_director THEN 1 ELSE 0 END) AS is_director,
               MAX(CASE WHEN o.is_officer THEN 1 ELSE 0 END) AS is_officer,
               MAX(CASE WHEN o.is_ten_percent_owner THEN 1 ELSE 0 END) AS is_ten_percent_owner
        FROM sec_ownership_reporting_owner o
        JOIN sec_company_filing f ON o.accession_number = f.accession_number
        {where}
        GROUP BY o.owner_cik, o.owner_name, f.cik
        """,
        params,
    )
    excluded = {int(c) for c in (exclude_owner_ciks or ())}
    seen: dict[tuple, InsiderObservation] = {}
    for row in rows:
        raw_cik = row.get("owner_cik")
        owner_cik = int(raw_cik) if raw_cik not in (None, "") else None
        name = str(row.get("owner_name") or "").strip()
        issuer = int(row.get("issuer_cik"))
        if owner_cik is not None and owner_cik in excluded:
            continue
        if owner_cik is None and not name:
            continue  # no usable identity at all
        key = (owner_cik if owner_cik is not None else name.casefold(), issuer)
        obs = InsiderObservation(
            owner_cik=owner_cik,
            owner_name=name,
            issuer_cik=issuer,
            is_director=bool(row.get("is_director")),
            is_officer=bool(row.get("is_officer")),
            is_ten_percent_owner=bool(row.get("is_ten_percent_owner")),
        )
        prior = seen.get(key)
        if prior is not None:
            obs = InsiderObservation(
                owner_cik=obs.owner_cik if obs.owner_cik is not None else prior.owner_cik,
                owner_name=obs.owner_name or prior.owner_name,
                issuer_cik=issuer,
                is_director=obs.is_director or prior.is_director,
                is_officer=obs.is_officer or prior.is_officer,
                is_ten_percent_owner=obs.is_ten_percent_owner or prior.is_ten_percent_owner,
            )
        seen[key] = obs
    return tuple(sorted(
        seen.values(),
        key=lambda o: (o.issuer_cik, o.owner_cik if o.owner_cik is not None else -1,
                       o.owner_name.casefold()),
    ))


def partition_insider_coverage(
    inventory: Iterable[InsiderObservation],
    *,
    resolve_person,        # (owner_cik, owner_name) -> person_id | None
    resolve_issuer,        # (issuer_cik) -> issuer_entity_id | None
    has_insider_version,   # (person_id, issuer_entity_id) -> bool
) -> dict[str, object]:
    """Ticket 21 slice 2: partition observed insiders into identified vs
    unresolved against MDM. Identified means the person resolves to exactly
    one MDM entity AND carries an IS_INSIDER version to the resolved issuer.
    Fail-closed consumers require unresolved == []. Resolver callables are
    injected so this is testable without an MDM connection."""
    identified: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    for obs in inventory:
        record: dict[str, object] = {
            "owner_cik": obs.owner_cik,
            "owner_name": obs.owner_name,
            "issuer_cik": obs.issuer_cik,
        }
        person_id = resolve_person(obs.owner_cik, obs.owner_name)
        if person_id is None:
            unresolved.append({**record, "reason": "unresolved_person"})
            continue
        issuer_id = resolve_issuer(obs.issuer_cik)
        if issuer_id is None:
            unresolved.append({**record, "reason": "unresolved_issuer"})
            continue
        if not has_insider_version(person_id, issuer_id):
            unresolved.append({**record, "reason": "missing_is_insider_version"})
            continue
        identified.append(record)
    return {
        "insider_total": len(identified) + len(unresolved),
        "insider_identified": len(identified),
        "insider_unresolved": len(unresolved),
        "unresolved": unresolved,
        "source": "sec_ownership_reporting_owner",
    }
