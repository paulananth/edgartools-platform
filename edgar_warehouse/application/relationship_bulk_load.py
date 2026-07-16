"""Fail-closed source inventory and completion-ledger contracts.

The release workflow uses these pure functions before it makes SEC requests.
They deliberately contain no network or database behavior, which makes the
frozen inventory reproducible and independently auditable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable, Mapping


PROXY_FORMS = frozenset({"DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A"})
THIRTEENF_FORMS = frozenset({"13F-HR", "13F-HR/A"})
EIGHT_K_FORMS = frozenset({"8-K", "8-K/A"})
TERMINAL_STATUSES = frozenset({"applicable_loaded", "not_applicable", "superseded"})
DEFAULT_COVERAGE_START = date(2013, 5, 20)


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


def candidate_inventory_from_manifest(
    manifest: object, *, ciks: set[int] | None = None
) -> CandidateInventory:
    """Restore a frozen inventory (or one CIK batch) from its release manifest."""
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


def build_candidate_inventory(
    filings: Iterable[Mapping[str, object]],
    *,
    watermark: date,
    source_manifest_fingerprints: Mapping[str, str],
    quarter_index_fingerprints: Mapping[str, str],
    coverage_start: date = DEFAULT_COVERAGE_START,
) -> CandidateInventory:
    """Build a deterministic accession inventory and fail on source gaps."""
    expected = expected_quarters(coverage_start, watermark)
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
        if filing_date is None or not coverage_start <= filing_date <= watermark:
            continue
        if form not in PROXY_FORMS | EIGHT_K_FORMS | THIRTEENF_FORMS:
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
        assert isinstance(filing_date, date)
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
            relationship_type, reason, artifact_required = "EMPLOYED_BY", "unrelated_8k_metadata", False
        source_index_identity = _quarter_key(filing_date)
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
        "coverage_start": coverage_start.isoformat(),
        "watermark": watermark.isoformat(),
        "quarters": quarters,
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    return CandidateInventory(coverage_start, watermark, tuple(candidates), quarters,
                              _sha256(inventory_payload))


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
