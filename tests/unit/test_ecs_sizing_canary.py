"""Contract tests for the Ticket 28 ECS sizing canary operator tool."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "ecs_sizing_canary", REPO_ROOT / "scripts" / "ops" / "ecs_sizing_canary.py"
)
ecs_sizing_canary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ecs_sizing_canary)


def _task(task_definition: str) -> dict:
    return {
        "Type": "Task",
        "Parameters": {"TaskDefinition": task_definition},
        "End": True,
    }


def test_rewrite_task_definitions_is_scoped_and_exact() -> None:
    definition = {
        "States": {
            "mdm_sync_graph_Default": _task("medium:203"),
            "mdm_sync_graph_WithLimit": _task("medium:203"),
            "mdm_run_Default": _task("medium:203"),
            "Reconcile": _task("small:203"),
        }
    }

    rewritten, changes = ecs_sizing_canary.rewrite_task_definitions(
        definition,
        state_names={"mdm_sync_graph_Default", "mdm_sync_graph_WithLimit"},
        source_arn="medium:203",
        candidate_arn="large:137",
    )

    assert changes == 2
    assert (
        rewritten["States"]["mdm_sync_graph_Default"]["Parameters"]["TaskDefinition"]
        == "large:137"
    )
    assert (
        rewritten["States"]["mdm_sync_graph_WithLimit"]["Parameters"]["TaskDefinition"]
        == "large:137"
    )
    assert (
        rewritten["States"]["mdm_run_Default"]["Parameters"]["TaskDefinition"]
        == "medium:203"
    )
    assert rewritten["States"]["Reconcile"]["Parameters"]["TaskDefinition"] == (
        "small:203"
    )
    assert (
        definition["States"]["mdm_sync_graph_Default"]["Parameters"]["TaskDefinition"]
        == "medium:203"
    )


def test_rewrite_task_definitions_fails_closed_on_unexpected_source() -> None:
    definition = {"States": {"Publish Relationships": _task("medium:202")}}

    with pytest.raises(ValueError, match="expected source task definition"):
        ecs_sizing_canary.rewrite_task_definitions(
            definition,
            state_names={"Publish Relationships"},
            source_arn="medium:203",
            candidate_arn="large:137",
        )


def test_add_unbounded_sync_route_preserves_source_fallback() -> None:
    definition = {
        "States": {
            "SelectMode": {
                "Type": "Choice",
                "Choices": [
                    {
                        "Variable": "$.mode",
                        "StringEquals": "mdm_sync_graph",
                        "Next": "mdm_sync_graph_HasLimitPerTypeOverride",
                    }
                ],
            },
            "mdm_sync_graph_RunMdmTaskWithLimit": {
                "Type": "Task",
                "Parameters": {
                    "TaskDefinition": "large:137",
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Name": "edgar-warehouse",
                                "Command.$": (
                                    "States.Array('mdm', 'publish-relationships', '--limit', "
                                    "States.Format('{}', $.limit))"
                                ),
                            }
                        ]
                    },
                },
                "End": True,
            },
        }
    }

    rewritten = ecs_sizing_canary.add_unbounded_sync_route(definition)

    route = rewritten["States"]["Ticket28HasUnboundedSyncLimit"]
    assert route["Choices"][0]["And"] == [
        {"Variable": "$.limit", "IsPresent": True},
        {"Variable": "$.limit", "IsNumeric": True},
        {"Variable": "$.limit", "NumericEquals": 0},
    ]
    assert route["Default"] == "mdm_sync_graph_HasLimitPerTypeOverride"
    command = rewritten["States"]["Ticket28RunUnboundedSync"]["Parameters"][
        "Overrides"
    ]["ContainerOverrides"][0]["Command.$"]
    assert command == "States.Array('mdm', 'publish-relationships')"
    assert definition["States"]["SelectMode"]["Choices"][0]["Next"] == (
        "mdm_sync_graph_HasLimitPerTypeOverride"
    )


def test_add_unbounded_residual_sync_removes_only_the_legacy_cap() -> None:
    definition = {
        "States": {
            "Publish Relationships": {
                "Type": "Task",
                "Parameters": {
                    "TaskDefinition": "medium:203",
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Name": "edgar-warehouse",
                                "Command.$": (
                                    "States.Array('mdm', 'publish-relationships', "
                                    "'--generation-id', $$.Execution.Name, "
                                    "'--limit-per-type', '200000')"
                                ),
                            }
                        ]
                    },
                },
                "End": True,
            }
        }
    }

    rewritten, changed = ecs_sizing_canary.add_unbounded_residual_sync(definition)

    assert changed is True
    command = rewritten["States"]["Publish Relationships"]["Parameters"]["Overrides"][
        "ContainerOverrides"
    ][0]["Command.$"]
    assert command == (
        "States.Array('mdm', 'publish-relationships', "
        "'--generation-id', $$.Execution.Name)"
    )
    assert "--limit-per-type" in definition["States"]["Publish Relationships"]["Parameters"][
        "Overrides"
    ]["ContainerOverrides"][0]["Command.$"]


def test_add_unbounded_residual_sync_fails_closed_on_unknown_command() -> None:
    definition = {
        "States": {
            "Publish Relationships": {
                "Parameters": {
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Command.$": (
                                    "States.Array('mdm', 'publish-relationships', "
                                    "'--relationship-type', 'HOLDS')"
                                )
                            }
                        ]
                    }
                }
            }
        }
    }

    with pytest.raises(ValueError, match="unexpected residual sync command"):
        ecs_sizing_canary.add_unbounded_residual_sync(definition)


def test_extract_task_attempts_preserves_state_retry_and_task_identity() -> None:
    events = [
        {
            "id": 1,
            "type": "TaskStateEntered",
            "stateEnteredEventDetails": {"name": "Publish Relationships"},
        },
        {
            "id": 2,
            "previousEventId": 1,
            "type": "TaskSubmitted",
            "taskSubmittedEventDetails": {
                "output": '{"Tasks":[{"TaskArn":"arn:aws:ecs:r:a:task/c/task-1"}]}'
            },
        },
        {
            "id": 3,
            "type": "TaskStateEntered",
            "stateEnteredEventDetails": {"name": "Publish Relationships"},
        },
        {
            "id": 4,
            "previousEventId": 3,
            "type": "TaskSubmitted",
            "taskSubmittedEventDetails": {
                "output": '{"tasks":[{"taskArn":"arn:aws:ecs:r:a:task/c/task-2"}]}'
            },
        },
    ]

    attempts = ecs_sizing_canary.extract_task_attempts(events)

    assert attempts == [
        {"state": "Publish Relationships", "retry_ordinal": 1, "task_id": "task-1"},
        {"state": "Publish Relationships", "retry_ordinal": 2, "task_id": "task-2"},
    ]


def test_extract_task_attempts_retains_terminal_task_when_ecs_ages_it_out() -> None:
    task_arn = "arn:aws:ecs:r:a:task/c/task-1"
    terminal_task = {
        "TaskArn": task_arn,
        "TaskDefinitionArn": "arn:aws:ecs:r:a:task-definition/mdm-medium:203",
        "CreatedAt": 1_788_010_386_729,
        "StoppedAt": 1_788_013_315_683,
        "Containers": [{"ExitCode": 0, "Name": "edgar-warehouse"}],
    }
    events = [
        {
            "id": 1,
            "type": "TaskStateEntered",
            "stateEnteredEventDetails": {"name": "MdmSecurities"},
        },
        {
            "id": 2,
            "previousEventId": 1,
            "type": "TaskSubmitted",
            "taskSubmittedEventDetails": {
                "output": json.dumps({"Tasks": [{"TaskArn": task_arn}]})
            },
        },
        {
            "id": 3,
            "previousEventId": 2,
            "type": "TaskSucceeded",
            "taskSucceededEventDetails": {"output": json.dumps(terminal_task)},
        },
    ]

    attempts = ecs_sizing_canary.extract_task_attempts(events)

    assert attempts[0]["task_snapshot"] == terminal_task


def test_parse_datetime_accepts_step_functions_ecs_epoch_milliseconds() -> None:
    parsed = ecs_sizing_canary._parse_datetime(1_788_010_386_729)

    assert parsed.tzinfo is not None
    assert parsed.timestamp() == pytest.approx(1_788_010_386.729)


def test_extract_json_documents_handles_structured_and_pretty_log_output() -> None:
    messages = [
        '{"event":"mdm_command_started","command":"sync-graph"}',
        "not json",
        "{",
        '  "status": "ok",',
        '  "graph_nodes_materialized": 193323,',
        '  "graph_edges_materialized": 157732',
        "}",
    ]

    assert ecs_sizing_canary.extract_json_documents(messages) == [
        {"event": "mdm_command_started", "command": "sync-graph"},
        {
            "status": "ok",
            "graph_nodes_materialized": 193323,
            "graph_edges_materialized": 157732,
        },
    ]


def test_summarize_utilization_calculates_bands_and_p95() -> None:
    samples = [
        {"cpu": 100.0, "memory": 1000.0},
        {"cpu": 900.0, "memory": 3000.0},
        {"cpu": 500.0, "memory": 2000.0},
        {"cpu": 950.0, "memory": 3500.0},
    ]

    summary = ecs_sizing_canary.summarize_utilization(
        samples, cpu_reserved=1024.0, memory_reserved=4096.0, period_seconds=60
    )

    assert summary["sample_count"] == 4
    assert summary["cpu"]["maximum"] == 950.0
    assert summary["memory"]["average"] == 2375.0
    assert summary["memory"]["maximum_percent"] == pytest.approx(85.4492, rel=1e-4)
    assert summary["cpu"]["seconds_at_or_above_90_percent"] == 60
    assert summary["memory"]["seconds_at_or_above_80_percent"] == 60


def test_fargate_usage_rounds_billable_time_up_to_the_next_second() -> None:
    usage = ecs_sizing_canary.fargate_usage(
        cpu_units=1024,
        memory_mib=4096,
        pull_to_stop_seconds=60.001,
    )

    assert usage["billed_duration_seconds"] == 61
    assert usage["requested_vcpu_hours"] == pytest.approx(61 / 3600)
    assert usage["requested_memory_gib_hours"] == pytest.approx(4 * 61 / 3600)
    assert usage["estimated_compute_cost_usd"] == pytest.approx(
        (61 / 3600 * ecs_sizing_canary.FARGATE_VCPU_HOUR_USD)
        + (4 * 61 / 3600 * ecs_sizing_canary.FARGATE_GIB_HOUR_USD)
    )


def test_evaluate_candidate_fails_closed_for_retry_missing_metrics_and_memory() -> None:
    tasks = [
        {
            "state": "MdmSecurities",
            "retry_ordinal": 1,
            "exit_code": 0,
            "stop_code": "EssentialContainerExited",
            "telemetry": {
                "sample_count": 2,
                "memory": {"maximum_percent": 84.0, "p95_percent": 70.0},
            },
        },
        {
            "state": "MdmPersons",
            "retry_ordinal": 2,
            "exit_code": 0,
            "stop_code": "EssentialContainerExited",
            "telemetry": {
                "sample_count": 2,
                "memory": {"maximum_percent": 86.0, "p95_percent": 74.0},
            },
        },
        {
            "state": "Reconcile",
            "retry_ordinal": 1,
            "exit_code": 0,
            "stop_code": "EssentialContainerExited",
            "telemetry": None,
        },
    ]

    result = ecs_sizing_canary.evaluate_execution(
        execution_status="SUCCEEDED", tasks=tasks
    )

    assert result["passed"] is False
    assert "workload retry observed: MdmPersons attempt 2" in result["failures"]
    assert "memory peak gate failed for MdmPersons: 86.00% >= 85%" in result["failures"]
    assert "task-bound telemetry missing for Reconcile" in result["failures"]


def test_parser_is_safe_by_default() -> None:
    args = ecs_sizing_canary.build_parser().parse_args(["prepare"])
    assert args.profile == "sec_platform_deployer"
    assert args.region == "us-east-1"
    assert args.env == "prod"
    assert args.apply is False


def test_parser_exposes_a_matched_large_profile_residual_control() -> None:
    args = ecs_sizing_canary.build_parser().parse_args(
        ["start", "residual-control", "--attempt", "1"]
    )

    assert args.cohort == "residual-control"
    control = ecs_sizing_canary.CANARIES["residual-control"]
    assert control["source_family"] == "mdm-large"
    assert control["candidate_family"] == "mdm-large"


def test_validate_attempt_sequence_requires_terminal_predecessor_and_no_reuse() -> None:
    executions = [
        {"name": "ticket28-residual-1-20260829T000000Z", "status": "SUCCEEDED"}
    ]
    ecs_sizing_canary.validate_attempt_sequence(
        executions, cohort="residual", attempt=2
    )

    with pytest.raises(ValueError, match="already been used"):
        ecs_sizing_canary.validate_attempt_sequence(
            executions, cohort="residual", attempt=1
        )
    with pytest.raises(ValueError, match="prior attempt 2 is absent"):
        ecs_sizing_canary.validate_attempt_sequence(
            executions, cohort="residual", attempt=3
        )


def test_validate_attempt_sequence_rejects_any_running_cohort_execution() -> None:
    executions = [{"name": "ticket28-residual-1-20260829T000000Z", "status": "RUNNING"}]
    with pytest.raises(ValueError, match="still RUNNING"):
        ecs_sizing_canary.validate_attempt_sequence(
            executions, cohort="residual", attempt=2
        )


def test_residual_candidate_and_control_share_a_mutual_exclusion_group() -> None:
    assert ecs_sizing_canary.sequencing_cohorts("residual") == (
        "residual",
        "residual-control",
    )
    assert ecs_sizing_canary.sequencing_cohorts("residual-control") == (
        "residual",
        "residual-control",
    )
    assert ecs_sizing_canary.sequencing_cohorts("sync") == ("sync",)


def test_residual_launch_lock_uses_conditional_create_and_owned_delete() -> None:
    class FakeCli:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []
            self.payload: dict | None = None

        def call(self, *args: str) -> dict:
            self.calls.append(args)
            if args[:2] == ("s3api", "put-object"):
                body = Path(args[args.index("--body") + 1])
                self.payload = json.loads(body.read_text(encoding="utf-8"))
                return {"ETag": '"owner-etag"'}
            if args[:2] == ("s3api", "delete-object"):
                return {}
            raise AssertionError(args)

    cli = FakeCli()
    with ecs_sizing_canary.residual_launch_lock(
        cli, env="prod", account="690839588395"
    ):
        assert cli.payload is not None
        assert cli.payload["operator"].startswith("ticket28:")

    put, delete = cli.calls
    assert put[put.index("--bucket") + 1] == (
        "edgartools-prod-warehouse-690839588395"
    )
    assert put[put.index("--key") + 1] == (
        "warehouse/release/ecs_sizing_ticket28.lock"
    )
    assert put[put.index("--if-none-match") + 1] == "*"
    assert delete[delete.index("--if-match") + 1] == '"owner-etag"'


def test_task_definition_parity_ignores_only_sizing_and_registration_metadata() -> None:
    source = {
        "family": "mdm-large",
        "revision": 137,
        "taskDefinitionArn": "large:137",
        "cpu": "2048",
        "memory": "8192",
        "status": "ACTIVE",
        "registeredAt": "now",
        "registeredBy": "operator",
        "containerDefinitions": [
            {
                "name": "edgar-warehouse",
                "image": "repo@sha256:abc",
                "environment": [],
                "logConfiguration": {
                    "options": {"awslogs-stream-prefix": "mdm-mdm-large"}
                },
            }
        ],
        "taskRoleArn": "role",
    }
    candidate = {
        **source,
        "family": "mdm-medium",
        "revision": 203,
        "taskDefinitionArn": "medium:203",
        "cpu": "1024",
        "memory": "4096",
    }
    candidate["containerDefinitions"] = [
        {
            **source["containerDefinitions"][0],
            "logConfiguration": {
                "options": {"awslogs-stream-prefix": "mdm-mdm-medium"}
            },
        }
    ]
    ecs_sizing_canary.validate_task_definition_parity(source, candidate)

    candidate["containerDefinitions"] = [
        {
            "name": "edgar-warehouse",
            "image": "repo@sha256:abc",
            "environment": [{"name": "MODE", "value": "different"}],
        }
    ]
    with pytest.raises(ValueError, match="differ beyond sizing"):
        ecs_sizing_canary.validate_task_definition_parity(source, candidate)


def test_validate_report_contract_binds_execution_state_tasks_and_image() -> None:
    launch = {
        "execution_arn": "execution:ticket28",
        "state_machine_arn": "stateMachine:immutable-hash",
        "image": "repo@sha256:abc",
        "expected_task_states": ["MdmSecurities", "Reconcile"],
        "task_definition_contract": {
            "MdmSecurities": "medium:203",
            "Reconcile": "small:203",
        },
    }
    execution = {
        "executionArn": "execution:ticket28",
        "stateMachineArn": "stateMachine:immutable-hash",
    }
    tasks = [
        {
            "state": "MdmSecurities",
            "task_definition_arn": "medium:203",
            "image": "repo@sha256:abc",
        },
        {
            "state": "Reconcile",
            "task_definition_arn": "small:203",
            "image": "repo@sha256:abc",
        },
    ]
    ecs_sizing_canary.validate_report_contract(execution, launch, tasks)

    tasks[1]["task_definition_arn"] = "small:202"
    with pytest.raises(ValueError, match="task definition mismatch"):
        ecs_sizing_canary.validate_report_contract(execution, launch, tasks)
