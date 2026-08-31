"""Thin-wrapper tests for ops-cost-control ticket 05's CLI.

The pure decision logic is covered by tests/application/test_ecr_rollback_*.py;
this file covers only what actually lives in the CLI module itself:
argument-parsing wiring and the recursive ASL-walker that finds
TaskDefinition references (including inside nested Map/Parallel branches),
which is genuinely CLI-module logic even though it needs no AWS I/O to test.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from edgar_warehouse.scripts import ecr_rollback_cli as cli


class _Paginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **_kwargs):
        return iter(self.pages)


def test_gather_ecr_images_normalizes_aws_timestamps_to_utc():
    class FakeEcr:
        def get_paginator(self, name):
            assert name == "describe_images"
            return _Paginator(
                [
                    {
                        "imageDetails": [
                            {
                                "imageDigest": "sha256:" + "a" * 64,
                                "imagePushedAt": datetime(
                                    2026,
                                    8,
                                    28,
                                    9,
                                    30,
                                    tzinfo=timezone(-timedelta(hours=4)),
                                ),
                            }
                        ]
                    }
                ]
            )

    images, _counts = cli.gather_ecr_images(FakeEcr(), "edgartools-prod-images")

    assert images[0]["pushed_at"] == "2026-08-28T13:30:00Z"


def test_walk_task_definition_arns_finds_a_top_level_reference():
    found: set[str] = set()
    definition = {"States": {"RunTask": {"Parameters": {"TaskDefinition": "arn:aws:ecs:us-east-1:1:task-definition/x:1"}}}}
    cli._walk_task_definition_arns(definition, found)
    assert found == {"arn:aws:ecs:us-east-1:1:task-definition/x:1"}


def test_walk_task_definition_arns_finds_references_nested_inside_map_and_parallel_branches():
    found: set[str] = set()
    branch_a = {"States": {"Leaf": {"Parameters": {"TaskDefinition": "arn:aws:ecs:us-east-1:1:task-definition/a:1"}}}}
    branch_b = {"States": {"Leaf2": {"Parameters": {"TaskDefinition": "arn:aws:ecs:us-east-1:1:task-definition/b:2"}}}}
    definition = {
        "States": {
            "Fan": {
                "Type": "Map",
                "Iterator": {
                    "States": {
                        "Branch": {
                            "Type": "Parallel",
                            "Branches": [branch_a, branch_b],
                        }
                    }
                },
            }
        }
    }
    cli._walk_task_definition_arns(definition, found)
    assert found == {
        "arn:aws:ecs:us-east-1:1:task-definition/a:1",
        "arn:aws:ecs:us-east-1:1:task-definition/b:2",
    }


def test_walk_task_definition_arns_ignores_non_arn_task_definition_values():
    """A tag-only TaskDefinition (e.g. a States.Format(...) expression that
    hasn't been resolved) must not be silently treated as a real reference."""
    found: set[str] = set()
    definition = {"Parameters": {"TaskDefinition": "States.Format('{}', $.some_value)"}}
    cli._walk_task_definition_arns(definition, found)
    assert found == set()


def test_walk_task_definition_arns_reports_an_unresolved_dynamic_reference():
    found: set[str] = set()
    unresolved: set[str] = set()
    expression = "States.Format('{}', $.some_value)"
    definition = {"Parameters": {"TaskDefinition": expression}}

    cli._walk_task_definition_arns(definition, found, unresolved)

    assert found == set()
    assert unresolved == {expression}


def test_walk_task_definition_arns_reports_task_definition_jsonpath_field():
    found: set[str] = set()
    unresolved: set[str] = set()
    definition = {"Parameters": {"TaskDefinition.$": "$.task_definition_arn"}}

    cli._walk_task_definition_arns(definition, found, unresolved)

    assert found == set()
    assert unresolved == {"$.task_definition_arn"}


def test_gather_task_definitions_preserves_out_of_repository_images_for_fail_closed_audit():
    task_definition_arn = "arn:aws:ecs:us-east-1:1:task-definition/edgartools-prod-small:1"

    class FakeEcs:
        def get_paginator(self, name):
            if name == "list_task_definition_families":
                return _Paginator(
                    [
                        {
                            "families": [
                                "edgartools-prod-small",
                                "unrelated-family",
                            ]
                        }
                    ]
                )
            if name == "list_task_definitions":
                class DefinitionPaginator:
                    def paginate(self, **kwargs):
                        assert kwargs["familyPrefix"] == "edgartools-prod-small"
                        return iter([{"taskDefinitionArns": [task_definition_arn]}])

                return DefinitionPaginator()
            raise AssertionError(name)

        def describe_task_definition(self, *, taskDefinition):
            assert taskDefinition == task_definition_arn
            return {
                "taskDefinition": {
                    "taskDefinitionArn": task_definition_arn,
                    "containerDefinitions": [
                        {"image": "1.dkr.ecr.us-east-1.amazonaws.com/unexpected@sha256:" + "a" * 64}
                    ],
                }
            }

    definitions, _counts = cli.gather_task_definitions(FakeEcs(), "edgartools-prod")

    assert definitions[0]["images"] == [
        "1.dkr.ecr.us-east-1.amazonaws.com/unexpected@sha256:" + "a" * 64
    ]
    assert _counts["task_definition_families_matched"] == 1


def test_gather_workflows_reports_dynamic_task_definition_references():
    state_machine_arn = "arn:aws:states:us-east-1:1:stateMachine:edgartools-prod-dynamic"

    class WorkingFakeSfn:
        def get_paginator(self, name):
            assert name == "list_state_machines"
            return _Paginator(
                [{"stateMachines": [{"name": "edgartools-prod-dynamic", "stateMachineArn": state_machine_arn}]}]
            )

        def describe_state_machine(self, *, stateMachineArn):
            assert stateMachineArn == state_machine_arn
            return {
                "definition": '{"States":{"Run":{"Parameters":{"TaskDefinition":"States.Format(\'{}\', $.task_definition)"}}}}'
            }

    workflows, errors, _counts = cli.gather_workflow_task_definition_arns(
        WorkingFakeSfn(), "edgartools-prod"
    )

    assert workflows == {"edgartools-prod-dynamic": []}
    assert errors == [
        (
            "state machine 'edgartools-prod-dynamic' has unresolved TaskDefinition reference "
            "\"States.Format('{}', $.task_definition)\""
        )
    ]


def test_gather_live_tasks_fails_closed_when_the_scoped_cluster_is_missing():
    class FakeEcs:
        def get_paginator(self, name):
            assert name == "list_clusters"
            return _Paginator(
                [
                    {
                        "clusterArns": [
                            "arn:aws:ecs:us-east-1:1:cluster/some-other-cluster"
                        ]
                    }
                ]
            )

    live_tasks, services, errors, counts = cli.gather_ecs_clusters_tasks(
        FakeEcs(),
        "edgartools-prod-warehouse",
        "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images",
    )

    assert live_tasks == []
    assert services == []
    assert errors == [
        "expected exactly one ECS cluster named 'edgartools-prod-warehouse', found 0"
    ]
    assert counts["ecs_clusters_matched"] == 0


def test_gather_live_tasks_includes_transitioning_tasks_and_reports_describe_failures():
    cluster_arn = "arn:aws:ecs:us-east-1:1:cluster/edgartools-prod-warehouse"
    running_arn = f"{cluster_arn}/running"
    transitioning_arn = f"{cluster_arn}/transitioning"
    stopped_arn = f"{cluster_arn}/stopped"

    class FakeEcs:
        def get_paginator(self, name):
            if name == "list_clusters":
                return _Paginator([{"clusterArns": [cluster_arn]}])
            if name == "list_services":
                return _Paginator([{"serviceArns": []}])
            if name == "list_tasks":
                class TaskPaginator:
                    def paginate(self, **kwargs):
                        assert kwargs["cluster"] == cluster_arn
                        if kwargs["desiredStatus"] == "RUNNING":
                            return iter([{"taskArns": [running_arn]}])
                        assert kwargs["desiredStatus"] == "STOPPED"
                        return iter([{"taskArns": [transitioning_arn, stopped_arn]}])

                return TaskPaginator()
            raise AssertionError(name)

        def describe_tasks(self, *, cluster, tasks):
            assert cluster == cluster_arn
            assert tasks == sorted([running_arn, transitioning_arn, stopped_arn])
            return {
                "tasks": [
                    {
                        "taskArn": running_arn,
                        "taskDefinitionArn": "arn:aws:ecs:us-east-1:1:task-definition/prod:1",
                        "lastStatus": "RUNNING",
                        "containers": [
                            {
                                "image": "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images@sha256:"
                                + "a" * 64,
                                "imageDigest": "sha256:" + "a" * 64,
                            }
                        ],
                    },
                    {
                        "taskArn": transitioning_arn,
                        "taskDefinitionArn": "arn:aws:ecs:us-east-1:1:task-definition/prod:2",
                        "lastStatus": "DEPROVISIONING",
                        "containers": [
                            {
                                "image": "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images@sha256:"
                                + "b" * 64,
                                "imageDigest": "sha256:" + "b" * 64,
                            }
                        ],
                    },
                    {
                        "taskArn": stopped_arn,
                        "taskDefinitionArn": "arn:aws:ecs:us-east-1:1:task-definition/prod:3",
                        "lastStatus": "STOPPED",
                        "containers": [],
                    },
                ],
                "failures": [{"arn": "missing-task", "reason": "MISSING"}],
            }

    live_tasks, services, errors, counts = cli.gather_ecs_clusters_tasks(
        FakeEcs(),
        "edgartools-prod-warehouse",
        "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images",
    )

    assert [task["task_arn"] for task in live_tasks] == [
        running_arn,
        transitioning_arn,
    ]
    assert live_tasks[0]["images"][0]["repository"] == (
        "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images"
    )
    assert services == []
    assert errors == ["ECS DescribeTasks failure for 'missing-task': MISSING"]
    assert counts["ecs_list_tasks_pages"] == 2
    assert counts["ecs_describe_tasks_failures"] == 1


def test_gather_live_tasks_finds_prod_task_references_in_another_cluster():
    expected_cluster = "arn:aws:ecs:us-east-1:1:cluster/edgartools-prod-warehouse"
    other_cluster = "arn:aws:ecs:us-east-1:1:cluster/shared-operations"
    prod_task_arn = f"{other_cluster}/prod-task"
    tag_pinned_task_arn = f"{other_cluster}/tag-pinned-task"

    class FakeEcs:
        def get_paginator(self, name):
            if name == "list_clusters":
                return _Paginator([{"clusterArns": [expected_cluster, other_cluster]}])
            if name == "list_services":
                class ServicePaginator:
                    def paginate(self, **kwargs):
                        if kwargs["cluster"] == other_cluster:
                            return iter(
                                [
                                    {
                                        "serviceArns": [
                                            f"{other_cluster}/generic-zero-scaled-service"
                                        ]
                                    }
                                ]
                            )
                        return iter([{"serviceArns": []}])

                return ServicePaginator()
            if name == "list_tasks":
                class TaskPaginator:
                    def paginate(self, **kwargs):
                        if (
                            kwargs["cluster"] == other_cluster
                            and kwargs["desiredStatus"] == "RUNNING"
                        ):
                            return iter(
                                [{"taskArns": [prod_task_arn, tag_pinned_task_arn]}]
                            )
                        return iter([{"taskArns": []}])

                return TaskPaginator()
            raise AssertionError(name)

        def describe_tasks(self, *, cluster, tasks):
            assert cluster == other_cluster
            assert tasks == [prod_task_arn, tag_pinned_task_arn]
            return {
                "tasks": [
                    {
                        "taskArn": prod_task_arn,
                        "taskDefinitionArn": (
                            "arn:aws:ecs:us-east-1:1:task-definition/"
                            "edgartools-prod-medium:42"
                        ),
                        "lastStatus": "RUNNING",
                        "containers": [
                            {
                                "image": (
                                    "1.dkr.ecr.us-east-1.amazonaws.com/"
                                    "edgartools-prod-images@sha256:" + "c" * 64
                                ),
                                "imageDigest": "sha256:" + "c" * 64,
                            }
                        ],
                    },
                    {
                        "taskArn": tag_pinned_task_arn,
                        "taskDefinitionArn": (
                            "arn:aws:ecs:us-east-1:1:task-definition/"
                            "generic-shared-worker:7"
                        ),
                        "lastStatus": "RUNNING",
                        "containers": [
                            {
                                "image": (
                                    "1.dkr.ecr.us-east-1.amazonaws.com/"
                                    "edgartools-prod-images:warehouse-prod"
                                ),
                                "imageDigest": "sha256:" + "d" * 64,
                            }
                        ],
                    },
                ],
                "failures": [],
            }

    live_tasks, services, errors, counts = cli.gather_ecs_clusters_tasks(
        FakeEcs(),
        "edgartools-prod-warehouse",
        "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images",
    )

    assert [task["task_arn"] for task in live_tasks] == [
        prod_task_arn,
        tag_pinned_task_arn,
    ]
    assert live_tasks[1]["images"][0]["repository"] == (
        "1.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images"
    )
    assert services == [
        {
            "cluster": other_cluster,
            "service_arn": f"{other_cluster}/generic-zero-scaled-service",
        }
    ]
    assert errors == []
    assert counts["ecs_clusters_scanned"] == 2


def test_release_lock_rejects_a_different_owners_token(tmp_path):
    lock_path = tmp_path / "cleanup.lock"
    lock_path.write_text(json.dumps({"token": "owner-token"}), encoding="utf-8")
    deletes: list[tuple[str, str | None]] = []

    class FakeStorage:
        def read_object_version(self, relative_path):
            assert relative_path == "cleanup.lock"
            return SimpleNamespace(exists=True, etag="owner-etag")

        def join(self, relative_path):
            assert relative_path == "cleanup.lock"
            return str(lock_path)

        def delete_object(self, relative_path, *, expected_etag=None):
            deletes.append((relative_path, expected_etag))

    storage = FakeStorage()

    with pytest.raises(RuntimeError, match="ownership changed"):
        cli.release_lock(storage, "cleanup.lock", expected_token="other-token")
    assert deletes == []

    cli.release_lock(storage, "cleanup.lock", expected_token="owner-token")
    assert deletes == [("cleanup.lock", "owner-etag")]


@pytest.mark.parametrize(
    ("handler", "extra_args"),
    [
        (cli.cmd_acquire_lock, {"operator": "deploy:123"}),
        (cli.cmd_release_lock, {"token": None, "force": True}),
        (
            cli.cmd_apply,
            {
                "operator": "operator",
                "plan_hash": "sha256:reviewed",
                "task_definition_batch_size": 100,
            },
        ),
    ],
)
def test_lock_mutations_reject_the_wrong_aws_account_before_storage(
    monkeypatch, handler, extra_args
):
    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "111111111111"}

    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (object(), object(), object(), FakeSts()),
    )
    monkeypatch.setattr(
        cli,
        "_storage",
        lambda _bucket: (_ for _ in ()).throw(
            AssertionError("storage must not be touched for the wrong account")
        ),
    )
    args = SimpleNamespace(
        region="us-east-1",
        account_id="690839588395",
        repository="edgartools-prod-images",
        name_prefix="edgartools-prod",
        registry_bucket="edgartools-prod-warehouse-690839588395",
        registry_path="warehouse/release/ecr_rollback_registry.json",
        lock_path="warehouse/release/ecr_rollback_cleanup.lock",
        **extra_args,
    )

    assert handler(args) == 2


