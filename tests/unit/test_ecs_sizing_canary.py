"""Contract tests for the Ticket 28/29 ECS sizing canary operator tool."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edgar_warehouse.serving.source_dimensional_export import GOLD_INPUT_COLUMNS

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
    assert (
        "--limit-per-type"
        in definition["States"]["Publish Relationships"]["Parameters"]["Overrides"][
            "ContainerOverrides"
        ][0]["Command.$"]
    )


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


def test_parser_exposes_ticket29_gold_candidate_and_control_cohorts() -> None:
    args = ecs_sizing_canary.build_parser().parse_args(
        ["prepare", "--cohort", "gold", "--cohort", "gold-control"]
    )

    assert args.cohorts == ["gold", "gold-control"]
    candidate = ecs_sizing_canary.CANARIES["gold"]
    control = ecs_sizing_canary.CANARIES["gold-control"]
    assert candidate == {
        "ticket": 29,
        "source": "gold-refresh",
        "name": "canary-ticket29-gold-medium",
        "source_family": "large",
        "candidate_family": "medium",
        "state_prefix": "RunWarehouseTask",
        "expected_changes": {1},
        "input": {},
        "execution_prefix": "ticket29-gold",
    }
    assert control == {
        **candidate,
        "name": "canary-ticket29-gold-large-control",
        "candidate_family": "large",
        "execution_prefix": "ticket29-gold-control",
    }

    evaluate_args = ecs_sizing_canary.build_parser().parse_args(
        [
            "evaluate-gold",
            "--control-report",
            "control.json",
            "--candidate-report",
            "candidate-1.json",
            "--candidate-report",
            "candidate-2.json",
            "--output",
            "cohort.json",
        ]
    )
    assert evaluate_args.control_report == Path("control.json")
    assert evaluate_args.candidate_reports == [
        Path("candidate-1.json"),
        Path("candidate-2.json"),
    ]
    assert evaluate_args.output == Path("cohort.json")

    start_args = ecs_sizing_canary.build_parser().parse_args(
        [
            "start",
            "gold-control",
            "--attempt",
            "5",
            "--input-snapshot-at",
            "2026-09-11T12:00:00Z",
        ]
    )
    assert start_args.input_snapshot_at == "2026-09-11T12:00:00Z"


def test_prepare_dry_run_is_scoped_to_selected_gold_cohort(tmp_path: Path) -> None:
    account = "690839588395"
    region = "us-east-1"
    large_arn = (
        f"arn:aws:ecs:{region}:{account}:task-definition/edgartools-prod-large:233"
    )
    medium_arn = (
        f"arn:aws:ecs:{region}:{account}:task-definition/edgartools-prod-medium:238"
    )

    def task_definition(*, family: str, arn: str, cpu: str, memory: str) -> dict:
        return {
            "family": family,
            "revision": int(arn.rsplit(":", 1)[-1]),
            "taskDefinitionArn": arn,
            "cpu": cpu,
            "memory": memory,
            "containerDefinitions": [
                {
                    "name": "edgar-warehouse",
                    "image": "repo@sha256:abc",
                    "environment": [],
                    "logConfiguration": {
                        "options": {
                            "awslogs-stream-prefix": f"warehouse-{family.rsplit('-', 1)[-1]}"
                        }
                    },
                }
            ],
            "taskRoleArn": "task-role",
        }

    class FakeCli:
        def __init__(self) -> None:
            self.region = region
            self.calls: list[tuple[str, ...]] = []

        def call(self, *args: str) -> dict:
            self.calls.append(args)
            if args[:2] == ("sts", "get-caller-identity"):
                return {"Account": account}
            if args[:2] == ("stepfunctions", "describe-state-machine"):
                task = _task(large_arn)
                task["Parameters"]["Overrides"] = {
                    "ContainerOverrides": [
                        {
                            "Name": "edgar-warehouse",
                            "Command.$": (
                                "States.Array('gold-refresh', '--run-id', "
                                "$$.Execution.Name)"
                            ),
                        }
                    ]
                }
                return {
                    "roleArn": "step-functions-role",
                    "definition": json.dumps(
                        {
                            "StartAt": "RunWarehouseTask",
                            "States": {
                                "RunWarehouseTask": task,
                            },
                        }
                    ),
                }
            if args[:2] == ("ecs", "describe-task-definition"):
                family = args[args.index("--task-definition") + 1]
                if family == "edgartools-prod-large":
                    value = task_definition(
                        family=family, arn=large_arn, cpu="2048", memory="8192"
                    )
                elif family == "edgartools-prod-medium":
                    value = task_definition(
                        family=family, arn=medium_arn, cpu="1024", memory="4096"
                    )
                else:
                    raise AssertionError(family)
                return {"taskDefinition": value}
            raise AssertionError(args)

    output = tmp_path / "ticket29-gold-plan.json"
    args = ecs_sizing_canary.build_parser().parse_args(
        ["prepare", "--cohort", "gold", "--output", str(output)]
    )

    assert ecs_sizing_canary.prepare(FakeCli(), args) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [plan["cohort"] for plan in payload["plans"]] == ["gold"]
    assert payload["plans"][0]["ticket"] == 29
    assert payload["plans"][0]["source_task_definition_arn"] == large_arn
    assert payload["plans"][0]["candidate_task_definition_arn"] == medium_arn
    assert payload["plans"][0]["covered_states"] == ["RunWarehouseTask"]
    assert payload["plans"][0]["changed_reference_count"] == 1
    assert payload["plans"][0]["compatibility_overlays"] == [
        "gold input pinned to $.input_snapshot_at"
    ]


def test_gold_input_snapshot_normalization_requires_utc_timestamp() -> None:
    assert ecs_sizing_canary.normalize_gold_input_snapshot_at(
        "2026-09-11T08:00:00-04:00"
    ) == "2026-09-11T12:00:00.000000Z"

    with pytest.raises(ValueError, match="timezone-aware"):
        ecs_sizing_canary.normalize_gold_input_snapshot_at("2026-09-11T12:00:00")

    assert ecs_sizing_canary.canary_execution_input(
        "gold", "2026-09-11T08:00:00-04:00"
    ) == {"input_snapshot_at": "2026-09-11T12:00:00.000000Z"}
    with pytest.raises(ValueError, match="only valid for Ticket 29"):
        ecs_sizing_canary.canary_execution_input(
            "residual", "2026-09-11T12:00:00Z"
        )


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


def test_gold_candidate_and_control_use_ticket29_sequence_identity() -> None:
    executions = [{"name": "ticket29-gold-1-20260901T120000Z", "status": "SUCCEEDED"}]

    ecs_sizing_canary.validate_attempt_sequence(executions, cohort="gold", attempt=2)
    with pytest.raises(ValueError, match="already been used"):
        ecs_sizing_canary.validate_attempt_sequence(
            executions, cohort="gold", attempt=1
        )
    assert ecs_sizing_canary.sequencing_cohorts("gold") == (
        "gold",
        "gold-control",
    )
    assert ecs_sizing_canary.sequencing_cohorts("gold-control") == (
        "gold",
        "gold-control",
    )
    assert (
        ecs_sizing_canary.execution_name(
            "gold", attempt=2, timestamp="20260901T120000Z"
        )
        == "ticket29-gold-2-20260901T120000Z"
    )
    assert ecs_sizing_canary.launch_concurrency_context(
        ["task-b", "task-a", "task-b"], allow_concurrent=True
    ) == {
        "allow_concurrent": True,
        "active_task_arns": ["task-a", "task-b"],
    }


def test_gold_launch_order_requires_control_then_two_candidates() -> None:
    control = {
        "name": "ticket29-gold-control-3-20260910T120000Z",
        "status": "SUCCEEDED",
        "startDate": "2026-09-10T12:00:00+00:00",
        "stateMachineArn": "state-machine:current-control",
    }
    candidate = {
        "name": "ticket29-gold-2-20260910T121000Z",
        "status": "SUCCEEDED",
        "startDate": "2026-09-10T12:10:00+00:00",
    }

    ecs_sizing_canary.validate_gold_launch_order(
        [control],
        cohort="gold",
        expected_control_state_machine_arn="state-machine:current-control",
    )
    ecs_sizing_canary.validate_gold_launch_order(
        [control, candidate],
        cohort="gold",
        expected_control_state_machine_arn="state-machine:current-control",
    )
    with pytest.raises(ValueError, match="fresh large control"):
        ecs_sizing_canary.validate_gold_launch_order(
            [],
            cohort="gold",
            expected_control_state_machine_arn="state-machine:current-control",
        )
    with pytest.raises(ValueError, match="already has two medium candidates"):
        ecs_sizing_canary.validate_gold_launch_order(
            [
                control,
                candidate,
                {
                    **candidate,
                    "name": "ticket29-gold-3-20260910T122000Z",
                    "startDate": "2026-09-10T12:20:00+00:00",
                },
            ],
            cohort="gold",
            expected_control_state_machine_arn="state-machine:current-control",
        )
    with pytest.raises(ValueError, match="latest large control is FAILED"):
        ecs_sizing_canary.validate_gold_launch_order(
            [{**control, "status": "FAILED"}],
            cohort="gold",
            expected_control_state_machine_arn="state-machine:current-control",
        )
    with pytest.raises(ValueError, match="current immutable definition"):
        ecs_sizing_canary.validate_gold_launch_order(
            [control],
            cohort="gold",
            expected_control_state_machine_arn="state-machine:new-control",
        )
    ecs_sizing_canary.validate_gold_launch_order(
        [control, candidate], cohort="gold-control"
    )


def test_cluster_overlap_filters_to_other_tasks_in_execution_window() -> None:
    tasks = [
        {
            "taskArn": "task/own",
            "taskDefinitionArn": "large:1",
            "createdAt": "2026-09-01T12:01:00+00:00",
            "stoppedAt": "2026-09-01T12:02:00+00:00",
        },
        {
            "taskArn": "task/before",
            "taskDefinitionArn": "medium:1",
            "createdAt": "2026-09-01T11:00:00+00:00",
            "stoppedAt": "2026-09-01T11:59:59+00:00",
        },
        {
            "taskArn": "task/overlap",
            "taskDefinitionArn": "medium:2",
            "createdAt": "2026-09-01T12:04:00+00:00",
            "stoppedAt": "2026-09-01T12:08:00+00:00",
            "overrides": {"containerOverrides": [{"command": ["daily-incremental"]}]},
        },
        {
            "taskArn": "task/running",
            "taskDefinitionArn": "large:2",
            "createdAt": "2026-09-01T12:09:00+00:00",
        },
    ]

    assert ecs_sizing_canary.overlapping_cluster_tasks(
        tasks,
        start=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 12, 10, tzinfo=UTC),
        excluded_task_arns={"task/own"},
    ) == [
        {
            "task_arn": "task/overlap",
            "task_definition_arn": "medium:2",
            "created_at": "2026-09-01T12:04:00+00:00",
            "stopped_at": "2026-09-01T12:08:00+00:00",
            "command": ["daily-incremental"],
        },
        {
            "task_arn": "task/running",
            "task_definition_arn": "large:2",
            "created_at": "2026-09-01T12:09:00+00:00",
            "stopped_at": None,
            "command": [],
        },
    ]


def test_cluster_overlap_pages_every_ecs_task_status() -> None:
    class FakeCli:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def call(self, *args: str) -> dict:
            self.calls.append(args)
            if args[:2] == ("ecs", "list-tasks"):
                status = args[args.index("--desired-status") + 1]
                token = (
                    args[args.index("--next-token") + 1]
                    if "--next-token" in args
                    else None
                )
                if status == "STOPPED" and token is None:
                    return {"taskArns": ["task/own"], "nextToken": "page-2"}
                if status == "STOPPED" and token == "page-2":
                    return {"taskArns": ["task/overlap"]}
                return {"taskArns": []}
            if args[:2] == ("ecs", "describe-tasks"):
                return {
                    "tasks": [
                        {
                            "taskArn": "task/own",
                            "createdAt": "2026-09-01T12:01:00+00:00",
                            "stoppedAt": "2026-09-01T12:02:00+00:00",
                        },
                        {
                            "taskArn": "task/overlap",
                            "createdAt": "2026-09-01T12:03:00+00:00",
                            "stoppedAt": "2026-09-01T12:04:00+00:00",
                        },
                    ]
                }
            raise AssertionError(args)

    cli = FakeCli()
    assert ecs_sizing_canary._cluster_overlap(
        cli,
        cluster="edgartools-prod-warehouse",
        start=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 12, 10, tzinfo=UTC),
        excluded_task_arns={"task/own"},
    ) == [
        {
            "task_arn": "task/overlap",
            "task_definition_arn": None,
            "created_at": "2026-09-01T12:03:00+00:00",
            "stopped_at": "2026-09-01T12:04:00+00:00",
            "command": [],
        }
    ]
    assert any("--next-token" in call for call in cli.calls)


def test_overlap_evidence_fails_closed_when_report_is_late() -> None:
    with pytest.raises(ValueError, match="within 30 minutes"):
        ecs_sizing_canary.validate_overlap_evidence_freshness(
            window_start=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            captured_at=datetime(2026, 9, 1, 12, 31, tzinfo=UTC),
        )


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
    assert put[put.index("--bucket") + 1] == ("edgartools-prod-warehouse-690839588395")
    assert put[put.index("--key") + 1] == ("warehouse/release/ecs_sizing_ticket28.lock")
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


def test_evaluate_gold_cohort_scores_sizing_but_fails_promotion_without_recovery() -> (
    None
):
    manifest = [
        {
            "table_name": "dim_company",
            "row_count": 10,
            "parquet_sha256": "company-sha",
            "byte_size": 100,
        },
        {
            "table_name": "dim_filing",
            "row_count": 20,
            "parquet_sha256": "filing-sha",
            "byte_size": 200,
        },
    ]

    envelope_identity = {
        "schema_version": 1,
        "source_system": "EDGARTOOLS_SILVER",
        "account": "prod-account",
        "database": "EDGARTOOLS_PROD",
        "schema": "EDGARTOOLS_SILVER",
        "snapshot_at": "2026-09-10T11:59:55.000000Z",
        "tables": [
            {
                "table_name": name,
                "row_count": index + 1,
                "selected_columns": list(GOLD_INPUT_COLUMNS[name]),
            }
            for index, name in enumerate(
                [
                    "SEC_ADV_FIRM_ROSTER",
                    "SEC_ADV_PRIVATE_FUND",
                    "SEC_AUDITOR_REPORT_EVIDENCE",
                    "SEC_EMPLOYMENT_EVENT",
                    "SEC_SUBSIDIARY_EVIDENCE",
                ]
            )
        ],
    }
    input_envelope = {
        **envelope_identity,
        "envelope_sha256": ecs_sizing_canary._json_hash(envelope_identity),
        "query_ids": {
            entry["table_name"]: f"query-{index}"
            for index, entry in enumerate(envelope_identity["tables"])
        },
    }

    def evidence(*, cohort: str, profile: str, duration: float, cost: float) -> dict:
        return {
            "launch_contract": {
                "ticket": 29,
                "cohort": cohort,
                "image": "repo@sha256:current",
                "input_snapshot_at": input_envelope["snapshot_at"],
                "source_definition_hash": "source-hash",
                "changed_reference_count": 0 if profile == "large" else 1,
                "compatibility_overlays": [
                    "gold input pinned to $.input_snapshot_at"
                ],
                "covered_states": ["RunWarehouseTask"],
                "concurrency_context": {
                    "allow_concurrent": False,
                    "active_task_arns": [],
                },
                "candidate_task_definition_arn": (
                    f"arn:aws:ecs:r:a:task-definition/edgartools-prod-{profile}:1"
                ),
            },
            "execution": {
                "status": "SUCCEEDED",
                "duration_seconds": duration,
                "start_date": (
                    "2026-09-10T12:00:00+00:00"
                    if cohort == "gold-control"
                    else (
                        "2026-09-10T12:10:00+00:00"
                        if duration == 102.0
                        else "2026-09-10T12:20:00+00:00"
                    )
                ),
                "stop_date": (
                    "2026-09-10T12:05:00+00:00"
                    if cohort == "gold-control"
                    else (
                        "2026-09-10T12:15:00+00:00"
                        if duration == 102.0
                        else "2026-09-10T12:25:00+00:00"
                    )
                ),
            },
            "tasks": [
                {
                    "state": "RunWarehouseTask",
                    "retry_ordinal": 1,
                    "exit_code": 0,
                    "telemetry": {
                        "sample_count": 3,
                        "memory": {
                            "maximum_percent": 40.0,
                            "p95_percent": 35.0,
                        },
                    },
                    "application_evidence": [
                        {
                            "event": "gold_publish_started",
                            "gold_input_envelope": input_envelope,
                        },
                        {
                            "event": "gold_build_completed",
                            "gold_input_envelope": input_envelope,
                            "table_count": 2,
                            "gold_manifest": [dict(entry) for entry in manifest],
                            "gold_row_counts": {
                                "dim_company": 10,
                                "dim_filing": 20,
                            },
                            "snowflake_export_counts": {
                                "company": 10,
                                "filing_detail": 20,
                            },
                        },
                        {
                            "event": "gold_publish_completed",
                            "gold_input_envelope": input_envelope,
                            "gold_row_counts": {
                                "dim_company": 10,
                                "dim_filing": 20,
                            },
                            "snowflake_export_counts": {
                                "company": 10,
                                "filing_detail": 20,
                            },
                        },
                    ],
                }
            ],
            "estimated_compute_cost_usd": cost,
            "execution_local_gates": {
                "passed": True,
                "failures": [],
                "warnings": [],
            },
            "cluster_overlap": [],
        }

    result = ecs_sizing_canary.evaluate_gold_cohort(
        control=evidence(
            cohort="gold-control", profile="large", duration=100.0, cost=0.010
        ),
        candidates=[
            evidence(cohort="gold", profile="medium", duration=102.0, cost=0.0055),
            evidence(cohort="gold", profile="medium", duration=104.0, cost=0.0056),
        ],
        cohort_overlap=[],
    )

    assert result["performance_gates_passed"] is True
    assert result["sizing_gates_passed"] is True
    assert result["passed"] is False
    assert result["candidate_duration_p95_seconds"] == pytest.approx(103.9)
    assert result["duration_regression_percent"] == pytest.approx(3.9)
    assert result["candidate_cost_p95_usd"] == pytest.approx(0.005595)
    assert result["cost_improvement_percent"] == pytest.approx(44.05)
    assert result["output_identity_summary"]["mode"] == "exact_gold_output"
    assert result["input_envelope_evidence"] == {
        "passed": True,
        "status": "matched",
        "source_system": "EDGARTOOLS_SILVER",
        "snapshot_at": "2026-09-10T11:59:55.000000Z",
        "envelope_sha256": input_envelope["envelope_sha256"],
    }
    assert result["record_funnel"] == {
        "output_tables": ["dim_company", "dim_filing"],
        "attempted_gold_tables": 2,
        "committed_gold_tables": 2,
        "committed_gold_rows": 30,
        "exported_serving_tables": 2,
        "exported_serving_rows": 30,
        "skipped_rejected_deduplicated": "not_applicable",
    }
    assert result["structural_recovery_parity"] == {
        "passed": True,
        "mode": "same_asl_except_task_definition",
    }
    assert result["recovery_evidence"] == {
        "passed": False,
        "status": "not_exercised",
    }
    assert result["idempotency"]["passed"] is True
    assert result["performance_failures"] == []
    assert result["sizing_failures"] == []
    assert result["failures"] == ["recovery behavior was not exercised"]

    missing_envelope = evidence(
        cohort="gold", profile="medium", duration=104.0, cost=0.0056
    )
    for event in missing_envelope["tasks"][0]["application_evidence"]:
        event.pop("gold_input_envelope")
    missing_result = ecs_sizing_canary.evaluate_gold_cohort(
        control=evidence(
            cohort="gold-control", profile="large", duration=100.0, cost=0.010
        ),
        candidates=[
            evidence(cohort="gold", profile="medium", duration=102.0, cost=0.0055),
            missing_envelope,
        ],
        cohort_overlap=[],
    )
    assert "matched Snowflake input envelope was not captured" in missing_result[
        "sizing_failures"
    ]

    mismatched_envelope = evidence(
        cohort="gold", profile="medium", duration=104.0, cost=0.0056
    )
    changed_envelope = dict(input_envelope)
    changed_envelope["snapshot_at"] = "2026-09-10T12:00:00.000000Z"
    changed_identity = {
        key: value
        for key, value in changed_envelope.items()
        if key not in {"envelope_sha256", "query_ids"}
    }
    changed_envelope["envelope_sha256"] = ecs_sizing_canary._json_hash(
        changed_identity
    )
    mismatched_envelope["launch_contract"]["input_snapshot_at"] = changed_envelope[
        "snapshot_at"
    ]
    for event in mismatched_envelope["tasks"][0]["application_evidence"]:
        event["gold_input_envelope"] = changed_envelope
    envelope_result = ecs_sizing_canary.evaluate_gold_cohort(
        control=evidence(
            cohort="gold-control", profile="large", duration=100.0, cost=0.010
        ),
        candidates=[
            evidence(cohort="gold", profile="medium", duration=102.0, cost=0.0055),
            mismatched_envelope,
        ],
        cohort_overlap=[],
    )
    assert "Snowflake input envelopes do not match" in envelope_result[
        "sizing_failures"
    ]

    mismatched = evidence(cohort="gold", profile="medium", duration=104.0, cost=0.0056)
    mismatched["tasks"][0]["application_evidence"][1]["gold_manifest"][0] = {
        **manifest[0],
        "parquet_sha256": "changed-output",
    }
    rejected = ecs_sizing_canary.evaluate_gold_cohort(
        control=evidence(
            cohort="gold-control", profile="large", duration=100.0, cost=0.010
        ),
        candidates=[
            evidence(cohort="gold", profile="medium", duration=102.0, cost=0.0055),
            mismatched,
        ],
        cohort_overlap=[],
    )
    assert (
        "gold manifest or Snowflake export output parity failed" in rejected["failures"]
    )


def test_evaluate_gold_cohort_rejects_overlapping_run_order() -> None:
    # The detailed fixture above exercises the accepted order. This guard is
    # intentionally a small pure-function seam around report timestamps.
    with pytest.raises(ValueError, match="control must stop before candidate 1"):
        ecs_sizing_canary.validate_gold_report_order(
            control={
                "execution": {
                    "start_date": "2026-09-10T12:00:00+00:00",
                    "stop_date": "2026-09-10T12:12:00+00:00",
                }
            },
            candidates=[
                {
                    "execution": {
                        "start_date": "2026-09-10T12:10:00+00:00",
                        "stop_date": "2026-09-10T12:15:00+00:00",
                    }
                },
                {
                    "execution": {
                        "start_date": "2026-09-10T12:20:00+00:00",
                        "stop_date": "2026-09-10T12:25:00+00:00",
                    }
                },
            ],
        )


def test_evaluate_gold_cohort_requires_full_window_overlap_evidence() -> None:
    with pytest.raises(ValueError, match="full cohort-window overlap evidence"):
        ecs_sizing_canary.evaluate_gold_cohort(
            control={}, candidates=[{}, {}], cohort_overlap=None
        )
