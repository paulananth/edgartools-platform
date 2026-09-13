"""Ticket 04: Atlas operator path stays out of CI and off the aggregator."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WIZARD = REPO_ROOT / "infra" / "scripts" / "provision-atlas-decision-projection.sh"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_wizard_is_operator_local_env_not_github_secrets() -> None:
    text = WIZARD.read_text(encoding="utf-8")
    _, _, stages = text.partition("# STAGES")
    assert stages, "wizard is missing the STAGES marker"
    secret_calls = [
        line.strip()
        for line in stages.splitlines()
        if line.strip().startswith("set_secret")
    ]
    assert secret_calls == []
    assert "TOTAL_STAGES=8" in stages
    assert stages.count("\nstage ") == 8
    assert "0.0.0.0/0" in stages
    assert "edgartools_decision" in stages
    assert "edgartools_publisher" in stages
    assert "edgartools_agent" in stages
    assert "MONGO_PUBLISHER_URI" in stages
    assert "MONGO_AGENT_URI" in stages


def test_ci_workflows_still_have_no_atlas_secrets() -> None:
    offenders: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        source = workflow.read_text(encoding="utf-8").lower()
        if any(
            token in source
            for token in ("atlas", "mongodb+srv", "mongo_uri", "mongouri")
        ):
            offenders.append(workflow.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_pymongo_is_not_a_required_dependency() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    required, _, _rest = text.partition("[project.optional-dependencies]")
    assert "pymongo" not in required.lower()


def test_github_actions_do_not_run_mongo_smoke() -> None:
    smoke = "smoke-mongo-decision-projection.py"
    apply = "apply-mongo-decision-schema.py"
    hits = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        source = workflow.read_text(encoding="utf-8")
        if smoke in source or apply in source:
            hits.append(workflow.relative_to(REPO_ROOT).as_posix())
    assert hits == []