def test_apply_reaudits_between_retirement_and_deletion_and_releases_owned_lock(
    monkeypatch,
):
    events: list[str] = []
    stale_arn = (
        "arn:aws:ecs:us-east-1:690839588395:task-definition/"
        "edgartools-prod-medium:41"
    )
    digest = "sha256:" + "e" * 64

    class FakeSts:
        def get_caller_identity(self):
            events.append("identity")
            return {"Account": "690839588395"}

    class FakeEcs:
        def deregister_task_definition(self, *, taskDefinition):
            assert taskDefinition == stale_arn
            events.append("deregister")

        def describe_task_definition(self, *, taskDefinition):
            assert taskDefinition == stale_arn
            events.append("confirm-inactive")
            return {"taskDefinition": {"status": "INACTIVE"}}

    class FakeEcr:
        def batch_delete_image(self, *, repositoryName, imageIds):
            assert repositoryName == "edgartools-prod-images"
            assert imageIds == [{"imageDigest": digest}]
            events.append("delete")
            return {"imageIds": imageIds, "failures": []}

    reviewed_plan = SimpleNamespace(
        plan_sha256="sha256:reviewed",
        account_id="690839588395",
        region="us-east-1",
        repository="edgartools-prod-images",
        registry_sha256="sha256:registry",
        errors=(),
        fail_closed_reasons=(),
        stale_task_definition_arns=(stale_arn,),
        candidate_digests=(digest,),
    )
    post_retirement_plan = SimpleNamespace(
        account_id="690839588395",
        region="us-east-1",
        repository="edgartools-prod-images",
        registry_sha256="sha256:registry",
        errors=(),
        fail_closed_reasons=(),
        stale_task_definition_arns=(),
        candidate_digests=(digest,),
    )
    plans = iter([reviewed_plan, post_retirement_plan])

    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (FakeEcr(), FakeEcs(), object(), FakeSts()),
    )
    monkeypatch.setattr(cli, "_storage", lambda _bucket: object())
    monkeypatch.setattr(
        cli,
        "acquire_lock",
        lambda _storage, _path, *, operator: events.append("lock") or "owner-token",
    )
    monkeypatch.setattr(
        cli,
        "release_lock",
        lambda _storage, _path, *, expected_token: events.append(
            f"release:{expected_token}"
        ),
    )
    monkeypatch.setattr(cli, "load_registry", lambda *_args, **_kwargs: ({}, None))
    monkeypatch.setattr(
        cli,
        "build_plan",
        lambda **_kwargs: events.append("audit") or next(plans),
    )

    args = SimpleNamespace(
        region="us-east-1",
        account_id="690839588395",
        repository="edgartools-prod-images",
        name_prefix="edgartools-prod",
        registry_bucket="edgartools-prod-warehouse-690839588395",
        registry_path="warehouse/release/ecr_rollback_registry.json",
        lock_path="warehouse/release/ecr_rollback_cleanup.lock",
        operator="operator",
        plan_hash="sha256:reviewed",
        task_definition_batch_size=100,
    )

    assert cli.cmd_apply(args) == 0
    assert events == [
        "identity",
        "lock",
        "audit",
        "deregister",
        "confirm-inactive",
        "audit",
        "delete",
        "release:owner-token",
    ]


