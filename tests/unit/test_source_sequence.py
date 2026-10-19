"""Source sequence checks use files only; they never submit or activate a run."""
import argparse
import json

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.rules.cli import register


def source(root, name, target="mastering"):
    folder = root / "sources" / name
    folder.mkdir(parents=True)
    (folder / "source.yaml").write_text(files.dumps({
        "bookkeeping": {"version": 1, "targets": {target: {
            "steps": [{"name": "read", "operation": "source.read", "requires": [],
                       "key": "{unit}", "leases": ["artifact:{destination}"],
                       "checks": ["input.hash", "output.receipt", "source.output"]}],
            "checks": ["manifest.hash", "work.accounting", "journal.delivered"],
        }}}
    }))


def entry(*, requires=(), after=(), target="mastering"):
    return {"target": target, "requires": list(requires), "after": list(after)}


def check(tmp_path, capsys, entries, *options):
    path = tmp_path / "source-sequence.yaml"
    path.write_text(files.dumps({"version": 1, "sources": entries}))
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["rules", "sequence", "check", "--root", str(tmp_path),
                             "--file", str(path), *options])
    code = args.handler(args)
    output = capsys.readouterr()
    return code, json.loads(output.out) if output.out else output.err


def test_selected_source_does_not_pull_preferred_predecessors(tmp_path, capsys):
    source(tmp_path, "company")
    source(tmp_path, "person")
    code, result = check(tmp_path, capsys, {"company": entry(), "person": entry(after=["company"])},
                         "--source", "person")
    assert code == 0
    assert result["order"] == ["person"]
    assert result["sources"]["person"]["status"] == "configured"
    assert result["runtime_readiness"] == "not_checked"


def test_delayed_source_does_not_stop_independent_sources(tmp_path, capsys):
    # Missing deferred/unselected files must not prevent independent work.
    source(tmp_path, "person")
    source(tmp_path, "security")
    source(tmp_path, "filings")
    code, result = check(tmp_path, capsys, {
        "company": entry(),
        "person": entry(after=["company"]),
        "security": entry(requires=["company"]),
        "filings": entry(requires=["security"]),
    }, "--defer", "company")
    assert code == 3
    assert result["order"] == ["person"]
    assert result["sources"] == {
        "company": {"target": "mastering", "status": "deferred", "reasons": ["explicit_source_deferral"]},
        "person": {"target": "mastering", "status": "configured", "reasons": []},
        "security": {"target": "mastering", "status": "blocked",
                     "reasons": ["required_source_unavailable:company"]},
        "filings": {"target": "mastering", "status": "blocked",
                    "reasons": ["required_source_unavailable:security"]},
    }


def test_required_sources_are_included_before_the_selected_source(tmp_path, capsys):
    source(tmp_path, "company")
    source(tmp_path, "security")
    # Input declaration order is deliberately different from dependency order.
    code, result = check(tmp_path, capsys, {
        "security": entry(requires=["company"]), "company": entry(), "unrelated": entry(),
    }, "--source", "security")
    assert code == 0
    assert result["order"] == ["company", "security"]
    assert set(result["sources"]) == {"company", "security"}


@pytest.mark.parametrize("entries, options", [
    ({"company": entry(requires=["unknown"])}, []),
    ({"company": entry(requires=["company"])}, []),
    ({"company": entry(after=["person"]), "person": entry(requires=["company"])}, []),
    ({"company": entry(requires=["person", "person"]), "person": entry()}, []),
    ({"company": {**entry(), "skip_checks": True}}, []),
    ({"company": entry(target="../outside")}, []),
    ({"company": entry()}, ["--source", "unknown"]),
    ({"company": entry()}, ["--defer", "unknown"]),
    ({"company": entry(), "person": entry()}, ["--source", "person", "--defer", "company"]),
    ({"company": entry()}, ["--source", "company", "--source", "company"]),
])
def test_invalid_sequence_is_refused_before_source_files_are_read(tmp_path, capsys, entries, options):
    code, result = check(tmp_path, capsys, entries, *options)
    assert code == 2
    assert result.startswith("Source sequence refused:")


