"""ADV bronze artifact discovery contract."""

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
    source_kind: str = "registry"


@dataclass(frozen=True)
class AdvBronzeArtifactIssue:
    reason: str
    accession_number: str | None = None
    storage_path: str | None = None
    source_kind: str = "registry"
    detail: str | None = None


@dataclass(frozen=True)
class AdvBronzeDiscoveryResult:
    candidates: tuple[AdvBronzeArtifactCandidate, ...]
    issues: tuple[AdvBronzeArtifactIssue, ...]
    skipped_non_adv: int = 0


@dataclass(frozen=True)
class AdvBronzePayload:
    candidate: AdvBronzeArtifactCandidate
    payload: bytes


@dataclass(frozen=True)
class AdvBronzeReadResult:
    payloads: tuple[AdvBronzePayload, ...]
    issues: tuple[AdvBronzeArtifactIssue, ...]


def discover_adv_bronze_artifacts(
    db: Any,
    accession_list: list[str] | tuple[str, ...] | set[str] | None = None,
    explicit_artifacts: list[Any] | tuple[Any, ...] | None = None,
    limit: int | None = None,
) -> AdvBronzeDiscoveryResult:
    """Discover already-captured ADV bronze artifacts without external side effects."""
    allowed_accessions = _normalize_accession_filter(accession_list)
    remaining = limit
    candidates: list[AdvBronzeArtifactCandidate] = []
    issues: list[AdvBronzeArtifactIssue] = []
    skipped_non_adv = 0

    filings = db.fetch(
        """
        SELECT accession_number, cik, form
        FROM sec_company_filing
        WHERE form IN ('ADV','ADV/A','ADV-E','ADV-E/A','ADV-H','ADV-H/A','ADV-NR','ADV-W','ADV-W/A')
        ORDER BY cik, accession_number
        """
    )

    for filing in filings:
        if remaining is not None and remaining <= 0:
            break
        accession = _clean_text(_get_field(filing, "accession_number"))
        if not accession:
            issues.append(
                AdvBronzeArtifactIssue(
                    reason="missing_accession_number",
                    source_kind="registry",
                    detail="sec_company_filing row has no accession_number",
                )
            )
            continue
        if allowed_accessions is not None and accession not in allowed_accessions:
            continue

        form = _normalize_form(_get_field(filing, "form"))
        if form not in ADV_FORMS:
            skipped_non_adv += 1
            issues.append(
                AdvBronzeArtifactIssue(
                    accession_number=accession,
                    reason="non_adv_form",
                    source_kind="registry",
                    detail=f"form {form or '<empty>'} is not in the ADV allowlist",
                )
            )
            continue

        candidate = _registry_candidate(db, filing, accession, form, issues)
        if candidate is None:
            continue
        candidates.append(candidate)
        if remaining is not None:
            remaining -= 1

    for artifact in explicit_artifacts or ():
        if remaining is not None and remaining <= 0:
            break
        candidate, artifact_issues, skipped = _explicit_candidate(artifact, allowed_accessions)
        issues.extend(artifact_issues)
        skipped_non_adv += skipped
        if candidate is None:
            continue
        candidates.append(candidate)
        if remaining is not None:
            remaining -= 1

    return AdvBronzeDiscoveryResult(
        candidates=tuple(candidates),
        issues=tuple(issues),
        skipped_non_adv=skipped_non_adv,
    )


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
                    source_kind=candidate.source_kind,
                    detail=str(exc),
                )
            )
            continue
        payloads.append(AdvBronzePayload(candidate=candidate, payload=payload))

    return AdvBronzeReadResult(payloads=tuple(payloads), issues=tuple(issues))


def _registry_candidate(
    db: Any,
    filing: Any,
    accession: str,
    form: str,
    issues: list[AdvBronzeArtifactIssue],
) -> AdvBronzeArtifactCandidate | None:
    attachments = db.get_filing_attachments(accession)
    primary = next((row for row in attachments if row.get("is_primary")), None)
    if primary is None or not _clean_text(primary.get("raw_object_id")):
        issues.append(
            AdvBronzeArtifactIssue(
                accession_number=accession,
                reason="missing_primary_attachment",
                source_kind="registry",
            )
        )
        return None

    raw_object = db.get_raw_object(str(primary["raw_object_id"]))
    if raw_object is None:
        issues.append(
            AdvBronzeArtifactIssue(
                accession_number=accession,
                reason="missing_raw_object",
                source_kind="registry",
            )
        )
        return None

    storage_path = _clean_text(raw_object.get("storage_path"))
    if not storage_path:
        issues.append(
            AdvBronzeArtifactIssue(
                accession_number=accession,
                reason="empty_storage_path",
                source_kind="registry",
            )
        )
        return None

    return AdvBronzeArtifactCandidate(
        accession_number=accession,
        cik=_normalize_cik(_get_field(filing, "cik")),
        form=form,
        storage_path=storage_path,
        source_kind="registry",
    )


def _explicit_candidate(
    artifact: Any,
    allowed_accessions: set[str] | None,
) -> tuple[AdvBronzeArtifactCandidate | None, list[AdvBronzeArtifactIssue], int]:
    issues: list[AdvBronzeArtifactIssue] = []
    accession = _clean_text(_get_field(artifact, "accession_number"))
    if not accession:
        issues.append(
            AdvBronzeArtifactIssue(
                reason="missing_accession_number",
                source_kind="explicit",
                detail="explicit artifact record has no accession_number",
            )
        )
        return None, issues, 0
    if allowed_accessions is not None and accession not in allowed_accessions:
        return None, issues, 0

    form = _normalize_form(_get_field(artifact, "form"))
    if form not in ADV_FORMS:
        issues.append(
            AdvBronzeArtifactIssue(
                accession_number=accession,
                reason="non_adv_form",
                source_kind="explicit",
                detail=f"form {form or '<empty>'} is not in the ADV allowlist",
            )
        )
        return None, issues, 1

    storage_path = _clean_text(_get_field(artifact, "storage_path"))
    if not storage_path:
        issues.append(
            AdvBronzeArtifactIssue(
                accession_number=accession,
                reason="empty_storage_path",
                source_kind="explicit",
            )
        )
        return None, issues, 0

    return (
        AdvBronzeArtifactCandidate(
            accession_number=accession,
            cik=_normalize_cik(_get_field(artifact, "cik")),
            form=form,
            storage_path=storage_path,
            source_kind="explicit",
        ),
        issues,
        0,
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