def test_apply_aborts_before_delete_when_the_repeated_audit_drifts(monkeypatch):
    events: list[str] = []
    stale_arn = "arn:aws:ecs:us-east-1:1:task-definition/edgartools-prod-medium:41"
    digest = "sha256:" + "f" * 64
    reviewed_plan = SimpleNamespace(
        plan_sha256="sha256:reviewed",
        account_id="690839588395",
        region="us-east-1",
        repository="edgartools-prod-images",
        errors=(),
        fail_closed_reasons=(),
        stale_task_definition_arns=(stale_arn,),
        candidate_digests=(digest,),
    )

    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "690839588395"}

    class FakeEcs:
        def deregister_task_definition(self, **_kwargs):
            events.append("deregister")

        def describe_task_definition(self, **_kwargs):
            return {"taskDefinition": {"status": "INACTIVE"}}

    class FakeEcr:
        def batch_delete_image(self, **_kwargs):
            events.append("delete")
            return {"failures": []}

    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (FakeEcr(), FakeEcs(), object(), FakeSts()),
    )
    monkeypatch.setattr(cli, "_storage", lambda _bucket: object())
    monkeypatch.setattr(cli, "acquire_lock", lambda *_args, **_kwargs: "owner-token")
    monkeypatch.setattr(
        cli,
        "release_lock",
        lambda _storage, _path, *, expected_token: events.append("release"),
    )
    monkeypatch.setattr(cli, "load_registry", lambda *_args, **_kwargs: ({}, None))
    monkeypatch.setattr(cli, "build_plan", lambda **_kwargs: reviewed_plan)
    monkeypatch.setattr(
        cli,
        "post_deregistration_findings",
        lambda *_args, **_kwargs: ["new live reference appeared"],
    )

    args = SimpleNamespace(
        region="us-east-1",
        account_id="690839588395",
        repository="edgartools-prod-images",
        name_prefix="edgartools-prod",
        registry_bucket="edgartools-prod-warehouse-690839588395",
        registry_path="warehouse/release/ecr_rollback_registry.json",
        lock_path="warehouse/release/ecr_rollback_cleanup.lock",
        operator="operator",
        plan_hash="sha256:reviewed",
        task_definition_batch_size=100,
    )

    assert cli.cmd_apply(args) == 2
    assert events == ["deregister", "release"]