@pytest.mark.parametrize("target", [None, "not-built"])
def test_missing_target_blocks_only_affected_work(tmp_path, capsys, target):
    source(tmp_path, "person")
    source(tmp_path, "company")
    source(tmp_path, "security")
    code, result = check(tmp_path, capsys, {
        "company": entry(target=target), "person": entry(after=["company"]),
        "security": entry(requires=["company"]),
    })
    assert code == 3
    assert result["order"] == ["person"]
    assert result["sources"]["company"]["status"] == "blocked"
    assert "required_source_unavailable:company" in result["sources"]["security"]["reasons"]


@pytest.mark.parametrize("operation,reason", [
    ("provider.capture", "provider_acquisition_is_separate"),
    ("not.installed", "unsupported_worker_profile"),
])
def test_unsupported_or_provider_workers_cannot_be_planned_as_local_processing(tmp_path, capsys, operation, reason):
    source(tmp_path, "company")
    path = tmp_path / "sources" / "company" / "source.yaml"
    body = files.load(path)
    body["bookkeeping"]["targets"]["mastering"]["steps"][0]["operation"] = operation
    path.write_text(files.dumps(body))
    code, result = check(tmp_path, capsys, {"company": entry()})
    assert code == 3
    assert result["order"] == []
    assert result["sources"]["company"]["reasons"] == [reason]


def test_default_inventory_accounts_for_each_committed_source(capsys):
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["rules", "sequence", "check", "--root", str(files.ROOT)])
    assert args.handler(args) == 3
    result = json.loads(capsys.readouterr().out)
    expected_sources = {path.parent.name for path in (files.ROOT / "sources").glob("*/source.yaml")}
    assert set(result["sources"]) == expected_sources
    assert result["order"] == ["sec.submissions.company", "gleif", "sec.nport.registrant", "sec.submissions.person",
                               "sec.nport.fund"]
    assert {name for name, item in result["sources"].items() if item["status"] == "blocked"} == {
        "iapd.adv", "sec.ownership", "sec.thirteenf.information_table",
        "sec.nport.security", "openfigi",
    }


@pytest.mark.parametrize("name", [
    "sec.submissions.company", "gleif", "sec.submissions.person", "iapd.adv", "sec.ownership",
    "sec.thirteenf.information_table", "sec.nport.registrant", "sec.nport.fund", "sec.nport.security", "openfigi",
])
def test_each_committed_source_can_be_checked_on_its_own(capsys, name):
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["rules", "sequence", "check", "--root", str(files.ROOT), "--source", name])
    code = args.handler(args)
    result = json.loads(capsys.readouterr().out)
    assert set(result["sources"]) == {name}
    assert code == (0 if name in {"sec.submissions.company", "gleif", "sec.submissions.person",
                                  "sec.nport.registrant", "sec.nport.fund"} else 3)


def test_malformed_source_is_reported_without_leaking_its_values(tmp_path, capsys):
    source(tmp_path, "company")
    path = tmp_path / "sources" / "company" / "source.yaml"
    path.write_text("private: invented-secret\nprivate: duplicate\n")
    code, result = check(tmp_path, capsys, {"company": entry()})
    assert code == 3
    assert result["sources"]["company"]["reasons"] == ["source_target_invalid_or_missing"]
    assert "invented-secret" not in json.dumps(result)


def test_malformed_sequence_is_reported_without_echoing_private_yaml(tmp_path, capsys):
    (tmp_path / "source-sequence.yaml").write_text("version: 1\npassword: [invented-secret\n")
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["rules", "sequence", "check", "--root", str(tmp_path)])
    assert args.handler(args) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Source sequence refused: sequence_file_invalid_or_missing\n"
