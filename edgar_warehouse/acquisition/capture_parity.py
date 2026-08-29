"""Ticket 51: Decision 2 capture-parity harness for ``filing_artifact``.

Observe-only. Compares a legacy capture snapshot to a ledger-gated snapshot
for one CIK scope and one business date. Pass is equal-or-superset on
Logical Source Keys, Verified Source Evidence, and Source Fetch Decision
rows, with zero silent gaps and no out-of-scope CIKs.

Stage 1 default is Apple CIK 320193. Stage 2 is ``limit=100``. 1-CIK and
100-CIK share this function; they are not a Template Method hierarchy.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APPLE_CIK = 320193


@dataclass(frozen=True)
class CaptureArtifact:
    """One captured filing, keyed the same way on both paths."""

    cik: int
    logical_source_key: str
    verified_evidence_reference: str | None = None
    decision_id: str | None = None


@dataclass(frozen=True)
class CaptureSnapshot:
    path: str
    cause_reference: str
    artifacts: tuple[CaptureArtifact, ...]


@dataclass(frozen=True)
class ParityScope:
    business_date: str
    cik_list: tuple[int, ...]
    limit: int


@dataclass(frozen=True)
class SetDiff:
    only_legacy: frozenset[str]
    only_gated: frozenset[str]
    shared: frozenset[str]

    @property
    def gated_covers_legacy(self) -> bool:
        return not self.only_legacy


@dataclass(frozen=True)
class ParityVerdict:
    passed: bool
    reasons: tuple[str, ...]
    scope: ParityScope
    logical_source_keys: SetDiff
    verified_evidence: SetDiff
    source_fetch_decisions: SetDiff
    out_of_scope_ciks: frozenset[int]

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "business_date": self.scope.business_date,
            "cik_list": list(self.scope.cik_list),
            "limit": self.scope.limit,
            "out_of_scope_ciks": sorted(self.out_of_scope_ciks),
            "logical_source_keys": _diff_payload(self.logical_source_keys),
            "verified_evidence": _diff_payload(self.verified_evidence),
            "source_fetch_decisions": _diff_payload(self.source_fetch_decisions),
        }


def resolve_parity_scope(
    *,
    business_date: str,
    cik_list: Sequence[int] | None = None,
    limit: int = 1,
) -> ParityScope:
    """Stage 1 default is Apple. Stage 2 passes ``limit=100`` and a universe."""

    if limit < 1:
        raise ValueError("limit must be >= 1")
    ordered = tuple(int(cik) for cik in (cik_list or (APPLE_CIK,)))
    if not ordered:
        ordered = (APPLE_CIK,)
    return ParityScope(
        business_date=business_date,
        cik_list=ordered[:limit],
        limit=limit,
    )


def artifact_from_silver_raw_object(row: Mapping[str, Any]) -> CaptureArtifact:
    """Map a ``sec_raw_object`` row onto the Decision 2 compare key."""

    cik = int(row["cik"])
    accession = str(row["accession_number"])
    evidence = row.get("sha256") or row.get("storage_path")
    return CaptureArtifact(
        cik=cik,
        logical_source_key=f"{cik}/{accession}/full-submission-text",
        verified_evidence_reference=str(evidence) if evidence else None,
        decision_id=None,
    )


def artifact_from_source_fetch_decision(row: Mapping[str, Any]) -> CaptureArtifact:
    """Map a Source Fetch Decision row onto the Decision 2 compare key."""

    key = str(row["logical_source_key"])
    cik_token = key.split("/", 1)[0]
    decision_id = row.get("decision_id")
    evidence = row.get("verified_evidence_reference") or row.get(
        "captured_artifact_reference"
    )
    return CaptureArtifact(
        cik=int(row["cik"]) if row.get("cik") is not None else int(cik_token),
        logical_source_key=key,
        verified_evidence_reference=str(evidence) if evidence else None,
        decision_id=str(decision_id) if decision_id else None,
    )


def filter_discovery_rows_by_cik(
    rows: Iterable[dict],
    cik_list: Sequence[int] | None,
) -> list[dict]:
    """Keep sealed daily-index rows in the Decision 2 CIK scope.

    Form 3/4/5 daily-index files list the issuer and each reporting owner as
    separate lines that share one accession. Silver's PK is
    ``(business_date, accession_number)``, last-write-wins, so the surviving
    ``cik`` is often the owner. Scope still matches when the issuer CIK is
    in the file path (``edgar/data/<issuer_cik>/...``).
    """

    if not cik_list:
        return list(rows)
    return [row for row in rows if issuer_cik_from_daily_index_row(row, cik_list) is not None]


def issuer_cik_from_daily_index_row(
    row: Mapping[str, Any], cik_list: Sequence[int]
) -> int | None:
    """Issuer CIK for a daily-index row under a Decision 2 CIK scope."""

    allowed = {int(cik) for cik in cik_list}
    cik_value = row.get("cik")
    if cik_value is not None and int(cik_value) in allowed:
        return int(cik_value)
    haystack = f"{row.get('file_name') or ''} {row.get('filing_txt_url') or ''}"
    for cik in allowed:
        if f"/{cik}/" in haystack:
            return int(cik)
    return None


def should_record_family_catchup(cik_list: Sequence[int] | None) -> bool:
    """A CIK-scoped run must not mark the whole date caught up."""

    return not cik_list


def compare_capture_snapshots(
    *,
    legacy: CaptureSnapshot,
    gated: CaptureSnapshot,
    scope: ParityScope,
) -> ParityVerdict:
    scoped = set(scope.cik_list)
    reasons: list[str] = []

    if not legacy.cause_reference or not gated.cause_reference:
        reasons.append("each path needs a non-empty cause_reference")
    elif legacy.cause_reference == gated.cause_reference:
        reasons.append("legacy and gated must use distinct cause_reference values")

    out_of_scope = frozenset(
        artifact.cik
        for artifact in (*legacy.artifacts, *gated.artifacts)
        if artifact.cik not in scoped
    )
    if out_of_scope:
        reasons.append(
            "out of scope CIKs were processed: " + ",".join(str(cik) for cik in sorted(out_of_scope))
        )

    in_scope_legacy = [a for a in legacy.artifacts if a.cik in scoped]
    in_scope_gated = [a for a in gated.artifacts if a.cik in scoped]

    key_diff = _diff(
        {a.logical_source_key for a in in_scope_legacy},
        {a.logical_source_key for a in in_scope_gated},
    )
    evidence_diff = _diff(
        {
            a.logical_source_key
            for a in in_scope_legacy
            if a.verified_evidence_reference
        },
        {
            a.logical_source_key
            for a in in_scope_gated
            if a.verified_evidence_reference
        },
    )
    decision_diff = _diff(
        {a.logical_source_key for a in in_scope_legacy if a.decision_id},
        {a.logical_source_key for a in in_scope_gated if a.decision_id},
    )

    if not key_diff.gated_covers_legacy:
        reasons.append(
            "silent gap on Silver Logical Source Keys: "
            + ",".join(sorted(key_diff.only_legacy))
        )
    if not evidence_diff.gated_covers_legacy:
        reasons.append(
            "silent gap on Verified Source Evidence: "
            + ",".join(sorted(evidence_diff.only_legacy))
        )
    if not decision_diff.gated_covers_legacy:
        reasons.append(
            "silent gap on Source Fetch Decision rows: "
            + ",".join(sorted(decision_diff.only_legacy))
        )

    return ParityVerdict(
        passed=not reasons,
        reasons=tuple(reasons),
        scope=scope,
        logical_source_keys=key_diff,
        verified_evidence=evidence_diff,
        source_fetch_decisions=decision_diff,
        out_of_scope_ciks=out_of_scope,
    )


def write_capture_snapshot(path: Path, snapshot: CaptureSnapshot) -> None:
    payload = {
        "path": snapshot.path,
        "cause_reference": snapshot.cause_reference,
        "artifacts": [
            {
                "cik": artifact.cik,
                "logical_source_key": artifact.logical_source_key,
                "verified_evidence_reference": artifact.verified_evidence_reference,
                "decision_id": artifact.decision_id,
            }
            for artifact in snapshot.artifacts
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_capture_snapshot(path: Path) -> CaptureSnapshot:
    payload = json.loads(path.read_text())
    artifacts = tuple(
        CaptureArtifact(
            cik=int(row["cik"]),
            logical_source_key=str(row["logical_source_key"]),
            verified_evidence_reference=row.get("verified_evidence_reference"),
            decision_id=row.get("decision_id"),
        )
        for row in payload.get("artifacts", [])
    )
    return CaptureSnapshot(
        path=str(payload["path"]),
        cause_reference=str(payload["cause_reference"]),
        artifacts=artifacts,
    )


@dataclass(frozen=True)
class DualPathParityResult:
    """Ticket 53: both producers ran; ``verdict`` is Ticket 51's compare."""

    verdict: ParityVerdict
    legacy: CaptureSnapshot
    gated: CaptureSnapshot