def test_apply_reports_successful_deletes_from_a_partially_failed_batch(
    monkeypatch, capsys
):
    first_digest = "sha256:" + "1" * 64
    second_digest = "sha256:" + "2" * 64
    plan = SimpleNamespace(
        plan_sha256="sha256:reviewed",
        account_id="690839588395",
        region="us-east-1",
        repository="edgartools-prod-images",
        errors=(),
        fail_closed_reasons=(),
        stale_task_definition_arns=(),
        candidate_digests=(first_digest, second_digest),
    )

    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "690839588395"}

    class FakeEcr:
        def batch_delete_image(self, **_kwargs):
            return {
                "imageIds": [{"imageDigest": first_digest}],
                "failures": [{"imageId": {"imageDigest": second_digest}}],
            }

    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (FakeEcr(), object(), object(), FakeSts()),
    )
    monkeypatch.setattr(cli, "_storage", lambda _bucket: object())
    monkeypatch.setattr(cli, "acquire_lock", lambda *_args, **_kwargs: "owner-token")
    monkeypatch.setattr(cli, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "load_registry", lambda *_args, **_kwargs: ({}, None))
    monkeypatch.setattr(cli, "build_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(cli, "post_deregistration_findings", lambda *_args, **_kwargs: [])

    args = SimpleNamespace(
        region="us-east-1",
        account_id="690839588395",
        repository="edgartools-prod-images",
        name_prefix="edgartools-prod",
        registry_bucket="edgartools-prod-warehouse-690839588395",
        registry_path="warehouse/release/ecr_rollback_registry.json",
        lock_path="warehouse/release/ecr_rollback_cleanup.lock",
        operator="operator",
        plan_hash="sha256:reviewed",
        task_definition_batch_size=100,
    )

    assert cli.cmd_apply(args) == 2
    assert "after 1 images deleted" in capsys.readouterr().err


def _record_cohort_args():
    return cli.build_parser().parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "record-cohort",
            "--operator", "paul",
            "--candidate-id", "rc-20260811-abc123abc123",
            "--verified-at", "2026-08-11T00:00:00Z",
            "--verification-evidence", "evidence-ref",
            "--warehouse-digest", "sha256:" + "a" * 64,
            "--warehouse-tag", "warehouse-sha-abc123abc123",
            "--warehouse-task-definition-arns",
            "arn:aws:ecs:us-east-1:690839588395:task-definition/edgartools-prod-warehouse:1",
            "--mdm-digest", "sha256:" + "b" * 64,
            "--mdm-tag", "mdm-sha-abc123abc123",
            "--mdm-task-definition-arns",
            "arn:aws:ecs:us-east-1:690839588395:task-definition/edgartools-prod-mdm:1",
        ]
    )


