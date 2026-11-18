from datetime import datetime, timedelta, timezone

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from tests.support.exposure import invented_manifest
from exposure_operations import (
    ExposureRunError,
    production_policy,
    run_exposure_cycle,
)


def manifest():
    return invented_manifest({"layer": "mdm", "table": "company", "description": "Mastered companies.",
                              "columns": [("company_id", "BIGINT", "Key.")]})


def snapshots(_manifest):
    table = {"database": "INVENTED_MIRROR", "schema": "MDM", "table": "COMPANY", "description": "Mastered companies.", "authority": "mdm", "columns": [{"name": "company_id", "data_type": "BIGINT"}]}
    return {"snowflake": {"tables": [table]}, "openmetadata": {"tables": [table]}, "autoontology": {"tables": [table]}}


def test_cycle_is_bounded_and_receipt_is_redacted():
    seen = []
    result = run_exposure_cycle(
        manifest(), manifest_created_at=datetime.now(timezone.utc),
        ingest=lambda value: seen.append("ingest") or {"ok": True},
        publish=lambda value: seen.append("publish") or {"ok": True},
        snapshots=snapshots,
    )
    assert result["ok"] is True
    assert seen == ["ingest", "publish"]
    assert "secret" not in str(result)
    assert production_policy() == {
        "target": "EDGARTOOLS_PROD", "role": "EDGARTOOLS_PROD_READER",
        "scope": ["EDGARTOOLS_GOLD", "EDGARTOOLS_SILVER"],
        "approval_gate": "operator-approved production run",
    }


def test_stale_manifest_fails_before_side_effects():
    called = []
    with pytest.raises(ExposureRunError, match="stale"):
        run_exposure_cycle(
            manifest(), manifest_created_at=datetime.now(timezone.utc) - timedelta(days=2),
            ingest=lambda value: called.append("ingest") or {"ok": True},
            publish=lambda value: called.append("publish") or {"ok": True},
            snapshots=snapshots,
        )
    assert called == []


def test_parity_failure_is_fail_closed():
    with pytest.raises(ExposureRunError, match="parity"):
        run_exposure_cycle(
            manifest(), manifest_created_at=datetime.now(timezone.utc),
            ingest=lambda value: {"ok": True}, publish=lambda value: {"ok": True},
            snapshots=lambda value: {"snowflake": {"tables": []}, "openmetadata": {"tables": []}, "autoontology": {"tables": []}},
        )
