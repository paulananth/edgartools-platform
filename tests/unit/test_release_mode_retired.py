"""silver-merge-engine-migration Ticket 11: release mode is retired.

The strict release path of `one_click_data_refresh` (Ticket 20's
manifest-bounded relationship bulk load) last ran 2026-07-25. Since then its
manifest builder read a retired DuckDB file and its Branch B parsers read
same-run silver rows through raw SQL, which Ticket 06d made impossible. The
user decided 2026-09-14 that release mode is not needed, so the strict
Step Functions path, `reconcile-relationship-release`, and every
`--release-mode` code path are deleted.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from edgar_warehouse import cli
from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.workflows import fundamentals_ingest


@pytest.mark.parametrize(
    "argv",
    [
        ["bootstrap-batch", "--cik-list", "1001", "--release-mode"],
        ["bootstrap-batch", "--cik-list", "1001", "--candidate-manifest", "s3://b/c.json"],
        ["bootstrap-batch", "--cik-list", "1001", "--repair-manifest", "s3://b/r.json"],
        ["bootstrap-fundamentals", "--cik-list", "1001", "--release-mode"],
        ["bootstrap-fundamentals", "--cik-list", "1001", "--candidate-manifest", "s3://b/c.json"],
        [
            "reconcile-relationship-release",
            "--candidate-manifest", "s3://b/c.json",
            "--attestations-json", "{}",
        ],
    ],
)
def test_release_mode_cli_surface_is_gone(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(argv)


def test_mdm_release_manifest_command_is_gone() -> None:
    import argparse

    from edgar_warehouse.mdm.cli import register_mdm_subparser

    parser = argparse.ArgumentParser()
    register_mdm_subparser(parser.add_subparsers())
    with pytest.raises(SystemExit):
        parser.parse_args(["mdm", "build-relationship-release-manifest", "--help"])


def test_branch_b_deferred_parser_policy_is_gone() -> None:
    with pytest.raises(WarehouseRuntimeError, match="Unsupported parser_policy"):
        warehouse_orchestrator._parser_policy_runs("branch_b_deferred")


def test_release_parameters_are_gone_from_capture_and_fundamentals() -> None:
    assert not hasattr(warehouse_orchestrator, "_run_release_branch_b_parsers")
    for function, removed in (
        (
            warehouse_orchestrator._run_submissions_bronze_then_silver,
            {"release_mode", "repair_manifest_accessions"},
        ),
        (
            warehouse_orchestrator._run_configured_form_artifact_pipeline,
            {"release_mode", "repair_manifest_accessions"},
        ),
        (fundamentals_ingest.run_bootstrap_fundamentals_per_filing, {"release_mode", "candidate_accessions"}),
        (fundamentals_ingest.run_bootstrap_thirteenf, {"release_mode", "candidate_accessions"}),
    ):
        assert removed.isdisjoint(inspect.signature(function).parameters), function.__name__


def test_one_click_data_refresh_has_no_strict_release_path(tmp_path: Path) -> None:
    from tests.architecture.test_mdm_pipeline_machine_tails import _generate

    definition = _generate("write_one_click_data_refresh_definition", tmp_path, "one_click")

    assert definition["StartAt"] == "ResumeFromRunIdPresenceCheck"
    leftovers = sorted(
        name
        for name in definition["States"]
        if "strict" in name.lower() or name in {"ReleaseModeCheck", "ReconcileRelationshipRelease"}
    )
    assert leftovers == []
