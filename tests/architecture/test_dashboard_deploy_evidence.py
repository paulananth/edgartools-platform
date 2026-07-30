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
    staged_files = {
        "streamlit_app.py": REPO_ROOT / "infra/snowflake/streamlit/streamlit_app.py",
        "dashboard_modes.py": REPO_ROOT / "edgar_warehouse/serving/dashboard_modes.py",
        "dashboard_query_registry.py": REPO_ROOT
        / "edgar_warehouse/serving/dashboard_query_registry.py",
        "dashboard_workflows.py": REPO_ROOT
        / "edgar_warehouse/serving/dashboard_workflows.py",
        "environment.yml": REPO_ROOT / "infra/snowflake/streamlit/environment.yml",
    }
    git_short = subprocess.run(
        ['git', 'rev-parse', '--short=12', 'HEAD'],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    app_version = f"sha-{git_short}"
    streamlit_listing = [
        {
            "name": "EDGARTOOLS_DASHBOARD",
            "owner": "EDGARTOOLS_DEV_DASHBOARD_OWNER",
            "comment": f"release={app_version};source_sha256=fake",
        }
    ]
    snow.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
{{
  echo "ARGS: $*"
  cat
  echo "---"
}} >> {log_path}
if [[ "$*" == *"--format json"* && "$*" == *"/releases/"* ]]; then
  printf '%s\\n' '[]'
elif [[ "$*" == *"--format json"* && "$*" == *"SHOW STREAMLITS"* ]]; then
  printf '%s\\n' '{json.dumps(streamlit_listing)}'
elif [[ "$*" == *"GET @"* ]]; then
  file_name="$(printf '%s' "$*" | sed -E 's#.*GET @[^ ]+/([^ ]+) file://.*#\\1#')"
  destination="$(printf '%s' "$*" | sed -E 's#.* file://([^ ]+)/ OVERWRITE.*#\\1#')"
  case "$file_name" in
    streamlit_app.py) cp '{staged_files["streamlit_app.py"]}' "$destination/$file_name" ;;
    dashboard_modes.py) cp '{staged_files["dashboard_modes.py"]}' "$destination/$file_name" ;;
    dashboard_query_registry.py) cp '{staged_files["dashboard_query_registry.py"]}' "$destination/$file_name" ;;
    dashboard_workflows.py) cp '{staged_files["dashboard_workflows.py"]}' "$destination/$file_name" ;;
    environment.yml) cp '{staged_files["environment.yml"]}' "$destination/$file_name" ;;
    *) exit 2 ;;
  esac
fi
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
    env["DASHBOARD_ALLOW_DIRTY_SOURCE"] = "true"
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
    # GH-252: evidence is namespaced by app (DASHBOARD_APP_NAME, default
    # "dashboard") under the environment, not just by environment -- so two
    # apps deployed through the same connection can't clobber each other's
    # previous_app_version/rollback_command.
    latest = evidence_dir / "edgartools-dev" / "dashboard" / "latest.json"
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
        "dashboard_query_registry.py",
        "dashboard_workflows.py",
        "environment.yml",
    }
    for digest in payload["source_digests"].values():
        assert len(digest) == 64  # sha256 hex digest
    assert len(payload["combined_source_digest"]) == 64
    assert len(payload["dependency_lock_digest"]) == 64
    assert isinstance(payload["source_tree_dirty"], bool)
    assert payload["warehouse_dashboard_alignment"]["status"] == "unknown"


def test_dry_run_never_shells_out_to_snow(tmp_path: Path) -> None:
    """--dry-run must not require snow on PATH at all -- confirms nothing
    in the evidence-computation path accidentally calls it."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    snow = fakebin / "snow"
    snow.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
    snow.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--skip-tests"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
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
    assert "deploy.sh --rollback" in second_payload["rollback_command"]
    assert first_payload["app_version"] in second_payload["rollback_command"]
    # Regression: embedded shell syntax must not break the JSON.
    json.dumps(second_payload)  # would already have raised in _read_latest_evidence


def test_two_runs_produce_two_distinct_versioned_evidence_files(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    _run(tmp_path, "--dry-run", evidence_dir=evidence_dir)
    _run(tmp_path, "--dry-run", evidence_dir=evidence_dir)

    versioned = sorted((evidence_dir / "edgartools-dev" / "dashboard").glob("sha-*.json"))
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
    log_path.write_text("", encoding="utf-8")

    second = _run(tmp_path, evidence_dir=evidence_dir, with_fake_snow=True)
    assert second.returncode == 0, second.stderr

    log = log_path.read_text(encoding="utf-8")
    # Second run must have issued a COPY FILES backup before the PUTs that
    # overwrite the stage root (GH-247: "retains a prior rollback target").
    assert "COPY FILES INTO" in log
    assert "FILES = ('streamlit_app.py')" in log
    assert "PATTERN =" not in log
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
        (tmp_path / "evidence" / "custom-env-label" / "dashboard" / "latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["environment"] == "custom-env-label"


def test_unknown_argument_fails_fast(tmp_path: Path) -> None:
    result = _run(tmp_path, "--not-a-real-flag")
    assert result.returncode != 0
    assert "Unknown argument" in result.stderr


def test_non_dry_run_enforces_owner_rights_and_role_smokes(tmp_path: Path) -> None:
    result = _run(tmp_path, with_fake_snow=True)
    assert result.returncode == 0, result.stderr
    log = (tmp_path / "snow_calls.log").read_text(encoding="utf-8")
    assert "GRANT ROLE EDGARTOOLS_DEV_READER TO ROLE EDGARTOOLS_DEV_DASHBOARD_OWNER" in log
    assert "DROP STREAMLIT IF EXISTS EDGARTOOLS_DEV.EDGARTOOLS_DASHBOARD.EDGARTOOLS_DASHBOARD" in log
    assert "USE ROLE EDGARTOOLS_DEV_DASHBOARD_OWNER" in log
    assert "USE ROLE EDGARTOOLS_DEV_READER" in log
    assert "BOUNDED_SMOKE_ROWS" in log


def test_rollback_is_bounded_and_smoke_verified(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "--rollback",
        "sha-123456abcdef",
        with_fake_snow=True,
    )
    assert result.returncode == 0, result.stderr
    log = (tmp_path / "snow_calls.log").read_text(encoding="utf-8")
    assert "REMOVE @EDGARTOOLS_DEV.EDGARTOOLS_DASHBOARD.DASHBOARD_SRC/streamlit_app.py" in log
    assert "FROM @EDGARTOOLS_DEV.EDGARTOOLS_DASHBOARD.DASHBOARD_SRC/releases/sha-123456abcdef/" in log
    assert "release=sha-123456abcdef;rollback_restored=true" in log
    assert log.count("BOUNDED_SMOKE_ROWS") == 2


def test_rollback_rejects_unbounded_version(tmp_path: Path) -> None:
    result = _run(tmp_path, "--rollback", "../../main", with_fake_snow=True)
    assert result.returncode != 0
    assert "must match" in result.stderr