def test_record_cohort_verifies_identity_and_publishes_mirrors_before_registry(monkeypatch):
    events: list[str] = []

    class MissingVersion:
        exists = False
        etag = None

    class FakeStorage:
        def read_object_version(self, _relative_path):
            events.append("registry_read")
            return MissingVersion()

        def write_immutable_bytes(self, _relative_path, _payload):
            events.append("lock_acquire")
            return "lock"

        def write_staged_bytes(self, _relative_path, _payload):
            events.append("registry_stage")
            return "staged-registry"

        def promote_staged(self, _staged, _relative_path, *, expected_etag):
            assert expected_etag is None
            events.append("registry_promote")

        def delete_object(self, _relative_path):
            events.append("lock_release")

    class FakeSts:
        def get_caller_identity(self):
            events.append("identity_check")
            return {"Account": "690839588395"}

    class FakeEcr:
        class exceptions:
            class ImageNotFoundException(Exception):
                pass

        def describe_images(self, *, repositoryName, imageIds):
            assert repositoryName == "edgartools-prod-images"
            tag = imageIds[0]["imageTag"]
            events.append(f"source_tag:{tag}")
            digest = "sha256:" + ("a" if tag.startswith("warehouse-") else "b") * 64
            return {"imageDetails": [{"imageDigest": digest}]}

        def batch_get_image(self, *, repositoryName, imageIds):
            assert repositoryName == "edgartools-prod-images"
            digest = imageIds[0]["imageDigest"]
            events.append(f"manifest:{digest}")
            return {"images": [{"imageManifest": f"manifest-for-{digest}"}]}

        def put_image(self, *, repositoryName, imageTag, imageManifest):
            assert repositoryName == "edgartools-prod-images"
            assert imageManifest.startswith("manifest-for-sha256:")
            events.append(f"mirror:{imageTag}")

    storage = FakeStorage()
    monkeypatch.setattr(cli, "_storage", lambda _bucket: storage)
    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (FakeEcr(), object(), object(), FakeSts()),
    )
    monkeypatch.setattr(
        cli,
        "release_lock",
        lambda _storage, _path, *, expected_token: events.append("lock_release"),
    )

    assert cli.cmd_record_cohort(_record_cohort_args()) == 0

    assert events.index("identity_check") < events.index("lock_acquire")
    mirror_indexes = [index for index, event in enumerate(events) if event.startswith("mirror:")]
    assert mirror_indexes
    assert max(mirror_indexes) < events.index("registry_stage")
    assert events.index("registry_promote") < events.index("lock_release")


