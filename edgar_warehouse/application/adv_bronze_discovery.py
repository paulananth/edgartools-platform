"""ADV bronze artifact discovery contract.

Takes the operator-named ``--artifact`` records only. The registry path
(``sec_company_filing`` plus attachments and raw objects read from the local
store) was deleted by silver-merge-engine-migration Ticket 07: that store is
never hydrated, so it always found nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from edgar_warehouse.infrastructure.object_storage import read_bytes

ADV_FORMS = frozenset({"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H", "ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"})


@dataclass(frozen=True)
class AdvBronzeArtifactCandidate:
    accession_number: str
    form: str
    storage_path: str
    cik: int | None = None


@dataclass(frozen=True)
class AdvBronzeArtifactIssue:
    reason: str
    accession_number: str | None = None
    storage_path: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class AdvBronzeDiscoveryResult:
    candidates: tuple[AdvBronzeArtifactCandidate, ...]
    issues: tuple[AdvBronzeArtifactIssue, ...]


@dataclass(frozen=True)
class AdvBronzePayload:
    candidate: AdvBronzeArtifactCandidate
    payload: bytes


@dataclass(frozen=True)
class AdvBronzeReadResult:
    payloads: tuple[AdvBronzePayload, ...]
    issues: tuple[AdvBronzeArtifactIssue, ...]


def discover_adv_bronze_artifacts(
    explicit_artifacts: list[Any] | tuple[Any, ...],
    accession_list: list[str] | tuple[str, ...] | set[str] | None = None,
) -> AdvBronzeDiscoveryResult:
    """Check operator-named ADV artifacts without external side effects."""
    allowed_accessions = _normalize_accession_filter(accession_list)
    candidates: list[AdvBronzeArtifactCandidate] = []
    issues: list[AdvBronzeArtifactIssue] = []

    for artifact in explicit_artifacts:
        accession = _clean_text(_get_field(artifact, "accession_number"))
        if allowed_accessions is not None and accession and accession not in allowed_accessions:
            continue
        candidate, issue = _explicit_candidate(artifact)
        if issue is not None:
            issues.append(issue)
        if candidate is not None:
            candidates.append(candidate)

    return AdvBronzeDiscoveryResult(candidates=tuple(candidates), issues=tuple(issues))


def read_adv_bronze_artifacts(
    candidates: list[AdvBronzeArtifactCandidate] | tuple[AdvBronzeArtifactCandidate, ...],
    read_bytes_fn: Callable[[str], bytes] = read_bytes,
) -> AdvBronzeReadResult:
    """Read selected ADV bronze artifacts through the storage adapter contract."""
    payloads: list[AdvBronzePayload] = []
    issues: list[AdvBronzeArtifactIssue] = []

    for candidate in candidates:
        try:
            payload = read_bytes_fn(candidate.storage_path)
        except Exception as exc:
            issues.append(
                AdvBronzeArtifactIssue(
                    accession_number=candidate.accession_number,
                    storage_path=candidate.storage_path,
                    reason="unreadable_storage_path",
                    detail=str(exc),
                )
            )
            continue
        payloads.append(AdvBronzePayload(candidate=candidate, payload=payload))

    return AdvBronzeReadResult(payloads=tuple(payloads), issues=tuple(issues))


def _explicit_candidate(
    artifact: Any,
) -> tuple[AdvBronzeArtifactCandidate | None, AdvBronzeArtifactIssue | None]:
    accession = _clean_text(_get_field(artifact, "accession_number"))
    if not accession:
        return None, AdvBronzeArtifactIssue(
            reason="missing_accession_number",
            detail="explicit artifact record has no accession_number",
        )

    form = _normalize_form(_get_field(artifact, "form"))
    if form not in ADV_FORMS:
        return None, AdvBronzeArtifactIssue(
            accession_number=accession,
            reason="non_adv_form",
            detail=f"form {form or '<empty>'} is not in the ADV allowlist",
        )

    storage_path = _clean_text(_get_field(artifact, "storage_path"))
    if not storage_path:
        return None, AdvBronzeArtifactIssue(
            accession_number=accession,
            reason="empty_storage_path",
        )

    return (
        AdvBronzeArtifactCandidate(
            accession_number=accession,
            cik=_normalize_cik(_get_field(artifact, "cik")),
            form=form,
            storage_path=storage_path,
        ),
        None,
    )


def _normalize_accession_filter(accession_list: list[str] | tuple[str, ...] | set[str] | None) -> set[str] | None:
    if accession_list is None:
        return None
    return {accession for value in accession_list if (accession := _clean_text(value))}


def _normalize_form(value: Any) -> str:
    return _clean_text(value).upper()


def _normalize_cik(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _get_field(record: Any, field: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field)
    return getattr(record, field, None)
