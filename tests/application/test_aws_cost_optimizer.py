from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from edgar_warehouse.application.aws_cost_optimizer import (
    AccessionAuthority,
    AwsOperationGuard,
    CostPolicy,
    ObjectVersion,
    build_cost_findings,
    build_s3_retention_plan,
    compute_plan_hash,
    validate_s3_retention_plan_for_apply,
    verify_plan_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_SPEC = importlib.util.spec_from_file_location(
    "aws_cost_optimizer_cli", REPO_ROOT / "scripts" / "ops" / "aws_cost_optimizer.py"
)
assert _CLI_SPEC and _CLI_SPEC.loader
aws_cost_optimizer_cli = importlib.util.module_from_spec(_CLI_SPEC)
sys.modules[_CLI_SPEC.name] = aws_cost_optimizer_cli
_CLI_SPEC.loader.exec_module(aws_cost_optimizer_cli)


def _authority(
    accession: str,
    form: str,
    filing_date: str,
    *,
    keys: tuple[str, ...] | None = None,
    item_502: bool = False,
    retain_current: bool = False,
    complete: bool = True,
) -> AccessionAuthority:
    prefix = f"warehouse/bronze/filings/sec/cik=1/accession={accession}"
    return AccessionAuthority(
        accession_number=accession,
        form=form,
        filing_date=date.fromisoformat(filing_date),
        item_502=item_502,
        retain_current=retain_current,
        complete=complete,
        object_keys=keys
        or (
            f"{prefix}/index/{accession.replace('-', '')}-index.html",
            f"{prefix}/primary/document.xml",
        ),
    )


def _versions(authority: AccessionAuthority) -> list[ObjectVersion]:
    return [
        ObjectVersion(
            bucket="edgartools-prod-bronze-690839588395",
            key=key,
            version_id=f"version-{index}",
            etag=f'"etag-{index}"',
            size_bytes=100 + index,
            is_latest=True,
            kind="version",
        )
        for index, key in enumerate(authority.object_keys, start=1)
    ]


def test_retention_plan_uses_each_artifacts_canonical_year_window() -> None:
    authorities = [
        _authority("0000000001-22-000001", "13F-HR", "2022-06-01"),
        _authority("0000000001-20-000002", "DEF 14A", "2020-06-01"),
        _authority("0000000001-23-000003", "4", "2023-06-01"),
        _authority("0000000001-23-000004", "8-K", "2023-06-01", item_502=True),
        _authority("0000000001-23-000005", "8-K", "2023-06-01", item_502=False),
        _authority("0000000001-20-000006", "ADV", "2020-06-01", retain_current=True),
    ]

    plan = build_s3_retention_plan(
        authorities,
        [version for authority in authorities for version in _versions(authority)],
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    )

    assert {bundle.accession_number for bundle in plan.bundles} == {
        "0000000001-22-000001",
        "0000000001-20-000002",
        "0000000001-23-000003",
        "0000000001-23-000004",
    }
    assert {bundle.retention_years for bundle in plan.bundles} == {2, 3, 5}
    assert plan.total_versions == 8
    assert plan.total_bytes == 812
    assert plan.unmatched == (
        "0000000001-23-000005: form 8-K has no classified retention rule",
    )


def test_retention_plan_fails_closed_for_incomplete_bundle() -> None:
    authority = _authority("0000000001-20-000001", "DEF 14A", "2020-01-01")
    plan = build_s3_retention_plan(
        [authority],
        _versions(authority)[:1],
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    )

    assert plan.bundles == ()
    assert plan.unmatched == (
        "0000000001-20-000001: missing version inventory for 1 expected object(s)",
    )


def test_retention_plan_fails_closed_for_unclassified_object_in_bundle() -> None:
    authority = _authority("0000000001-20-000001", "DEF 14A", "2020-01-01")
    unexpected = ObjectVersion(
        bucket="edgartools-prod-bronze-690839588395",
        key=(
            "warehouse/bronze/filings/sec/cik=1/"
            "accession=0000000001-20-000001/attachment/unclassified.pdf"
        ),
        version_id="unexpected-version",
        etag='"unexpected"',
        size_bytes=42,
        is_latest=True,
        kind="version",
    )
    plan = build_s3_retention_plan(
        [authority],
        [*_versions(authority), unexpected],
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    )

    assert plan.bundles == ()
    assert plan.unmatched == (
        "0000000001-20-000001: version inventory contains 1 unclassified object(s)",
    )


def test_plan_hash_detects_any_reviewed_plan_change() -> None:
    authority = _authority("0000000001-20-000001", "DEF 14A", "2020-01-01")
    plan = build_s3_retention_plan(
        [authority],
        _versions(authority),
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    )

    verify_plan_hash(plan.to_dict(), plan.plan_hash)
    changed = plan.to_dict()
    changed["total_bytes"] += 1
    with pytest.raises(ValueError, match="plan hash mismatch"):
        verify_plan_hash(changed, plan.plan_hash)


def test_apply_validation_rejects_hashable_plan_outside_bronze_scope() -> None:
    authority = _authority("0000000001-20-000001", "DEF 14A", "2020-01-01")
    plan = build_s3_retention_plan(
        [authority],
        _versions(authority),
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    ).to_dict()
    plan["bundles"][0]["versions"][0]["bucket"] = (
        "edgartools-prod-tfstate-690839588395"
    )
    plan["plan_hash"] = compute_plan_hash(plan)

    with pytest.raises(ValueError, match="unauthorized bucket"):
        validate_s3_retention_plan_for_apply(plan)


def test_apply_validation_rejects_coerced_policy_flags_and_empty_versions() -> None:
    authority = _authority(
        "0000000001-20-000001", "8-K", "2020-01-01", item_502=True
    )
    plan = build_s3_retention_plan(
        [authority],
        _versions(authority),
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    ).to_dict()
    plan["bundles"][0]["item_502"] = "false"
    with pytest.raises(TypeError, match="policy flags must be booleans"):
        validate_s3_retention_plan_for_apply(plan)

    plan["bundles"][0]["item_502"] = True
    plan["bundles"][0]["versions"][0]["version_id"] = ""
    with pytest.raises(ValueError, match="empty VersionId"):
        validate_s3_retention_plan_for_apply(plan)


def test_require_account_rejects_invalid_or_unexpected_identity() -> None:
    class FakeCli:
        def read(self, service: str, operation: str) -> dict[str, str]:
            assert (service, operation) == ("sts", "get-caller-identity")
            return {"Account": "111111111111"}

    with pytest.raises(ValueError, match="exactly 12 digits"):
        aws_cost_optimizer_cli.require_account(FakeCli(), "prod")
    with pytest.raises(RuntimeError, match="AWS account mismatch"):
        aws_cost_optimizer_cli.require_account(FakeCli(), "690839588395")


def test_aws_operation_guard_separates_audit_reads_from_s3_apply() -> None:
    guard = AwsOperationGuard()

    guard.require_read("ce", "get-cost-and-usage")
    guard.require_read("s3api", "list-object-versions")
    with pytest.raises(ValueError, match="not an allowed read-only AWS operation"):
        guard.require_read("s3api", "delete-objects")
    guard.require_s3_delete("s3api", "delete-objects")
    with pytest.raises(ValueError, match="only exact S3 version deletion"):
        guard.require_s3_delete("ecs", "stop-task")


def test_cost_findings_rank_s3_and_fargate_and_apply_thresholds() -> None:
    findings = build_cost_findings(
        previous_month={
            "Amazon Simple Storage Service": 20.0,
            "Amazon Elastic Container Service": 20.0,
            "AWS Key Management Service": 0.80,
        },
        latest_month={
            "Amazon Simple Storage Service": 48.0,
            "Amazon Elastic Container Service": 31.0,
            "AWS Key Management Service": 0.90,
        },
        policy=CostPolicy(minimum_monthly_savings_usd=1.0, drift_percent=20.0),
    )

    assert [finding.service for finding in findings] == [
        "Amazon Simple Storage Service",
        "Amazon Elastic Container Service",
    ]
    assert all(finding.kind == "spend_drift" for finding in findings)
    assert findings[0].drift_percent == pytest.approx(140.0)


def test_authority_jsonl_requires_explicit_complete_bundle(tmp_path: Path) -> None:
    path = tmp_path / "authority.jsonl"
    path.write_text(
        json.dumps(
            {
                "accession_number": "0000000001-22-000001",
                "form": "13F-HR",
                "filing_date": "2022-06-01",
                "complete": True,
                "object_keys": [
                    "warehouse/bronze/filings/sec/cik=1/accession=0000000001-22-000001/primary/a.xml"
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (authority,) = aws_cost_optimizer_cli.load_authorities(path)
    assert authority.complete is True
    assert authority.form == "13F-HR"


def test_normalize_snowflake_authority_accepts_uppercase_columns(tmp_path: Path) -> None:
    source = tmp_path / "snowflake.json"
    destination = tmp_path / "authority.jsonl"
    source.write_text(
        json.dumps(
            [
                {
                    "ACCESSION_NUMBER": "0000000001-23-000001",
                    "FORM": "4",
                    "FILING_DATE": "2023-01-02",
                    "ITEM_502": "false",
                    "COMPLETE": "true",
                    "OBJECT_KEYS": [
                        "warehouse/bronze/filings/sec/cik=1/accession=0000000001-23-000001/primary/a.xml"
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    assert aws_cost_optimizer_cli.normalize_snowflake_authority(source, destination) == 1
    (authority,) = aws_cost_optimizer_cli.load_authorities(destination)
    assert authority.accession_number == "0000000001-23-000001"
    assert authority.complete is True
    assert authority.item_502 is False


def test_apply_revalidates_then_deletes_exact_versions(tmp_path: Path) -> None:
    authority = _authority("0000000001-20-000001", "DEF 14A", "2020-01-01")
    plan = build_s3_retention_plan(
        [authority],
        _versions(authority),
        as_of=date(2026, 9, 2),
        expected_account_id="690839588395",
    )

    class FakeCli:
        def __init__(self) -> None:
            self.list_calls = 0
            self.deleted: list[dict[str, object]] = []

        def read(self, service: str, operation: str, *arguments: str) -> dict[str, object]:
            if (service, operation) == ("sts", "get-caller-identity"):
                return {"Account": "690839588395"}
            assert (service, operation) == ("s3api", "list-object-versions")
            self.list_calls += 1
            if self.list_calls == 1:
                return {
                    "IsTruncated": False,
                    "Versions": [
                        {
                            "Key": version.key,
                            "VersionId": version.version_id,
                            "ETag": version.etag,
                            "Size": version.size_bytes,
                            "IsLatest": version.is_latest,
                        }
                        for version in _versions(authority)
                    ],
                }
            return {"IsTruncated": False, "Versions": []}

        def delete_versions(self, *, bucket: str, batch_file: Path) -> dict[str, object]:
            payload = json.loads(batch_file.read_text(encoding="utf-8"))
            self.deleted.extend(payload["Objects"])
            return {"Deleted": payload["Objects"]}

    cli = FakeCli()
    result = aws_cost_optimizer_cli.apply_retention_plan(
        cli,
        plan=plan.to_dict(),
        expected_hash=plan.plan_hash,
        evidence_dir=tmp_path / "evidence",
    )

    assert result["complete"] is True
    assert result["deleted_versions"] == 2
    assert {row["VersionId"] for row in cli.deleted} == {"version-1", "version-2"}
    assert (tmp_path / "evidence" / "reviewed-plan.json").exists()
    assert (tmp_path / "evidence" / "post-delete-result.json").exists()