def test_record_cohort_rejects_the_wrong_aws_account_before_locking(monkeypatch):
    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "111111111111"}

    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (object(), object(), object(), FakeSts()),
    )
    monkeypatch.setattr(
        cli,
        "_storage",
        lambda _bucket: (_ for _ in ()).throw(AssertionError("storage must not be touched")),
    )

    assert cli.cmd_record_cohort(_record_cohort_args()) == 2


def test_record_cohort_rejects_a_mismatched_source_tag_before_registry_commit(monkeypatch):
    events: list[str] = []

    class MissingVersion:
        exists = False
        etag = None

    class FakeStorage:
        def read_object_version(self, _relative_path):
            events.append("registry_read")
            return MissingVersion()

        def write_immutable_bytes(self, _relative_path, _payload):
            events.append("lock_acquire")
            return "lock"

        def write_staged_bytes(self, _relative_path, _payload):
            events.append("registry_stage")
            return "staged-registry"

        def promote_staged(self, _staged, _relative_path, *, expected_etag):
            events.append("registry_promote")

        def delete_object(self, _relative_path):
            events.append("lock_release")

    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "690839588395"}

    class FakeEcr:
        class exceptions:
            class ImageNotFoundException(Exception):
                pass

        def describe_images(self, *, repositoryName, imageIds):
            return {"imageDetails": [{"imageDigest": "sha256:" + "f" * 64}]}

        def batch_get_image(self, **_kwargs):
            raise AssertionError("mirror publication must not start")

        def put_image(self, **_kwargs):
            raise AssertionError("mirror publication must not start")

    storage = FakeStorage()
    monkeypatch.setattr(cli, "_storage", lambda _bucket: storage)
    monkeypatch.setattr(
        cli,
        "_clients",
        lambda _region: (FakeEcr(), object(), object(), FakeSts()),
    )
    monkeypatch.setattr(
        cli,
        "release_lock",
        lambda _storage, _path, *, expected_token: events.append("lock_release"),
    )

    assert cli.cmd_record_cohort(_record_cohort_args()) == 2
    assert events == ["lock_acquire", "registry_read", "lock_release"]


