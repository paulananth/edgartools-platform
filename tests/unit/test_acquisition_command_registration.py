from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, datetime

import pytest

from edgar_warehouse.application.acquisition_command_registry import (
    AcquisitionCommandRegistration,
    acquisition_command_registration,
    build_acquisition_command_registry,
)


def test_registered_daily_index_command_preserves_scope_and_planned_writes() -> None:
    registration = acquisition_command_registration("load-daily-form-index-for-date")

    assert registration is not None
    scope = registration.resolve_scope(
        arguments={"target_date": "2026-04-22"},
        now=datetime(2026, 4, 23, tzinfo=UTC),
        silver_root=None,
    )
    assert scope == {"target_date": "2026-04-22"}
    assert registration.planned_writes(
        command_path="load-daily-form-index-for-date",
        run_id="run-123",
        scope=scope,
    ) == {
        "bronze": "daily-index/date=2026-04-22/run-123/manifest.json",
        "staging": "staging/daily-index/date=2026-04-22/run-123/manifest.json",
        "artifacts": "artifacts/runs/load-daily-form-index-for-date/run-123/manifest.json",
    }


def test_registration_rejects_missing_required_behavior() -> None:
    with pytest.raises(TypeError, match="execute must be callable"):
        AcquisitionCommandRegistration(
            name="broken-acquisition",
            execute=None,  # type: ignore[arg-type]
            resolve_scope=lambda **_: {},
            planned_writes=lambda **_: {},
        )


def test_registration_registry_rejects_duplicate_command_name() -> None:
    registration = AcquisitionCommandRegistration(
        name="duplicate-acquisition",
        execute=lambda _: 0,
        resolve_scope=lambda **_: {},
        planned_writes=lambda **_: {},
    )

    with pytest.raises(ValueError, match="Duplicate acquisition command registration"):
        build_acquisition_command_registry((registration, registration))


def test_migrated_command_is_separate_from_legacy_fallback() -> None:
    from edgar_warehouse.application.commands import (
        COMMAND_REGISTRY,
        LEGACY_COMMAND_REGISTRY,
    )

    assert "load-daily-form-index-for-date" in COMMAND_REGISTRY
    assert "load-daily-form-index-for-date" not in LEGACY_COMMAND_REGISTRY
    assert "daily-incremental" in LEGACY_COMMAND_REGISTRY


def test_capture_filing_artifact_is_registered_through_ticket_13_seam() -> None:
    from edgar_warehouse.application.commands import (
        COMMAND_REGISTRY,
        LEGACY_COMMAND_REGISTRY,
    )

    registration = acquisition_command_registration("capture-filing-artifact")

    assert registration is not None
    assert "capture-filing-artifact" in COMMAND_REGISTRY
    assert "capture-filing-artifact" not in LEGACY_COMMAND_REGISTRY

    scope = registration.resolve_scope(
        arguments={"candidate_id": "candidate-1"},
        now=datetime(2026, 4, 23, tzinfo=UTC),
        silver_root=None,
    )
    assert scope == {"candidate_id": "candidate-1"}
    assert registration.planned_writes(
        command_path="capture-filing-artifact",
        run_id="run-123",
        scope=scope,
    ) == {
        "bronze": "runs/capture-filing-artifact/run-123/manifest.json",
        "staging": "staging/runs/capture-filing-artifact/run-123/manifest.json",
        "artifacts": "artifacts/runs/capture-filing-artifact/run-123/manifest.json",
    }


def test_capture_filing_artifact_scope_requires_candidate_id() -> None:
    registration = acquisition_command_registration("capture-filing-artifact")
    assert registration is not None

    with pytest.raises(Exception, match="candidate_id is required"):
        registration.resolve_scope(arguments={}, now=datetime(2026, 4, 23, tzinfo=UTC), silver_root=None)


def test_drive_filing_discovery_for_date_is_registered_through_ticket_13_seam() -> None:
    from edgar_warehouse.application.commands import (
        COMMAND_REGISTRY,
        LEGACY_COMMAND_REGISTRY,
    )

    registration = acquisition_command_registration("drive-filing-discovery-for-date")

    assert registration is not None
    assert "drive-filing-discovery-for-date" in COMMAND_REGISTRY
    assert "drive-filing-discovery-for-date" not in LEGACY_COMMAND_REGISTRY

    scope = registration.resolve_scope(
        arguments={"business_date": "2026-08-24"},
        now=datetime(2026, 8, 25, tzinfo=UTC),
        silver_root=None,
    )
    assert scope == {"business_date": "2026-08-24"}
    assert registration.planned_writes(
        command_path="drive-filing-discovery-for-date",
        run_id="run-123",
        scope=scope,
    ) == {
        "bronze": "runs/drive-filing-discovery-for-date/run-123/manifest.json",
        "staging": "staging/runs/drive-filing-discovery-for-date/run-123/manifest.json",
        "artifacts": "artifacts/runs/drive-filing-discovery-for-date/run-123/manifest.json",
    }


def test_drive_filing_discovery_for_date_scope_requires_business_date() -> None:
    registration = acquisition_command_registration("drive-filing-discovery-for-date")
    assert registration is not None

    with pytest.raises(Exception, match="business_date is required"):
        registration.resolve_scope(arguments={}, now=datetime(2026, 8, 25, tzinfo=UTC), silver_root=None)


def test_registered_daily_index_command_preserves_public_result(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from edgar_warehouse.application.command_router import run_command

    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in (
        "SERVING_EXPORT_ROOT",
        "SNOWFLAKE_EXPORT_ROOT",
        "SILVER_LANDING_EXPORT_ROOT",
    ):
        monkeypatch.delenv(variable, raising=False)

    exit_code = run_command(
        "load-daily-form-index-for-date",
        Namespace(target_date="2026-04-22", force=False, run_id="run-123"),
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == {"target_date": "2026-04-22"}
    assert [(write["layer"], write["relative_path"]) for write in result["writes"]] == [
        ("bronze", "daily-index/date=2026-04-22/run-123/manifest.json"),
        ("staging", "staging/daily-index/date=2026-04-22/run-123/manifest.json"),
        (
            "artifacts",
            "artifacts/runs/load-daily-form-index-for-date/run-123/manifest.json",
        ),
        (
            "run_manifest",
            "runs/load-daily-form-index-for-date/run-123/run_manifest.json",
        ),
    ]
