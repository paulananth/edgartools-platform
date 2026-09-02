"""Contract tests for the Ticket 28/29 ECS sizing canary operator tool."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
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
            "MdmVerify": _task("small:203"),
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
    assert rewritten["States"]["MdmVerify"]["Parameters"]["TaskDefinition"] == (
        "small:203"
    )
    assert (
        definition["States"]["mdm_sync_graph_Default"]["Parameters"]["TaskDefinition"]
        == "medium:203"
    )


def test_rewrite_task_definitions_fails_closed_on_unexpected_source() -> None:
    definition = {"States": {"MdmSync": _task("medium:202")}}

    with pytest.raises(ValueError, match="expected source task definition"):
        ecs_sizing_canary.rewrite_task_definitions(
            definition,
            state_names={"MdmSync"},
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
                                    "States.Array('mdm', 'sync-graph', '--limit', "
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
    assert command == "States.Array('mdm', 'sync-graph')"
    assert definition["States"]["SelectMode"]["Choices"][0]["Next"] == (
        "mdm_sync_graph_HasLimitPerTypeOverride"
    )


def test_add_unbounded_residual_sync_removes_only_the_legacy_cap() -> None:
    definition = {
        "States": {
            "MdmSync": {
                "Type": "Task",
                "Parameters": {
                    "TaskDefinition": "medium:203",
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Name": "edgar-warehouse",
                                "Command.$": (
                                    "States.Array('mdm', 'sync-graph', "
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
    command = rewritten["States"]["MdmSync"]["Parameters"]["Overrides"][
        "ContainerOverrides"
    ][0]["Command.$"]
    assert command == (
        "States.Array('mdm', 'sync-graph', '--generation-id', $$.Execution.Name)"
    )
    assert (
        "--limit-per-type"
        in definition["States"]["MdmSync"]["Parameters"]["Overrides"][
            "ContainerOverrides"
        ][0]["Command.$"]
    )


def test_add_unbounded_residual_sync_fails_closed_on_unknown_command() -> None:
    definition = {
        "States": {
            "MdmSync": {
                "Parameters": {
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Command.$": (
                                    "States.Array('mdm', 'sync-graph', "
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
            "stateEnteredEventDetails": {"name": "MdmSync"},
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
            "stateEnteredEventDetails": {"name": "MdmSync"},
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
        {"state": "MdmSync", "retry_ordinal": 1, "task_id": "task-1"},
        {"state": "MdmSync", "retry_ordinal": 2, "task_id": "task-2"},
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
            "state": "MdmVerify",
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
    assert "task-bound telemetry missing for MdmVerify" in result["failures"]


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
                return {
                    "roleArn": "step-functions-role",
                    "definition": json.dumps(
                        {
                            "StartAt": "RunWarehouseTask",
                            "States": {
                                "RunWarehouseTask": _task(large_arn),
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


def test_gold_input_identity_captures_versioned_canonical_silver() -> None:
    class FakeCli:
        def call(self, *args: str) -> dict:
            assert args == (
                "s3api",
                "head-object",
                "--bucket",
                "edgartools-prod-warehouse-690839588395",
                "--key",
                "warehouse/silver/sec/silver.duckdb",
            )
            return {
                "VersionId": "version-1",
                "ETag": '"abc123"',
                "ContentLength": 42,
                "LastModified": "2026-09-01T00:00:00+00:00",
                "ServerSideEncryption": "AES256",
            }

    assert ecs_sizing_canary.gold_input_identity(
        FakeCli(), env="prod", account="690839588395"
    ) == {
        "bucket": "edgartools-prod-warehouse-690839588395",
        "key": "warehouse/silver/sec/silver.duckdb",
        "version_id": "version-1",
        "etag": "abc123",
        "content_length": 42,
        "last_modified": "2026-09-01T00:00:00+00:00",
        "server_side_encryption": "AES256",
    }


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
        "expected_task_states": ["MdmSecurities", "MdmVerify"],
        "task_definition_contract": {
            "MdmSecurities": "medium:203",
            "MdmVerify": "small:203",
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
            "state": "MdmVerify",
            "task_definition_arn": "small:203",
            "image": "repo@sha256:abc",
        },
    ]
    ecs_sizing_canary.validate_report_contract(execution, launch, tasks)

    tasks[1]["task_definition_arn"] = "small:202"
    with pytest.raises(ValueError, match="task definition mismatch"):
        ecs_sizing_canary.validate_report_contract(execution, launch, tasks)


def test_evaluate_gold_cohort_accepts_two_identical_faster_cheaper_candidates() -> None:
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

    def evidence(*, cohort: str, profile: str, duration: float, cost: float) -> dict:
        return {
            "launch_contract": {
                "ticket": 29,
                "cohort": cohort,
                "image": "repo@sha256:current",
                "source_definition_hash": "source-hash",
                "changed_reference_count": 0 if profile == "large" else 1,
                "compatibility_overlays": [],
                "covered_states": ["RunWarehouseTask"],
                "concurrency_context": {
                    "allow_concurrent": False,
                    "active_task_arns": [],
                },
                "input_identity": {
                    "etag": "input-sha",
                    "content_length": 300,
                    "version_id": f"{cohort}-{duration}",
                },
                "candidate_task_definition_arn": (
                    f"arn:aws:ecs:r:a:task-definition/edgartools-prod-{profile}:1"
                ),
            },
            "execution": {"status": "SUCCEEDED", "duration_seconds": duration},
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
                            "event": "silver_database_hydrated",
                            "size_bytes": 300,
                        },
                        {
                            "event": "gold_publish_started",
                            "silver_table_counts": {
                                "sec_company": 10,
                                "sec_company_filing": 20,
                            },
                        },
                        {
                            "event": "gold_build_completed",
                            "table_count": 2,
                            "gold_manifest": manifest,
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
                            "event": "silver_publish_completed",
                            "silver_database": {
                                "source_version": "input-sha",
                                "staged_checksum": "input-sha",
                                "size_bytes": 300,
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
    )

    assert result["passed"] is True
    assert result["candidate_duration_p95_seconds"] == pytest.approx(103.9)
    assert result["duration_regression_percent"] == pytest.approx(3.9)
    assert result["candidate_cost_p95_usd"] == pytest.approx(0.005595)
    assert result["cost_improvement_percent"] == pytest.approx(44.05)
    assert result["input_content_identity"] == {
        "etag": "input-sha",
        "content_length": 300,
    }
    assert result["record_funnel"] == {
        "input_silver_table_counts": {
            "sec_company": 10,
            "sec_company_filing": 20,
        },
        "input_silver_rows": 30,
        "attempted_gold_tables": 2,
        "committed_gold_tables": 2,
        "committed_gold_rows": 30,
        "exported_serving_tables": 2,
        "exported_serving_rows": 30,
        "skipped_rejected_deduplicated": "not_applicable",
    }
    assert result["recovery_parity"] == {
        "passed": True,
        "mode": "same_asl_except_task_definition",
    }
    assert result["failures"] == []

    mismatched = evidence(cohort="gold", profile="medium", duration=104.0, cost=0.0056)
    mismatched["launch_contract"]["input_identity"]["etag"] = "changed-input"
    rejected = ecs_sizing_canary.evaluate_gold_cohort(
        control=evidence(
            cohort="gold-control", profile="large", duration=100.0, cost=0.010
        ),
        candidates=[
            evidence(cohort="gold", profile="medium", duration=102.0, cost=0.0055),
            mismatched,
        ],
    )
    assert (
        "candidate and control input content identities do not match"
        in rejected["failures"]
    )
