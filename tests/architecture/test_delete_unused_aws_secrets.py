from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "delete_unused_aws_secrets.py"
SPEC = importlib.util.spec_from_file_location("delete_unused_aws_secrets", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _metadata(name: str, *, last_accessed: str | None = None) -> dict[str, object]:
    policy = module.approved_retirements("prod")[name]
    return {
        "Name": name,
        "ARN": f"arn:aws:secretsmanager:us-east-1:690839588395:secret:{name}-ABC123",
        "LastAccessedDate": last_accessed,
        "RotationEnabled": False,
        "ReplicationStatus": [],
        "Tags": [
            {"Key": "Project", "Value": "edgartools"},
            {"Key": "Environment", "Value": "prod"},
            {"Key": policy.required_tag_key, "Value": policy.required_tag_value},
        ],
    }


@pytest.mark.parametrize(
    "name",
    [
        "edgartools-prod-runner-credentials",
        "edgartools-prod/mdm/api_keys",
        "edgartools-prod/mdm/neo4j",
    ],
)
def test_only_reviewed_prod_secret_names_are_approved(name: str) -> None:
    assert name in module.approved_retirements("prod")


def test_active_secret_is_never_approved() -> None:
    assert "edgartools-prod/mdm/postgres_dsn" not in module.approved_retirements("prod")
    assert "edgartools-prod/mdm/snowflake" not in module.approved_retirements("prod")
    assert "edgartools-prod-edgar-identity" not in module.approved_retirements("prod")


def test_candidate_is_eligible_only_with_empty_unreferenced_metadata() -> None:
    name = "edgartools-prod/mdm/neo4j"
    result = module.assess_candidate(
        name=name,
        environment="prod",
        expected_account_id="690839588395",
        region="us-east-1",
        metadata=_metadata(name),
        versions=[],
        resource_policy=None,
        references=[],
    )

    assert result["eligible"] is True
    assert result["blockers"] == []


@pytest.mark.parametrize(
    ("overrides", "versions", "resource_policy", "references", "blocker"),
    [
        (
            {"LastAccessedDate": "2026-09-05T00:00:00Z"},
            [],
            None,
            [],
            "has_access_history",
        ),
        ({}, [{"VersionId": "v1"}], None, [], "has_secret_versions"),
        ({}, [], "{}", [], "has_resource_policy"),
        ({}, [], None, ["ecs:family:1"], "has_live_reference"),
        ({"RotationEnabled": True}, [], None, [], "rotation_enabled"),
        ({"ReplicationStatus": [{"Region": "us-west-2"}]}, [], None, [], "has_replica"),
    ],
)
def test_candidate_fails_closed_on_any_usage_signal(
    overrides: dict[str, object],
    versions: list[dict[str, str]],
    resource_policy: str | None,
    references: list[str],
    blocker: str,
) -> None:
    name = "edgartools-prod/mdm/neo4j"
    metadata = _metadata(name)
    metadata.update(overrides)

    result = module.assess_candidate(
        name=name,
        environment="prod",
        expected_account_id="690839588395",
        region="us-east-1",
        metadata=metadata,
        versions=versions,
        resource_policy=resource_policy,
        references=references,
    )

    assert result["eligible"] is False
    assert blocker in result["blockers"]


def test_candidate_requires_the_expected_account_region_and_tags() -> None:
    name = "edgartools-prod-runner-credentials"
    metadata = _metadata(name)
    metadata["ARN"] = (
        "arn:aws:secretsmanager:us-west-2:111111111111:secret:"
        "edgartools-prod-runner-credentials-ABC123"
    )
    metadata["Tags"] = []

    result = module.assess_candidate(
        name=name,
        environment="prod",
        expected_account_id="690839588395",
        region="us-east-1",
        metadata=metadata,
        versions=[],
        resource_policy=None,
        references=[],
    )

    assert result["eligible"] is False
    assert {
        "wrong_account_or_region",
        "missing_project_tag",
        "missing_environment_tag",
        "missing_retirement_tag",
    }.issubset(result["blockers"])


def test_apply_requires_confirmation_and_an_all_eligible_plan() -> None:
    eligible = [{"name": "one", "eligible": True}]
    blocked = [*eligible, {"name": "two", "eligible": False}]

    with pytest.raises(RuntimeError, match="confirmation"):
        module.require_apply_ready(eligible, confirmed=False)
    with pytest.raises(RuntimeError, match="ineligible"):
        module.require_apply_ready(blocked, confirmed=True)


def test_terraform_state_must_have_forgotten_every_selected_resource() -> None:
    names = list(module.approved_retirements("prod"))
    state = {
        "module.runtime.aws_secretsmanager_secret.runner_credentials",
        "module.runtime.aws_secretsmanager_secret.mdm_neo4j",
    }

    blockers = module.terraform_state_blockers(names, "prod", state)

    assert blockers == {
        "edgartools-prod-runner-credentials": ["still_managed_by_terraform"],
        "edgartools-prod/mdm/neo4j": ["still_managed_by_terraform"],
    }


def test_recovery_window_is_fixed_at_thirty_days() -> None:
    assert module.RECOVERY_WINDOW_DAYS == 30


def test_terraform_forgets_retired_containers_without_destroying_them() -> None:
    runtime_main = (
        REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf"
    ).read_text()
    runtime_outputs = (
        REPO_ROOT
        / "infra"
        / "terraform"
        / "modules"
        / "warehouse_runtime"
        / "outputs.tf"
    ).read_text()

    for policy in module.RETIREMENT_POLICIES:
        resource_name = policy.terraform_address.rsplit(".", 1)[-1]
        assert (
            f'resource "aws_secretsmanager_secret" "{resource_name}"'
            not in runtime_main
        )
        assert f"from = aws_secretsmanager_secret.{resource_name}" in runtime_main
        assert f'output "{resource_name}_secret_arn"' not in runtime_outputs


def test_access_roots_no_longer_grant_retired_secret_access() -> None:
    for environment in ("dev", "prod"):
        access_main = (
            REPO_ROOT
            / "infra"
            / "terraform"
            / "access"
            / "aws"
            / "accounts"
            / environment
            / "main.tf"
        ).read_text()
        account_outputs = (
            REPO_ROOT / "infra" / "terraform" / "accounts" / environment / "outputs.tf"
        ).read_text()
        for retired in ("runner_credentials", "mdm_neo4j", "mdm_api_keys"):
            assert f"{retired}_secret_arn" not in access_main
            assert f'output "{retired}_secret_arn"' not in account_outputs


def test_repository_reference_scan_finds_stale_operational_lookup(
    tmp_path: Path,
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "infra" / "scripts").mkdir(parents=True)
    (tmp_path / "edgar_warehouse").mkdir()
    stale = tmp_path / "scripts" / "stale.py"
    stale.write_text('secret = "edgartools-prod/mdm/neo4j"\n')

    blockers = module.repository_reference_blockers(
        ["edgartools-prod/mdm/neo4j"], "prod", tmp_path
    )

    assert blockers == {"edgartools-prod/mdm/neo4j": ["scripts/stale.py:1"]}


def test_current_operational_sources_do_not_reference_retired_secret_names() -> None:
    blockers = module.repository_reference_blockers(
        list(module.approved_retirements("prod")), "prod", REPO_ROOT
    )

    assert blockers == {}
