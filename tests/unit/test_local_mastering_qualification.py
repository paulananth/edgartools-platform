"""A missing database prerequisite cannot leave a successful report."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/ops/qualify_local_mastering.py"
spec = importlib.util.spec_from_file_location("qualify_local_mastering", PATH)
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def test_missing_postgres_image_fails_before_running_tests(tmp_path, monkeypatch):
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0 if len(calls) == 1 else 1)

    monkeypatch.setattr(qualification.subprocess, "run", command)
    output = tmp_path / "evidence"
    assert not qualification.qualify(output)
    report = json.loads((output / "report.json").read_text())
    assert not report["qualified"]
    assert [s["name"] for s in report["steps"]] == ["docker", "postgres-image"]
    assert not any("pytest" in argv for argv in calls)
    with pytest.raises(FileExistsError):
        qualification.qualify(output)


def test_timeout_keeps_the_gate_incomplete(tmp_path, monkeypatch):
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        if "pytest" in argv:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(qualification.subprocess, "run", command)
    output = tmp_path / "evidence"
    assert not qualification.qualify(output)
    report = json.loads((output / "report.json").read_text())
    assert not report["qualified"]
    assert report["steps"][-1]["error"] == "TimeoutExpired"
    assert "finished_at" not in report


def test_a_skipped_postgres_case_cannot_qualify_the_gate(tmp_path, monkeypatch):
    def command(argv, **kwargs):
        junit = next((arg.split('=', 1)[1] for arg in argv if arg.startswith('--junitxml=')), None)
        if junit:
            Path(junit).write_text('<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>')
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(qualification.subprocess, "run", command)
    output = tmp_path / "evidence"
    assert not qualification.qualify(output)
    report = json.loads((output / "report.json").read_text())
    assert not report["qualified"]
    assert report["steps"][-1]["name"] == 'mastering'
    assert not report["steps"][-1]["passed"]
