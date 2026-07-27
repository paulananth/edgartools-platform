"""GH-247: reproducible, verifiable Snowflake dashboard release path.

Tests infra/snowflake/streamlit/deploy.sh's release-evidence generation
(git commit, source digests, dependency-lock digest, app version, rollback
command) via --dry-run, which never calls `snow sql`. Mirrors the fake-tool-
on-PATH pattern in test_prod_promotion_preflight.py.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "snowflake" / "streamlit" / "deploy.sh"


def _fake_snow(tmp_path: Path) -> Path:
    """A `snow` on PATH that records every invocation and always succeeds --
    lets non-dry-run tests assert on the exact SQL issued without touching
    a real Snowflake account."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir(exist_ok=True)
    snow = fakebin / "snow"
    log_path = tmp_path / "snow_calls.log"
    snow.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
{{
  echo "ARGS: $*"
  cat
  echo "---"
}} >> {log_path}
exit 0
""",
        encoding="utf-8",
    )
    snow.chmod(0o755)
    return fakebin


def _run(
    tmp_path: Path,
    *extra_args: str,
    evidence_dir: Path | None = None,
    with_fake_snow: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DASHBOARD_EVIDENCE_DIR"] = str(evidence_dir or (tmp_path / "evidence"))
    if with_fake_snow:
        fakebin = _fake_snow(tmp_path)
        env["PATH"] = f"{fakebin}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), "--skip-tests", *extra_args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _read_latest_evidence(evidence_dir: Path) -> dict:
    latest = evidence_dir / "edgartools-dev" / "latest.json"
    return json.loads(latest.read_text(encoding="utf-8"))


def test_dry_run_emits_valid_json_with_expected_fields(tmp_path: Path) -> None:
    result = _run(tmp_path, "--dry-run")

    assert result.returncode == 0, result.stderr
    payload = _read_latest_evidence(tmp_path / "evidence")

    assert payload["dry_run"] is True
    assert len(payload["git_commit"]) == 40  # full sha
    assert payload["app_version"].startswith("sha-")
    assert payload["environment"] == "edgartools-dev"
    assert payload["previous_app_version"] is None
    assert "no previous release recorded" in payload["rollback_command"]
    assert set(payload["source_digests"]) == {
        "streamlit_app.py",
        "dashboard_modes.py",
        "environment.yml",
    }
    for digest in payload["source_digests"].values():
        assert len(digest) == 64  # sha256 hex digest
    assert len(payload["combined_source_digest"]) == 64
    assert len(payload["dependency_lock_digest"]) == 64


def test_dry_run_never_shells_out_to_snow(tmp_path: Path) -> None:
    """--dry-run must not require snow on PATH at all -- confirms nothing
    in the evidence-computation path accidentally calls it."""
    env_without_snow_dirs = tmp_path / "empty-path-marker"
    env_without_snow_dirs.mkdir()
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--skip-tests"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": "/usr/bin:/bin",  # deliberately no snow
            "DASHBOARD_EVIDENCE_DIR": str(tmp_path / "evidence"),
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_second_run_detects_previous_release_and_builds_rollback_command(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "evidence"

    first = _run(tmp_path, "--dry-run", evidence_dir=evidence_dir)
    assert first.returncode == 0, first.stderr
    first_payload = _read_latest_evidence(evidence_dir)

    second = _run(tmp_path, "--dry-run", evidence_dir=evidence_dir)
    assert second.returncode == 0, second.stderr
    second_payload = _read_latest_evidence(evidence_dir)

    assert second_payload["previous_app_version"] == first_payload["app_version"]
    assert "COPY FILES INTO" in second_payload["rollback_command"]
    assert first_payload["app_version"] in second_payload["rollback_command"]
    # Regression: the rollback_command's embedded `snow sql -q '...'` must
    # not itself break the JSON it's embedded in (caught during
    # development -- double-quoted -q argument broke parsing until the
    # script switched to single quotes + json_escape).
    json.dumps(second_payload)  # would already have raised in _read_latest_evidence


def test_two_runs_produce_two_distinct_versioned_evidence_files(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    _run(tmp_path, "--dry-run", evidence_dir=evidence_dir)
    _run(tmp_path, "--dry-run", evidence_dir=evidence_dir)

    versioned = sorted((evidence_dir / "edgartools-dev").glob("sha-*.json"))
    # Same repo commit both runs -> same app_version -> the per-version file
    # is the same path both times (overwritten), not two files. This
    # documents that behavior rather than asserting a stronger guarantee
    # the script doesn't actually make.
    assert len(versioned) == 1


def test_non_dry_run_backs_up_previous_release_before_overwriting(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "evidence"

    first = _run(tmp_path, evidence_dir=evidence_dir, with_fake_snow=True)
    assert first.returncode == 0, first.stderr

    log_path = tmp_path / "snow_calls.log"
    # Reset so the assertions below only see the SECOND run's own call
    # sequence -- otherwise the first run's PUTs (no backup expected: there
    # was no previous release yet) would make an index-order comparison
    # meaningless across both runs combined.
    log_path.unlink()

    second = _run(tmp_path, evidence_dir=evidence_dir, with_fake_snow=True)
    assert second.returncode == 0, second.stderr

    log = log_path.read_text(encoding="utf-8")
    # Second run must have issued a COPY FILES backup before the PUTs that
    # overwrite the stage root (GH-247: "retains a prior rollback target").
    assert "COPY FILES INTO" in log
    assert "PUT " in log
    assert log.index("COPY FILES INTO") < log.index("PUT ")


def test_environment_variable_overrides_are_honored(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DASHBOARD_EVIDENCE_DIR"] = str(tmp_path / "evidence")
    env["DASHBOARD_ENVIRONMENT"] = "custom-env-label"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--skip-tests"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(
        (tmp_path / "evidence" / "custom-env-label" / "latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["environment"] == "custom-env-label"


def test_unknown_argument_fails_fast(tmp_path: Path) -> None:
    result = _run(tmp_path, "--not-a-real-flag")
    assert result.returncode != 0
    assert "Unknown argument" in result.stderr
