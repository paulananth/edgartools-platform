from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "dashboard-release-control.py"


def _load():
    spec = importlib.util.spec_from_file_location("dashboard_release_control", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pruning_uses_exact_validated_versions_and_retains_newest() -> None:
    module = _load()
    listing = [
        {"name": "dashboard_src/releases/sha-111111111111/app.py", "last_modified": "2026-01-01"},
        {"name": "dashboard_src/releases/sha-222222222222/app.py", "last_modified": "2026-02-01"},
        {"name": "dashboard_src/releases/sha-333333333333/app.py", "last_modified": "2026-03-01"},
        {"name": "dashboard_src/releases/not-safe/app.py", "last_modified": "2025-01-01"},
        {"name": "dashboard_src/streamlit_app.py", "last_modified": "2026-04-01"},
    ]
    assert module.prune_candidates(listing, retain=2) == ["sha-111111111111"]


@pytest.mark.parametrize("retain", [0, 51])
def test_pruning_rejects_unsafe_retention(retain: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 50"):
        _load().prune_candidates([], retain=retain)


def test_drift_is_visible_against_warehouse_evidence(tmp_path: Path) -> None:
    module = _load()
    dashboard_commit = "1" * 40
    evidence = tmp_path / "warehouse.json"
    evidence.write_text(json.dumps({"commit_sha": "2" * 40}), encoding="utf-8")

    result = module.drift_status(dashboard_commit, evidence)

    assert result["status"] == "drift"
    assert result["dashboard_git_commit"] == dashboard_commit
    assert result["warehouse_git_commit"] == "2" * 40


def test_missing_warehouse_evidence_is_unknown_not_aligned() -> None:
    result = _load().drift_status("1" * 40, None)
    assert result["status"] == "unknown"
    assert result["warehouse_git_commit"] is None


def test_staged_release_verification_checks_digest_and_size(tmp_path: Path) -> None:
    module = _load()
    source = tmp_path / "source"
    source.mkdir()
    app = source / "streamlit_app.py"
    app.write_text("print('ok')\n", encoding="utf-8")
    digest = __import__("hashlib").md5(
        app.read_bytes(), usedforsecurity=False
    ).hexdigest()
    listing = [
        {
            "name": "dashboard_src/streamlit_app.py",
            "size": len(app.read_bytes()),
            "md5": digest,
        }
    ]

    assert module.verify_staged(listing, source, ["streamlit_app.py"]) == {
        "streamlit_app.py": digest
    }


def test_staged_release_verification_fails_on_digest_mismatch(tmp_path: Path) -> None:
    module = _load()
    (tmp_path / "app.py").write_text("x", encoding="utf-8")
    listing = [{"name": "stage/app.py", "size": 1, "md5": "0" * 32}]
    with pytest.raises(ValueError, match="digest mismatch"):
        module.verify_staged(listing, tmp_path, ["app.py"])


def test_streamlit_verification_binds_owner_and_release() -> None:
    listing = [
        {
            "name": "EDGARTOOLS_DASHBOARD",
            "owner": "EDGARTOOLS_PROD_DASHBOARD_OWNER",
            "comment": "release=sha-123456abcdef;source_sha256=abc",
        }
    ]
    result = _load().verify_streamlit(
        listing,
        expected_name="EDGARTOOLS_DASHBOARD",
        expected_owner="EDGARTOOLS_PROD_DASHBOARD_OWNER",
        expected_release="sha-123456abcdef",
    )
    assert result["owner"] == "EDGARTOOLS_PROD_DASHBOARD_OWNER"


def test_streamlit_verification_rejects_accountadmin_owner() -> None:
    listing = [
        {
            "name": "EDGARTOOLS_DASHBOARD",
            "owner": "ACCOUNTADMIN",
            "comment": "release=sha-123456abcdef",
        }
    ]
    with pytest.raises(ValueError, match="owner mismatch"):
        _load().verify_streamlit(
            listing,
            expected_name="EDGARTOOLS_DASHBOARD",
            expected_owner="EDGARTOOLS_PROD_DASHBOARD_OWNER",
            expected_release="sha-123456abcdef",
        )
