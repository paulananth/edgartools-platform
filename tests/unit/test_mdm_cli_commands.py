"""The `mdm` commands are each bound to one
function (platform validation slice 2a)."""
from __future__ import annotations

import pytest

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm import commands as commands

NAME_COUNT = ["--capture", "c", "--population", "p", "--gleif-reading", "a",
          "--gleif-reading-sha256", "s", "--gleif-metadata", "x", "--output", "o"]

@pytest.mark.parametrize("argv,function", [
    (["mdm", "counts"], "counts"),
    (["mdm", "check-connectivity"], "check_connectivity"),
    (["mdm", "name-count", *NAME_COUNT], "name_count"),
    (["mdm", "rebuild-name-index", "--limit", "1"], "rebuild_name_index"),
    (["mdm", "rebuild-detail-lookup", "--limit", "1"], "rebuild_detail_lookup"),
    (["mdm", "convert-native", "--limit", "1"], "convert_native"),
    (["mdm", "steward", "split", "--merge", "m", "--by", "Sam", "--reason", "wrong"], "steward_split"),
])
def test_each_command_runs_its_function(monkeypatch, argv, function):
    called = []
    monkeypatch.setattr(commands, function, lambda args: called.append(args.mdm_command) or 0)
    args = build_parser().parse_args(argv)
    assert args.handler(args) == 0 and called == [argv[1]]


def test_a_split_previews_unless_confirmed_and_needs_who_and_why():
    parser = build_parser()
    split = ["mdm", "steward", "split", "--merge", "m", "--by", "Sam", "--reason", "two different companies"]
    assert parser.parse_args(split).confirm is False and parser.parse_args([*split, "--confirm"]).confirm is True
    for missing in ("--by", "--reason", "--merge"):
        argv = split[:]
        at = argv.index(missing)
        del argv[at:at + 2]
        with pytest.raises(SystemExit):
            parser.parse_args(argv)


def test_retired_commands_stay_unavailable():
    parser = build_parser()
    for retired in ("mastering", "apply-decisions", "bronze-receipts", "correction-batch", "export", "force-publish"):
        with pytest.raises(SystemExit):
            parser.parse_args(["mdm", retired])
    with pytest.raises(SystemExit):
        parser.parse_args(["mdm", "migrate", "--model", "legacy"])


def test_owner_migration_defaults_to_governed_storage():
    assert build_parser().parse_args(["mdm", "migrate"]).prepared_store is True
