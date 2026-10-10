"""The `mdm` command offers five Clean MDM commands, each bound to one
function (platform validation slice 2a)."""
from __future__ import annotations

import pytest

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm.clean import cli as clean_cli

CENSUS = ["--landing-root", "r", "--landing-manifest", "m", "--gleif-reading", "a",
          "--gleif-reading-sha256", "s", "--gleif-metadata", "x", "--output", "o"]
PREPARE = ["--landing-root", "r", "--landing-manifest", "m", "--ticker-manifest", "t",
           "--name-census", "c", "--output", "o", "--as-of", "2026-09-30T00:00:00Z", "--revision", "0"]


@pytest.mark.parametrize("argv,function", [
    (["mdm", "counts"], "counts"),
    (["mdm", "check-connectivity"], "check_connectivity"),
    (["mdm", "name-census", *CENSUS], "name_census"),
    (["mdm", "prepare-clean-company", *PREPARE], "prepare_clean_company"),
])
def test_each_command_runs_its_function(monkeypatch, argv, function):
    called = []
    monkeypatch.setattr(clean_cli, function, lambda args: called.append(args.mdm_command) or 0)
    args = build_parser().parse_args(argv)
    assert args.handler(args) == 0 and called == [argv[1]]


def test_only_the_five_clean_commands_are_offered():
    parser = build_parser()
    for retired in ("mastering", "apply-decisions", "bronze-receipts", "correction-batch", "export"):
        with pytest.raises(SystemExit):
            parser.parse_args(["mdm", retired])
    with pytest.raises(SystemExit):
        parser.parse_args(["mdm", "migrate", "--model", "legacy"])
