from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from edgar_warehouse.rules import files

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/dev/rules_change_guard.py"
_spec = importlib.util.spec_from_file_location("rules_change_guard", SCRIPT)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def source_body(name: str, *, record_key: str = "id") -> dict:
    return {
        "source": name,
        "dataset_contracts": {
            f"{name}.v1": {
                "contract": {
                    "record_key": record_key,
                    "publication_key": "filing",
                    "adapter": {
                        "record_key": record_key,
                        "record_key_format": "text",
                        "identifiers": ["issuer_id"],
                    },
                }
            }
        },
    }


def write_source(root: Path, name: str, body: dict) -> Path:
    path = root / "sources" / name / "source.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(files.dumps(body), encoding="utf-8")
    return path


def test_main_checks_only_the_changed_source_when_legacy_rules_are_present(tmp_path):
    root = tmp_path / "rules"
    write_source(root, "changed", {"source": "changed"})
    write_source(root, "legacy", {"source": "legacy", "mdm": {"old": True}})
    paths_file = tmp_path / "changed-paths.txt"
    paths_file.write_text("rules/sources/changed/source.yaml\n", encoding="utf-8")

    assert files.check(root=root)["source:legacy"].startswith("refused (RulesFileError)")
    assert guard.main(["HEAD", str(paths_file), "--root", str(root)]) == 0



def test_changed_merge_policy_does_not_parse_unrelated_legacy_source(tmp_path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT / "merge", root / "merge")
    write_source(root, "legacy", {"source": "legacy", "mdm": {"old": True}})

    problems = guard.check_changed_documents(["rules/merge/kinds/company.yaml"], root)

    assert problems == []



def test_invalid_merge_is_reported_once_without_repeating_identity_parse(tmp_path):
    root = tmp_path / "rules"
    policy = root / "merge" / "policy.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("kinds: [\n", encoding="utf-8")

    problems = guard.check_changed_rules(["rules/merge/policy.yaml"], "HEAD", root)

    assert len(problems) == 1
    assert problems[0].startswith("merge: refused")


def test_changed_pipeline_does_not_parse_unrelated_legacy_source(tmp_path):
    root = tmp_path / "rules"
    write_source(root, "legacy", {"source": "legacy", "mdm": {"old": True}})
    pipeline = root / "pipelines" / "sample" / "pipeline.yaml"
    pipeline.parent.mkdir(parents=True)
    pipeline.write_text(files.dumps({"pipeline": "sample"}), encoding="utf-8")

    problems = guard.check_changed_documents(["rules/pipelines/sample/pipeline.yaml"], root)

    assert problems == []


def test_contract_identity_check_reads_contracts_without_expanding_legacy_source(tmp_path):
    before_path = write_source(tmp_path / "before", "sample", source_body("sample"))
    after_body = {**source_body("sample"), "mdm": {"legacy_extract": {"format": "csv"}}}
    after_path = write_source(tmp_path / "after", "sample", after_body)

    with pytest.raises(files.RulesFileError):
        files.source("sample", tmp_path / "after")
    before = guard.read_contracts(before_path)
    after = guard.read_contracts(after_path)

    assert guard.contract_identity_problems("sample", before, after) == []


def test_changed_contract_identity_is_refused_with_replacement_guidance():
    before = {code: entry["contract"] for code, entry in source_body("sample")["dataset_contracts"].items()}
    after = {code: entry["contract"] for code, entry in source_body("sample", record_key="accession")[
        "dataset_contracts"].items()}

    problems = guard.contract_identity_problems("sample", before, after)

    assert len(problems) == 1
    assert "sample.v1" in problems[0]
    assert "new source code" in problems[0]


def test_merge_rule_steps_require_a_new_version_when_existing_rule_changes():
    before = {"kinds": {"company": {"rules": [
        {"rule_id": "name-match", "version": "company-name-v1", "steps": [{"field": "name"}]}
    ]}}}
    changed = {"kinds": {"company": {"rules": [
        {"rule_id": "name-match", "version": "company-name-v1", "steps": [{"field": "address"}]}
    ]}}}
    versioned = {"kinds": {"company": {"rules": [
        {"rule_id": "name-match", "version": "company-name-v2", "steps": [{"field": "address"}]}
    ]}}}

    problems = guard.merge_identity_problems(before, changed)

    assert problems == ["company/name-match@company-name-v1: rule changed under the same version; use a new version"]
    assert guard.merge_identity_problems(before, versioned) == []
