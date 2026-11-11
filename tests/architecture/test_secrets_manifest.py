"""Tests for the credential-isolation secrets manifest.

Covers two layers:
1. infra/scripts/secrets-manifest.json itself: the declared secret list is accurate.
2. infra/scripts/lib/secrets-manifest.sh's secrets_manifest_name(): the shared lookup that fails loudly on an
   undeclared name.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "infra" / "scripts" / "secrets-manifest.json"
LIB_PATH = REPO_ROOT / "infra" / "scripts" / "lib" / "secrets-manifest.sh"

EXPECTED_NAMES = {
    "mdm/postgres_dsn",
    "mdm/snowflake",
    "dbt/snowflake",
}

def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())

def test_manifest_declares_exactly_the_three_active_namespaced_secrets():
    manifest = _load_manifest()
    names = {entry["name"] for entry in manifest["secrets"]}
    assert names == EXPECTED_NAMES

def test_manifest_entry_shape_is_consistent():
    manifest = _load_manifest()
    for entry in manifest["secrets"]:
        assert set(entry) == {
            "name",
            "description",
            "terraform_resource",
            "populated_in_prod",
        }
        assert isinstance(entry["description"], str) and entry["description"]
        assert isinstance(entry["populated_in_prod"], bool)

def test_dbt_snowflake_entry_has_no_terraform_resource():
    manifest = _load_manifest()
    entry = next(e for e in manifest["secrets"] if e["name"] == "dbt/snowflake")
    assert entry["terraform_resource"] is None
    assert entry["populated_in_prod"] is True

# --- infra/scripts/lib/secrets-manifest.sh -----------------------------------

def _run_lookup(key: str, manifest_path: Path = MANIFEST_PATH) -> subprocess.CompletedProcess[str]:
    script = f'source "{LIB_PATH}"; secrets_manifest_name "{key}"'
    env = os.environ.copy()
    env["SECRETS_MANIFEST_PATH"] = str(manifest_path)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
    )

def test_secrets_manifest_name_returns_a_declared_name_unchanged():
    result = _run_lookup("mdm/postgres_dsn")
    assert result.returncode == 0
    assert result.stdout.strip() == "mdm/postgres_dsn"

def test_secrets_manifest_name_fails_loudly_on_an_undeclared_name():
    result = _run_lookup("not/a/real/secret")
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert "not/a/real/secret" in result.stderr
    assert "is not declared" in result.stderr

def test_secrets_manifest_name_fails_loudly_when_the_manifest_file_is_missing(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    result = _run_lookup("mdm/postgres_dsn", manifest_path=missing)
    assert result.returncode == 1
    assert "not found" in result.stderr