def legacy_capture_cause_reference(business_date: str, cik_list: Sequence[int]) -> str:
    ciks = ",".join(str(int(cik)) for cik in cik_list)
    return f"legacy-capture:{business_date}:cik={ciks}"


def run_dual_path_filing_artifact_parity(
    *,
    context: Any,
    db: Any,
    business_date: str,
    sync_run_id: str,
    cik_list: Sequence[int] | None = None,
    limit: int = 1,
    download_bytes: Any = None,
    get_filing: Any = None,
) -> DualPathParityResult:
    """Run legacy ``fetch_filing_artifacts`` then gated discovery, and compare.

    Both paths hit SEC by default (``download_bytes`` / ``get_filing`` omitted).
    Snapshots the legacy silver ``sec_raw_object`` rows *before* gated capture
    writes the same table. Gated artifacts come from Source Fetch Decision /
    work rows.
    """

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from edgar_warehouse.acquisition.models import (
        SourceFetchDecisionRecord,
        SourceFetchWorkRecord,
    )
    from edgar_warehouse.application.workflows.drive_filing_discovery import (
        run_filing_artifact_gated_capture_for_business_date,
    )
    from edgar_warehouse.bronze_filing_artifacts import fetch_filing_artifacts
    from edgar_warehouse.mdm.database import get_engine

    scope = resolve_parity_scope(
        business_date=business_date, cik_list=cik_list, limit=limit
    )
    index_rows = filter_discovery_rows_by_cik(
        db.get_daily_index_filings(business_date), scope.cik_list
    )
    filing_rows = []
    for row in index_rows:
        issuer_cik = issuer_cik_from_daily_index_row(row, scope.cik_list)
        if issuer_cik is None:
            continue
        filing_rows.append(
            {
                "accession_number": str(row["accession_number"]),
                "cik": issuer_cik,
                "form": str(row["form"]),
                "filing_date": row["filing_date"],
                "primary_document": "primary.xml",
            }
        )
    if filing_rows:
        db.merge_filings(filing_rows, sync_run_id)

    for row in index_rows:
        fetch_kwargs: dict[str, Any] = {
            "context": context,
            "db": db,
            "accession_number": str(row["accession_number"]),
            "sync_run_id": sync_run_id,
            "force": False,
        }
        if download_bytes is not None:
            fetch_kwargs["download_bytes"] = download_bytes
        if get_filing is not None:
            fetch_kwargs["get_filing"] = get_filing
        fetch_filing_artifacts(**fetch_kwargs)

    legacy_rows = db.fetch("SELECT * FROM sec_raw_object")
    legacy = CaptureSnapshot(
        path="legacy",
        cause_reference=legacy_capture_cause_reference(business_date, scope.cik_list),
        artifacts=tuple(artifact_from_silver_raw_object(row) for row in legacy_rows),
    )

    run_filing_artifact_gated_capture_for_business_date(
        context=context,
        db=db,
        business_date=business_date,
        run_id=sync_run_id,
        cik_list=scope.cik_list,
    )

    gated_artifacts: list[CaptureArtifact] = []
    gated_cause = f"gated-capture:{business_date}"
    with Session(get_engine()) as session:
        works = {
            work.decision_id: work
            for work in session.execute(select(SourceFetchWorkRecord)).scalars().all()
        }
        for decision in session.execute(select(SourceFetchDecisionRecord)).scalars().all():
            work = works.get(decision.decision_id)
            evidence = decision.verified_evidence_reference
            if work is not None and work.captured_artifact_reference:
                evidence = evidence or work.captured_artifact_reference
            captured = evidence is not None or (
                work is not None and work.fetch_state == "CAPTURED"
            )
            if not captured:
                continue
            gated_artifacts.append(
                artifact_from_source_fetch_decision(
                    {
                        "logical_source_key": decision.logical_source_key,
                        "verified_evidence_reference": evidence,
                        "decision_id": decision.decision_id,
                    }
                )
            )
            gated_cause = decision.cause_reference

    gated = CaptureSnapshot(
        path="gated",
        cause_reference=gated_cause,
        artifacts=tuple(gated_artifacts),
    )
    return DualPathParityResult(
        verdict=compare_capture_snapshots(legacy=legacy, gated=gated, scope=scope),
        legacy=legacy,
        gated=gated,
    )


def evaluate_capture_parity_files(
    *,
    legacy_path: Path,
    gated_path: Path,
    business_date: str,
    cik_list: Sequence[int] | None = None,
    limit: int = 1,
) -> ParityVerdict:
    """CLI seam: load two JSON snapshots and apply Ticket 10 Decision 2."""

    scope = resolve_parity_scope(
        business_date=business_date, cik_list=cik_list, limit=limit
    )
    return compare_capture_snapshots(
        legacy=load_capture_snapshot(legacy_path),
        gated=load_capture_snapshot(gated_path),
        scope=scope,
    )


def _diff(legacy: set[str], gated: set[str]) -> SetDiff:
    return SetDiff(
        only_legacy=frozenset(legacy - gated),
        only_gated=frozenset(gated - legacy),
        shared=frozenset(legacy & gated),
    )


def _diff_payload(diff: SetDiff) -> dict[str, object]:
    return {
        "gated_covers_legacy": diff.gated_covers_legacy,
        "only_legacy": sorted(diff.only_legacy),
        "only_gated": sorted(diff.only_gated),
        "shared": sorted(diff.shared),
    }
