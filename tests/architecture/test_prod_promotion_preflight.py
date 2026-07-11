from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "preflight-prod-promotion.sh"


def _fake_tools(tmp_path: Path) -> Path:
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    aws = fakebin / "aws"
    aws.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *get-caller-identity*) printf '%s\\n' "${FAKE_ACCOUNT:-690839588395}" ;;
  *head-bucket*) [[ "${FAKE_OCCUPIED:-0}" == 1 ]] ;;
  *describe-secret*) [[ "${FAKE_MISSING_SECRETS:-0}" != 1 ]] ;;
  *describe-images*) exit 0 ;;
  *list-objects-v2*)
    if [[ "$*" == *"edgartools-prod-bronze"* ]]; then
      printf '%s\\n' "${FAKE_TARGET_COUNT:-10}"
    else
      printf '%s\\n' "${FAKE_SOURCE_COUNT:-10}"
    fi
    ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    snow = fakebin / "snow"
    snow.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "${FAKE_SNOW_ROWS:-EDGARTOOLS_PRODB}"
""",
        encoding="utf-8",
    )
    aws.chmod(0o755)
    snow.chmod(0o755)
    return fakebin


def _run(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    fakebin = _fake_tools(tmp_path)
    env = os.environ.copy()
    env.update(overrides)
    env["PATH"] = f"{fakebin}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), "--source-bucket", "former-bronze", "--expected-source-count", "10"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_preflight_passes_read_only_ready_inventory(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Preflight passed. No changes were made." in result.stdout


def test_preflight_rejects_wrong_account(tmp_path: Path) -> None:
    result = _run(tmp_path, FAKE_ACCOUNT="123456789012")
    assert result.returncode == 1
    assert "wrong AWS account" in result.stderr


def test_preflight_rejects_occupied_names_missing_secrets_and_incomplete_copy(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        FAKE_OCCUPIED="1",
        FAKE_MISSING_SECRETS="1",
        FAKE_TARGET_COUNT="9",
        FAKE_SNOW_ROWS="EDGARTOOLS_PRODB EDGARTOOLS_PROD",
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "canonical bucket name is occupied" in combined
    assert "missing secret container" in combined
    assert "copy incomplete" in combined
    assert "canonical Snowflake database is occupied" in combined
