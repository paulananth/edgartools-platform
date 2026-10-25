"""The `mdm` command offers five MDM commands, each bound to one
function (platform validation slice 2a)."""
from __future__ import annotations

import pytest

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm.clean import cli as clean_cli

CENSUS = ["--capture", "c", "--population", "p", "--gleif-reading", "a",
          "--gleif-reading-sha256", "s", "--gleif-metadata", "x", "--output", "o"]
PREPARE = ["--capture", "c", "--documents", "d", "--population", "p", "--catalog", "k", "--capture-run", "r",
           "--catalog-run", "t", "--observed-at", "2026-09-30T00:00:00Z", "--name-census", "c", "--output", "o", "--as-of", "2026-09-30T00:00:00Z", "--revision", "0"]


@pytest.mark.parametrize("argv,function", [
    (["mdm", "counts"], "counts"),
    (["mdm", "check-connectivity"], "check_connectivity"),
    (["mdm", "name-census", *CENSUS], "name_census"),
    (["mdm", "prepare-clean-company", *PREPARE], "prepare_clean_company"),
    (["mdm", "force-publish", "--consumer", "graph", "--output", "o"], "force_publish"),
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


def test_force_publish_keeps_the_legacy_route(monkeypatch, tmp_path, capsys):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    calls, disposed = [], []

    def page(statement, parameters):
        assert "mdm.force_publish" in str(statement)
        calls.append(parameters)
        return {"batch_id": "invented-forced-page", "generation": 1, "records": 1, "next": None}

    engine = SimpleNamespace(connect=lambda: nullcontext(object()),
        begin=lambda: nullcontext(SimpleNamespace(scalar=page)),
        dispose=lambda: disposed.append(True))
    monkeypatch.setattr(clean_cli, "engine_from_env", lambda name: engine)
    monkeypatch.setattr(clean_cli, "_inspection_adapter", lambda conn: None)
    args = build_parser().parse_args(["mdm", "force-publish", "--consumer", "invented-export",
                                     "--output", str(tmp_path / "output")])
    assert clean_cli.force_publish(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pages"] == report["records"] == 1 and report["forced"] is True
    assert len(calls) == 1 and calls[0]["c"] == "invented-export"
    assert disposed == [True]
