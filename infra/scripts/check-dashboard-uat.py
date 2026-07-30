#!/usr/bin/env python3
"""Fail-closed release-bound dashboard UAT evidence gate (GH-254).

The collector/operator supplies query IDs, timings, identities, and browser
observations.  This checker never fabricates them.  Dashboard acceptance is
explicitly scoped below the warehouse full-chain and integrity gates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCENARIOS = (
    "healthy",
    "empty",
    "partial",
    "stale",
    "permission_denied",
    "generation_mismatch",
)
WORKFLOWS = (
    "company360",
    "fundamentals_screener",
    "insider_watch",
    "freshness_strip",
    "adv_explorer",
    "graph_relationships",
)
REQUIRED_RELEASE_FIELDS = (
    "git_commit",
    "app_version",
    "combined_source_digest",
    "role",
    "decision_watermark",
    "graph_generation_id",
)


def skeleton(release_candidate: str) -> dict:
    return {
        "schema_version": 1,
        "release_candidate": release_candidate,
        "release": {field: None for field in REQUIRED_RELEASE_FIELDS},
        "automated_smoke": {
            "app_exists": False,
            "owner_grants_bounded": False,
            "viewer_grants_bounded": False,
            "stage_digest_verified": False,
            "representative_reads": {
                workflow: {
                    "query_id": None,
                    "elapsed_ms": None,
                    "row_count": None,
                    "passed": False,
                }
                for workflow in WORKFLOWS
            },
        },
        "browser_uat": {
            scenario: {
                "passed": False,
                "raw_exception_absent": False,
                "secret_leakage_absent": False,
                "note": None,
            }
            for scenario in SCENARIOS
        },
        "rollback": {
            "restored_app_version": None,
            "owner_smoke_passed": False,
            "viewer_smoke_passed": False,
            "verified_at": None,
        },
        "operator_signoff": {
            "operator": None,
            "signed_at": None,
            "approved": False,
            "scope_acknowledgement": (
                "Dashboard acceptance does not satisfy warehouse full-chain "
                "execution or data-integrity release gates."
            ),
        },
    }


def errors(payload: dict) -> list[str]:
    found: list[str] = []
    release = payload.get("release", {})
    for field in REQUIRED_RELEASE_FIELDS:
        if not release.get(field):
            found.append(f"release.{field}")
    smoke = payload.get("automated_smoke", {})
    for field in (
        "app_exists",
        "owner_grants_bounded",
        "viewer_grants_bounded",
        "stage_digest_verified",
    ):
        if smoke.get(field) is not True:
            found.append(f"automated_smoke.{field}")
    reads = smoke.get("representative_reads", {})
    for workflow in WORKFLOWS:
        read = reads.get(workflow, {})
        if read.get("passed") is not True:
            found.append(f"automated_smoke.representative_reads.{workflow}.passed")
        if not read.get("query_id"):
            found.append(f"automated_smoke.representative_reads.{workflow}.query_id")
        if type(read.get("elapsed_ms")) not in (int, float):
            found.append(f"automated_smoke.representative_reads.{workflow}.elapsed_ms")
        if type(read.get("row_count")) is not int or read.get("row_count", -1) < 0:
            found.append(f"automated_smoke.representative_reads.{workflow}.row_count")
    browser = payload.get("browser_uat", {})
    for scenario in SCENARIOS:
        result = browser.get(scenario, {})
        for field in ("passed", "raw_exception_absent", "secret_leakage_absent"):
            if result.get(field) is not True:
                found.append(f"browser_uat.{scenario}.{field}")
    rollback = payload.get("rollback", {})
    for field in (
        "restored_app_version",
        "verified_at",
    ):
        if not rollback.get(field):
            found.append(f"rollback.{field}")
    for field in ("owner_smoke_passed", "viewer_smoke_passed"):
        if rollback.get(field) is not True:
            found.append(f"rollback.{field}")
    signoff = payload.get("operator_signoff", {})
    if signoff.get("approved") is not True:
        found.append("operator_signoff.approved")
    for field in ("operator", "signed_at"):
        if not signoff.get(field):
            found.append(f"operator_signoff.{field}")
    expected_scope = skeleton("unused")["operator_signoff"]["scope_acknowledgement"]
    if signoff.get("scope_acknowledgement") != expected_scope:
        found.append("operator_signoff.scope_acknowledgement")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit-skeleton", action="store_true")
    mode.add_argument("--check", type=Path)
    parser.add_argument("--release-candidate")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.emit_skeleton:
        if not args.release_candidate:
            parser.error("--emit-skeleton requires --release-candidate")
        output = json.dumps(skeleton(args.release_candidate), indent=2) + "\n"
        if args.out:
            args.out.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0
    payload = json.loads(args.check.read_text(encoding="utf-8"))
    failures = errors(payload)
    if failures:
        print("NOT_READY")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
