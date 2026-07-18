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


def build_frozen_candidate_manifest(
    quarter_indexes: Mapping[str, Iterable[Mapping[str, object]]],
    *,
    silver_filings: Iterable[Mapping[str, object]],
    release_ciks: set[int],
    source_manifest_fingerprints: Mapping[int, str] | None = None,
    watermark: date,
    coverage_start: date = DEFAULT_COVERAGE_START,
    batch_size: int = 100,
) -> dict[str, object]:
    """Freeze complete SEC quarter indexes into the release candidate manifest.

    Quarterly indexes are the authority for 13F coverage and for proving that
    every proxy/8-K accession in the bounded company universe was considered.
    Silver contributes submissions-only metadata such as 8-K item numbers.
    """
    if batch_size <= 0:
        raise InventoryError("batch_size must be positive")
    expected = expected_quarters(coverage_start, watermark)
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
            if not coverage_start <= filing_date <= watermark:
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
        coverage_start=coverage_start,
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