def test_build_parser_wires_all_three_subcommands():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "plan",
        ]
    )
    assert args.command == "plan"
    assert args.handler is cli.cmd_plan


def test_build_parser_wires_read_only_check_subcommand():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "check",
        ]
    )
    assert args.command == "check"
    assert args.handler is cli.cmd_check


def test_build_parser_apply_requires_plan_hash_and_operator():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "apply",
            "--plan-hash", "sha256:abc",
            "--operator", "paul",
            "--task-definition-batch-size", "50",
        ]
    )
    assert args.command == "apply"
    assert args.plan_hash == "sha256:abc"
    assert args.task_definition_batch_size == 50
    assert args.handler is cli.cmd_apply


def test_build_parser_record_cohort_requires_both_roles():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "record-cohort",
            "--operator", "paul",
            "--candidate-id", "rc-20260811-abc123abc123",
            "--verified-at", "2026-08-11T00:00:00Z",
            "--verification-evidence", "evidence-ref",
            "--warehouse-digest", "sha256:" + "a" * 64,
            "--warehouse-tag", "warehouse-sha-abc123abc123",
            "--warehouse-task-definition-arns", "arn:aws:ecs:us-east-1:690839588395:task-definition/edgartools-prod-warehouse:1",
            "--mdm-digest", "sha256:" + "b" * 64,
            "--mdm-tag", "mdm-sha-abc123abc123",
            "--mdm-task-definition-arns", "arn:aws:ecs:us-east-1:690839588395:task-definition/edgartools-prod-mdm:1",
        ]
    )
    assert args.command == "record-cohort"
    assert args.operator == "paul"
    assert args.handler is cli.cmd_record_cohort


