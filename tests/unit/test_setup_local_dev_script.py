from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "setup-local-dev.sh"
BASH = shutil.which("bash") or "/bin/bash"


class FakeToolContext:
    def __init__(self, testcase: unittest.TestCase) -> None:
        self.testcase = testcase
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.log_path = self.root / "commands.log"
        self.log_path.write_text("", encoding="utf-8")

    def __enter__(self) -> "FakeToolContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.tempdir.cleanup()

    def add_tool(self, name: str, body: str) -> None:
        tool_path = self.bin_dir / name
        tool_path.write_text(
            f"#!{BASH}\n"
            "set -u\n"
            "log() { printf '%s\\n' \"$1\" >> \"$SETUP_TEST_COMMAND_LOG\"; }\n"
            f"{body}\n",
            encoding="utf-8",
        )
        tool_path.chmod(tool_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def add_standard_success_tools(
        self,
        *,
        omit: Iterable[str] | None = None,
        python_version: str = "3.12.4",
        aws_version: str = "aws-cli/2.17.0 Python/3.12.4 Linux/6 botocore/2.0.0",
        terraform_version: str = "Terraform v1.14.9",
        docker_info_exit: int = 0,
    ) -> None:
        omitted = set(omit or set())
        tools = {
            "bash": "if [ \"${1:-}\" = \"--version\" ]; then echo 'GNU bash, version 5.2.0'; fi",
            "git": "if [ \"${1:-}\" = \"--version\" ]; then echo 'git version 2.45.0'; else log \"git $*\"; fi",
            "python3": f"echo '{python_version}'",
            "uv": "if [ \"${1:-}\" = \"--version\" ]; then echo 'uv 0.5.0'; else log \"uv $*\"; fi",
            "gh": "if [ \"${1:-}\" = \"--version\" ]; then echo 'gh version 2.60.0'; else log \"gh $*\"; fi",
            "aws": (
                f"if [ \"${{1:-}}\" = \"--version\" ]; then echo '{aws_version}'; "
                "else log \"aws $*\"; echo '{\"Account\":\"123456789012\",\"Arn\":\"arn:aws:iam::123456789012:user/test\"}'; fi"
            ),
            "terraform": f"if [ \"${{1:-}}\" = \"version\" ]; then echo '{terraform_version}'; else log \"terraform $*\"; fi",
            "snow": "if [ \"${1:-}\" = \"--version\" ]; then echo 'snowflake-cli 3.4.0'; else log \"snow $*\"; echo 'connection'; fi",
            "docker": (
                "if [ \"${1:-}\" = \"--version\" ]; then echo 'Docker version 27.1.1, build test'; exit 0; fi\n"
                "if [ \"${1:-}\" = \"info\" ]; then log 'docker info'; "
                f"exit {docker_info_exit}; fi\n"
                "log \"docker $*\""
            ),
        }
        for name, body in tools.items():
            if name not in omitted:
                self.add_tool(name, body)

    def clear_command_log(self) -> None:
        self.log_path.write_text("", encoding="utf-8")

    def command_log(self) -> str:
        return self.log_path.read_text(encoding="utf-8")

    def run_setup(self, *args: str, env: dict[str, str] | None = None) -> SimpleNamespace:
        run_env = {
            "PATH": str(self.bin_dir),
            "SETUP_TEST_COMMAND_LOG": str(self.log_path),
            "SETUP_LOCAL_DEV_PLATFORM": "linux",
            "HOME": str(self.root),
            "TMPDIR": str(self.root),
        }
        run_env.update(env or {})
        proc = subprocess.run(
            [BASH, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            env=run_env,
            text=True,
            capture_output=True,
            check=False,
        )
        return SimpleNamespace(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            output=proc.stdout + proc.stderr,
        )


class SetupLocalDevScriptTests(unittest.TestCase):
    def fake_tools(self) -> FakeToolContext:
        return FakeToolContext(self)

    def test_default_mode_diagnoses_without_installing(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools()
            ctx.add_tool("winget", "log \"winget $*\"")

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 0, result.output)
            self.assertIn("Local Software Doctor", result.output)
            self.assertIn("Summary:", result.output)
            self.assertNotIn("winget", ctx.command_log())

    def test_missing_required_tool_reports_failure_and_fix(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools(omit={"gh"})

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 1, result.output)
            self.assertIn("gh", result.output)
            self.assertIn("GitHub CLI", result.output)
            self.assertIn("apt, dnf, or yum", result.output)

    def test_python_older_than_312_fails(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools(python_version="3.11.9")

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 1, result.output)
            self.assertIn("Python 3.12 or later", result.output)

    def test_aws_cli_v1_fails(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools(aws_version="aws-cli/1.32.0 Python/3.11")

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 1, result.output)
            self.assertIn("AWS CLI v2", result.output)

    def test_terraform_outside_114_fails_with_pinned_guidance(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools(terraform_version="Terraform v1.15.0")

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 1, result.output)
            self.assertIn("Terraform 1.14.x", result.output)
            self.assertIn("1.14", result.output)

    def test_terraform_114_before_minimum_patch_fails(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools(terraform_version="Terraform v1.14.7")

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 1, result.output)
            self.assertIn("Terraform 1.14.x", result.output)
            self.assertIn("1.14.8", result.output)

    def test_docker_cli_without_daemon_reports_daemon_failure(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools(docker_info_exit=1)

            result = ctx.run_setup()

            self.assertEqual(result.returncode, 1, result.output)
            self.assertIn("Docker daemon", result.output)

    def test_sync_project_invokes_uv_sync_with_expected_extras(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools()

            result = ctx.run_setup("--sync-project")

            self.assertEqual(result.returncode, 0, result.output)
            self.assertIn("uv sync --extra s3 --extra snowflake", ctx.command_log())

    def test_cloud_checks_only_run_when_requested(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools()

            default_result = ctx.run_setup()
            self.assertEqual(default_result.returncode, 0, default_result.output)
            self.assertNotIn("aws sts get-caller-identity", ctx.command_log())
            self.assertNotIn("snow connection list", ctx.command_log())

            ctx.clear_command_log()
            cloud_result = ctx.run_setup("--check-cloud")
            self.assertEqual(cloud_result.returncode, 0, cloud_result.output)
            self.assertIn("aws sts get-caller-identity", ctx.command_log())
            self.assertIn("snow connection list", ctx.command_log())

    def test_platform_guidance_mentions_expected_package_manager(self) -> None:
        cases = [
            ("windows", "winget"),
            ("macos", "brew"),
            ("linux", "apt, dnf, or yum"),
            ("wsl", "apt, dnf, or yum"),
        ]
        for platform, expected in cases:
            with self.subTest(platform=platform):
                with self.fake_tools() as ctx:
                    ctx.add_standard_success_tools(omit={"gh"})

                    result = ctx.run_setup(env={"SETUP_LOCAL_DEV_PLATFORM": platform})

                    self.assertEqual(result.returncode, 1, result.output)
                    self.assertIn(expected, result.output)

    def test_unknown_flag_prints_usage_and_exits_two(self) -> None:
        with self.fake_tools() as ctx:
            ctx.add_standard_success_tools()

            result = ctx.run_setup("--bogus")

            self.assertEqual(result.returncode, 2, result.output)
            self.assertIn("Usage:", result.output)


if __name__ == "__main__":
    unittest.main()
