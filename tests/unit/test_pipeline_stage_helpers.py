"""Unit tests for infra/scripts/pipeline_stage_helpers.py's
fundamentals_mode_stage() and force_capable_fetch_stage() (pipeline-stage-
builders wayfinder map, ticket 01).

Mirrors test_mdm_tail_helper.py's convention: import the sibling module
directly via sys.path.insert(0, .../infra/scripts), exercise each function
in isolation from the real deploy-script heredocs it will be called from
in tickets 02/03.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "infra" / "scripts"))

from pipeline_stage_helpers import (  # noqa: E402
    EcsNetworkContext,
    _ecs_state,
    fundamentals_mode_stage,
    force_capable_fetch_stage,
)


def _network(**extra):
    defaults = dict(
        cluster_arn="arn:aws:ecs:us-east-1:1:cluster/test",
        subnets=["subnet-1", "subnet-2"],
        security_groups=["sg-1"],
        container_name="edgar-warehouse",
    )
    defaults.update(extra)
    return EcsNetworkContext(**defaults)


class TestEcsState:
    def test_requires_next_state_or_is_end(self):
        with pytest.raises(ValueError):
            _ecs_state(_network(), "arn:task", "cmd")

    def test_is_end_true_sets_end_not_next(self):
        result = _ecs_state(_network(), "arn:task", "cmd", is_end=True)
        assert result["End"] is True
        assert "Next" not in result

    def test_uses_explicit_network_context_not_closure(self):
        net = _network(cluster_arn="arn:custom-cluster", container_name="custom-container")
        result = _ecs_state(net, "arn:task", "cmd", is_end=True)
        assert result["Parameters"]["Cluster"] == "arn:custom-cluster"
        assert result["Parameters"]["Overrides"]["ContainerOverrides"][0]["Name"] == "custom-container"

    def test_does_not_set_result_path_by_default(self):
        # Deliberately different from write_mdm_definition's ecs_state()
        # closure (a different machine) -- the two closures this module
        # actually replaces (deploy-aws-application.sh:3079/4095) don't set
        # ResultPath either, relying on each call site to add it explicitly
        # only where it matters. See test_pipeline_stage_helpers'
        # windowed-per-window-task and force-capable-fetch-stage tests for
        # where it is (and isn't) set.
        result = _ecs_state(_network(), "arn:task", "cmd", is_end=True)
        assert "ResultPath" not in result

    def test_retry_secs_is_configurable(self):
        result = _ecs_state(_network(), "arn:task", "cmd", is_end=True, retry_secs=60)
        assert result["Retry"][0]["IntervalSeconds"] == 60

    def test_retry_policy_defaults_to_three_attempts_matching_real_call_sites(self):
        # deploy-aws-application.sh:3079/4095 (load_history/daily_incremental's
        # own ecs_state() closures, the ones this module replaces) both
        # hardcode MaxAttempts=3 -- not mdm_tail_helper.py's call_mdm_machine,
        # a different kind of Task (nested execution), which uses 2.
        result = _ecs_state(_network(), "arn:task", "cmd", is_end=True)
        assert result["Retry"] == [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": 120,
            "BackoffRate": 2.0,
            "MaxAttempts": 3,
        }]

    def test_max_attempts_is_configurable(self):
        result = _ecs_state(_network(), "arn:task", "cmd", is_end=True, max_attempts=5)
        assert result["Retry"][0]["MaxAttempts"] == 5


class TestFundamentalsModeStage:
    def test_windowed_returns_distributed_map_over_cik_windows(self):
        result = fundamentals_mode_stage(
            "entity-facts", "arn:wh-large", windowed=True, network=_network(),
            outer_state_name="FetchEntityFacts", next_on_success="FetchPerFilingFundamentals",
            catch_next_state="FetchPerFilingFundamentals", bronze_bucket_name="my-bucket",
            item_processor_state_name="RunFundamentalsEntityFacts",
        )

        assert set(result) == {"FetchEntityFacts"}
        stage = result["FetchEntityFacts"]
        assert stage["Type"] == "Map"
        assert stage["MaxConcurrency"] == 1
        assert stage["ToleratedFailurePercentage"] == 15
        assert stage["ItemReader"]["Parameters"]["Bucket"] == "my-bucket"
        assert stage["ItemReader"]["Parameters"]["Key.$"] == (
            "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', "
            "$$.Execution.Name)"
        )
        assert stage["ItemProcessor"]["ProcessorConfig"] == {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"}
        assert stage["ItemProcessor"]["StartAt"] == "RunFundamentalsEntityFacts"
        per_window = stage["ItemProcessor"]["States"]["RunFundamentalsEntityFacts"]
        assert per_window["End"] is True
        assert "'--mode', 'entity-facts'" in per_window["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        # Matches the real per-window task exactly -- no ResultPath key at
        # all (unlike the outer Map, which does set it below).
        assert "ResultPath" not in per_window
        assert stage["ResultPath"] is None
        assert stage["Next"] == "FetchPerFilingFundamentals"
        assert stage["Catch"] == [{
            "ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "FetchPerFilingFundamentals",
        }]

    def test_windowed_requires_bronze_bucket_name(self):
        with pytest.raises(ValueError):
            fundamentals_mode_stage(
                "entity-facts", "arn:wh-large", windowed=True, network=_network(),
                outer_state_name="FetchEntityFacts", next_on_success="Next",
                catch_next_state="Next", item_processor_state_name="Run",
            )

    def test_windowed_requires_item_processor_state_name(self):
        with pytest.raises(ValueError):
            fundamentals_mode_stage(
                "entity-facts", "arn:wh-large", windowed=True, network=_network(),
                outer_state_name="FetchEntityFacts", next_on_success="Next",
                catch_next_state="Next", bronze_bucket_name="my-bucket",
            )

    def test_map_comment_only_set_when_provided(self):
        without = fundamentals_mode_stage(
            "entity-facts", "arn:wh-large", windowed=True, network=_network(),
            outer_state_name="FetchEntityFacts", next_on_success="Next",
            catch_next_state="Next", bronze_bucket_name="my-bucket",
            item_processor_state_name="Run",
        )
        assert "Comment" not in without["FetchEntityFacts"]

        with_comment = fundamentals_mode_stage(
            "entity-facts", "arn:wh-large", windowed=True, network=_network(),
            outer_state_name="FetchEntityFacts", next_on_success="Next",
            catch_next_state="Next", bronze_bucket_name="my-bucket",
            item_processor_state_name="Run", map_comment="a comment",
        )
        assert with_comment["FetchEntityFacts"]["Comment"] == "a comment"

    def test_non_windowed_returns_flat_task_no_map(self):
        result = fundamentals_mode_stage(
            "entity-facts", "arn:wh-large", windowed=False, network=_network(),
            outer_state_name="FetchEntityFacts", next_on_success="NextThing",
            catch_next_state="NextThing",
        )

        assert set(result) == {"FetchEntityFacts"}
        stage = result["FetchEntityFacts"]
        assert stage["Type"] == "Task"
        assert "ItemReader" not in stage
        assert "ItemProcessor" not in stage
        assert stage["Next"] == "NextThing"
        assert "'--mode', 'entity-facts'" in stage["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        assert "--cik-offset" not in stage["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        assert stage["Catch"] == [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "NextThing"}]
        assert stage["ResultPath"] is None

    def test_non_windowed_does_not_require_bronze_bucket_or_item_processor_name(self):
        # Should not raise -- those two params are windowed=True-only requirements.
        fundamentals_mode_stage(
            "per-filing", "arn:wh-large", windowed=False, network=_network(),
            outer_state_name="FetchPerFilingFundamentals", next_on_success="Next",
            catch_next_state="Next",
        )


class TestForceCapableFetchStage:
    def _build(self, **overrides):
        defaults = dict(
            command="fetch-adv-bulk", task_arn="arn:wh-medium", network=_network(),
            choice_state_name="ForceCheck", fetch_state_name="FetchAdvBulk",
            ingest_state_name="IngestAdvBulkSources", next_state_on_success="FirmRosterForceCheck",
            catch_next_state="ReleaseSecFetchLease", bronze_bucket_name="my-bucket",
        )
        defaults.update(overrides)
        return force_capable_fetch_stage(**defaults)

    def test_returns_four_states_keyed_by_name(self):
        result = self._build()
        assert set(result) == {"ForceCheck", "FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"}

    def test_choice_routes_absent_and_false_to_fetch_true_to_forced(self):
        choice = self._build()["ForceCheck"]
        assert choice["Type"] == "Choice"
        assert choice["Default"] == "InvalidForceInput"
        by_shape = {
            (c.get("IsPresent"), c.get("BooleanEquals")): c["Next"] for c in choice["Choices"]
        }
        assert by_shape[(False, None)] == "FetchAdvBulk"
        assert by_shape[(None, True)] == "FetchAdvBulkForced"
        assert by_shape[(None, False)] == "FetchAdvBulk"

    def test_choice_comment_generated_not_parameterized_and_uses_fuller_wording(self):
        # Deliberate normalization (ticket 01): both ADV-shaped and
        # FirmRoster-shaped calls get the fuller wording, regardless of
        # which existing hand-written copy happened to have it.
        choice = self._build(
            choice_state_name="FirmRosterForceCheck", fetch_state_name="FetchFirmRoster",
            ingest_state_name="IngestFirmRosterSources", command="fetch-firm-roster",
        )["FirmRosterForceCheck"]
        assert choice["Comment"] == (
            "Route to FetchFirmRosterForced (includes --force) when caller supplied "
            "force=true; otherwise FetchFirmRoster (no --force), the normal path."
        )

    def test_fetch_omits_force_forced_includes_it(self):
        result = self._build()
        fetch_cmd = result["FetchAdvBulk"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        forced_cmd = result["FetchAdvBulkForced"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        assert "--force" not in fetch_cmd
        assert "--force" in forced_cmd

    def test_fetch_and_forced_both_route_to_ingest_on_success(self):
        result = self._build()
        assert result["FetchAdvBulk"]["Next"] == "IngestAdvBulkSources"
        assert result["FetchAdvBulkForced"]["Next"] == "IngestAdvBulkSources"

    def test_ingest_reads_the_matching_command_manifest_prefix_and_routes_on_success(self):
        result = self._build()
        ingest_cmd = result["IngestAdvBulkSources"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        assert "warehouse/bronze/runs/fetch-adv-bulk/" in ingest_cmd
        assert result["IngestAdvBulkSources"]["Next"] == "FirmRosterForceCheck"

    def test_all_three_tasks_share_the_same_failure_catch_target(self):
        result = self._build()
        for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
            assert result[state_name]["Catch"] == [{
                "ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease",
            }]

    def test_all_three_tasks_set_result_path_none(self):
        # Matches the real ADV/FirmRoster call sites, which manually set
        # this after calling ecs_state() (D-15 bug prevention: without it,
        # the ECS task's own output would replace $.dataset_period/$.force
        # in the machine's running input).
        result = self._build()
        for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
            assert result[state_name]["ResultPath"] is None

    def test_choice_state_itself_has_no_catch(self):
        assert "Catch" not in self._build()["ForceCheck"]
