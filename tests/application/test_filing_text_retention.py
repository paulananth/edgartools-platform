from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edgar_warehouse.application.aws_cost_optimizer import ObjectVersion
from edgar_warehouse.application.filing_text_retention import (
    build_filing_text_retention_plan,
    build_filing_text_sweep_manifest,
    validate_filing_text_retention_plan_for_apply,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_SPEC = importlib.util.spec_from_file_location(
    "filing_text_retention_cli",
    REPO_ROOT / "scripts" / "ops" / "aws_cost_optimizer.py",
)
assert _CLI_SPEC and _CLI_SPEC.loader
filing_text_retention_cli = importlib.util.module_from_spec(_CLI_SPEC)
sys.modules[_CLI_SPEC.name] = filing_text_retention_cli
_CLI_SPEC.loader.exec_module(filing_text_retention_cli)

ACCOUNT_ID = "690839588395"
ACCESSION = "0000910001-24-000001"
TEXT_VERSION = "generic_text_v1"
TEXT_KEY = (
    "warehouse/text/sec/cik=910001/"
    f"accession={ACCESSION}/{TEXT_VERSION}.txt"
)
TEXT_URI = f"s3://edgartools-prod-warehouse-{ACCOUNT_ID}/{TEXT_KEY}"


def _manifest(
    run_id: str,
    observed_at: datetime,
    *,
    previous_manifest: dict | None = None,
) -> dict:
    return build_filing_text_sweep_manifest(
        run_id=run_id,
        observed_at=observed_at,
        required_rows=[
            {
                "accession_number": "0000910001-26-000001",
                "text_version": TEXT_VERSION,
            }
        ],
        processed_rows=[
            {
                "accession_number": ACCESSION,
                "text_version": TEXT_VERSION,
                "text_storage_path": TEXT_URI,
                "text_sha256": "a" * 64,
            }
        ],
        status="succeeded",
        previous_manifest=previous_manifest,
    )


def _empty_manifest(run_id: str, observed_at: datetime) -> dict:
    return build_filing_text_sweep_manifest(
        run_id=run_id,
        observed_at=observed_at,
        required_rows=[],
        processed_rows=[],
        status="succeeded",
    )


def _version() -> ObjectVersion:
    return ObjectVersion(
        bucket=f"edgartools-prod-warehouse-{ACCOUNT_ID}",
        key=TEXT_KEY,
        version_id="text-version-1",
        etag='"etag-1"',
        size_bytes=1234,
        is_latest=True,
        kind="version",
    )


def _plan() -> dict:
    prior = _manifest("sweep-prior", datetime(2026, 8, 1, tzinfo=UTC))
    current = _manifest(
        "sweep-current",
        datetime(2026, 9, 1, tzinfo=UTC),
        previous_manifest=prior,
    )
    return build_filing_text_retention_plan(
        prior_manifest=prior,
        current_manifest=current,
        versions=[_version()],
        expected_account_id=ACCOUNT_ID,
    )


def test_plan_binds_two_observations_to_exact_warehouse_text_version() -> None:
    prior = _manifest("sweep-prior", datetime(2026, 8, 1, tzinfo=UTC))
    current = _manifest(
        "sweep-current",
        datetime(2026, 9, 1, tzinfo=UTC),
        previous_manifest=prior,
    )

    plan = build_filing_text_retention_plan(
        prior_manifest=prior,
        current_manifest=current,
        versions=[_version()],
        expected_account_id=ACCOUNT_ID,
    )

    assert plan["prior_manifest_hash"] == prior["manifest_hash"]
    assert plan["current_manifest_hash"] == current["manifest_hash"]
    assert plan["observation_days"] == 31
    assert current["previous_manifest_hash"] == prior["manifest_hash"]
    assert current["not_required"][0]["not_required_since"] == prior["observed_at"]
    assert plan["targets"] == [
        {
            "accession_number": ACCESSION,
            "text_version": TEXT_VERSION,
            "text_storage_path": TEXT_URI,
            "text_sha256": "a" * 64,
            "not_required_since": prior["observed_at"],
            "continuous_days": 31,
            "business_key": f"{ACCESSION}|{TEXT_VERSION}",
            "versions": [_version().__dict__],
        }
    ]
    assert plan["blocked"] == []
    assert validate_filing_text_retention_plan_for_apply(plan) == (_version(),)
    assert len(plan["plan_hash"]) == 64


def test_plan_blocks_current_candidate_without_prior_not_required_observation() -> None:
    prior = _empty_manifest("sweep-prior", datetime(2026, 8, 1, tzinfo=UTC))
    plan = build_filing_text_retention_plan(
        prior_manifest=prior,
        current_manifest=_manifest(
            "sweep-current",
            datetime(2026, 9, 1, tzinfo=UTC),
            previous_manifest=prior,
        ),
        versions=[],
        expected_account_id=ACCOUNT_ID,
    )

    assert plan["targets"] == []
    assert plan["blocked"] == [
        f"{ACCESSION}|{TEXT_VERSION}: not observed as not required in both successful sweeps"
    ]


def test_plan_rejects_nonconsecutive_manifest_pair() -> None:
    prior = _manifest("sweep-prior", datetime(2026, 8, 1, tzinfo=UTC))
    intervening = _manifest(
        "sweep-intervening",
        datetime(2026, 8, 15, tzinfo=UTC),
        previous_manifest=prior,
    )
    current = _manifest(
        "sweep-current",
        datetime(2026, 9, 1, tzinfo=UTC),
        previous_manifest=intervening,
    )

    with pytest.raises(RuntimeError, match="not consecutive"):
        build_filing_text_retention_plan(
            prior_manifest=prior,
            current_manifest=current,
            versions=[_version()],
            expected_account_id=ACCOUNT_ID,
        )


def test_plan_rejects_incomplete_or_too_recent_sweep_evidence() -> None:
    incomplete = build_filing_text_sweep_manifest(
        run_id="sweep-incomplete",
        observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        required_rows=[],
        processed_rows=[],
        status="incomplete",
    )
    with pytest.raises(RuntimeError, match="failed or incomplete"):
        build_filing_text_retention_plan(
            prior_manifest=_empty_manifest(
                "sweep-prior", datetime(2026, 8, 1, tzinfo=UTC)
            ),
            current_manifest=incomplete,
            versions=[],
            expected_account_id=ACCOUNT_ID,
        )

    recent_prior = _manifest(
        "sweep-prior", datetime(2026, 8, 15, tzinfo=UTC)
    )
    with pytest.raises(RuntimeError, match="fewer than 30 days"):
        build_filing_text_retention_plan(
            prior_manifest=recent_prior,
            current_manifest=_manifest(
                "sweep-current",
                datetime(2026, 9, 1, tzinfo=UTC),
                previous_manifest=recent_prior,
            ),
            versions=[_version()],
            expected_account_id=ACCOUNT_ID,
        )


def test_plan_blocks_unknown_text_versions() -> None:
    unknown_version = "future_text_v2"
    processed = [
        {
            "accession_number": ACCESSION,
            "text_version": unknown_version,
            "text_storage_path": (
                f"s3://edgartools-prod-warehouse-{ACCOUNT_ID}/warehouse/text/sec/"
                f"cik=910001/accession={ACCESSION}/{unknown_version}.txt"
            ),
            "text_sha256": "b" * 64,
        }
    ]
    prior = build_filing_text_sweep_manifest(
        run_id="sweep-prior",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        required_rows=[],
        processed_rows=processed,
        status="succeeded",
    )
    current = build_filing_text_sweep_manifest(
        run_id="sweep-current",
        observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        required_rows=[],
        processed_rows=processed,
        status="succeeded",
        previous_manifest=prior,
    )

    plan = build_filing_text_retention_plan(
        prior_manifest=prior,
        current_manifest=current,
        versions=[],
        expected_account_id=ACCOUNT_ID,
    )

    assert plan["targets"] == []
    assert plan["blocked"] == [
        f"{ACCESSION}|{unknown_version}: unknown text version"
    ]


def test_plan_blocks_derived_object_drift_between_observations() -> None:
    prior = _manifest("sweep-prior", datetime(2026, 8, 1, tzinfo=UTC))
    current = build_filing_text_sweep_manifest(
        run_id="sweep-current",
        observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        required_rows=[],
        processed_rows=[
            {
                "accession_number": ACCESSION,
                "text_version": TEXT_VERSION,
                "text_storage_path": TEXT_URI,
                "text_sha256": "c" * 64,
            }
        ],
        status="succeeded",
        previous_manifest=prior,
    )

    plan = build_filing_text_retention_plan(
        prior_manifest=prior,
        current_manifest=current,
        versions=[],
        expected_account_id=ACCOUNT_ID,
    )

    assert plan["targets"] == []
    assert plan["blocked"] == [
        f"{ACCESSION}|{TEXT_VERSION}: derived object drifted"
    ]


def test_collect_versions_reads_only_the_exact_warehouse_text_object() -> None:
    manifest = _manifest("sweep-current", datetime(2026, 9, 1, tzinfo=UTC))

    class FakeCli:
        def read(self, service: str, operation: str, *arguments: str) -> dict:
            assert (service, operation) == ("s3api", "list-object-versions")
            assert arguments == (
                "--bucket",
                f"edgartools-prod-warehouse-{ACCOUNT_ID}",
                "--prefix",
                TEXT_KEY,
                "--max-keys",
                "1000",
            )
            return {
                "IsTruncated": False,
                "Versions": [
                    {
                        "Key": TEXT_KEY,
                        "VersionId": "text-version-1",
                        "ETag": '"etag-1"',
                        "Size": 1234,
                        "IsLatest": True,
                    }
                ],
            }

    assert filing_text_retention_cli.collect_filing_text_versions(
        FakeCli(), manifest=manifest, account_id=ACCOUNT_ID
    ) == [_version()]


def test_cli_builds_reviewable_plan_from_two_explicit_manifests(
    tmp_path: Path, monkeypatch
) -> None:
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    output_path = tmp_path / "plan.json"
    prior = _manifest("sweep-prior", datetime(2026, 8, 1, tzinfo=UTC))
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    current_path.write_text(
        json.dumps(
            _manifest(
                "sweep-current",
                datetime(2026, 9, 1, tzinfo=UTC),
                previous_manifest=prior,
            )
        ),
        encoding="utf-8",
    )

    class FakeCli:
        region = "us-east-1"

        def read(self, service: str, operation: str, *arguments: str) -> dict:
            if (service, operation) == ("sts", "get-caller-identity"):
                return {"Account": ACCOUNT_ID}
            return {
                "IsTruncated": False,
                "Versions": [
                    {
                        "Key": TEXT_KEY,
                        "VersionId": "text-version-1",
                        "ETag": '"etag-1"',
                        "Size": 1234,
                        "IsLatest": True,
                    }
                ],
            }

    monkeypatch.setattr(
        filing_text_retention_cli,
        "AwsCli",
        lambda *, profile, region: FakeCli(),
    )

    assert (
        filing_text_retention_cli.main(
            [
                "filing-text-retention-plan",
                "--expected-account-id",
                ACCOUNT_ID,
                "--prior-manifest",
                str(prior_path),
                "--current-manifest",
                str(current_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    plan = json.loads(output_path.read_text(encoding="utf-8"))
    assert plan["targets"][0]["business_key"] == f"{ACCESSION}|{TEXT_VERSION}"


def test_retire_phase_records_and_verifies_silver_retirement_evidence(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class FakeSilver:
        def record_retirements(
            self, business_keys: tuple[str, ...], *, cause_reference: str
        ) -> None:
            calls.append("record")
            assert business_keys == (f"{ACCESSION}|{TEXT_VERSION}",)
            assert cause_reference.startswith("filing-text-retention:")

        def recorded_business_keys(
            self, business_keys: tuple[str, ...], *, cause_reference: str
        ) -> set[str]:
            calls.append("verify-record")
            return set(business_keys)

    plan = _plan()
    result = filing_text_retention_cli.retire_filing_text_plan(
        FakeSilver(),
        plan=plan,
        expected_hash=plan["plan_hash"],
        evidence_dir=tmp_path,
    )

    assert calls == ["record", "verify-record"]
    assert result["retirement_recorded"] is True
    assert len(result["evidence_hash"]) == 64
    assert (tmp_path / "retirement-evidence.json").exists()


def test_apply_refuses_s3_delete_while_silver_identity_is_still_active(
    tmp_path: Path,
) -> None:
    plan = _plan()

    class RetirementRecorder:
        def record_retirements(self, business_keys, *, cause_reference) -> None:
            pass

        def recorded_business_keys(self, business_keys, *, cause_reference):
            return set(business_keys)

    retirement = filing_text_retention_cli.retire_filing_text_plan(
        RetirementRecorder(),
        plan=plan,
        expected_hash=plan["plan_hash"],
        evidence_dir=tmp_path / "retire",
    )

    class ActiveSilver:
        def active_business_keys(self, business_keys):
            return set(business_keys)

    class NoDeleteCli:
        def read(self, service: str, operation: str, *arguments: str) -> dict:
            if (service, operation) == ("sts", "get-caller-identity"):
                return {"Account": ACCOUNT_ID}
            raise AssertionError("S3 must not be read while Silver is still active")

        def delete_versions(self, *, bucket: str, batch_file: Path) -> dict:
            raise AssertionError("S3 must not be deleted while Silver is still active")

    with pytest.raises(RuntimeError, match="still active in canonical Silver"):
        filing_text_retention_cli.apply_filing_text_plan(
            NoDeleteCli(),
            ActiveSilver(),
            plan=plan,
            expected_hash=plan["plan_hash"],
            latest_manifest=_manifest(
                "sweep-current",
                datetime(2026, 9, 1, tzinfo=UTC),
                previous_manifest=_manifest(
                    "sweep-prior", datetime(2026, 8, 1, tzinfo=UTC)
                ),
            ),
            retirement_evidence=retirement,
            evidence_dir=tmp_path / "apply",
        )


def test_apply_deletes_exact_version_only_after_silver_is_verified_retired(
    tmp_path: Path,
) -> None:
    plan = _plan()
    events: list[str] = []

    class RetirementRecorder:
        def record_retirements(self, business_keys, *, cause_reference) -> None:
            pass

        def recorded_business_keys(self, business_keys, *, cause_reference):
            return set(business_keys)

    retirement = filing_text_retention_cli.retire_filing_text_plan(
        RetirementRecorder(),
        plan=plan,
        expected_hash=plan["plan_hash"],
        evidence_dir=tmp_path / "retire",
    )

    class RetiredSilver:
        def active_business_keys(self, business_keys):
            events.append("verify-silver")
            return set()

    class FakeCli:
        def __init__(self) -> None:
            self.list_calls = 0

        def read(self, service: str, operation: str, *arguments: str) -> dict:
            if (service, operation) == ("sts", "get-caller-identity"):
                return {"Account": ACCOUNT_ID}
            events.append("list-s3")
            self.list_calls += 1
            if self.list_calls == 1:
                return {
                    "IsTruncated": False,
                    "Versions": [
                        {
                            "Key": TEXT_KEY,
                            "VersionId": "text-version-1",
                            "ETag": '"etag-1"',
                            "Size": 1234,
                            "IsLatest": True,
                        }
                    ],
                }
            return {"IsTruncated": False, "Versions": []}

        def delete_versions(self, *, bucket: str, batch_file: Path) -> dict:
            events.append("delete-s3")
            assert bucket == f"edgartools-prod-warehouse-{ACCOUNT_ID}"
            payload = json.loads(batch_file.read_text(encoding="utf-8"))
            return {"Deleted": payload["Objects"]}

    result = filing_text_retention_cli.apply_filing_text_plan(
        FakeCli(),
        RetiredSilver(),
        plan=plan,
        expected_hash=plan["plan_hash"],
        latest_manifest=_manifest(
            "sweep-current",
            datetime(2026, 9, 1, tzinfo=UTC),
            previous_manifest=_manifest(
                "sweep-prior", datetime(2026, 8, 1, tzinfo=UTC)
            ),
        ),
        retirement_evidence=retirement,
        evidence_dir=tmp_path / "apply",
    )

    assert events == ["verify-silver", "list-s3", "delete-s3", "list-s3"]
    assert result["complete"] is True
    assert result["deleted_versions"] == 1
    assert (tmp_path / "apply" / "post-delete-result.json").exists()


def test_apply_refuses_newly_required_identity_before_reading_s3(
    tmp_path: Path,
) -> None:
    plan = _plan()

    class RetirementRecorder:
        def record_retirements(self, business_keys, *, cause_reference) -> None:
            pass

        def recorded_business_keys(self, business_keys, *, cause_reference):
            return set(business_keys)

    retirement = filing_text_retention_cli.retire_filing_text_plan(
        RetirementRecorder(),
        plan=plan,
        expected_hash=plan["plan_hash"],
        evidence_dir=tmp_path / "retire",
    )
    current = _manifest(
        "sweep-current",
        datetime(2026, 9, 1, tzinfo=UTC),
        previous_manifest=_manifest(
            "sweep-prior", datetime(2026, 8, 1, tzinfo=UTC)
        ),
    )
    latest = build_filing_text_sweep_manifest(
        run_id="sweep-latest",
        observed_at=datetime(2026, 9, 2, tzinfo=UTC),
        required_rows=[
            {"accession_number": ACCESSION, "text_version": TEXT_VERSION}
        ],
        processed_rows=[
            {
                "accession_number": ACCESSION,
                "text_version": TEXT_VERSION,
                "text_storage_path": TEXT_URI,
                "text_sha256": "a" * 64,
            }
        ],
        status="succeeded",
        previous_manifest=current,
    )

    class RetiredSilver:
        def active_business_keys(self, business_keys):
            return set()

    class NoS3Cli:
        def read(self, service: str, operation: str, *arguments: str) -> dict:
            if (service, operation) == ("sts", "get-caller-identity"):
                return {"Account": ACCOUNT_ID}
            raise AssertionError("S3 must not be read after a new requirement")

    with pytest.raises(RuntimeError, match="latest successful sweep"):
        filing_text_retention_cli.apply_filing_text_plan(
            NoS3Cli(),
            RetiredSilver(),
            plan=plan,
            expected_hash=plan["plan_hash"],
            latest_manifest=latest,
            retirement_evidence=retirement,
            evidence_dir=tmp_path / "apply",
        )


def test_apply_persists_delete_error_and_post_delete_evidence(tmp_path: Path) -> None:
    plan = _plan()

    class RetirementRecorder:
        def record_retirements(self, business_keys, *, cause_reference) -> None:
            pass

        def recorded_business_keys(self, business_keys, *, cause_reference):
            return set(business_keys)

    retirement = filing_text_retention_cli.retire_filing_text_plan(
        RetirementRecorder(),
        plan=plan,
        expected_hash=plan["plan_hash"],
        evidence_dir=tmp_path / "retire",
    )

    class RetiredSilver:
        def active_business_keys(self, business_keys):
            return set()

    class ErrorCli:
        def read(self, service: str, operation: str, *arguments: str) -> dict:
            if (service, operation) == ("sts", "get-caller-identity"):
                return {"Account": ACCOUNT_ID}
            return {
                "IsTruncated": False,
                "Versions": [
                    {
                        "Key": TEXT_KEY,
                        "VersionId": "text-version-1",
                        "ETag": '"etag-1"',
                        "Size": 1234,
                        "IsLatest": True,
                    }
                ],
            }

        def delete_versions(self, *, bucket: str, batch_file: Path) -> dict:
            return {"Errors": [{"Key": TEXT_KEY, "Code": "AccessDenied"}]}

    apply_dir = tmp_path / "apply"
    with pytest.raises(RuntimeError, match="deletion errors"):
        filing_text_retention_cli.apply_filing_text_plan(
            ErrorCli(),
            RetiredSilver(),
            plan=plan,
            expected_hash=plan["plan_hash"],
            latest_manifest=_manifest(
                "sweep-current",
                datetime(2026, 9, 1, tzinfo=UTC),
                previous_manifest=_manifest(
                    "sweep-prior", datetime(2026, 8, 1, tzinfo=UTC)
                ),
            ),
            retirement_evidence=retirement,
            evidence_dir=apply_dir,
        )

    assert (apply_dir / "delete-response-0001.json").exists()
    result = json.loads(
        (apply_dir / "post-delete-result.json").read_text(encoding="utf-8")
    )
    assert result["complete"] is False
    assert result["delete_errors"][0]["Code"] == "AccessDenied"


def test_snowflake_retirement_adapter_uses_landing_record_then_canonical_read() -> None:
    business_key = f"{ACCESSION}|{TEXT_VERSION}"
    statements: list[str] = []

    class FakeCursor:
        def executemany(self, sql: str, rows) -> None:
            statements.append(sql)
            assert list(rows) == [
                (
                    "filing_text_retention",
                    "sec_filing_text",
                    business_key,
                    "filing-text-retention:plan-hash",
                )
            ]

        def execute(self, sql: str, params) -> None:
            statements.append(sql)

        def fetchall(self):
            if "SILVER_LANDING_RETIREMENT" in statements[-1]:
                return [(business_key,)]
            return []

        def close(self) -> None:
            pass

    class FakeConnection:
        committed = False

        def cursor(self):
            return FakeCursor()

        def commit(self) -> None:
            self.committed = True

        def close(self) -> None:
            pass

    connection = FakeConnection()
    adapter = filing_text_retention_cli.SnowflakeFilingTextRetirement(connection)
    adapter.record_retirements(
        (business_key,), cause_reference="filing-text-retention:plan-hash"
    )

    assert adapter.recorded_business_keys(
        (business_key,), cause_reference="filing-text-retention:plan-hash"
    ) == {business_key}
    assert adapter.active_business_keys((business_key,)) == set()
    assert connection.committed is True
    assert "INSERT INTO EDGARTOOLS_SILVER_LANDING.SILVER_LANDING_RETIREMENT" in statements[0]
    assert any("FROM EDGARTOOLS_SILVER.SEC_FILING_TEXT" in sql for sql in statements)


def test_cli_requires_separate_retire_and_derived_delete_confirmations() -> None:
    retire = filing_text_retention_cli.build_parser().parse_args(
        [
            "filing-text-retention-retire",
            "--plan",
            "plan.json",
            "--plan-hash",
            "a" * 64,
            "--confirm-retire-filing-text",
            "--evidence-dir",
            "evidence",
        ]
    )
    apply = filing_text_retention_cli.build_parser().parse_args(
        [
            "filing-text-retention-apply",
            "--plan",
            "plan.json",
            "--plan-hash",
            "a" * 64,
            "--retirement-evidence",
            "retirement.json",
            "--latest-manifest",
            "latest.json",
            "--confirm-delete-derived-filing-text",
            "--evidence-dir",
            "evidence",
        ]
    )

    assert retire.confirm_retire_filing_text is True
    assert apply.confirm_delete_derived_filing_text is True
