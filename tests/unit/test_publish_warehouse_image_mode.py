"""Publish uses docker build and docker push on Linux and WSL."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "publish-warehouse-image.sh"
WSL_BRIDGE = REPO_ROOT / "infra" / "scripts" / "publish-warehouse-image-wsl-bridge.sh"
BUILDSPEC = REPO_ROOT / "infra" / "codebuild" / "buildspec.publish-warehouse-image.yml"


def _exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _fakes(tmp_path: Path, os_type: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(
        bin_dir / "docker",
        "#!/bin/bash\n"
        "if [[ \"$1\" == info ]]; then printf '%s\\r\\n' \"$FAKE_OS_TYPE\"; exit 0; fi\n"
        "echo \"unexpected docker: $*\" >&2\n"
        "exit 1\n",
    )
    _exe(
        bin_dir / "aws",
        "#!/bin/bash\n"
        "if [[ \"$*\" == *get-caller-identity* ]]; then printf '123456789012\\n'; exit 0; fi\n"
        "if [[ \"$*\" == *create-repository* ]]; then echo stopped-after-daemon-check >&2; exit 42; fi\n"
        "echo \"unexpected aws: $*\" >&2\n"
        "exit 1\n",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_OS_TYPE"] = os_type
    return env


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_help_publishes_with_docker() -> None:
    result = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "--mode <docker|crane>" in result.stdout
    assert "docker build and docker push" in result.stdout
    lowered = result.stdout.lower()
    assert "buildx" not in lowered
    assert "colima" not in lowered


def test_removed_mode_is_rejected_before_docker(tmp_path: Path) -> None:
    env = _fakes(tmp_path, "linux")
    result = _run(
        ["--aws-region", "us-east-1", "--ecr-repository", "example", "--mode", "buildx"],
        env,
    )
    assert result.returncode == 1
    assert "--mode must be docker or crane" in result.stderr
    assert "unexpected docker" not in result.stderr


def test_linux_alias_accepts_wsl_carriage_return(tmp_path: Path) -> None:
    result = _run(
        ["--aws-region", "us-east-1", "--ecr-repository", "example", "--image-tag", "sha-test", "--mode", "linux", "--skip-deps-build"],
        _fakes(tmp_path, "linux"),
    )
    assert result.returncode == 42
    assert "stopped-after-daemon-check" in result.stderr
    assert "Linux Docker daemon" not in result.stderr


def test_non_linux_daemon_stops(tmp_path: Path) -> None:
    result = _run(
        ["--aws-region", "us-east-1", "--ecr-repository", "example", "--mode", "docker"],
        _fakes(tmp_path, "windows"),
    )
    assert result.returncode == 1
    assert "Linux Docker daemon" in result.stderr
    assert "stopped-after-daemon-check" not in result.stderr


def test_callers_publish_with_docker() -> None:
    bridge = WSL_BRIDGE.read_text()
    spec = BUILDSPEC.read_text()
    assert "--mode docker" in bridge
    assert "buildx" not in bridge.lower()
    assert "--mode docker" in spec
    assert "buildx" not in spec.lower()
