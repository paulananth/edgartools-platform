"""Thin-wrapper tests for ops-cost-control ticket 05's CLI.

The pure decision logic is covered by tests/application/test_ecr_rollback_*.py;
this file covers only what actually lives in the CLI module itself:
argument-parsing wiring and the recursive ASL-walker that finds
TaskDefinition references (including inside nested Map/Parallel branches),
which is genuinely CLI-module logic even though it needs no AWS I/O to test.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
        FakeEcs(), "edgartools-prod-warehouse"
    )

    assert live_tasks == []
    assert services == []
    assert errors == [
        "expected exactly one ECS cluster named 'edgartools-prod-warehouse', found 0"
    ]
    assert counts["ecs_clusters_matched"] == 0


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
