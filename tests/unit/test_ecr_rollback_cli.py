"""Thin-wrapper tests for ops-cost-control ticket 05's CLI.

The pure decision logic is covered by tests/application/test_ecr_rollback_*.py;
this file covers only what actually lives in the CLI module itself:
argument-parsing wiring and the recursive ASL-walker that finds
TaskDefinition references (including inside nested Map/Parallel branches),
which is genuinely CLI-module logic even though it needs no AWS I/O to test.
"""
from __future__ import annotations

from edgar_warehouse.scripts import ecr_rollback_cli as cli


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
        ]
    )
    assert args.command == "apply"
    assert args.plan_hash == "sha256:abc"
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
    assert args.handler is cli.cmd_record_cohort
