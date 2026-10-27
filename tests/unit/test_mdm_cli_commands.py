"""The `mdm` commands are each bound to one
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
    (["mdm", "rebuild-name-index", "--limit", "1"], "rebuild_name_index"),
])
def test_each_command_runs_its_function(monkeypatch, argv, function):
    called = []
    monkeypatch.setattr(clean_cli, function, lambda args: called.append(args.mdm_command) or 0)
    args = build_parser().parse_args(argv)
    assert args.handler(args) == 0 and called == [argv[1]]


def test_retired_commands_stay_unavailable():
    parser = build_parser()
    for retired in ("mastering", "apply-decisions", "bronze-receipts", "correction-batch", "export"):
        with pytest.raises(SystemExit):
            parser.parse_args(["mdm", retired])
    with pytest.raises(SystemExit):
        parser.parse_args(["mdm", "migrate", "--model", "legacy"])


def test_force_publish_uses_the_governed_route(monkeypatch, tmp_path, capsys):
    import json
    from types import SimpleNamespace
    from edgar_warehouse.mdm.clean import forced_publication, store

    calls, disposed = [], []
    engine = SimpleNamespace(dispose=lambda: disposed.append(True))
    selected = object()
    monkeypatch.setattr(clean_cli, "engine_from_env", lambda name: engine)
    monkeypatch.setattr(store, "Store", lambda candidate: selected if candidate is engine else None)

    def page(actual, consumer, run, number, after, limit):
        assert actual is selected
        calls.append((consumer, number))
        return {"batch_id": "invented-forced-page", "generation": 1, "records": 1, "next": None}

    monkeypatch.setattr(forced_publication, "page", page)
    args = build_parser().parse_args(["mdm", "force-publish", "--consumer", "invented-export",
                                     "--output", str(tmp_path / "output")])
    assert clean_cli.force_publish(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pages"] == report["records"] == 1 and report["forced"] is True
    assert calls == [("invented-export", 1)] and disposed == [True]


def test_owner_migration_defaults_to_governed_storage():
    assert build_parser().parse_args(["mdm", "migrate"]).prepared_store is True