def test_build_parser_wires_explicit_cleanup_lock_acquisition():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "acquire-lock",
            "--operator", "deploy:1234",
        ]
    )
    assert args.command == "acquire-lock"
    assert args.handler is cli.cmd_acquire_lock


@pytest.mark.parametrize(
    ("release_args", "expected_token", "expected_force"),
    [
        (["--token", "owner-token"], "owner-token", False),
        (["--force"], None, True),
    ],
)
def test_build_parser_requires_an_explicit_lock_release_mode(
    release_args, expected_token, expected_force
):
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--region", "us-east-1",
            "--account-id", "690839588395",
            "--repository", "edgartools-prod-images",
            "--name-prefix", "edgartools-prod",
            "--registry-bucket", "edgartools-prod-warehouse-690839588395",
            "release-lock",
            *release_args,
        ]
    )

    assert args.token == expected_token
    assert args.force is expected_force
    assert args.handler is cli.cmd_release_lock


def test_build_parser_rejects_lock_release_without_owner_token_or_force():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--region", "us-east-1",
                "--account-id", "690839588395",
                "--repository", "edgartools-prod-images",
                "--name-prefix", "edgartools-prod",
                "--registry-bucket", "edgartools-prod-warehouse-690839588395",
                "release-lock",
            ]
        )
