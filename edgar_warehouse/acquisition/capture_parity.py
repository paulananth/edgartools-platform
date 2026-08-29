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
    return CaptureArtifact(
        cik=int(row["cik"]) if row.get("cik") is not None else int(cik_token),
        logical_source_key=key,
        verified_evidence_reference=row.get("verified_evidence_reference"),
        decision_id=str(decision_id) if decision_id else None,
    )


def filter_discovery_rows_by_cik(
    rows: Iterable[dict],
    cik_list: Sequence[int] | None,
) -> list[dict]:
    """Keep sealed daily-index rows whose CIK is in the Decision 2 scope."""

    if not cik_list:
        return list(rows)
    allowed = {int(cik) for cik in cik_list}
    return [row for row in rows if int(row["cik"]) in allowed]


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
