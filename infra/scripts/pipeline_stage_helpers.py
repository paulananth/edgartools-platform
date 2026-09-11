"""Shared pipeline-stage factory functions for load_history and
daily_incremental (pipeline-stage-builders wayfinder map, ticket 01).

write_load_history_definition and write_warehouse_mdm_gold_definition
(deploy-aws-application.sh) are bash functions, each running its own
independent `python3 -` subprocess against a heredoc -- there is no shared
Python runtime between them, confirmed by that file's own comments, which
state this outright. mdm_tail_helper.py already established the answer to
this exact constraint: a small sibling module both heredocs import via
sys.path.insert(0, SCRIPT_DIR). This module follows the identical
convention for the two other recurring shapes hand-copied across both
pipelines -- see .scratch/pipeline-stage-builders/spec.md for the full
diagnosis and .scratch/pipeline-stage-builders/map.md for the corrections a
/gof-refactor-reviewer pass made to the original plan (EcsNetworkContext
bundling the four network params; the Force-check Comment text generated
here rather than threaded in as a parameter; the CIK-window ItemReader key
hardcoded rather than exposed, since it has never varied across any
existing call site).

fundamentals_mode_stage's windowed=False branch has no real call site yet
-- daily_incremental's own fundamentals wiring is a separate, later map
(fundamentals-daily-integration). Its exact CLI args are a minimal,
provisional shape (mode + run-id, no --cik-offset/--cik-limit, since there
is no CIK-window manifest to fan out over); that later work may need to
extend this branch once its own incremental-scoping design is locked, but
the shape it will call is proven here first, not invented from scratch
there.
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class EcsNetworkContext(NamedTuple):
    """The ECS network/container context every stage in this module needs.

    This module has no heredoc-local variables to close over (unlike the
    file's 7 existing per-heredoc ecs_state() closures), so every caller
    passes this explicitly. Bundled into one type rather than four
    positional params since these four values always travel together --
    the same data-clump signature review flagged when this module was
    still in its planning stage.
    """

    cluster_arn: str
    subnets: list
    security_groups: list
    container_name: str


_CIK_WINDOWS_KEY_EXPR = (
    "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', "
    "$$.Execution.Name)"
)


def _ecs_state(network: EcsNetworkContext, task_def_arn, cmd_expr,
               next_state=None, is_end=False, retry_secs=120, max_attempts=3):
    """Parameter-explicit twin of the file's 7 existing local ecs_state()
    closures -- identical shape (matching the two closures at
    deploy-aws-application.sh:3079/4095 specifically, the ones actually
    replaced here), taking network context as an explicit argument instead
    of capturing it from an enclosing heredoc's locals.

    Deliberately does NOT default ResultPath the way one of this file's
    other 5 ecs_state() closures does (write_mdm_definition's, a different
    machine) -- the two closures load_history/daily_incremental actually
    use omit it, relying on each call site to set ResultPath explicitly
    only where it matters (see the public functions below).
    """
    if next_state is None and not is_end:
        raise ValueError("_ecs_state requires next_state or is_end=True")
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": network.cluster_arn,
            "TaskDefinition": task_def_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {
                "AwsvpcConfiguration": {
                    "AssignPublicIp": "ENABLED",
                    "SecurityGroups": network.security_groups,
                    "Subnets": network.subnets,
                },
            },
            "Overrides": {
                "ContainerOverrides": [{"Name": network.container_name, "Command.$": cmd_expr}],
            },
        },
        "Retry": [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": retry_secs,
            "BackoffRate": 2.0,
            "MaxAttempts": max_attempts,
        }],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s


def fundamentals_mode_stage(mode, task_arn, *, windowed, network,
                            outer_state_name, next_on_success, catch_next_state,
                            bronze_bucket_name=None,
                            item_processor_state_name=None,
                            map_comment=None,
                            tolerated_failure_percentage=15,
                            max_concurrency=1,
                            retry_secs=120):
    """Build a bootstrap-fundamentals mode stage: a windowed (Distributed
    Map over cik_windows.jsonl, load_history's shape) or non-windowed (flat
    single-task, daily_incremental's future shape) invocation of
    `bootstrap-fundamentals --mode <mode>`.

    `outer_state_name` is this stage's own key in the machine's States dict
    (e.g. "FetchEntityFacts"); when windowed, `item_processor_state_name` is
    the separate, inner per-window task's own state name inside the Map's
    ItemProcessor (e.g. "RunFundamentalsEntityFacts") -- these are two
    distinct ASL state names today, not one name reused, so both are
    required together.

    The AD-13 non-fatal Catch-and-continue convention is fixed behavior for
    this shape, not a parameter: a failure always routes to
    `catch_next_state` via `[{"ErrorEquals": ["States.ALL"], "ResultPath":
    None, "Next": catch_next_state}]`, matching every existing fundamentals
    call site exactly.

    Returns {state_name: state_dict}, keyed the same way wire_mdm_tail
    already does -- ready to merge into a machine's States dict.
    """
    catch = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": catch_next_state}]

    if windowed:
        if bronze_bucket_name is None:
            raise ValueError("windowed=True requires bronze_bucket_name")
        if item_processor_state_name is None:
            raise ValueError("windowed=True requires item_processor_state_name")

        cmd_expr = (
            "States.Array('bootstrap-fundamentals', '--mode', '%s', '--cik-offset', "
            "States.Format('{}', $.window_offset), '--cik-limit', "
            "States.Format('{}', $.window_limit), '--run-id', $$.Execution.Name)" % mode
        )
        per_window_task = _ecs_state(network, task_arn, cmd_expr, is_end=True, retry_secs=retry_secs)

        stage = {
            "Type": "Map",
            "MaxConcurrency": max_concurrency,
            "ToleratedFailurePercentage": tolerated_failure_percentage,
            "ItemReader": {
                "Resource": "arn:aws:states:::s3:getObject",
                "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
                "Parameters": {
                    "Bucket": bronze_bucket_name,
                    "Key.$": _CIK_WINDOWS_KEY_EXPR,
                },
            },
            "ItemProcessor": {
                "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
                "StartAt": item_processor_state_name,
                "States": {item_processor_state_name: per_window_task},
            },
            "ResultPath": None,
            "Catch": catch,
            "Next": next_on_success,
        }
        if map_comment is not None:
            stage["Comment"] = map_comment
        return {outer_state_name: stage}

    cmd_expr = "States.Array('bootstrap-fundamentals', '--mode', '%s', '--run-id', $$.Execution.Name)" % mode
    stage = _ecs_state(network, task_arn, cmd_expr, next_state=next_on_success, retry_secs=retry_secs)
    stage["Catch"] = catch
    stage["ResultPath"] = None
    return {outer_state_name: stage}


def force_capable_fetch_stage(command, task_arn, *, network,
                               choice_state_name, fetch_state_name,
                               ingest_state_name, next_state_on_success,
                               catch_next_state, bronze_bucket_name,
                               retry_secs=120):
    """Build a force-capable fetch trio's 4 states: a Force-check Choice,
    a Fetch/FetchForced ECS task pair, and an Ingest ECS task reading the
    Fetch step's own source_manifest.json back from S3.

    The Force-check `Comment` text is generated from `fetch_state_name`
    here rather than threaded in as a caller parameter -- the one real
    wording difference between the existing ADV-bulk and Firm-Roster
    copies ("...the normal path." present on one, absent on the other) is
    a copy-paste accident, not a behavioral difference worth preserving;
    this standardizes on the fuller wording for both.

    Returns {state_name: state_dict}, keyed the same way wire_mdm_tail
    already does.
    """
    forced_state_name = f"{fetch_state_name}Forced"
    catch = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": catch_next_state}]

    choice_state = {
        "Type": "Choice",
        "Comment": (
            f"Route to {forced_state_name} (includes --force) when caller supplied "
            f"force=true; otherwise {fetch_state_name} (no --force), the normal path."
        ),
        "Choices": [
            {"Variable": "$.force", "IsPresent": False, "Next": fetch_state_name},
            {"Variable": "$.force", "BooleanEquals": True, "Next": forced_state_name},
            {"Variable": "$.force", "BooleanEquals": False, "Next": fetch_state_name},
        ],
        "Default": "InvalidForceInput",
    }

    fetch_cmd = (
        "States.Array('%s', '--dataset-period', States.Format('{}', $.dataset_period), "
        "'--run-id', $$.Execution.Name)" % command
    )
    fetch_forced_cmd = (
        "States.Array('%s', '--dataset-period', States.Format('{}', $.dataset_period), "
        "'--force', '--run-id', $$.Execution.Name)" % command
    )
    ingest_cmd = (
        "States.Array('ingest-relationship-sources', '--source-manifest', "
        f"States.Format('s3://{bronze_bucket_name}/warehouse/bronze/runs/{command}/{{}}/source_manifest.json', "
        "$$.Execution.Name), '--run-id', $$.Execution.Name)"
    )

    fetch_state = _ecs_state(network, task_arn, fetch_cmd, next_state=ingest_state_name, retry_secs=retry_secs)
    fetch_state["Catch"] = catch
    fetch_state["ResultPath"] = None

    forced_state = _ecs_state(network, task_arn, fetch_forced_cmd, next_state=ingest_state_name, retry_secs=retry_secs)
    forced_state["Catch"] = catch
    forced_state["ResultPath"] = None

    ingest_state = _ecs_state(network, task_arn, ingest_cmd, next_state=next_state_on_success, retry_secs=retry_secs)
    ingest_state["Catch"] = catch
    ingest_state["ResultPath"] = None

    return {
        choice_state_name: choice_state,
        fetch_state_name: fetch_state,
        forced_state_name: forced_state,
        ingest_state_name: ingest_state,
    }
