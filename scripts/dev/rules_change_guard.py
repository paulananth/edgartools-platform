#!/usr/bin/env python3
"""Validate changed source, merge and pipeline documents plus protected identities."""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.mdm.store import Conflict, protected_change
from edgar_warehouse.rules import files


def _rules_parts(paths: Iterable[str]) -> list[PurePosixPath]:
    return [PurePosixPath(path) for path in paths
            if PurePosixPath(path).parts[:1] == ("rules",)]


def check_changed_documents(paths: Iterable[str], root: Path) -> list[str]:
    """Check changed source.yaml/quality.yaml, merge and pipeline documents only."""
    rules_paths = _rules_parts(paths)
    source_names = sorted({path.parts[2] for path in rules_paths
                           if len(path.parts) >= 4 and path.parts[1] == "sources"
                           and path.parts[-1] in {"source.yaml", "quality.yaml"}
                           and (root / "sources" / path.parts[2] / "source.yaml").is_file()})
    pipeline_names = sorted({path.parts[2] for path in rules_paths
                             if len(path.parts) >= 4 and path.parts[1] == "pipelines"
                             and path.parts[-1] == "pipeline.yaml"
                             and (root / "pipelines" / path.parts[2] / "pipeline.yaml").is_file()})
    merge_changed = any(len(path.parts) >= 3 and path.parts[1] == "merge"
                        and path.suffix in {".yaml", ".yml"} for path in rules_paths)

    problems = []
    if source_names:
        results = files.check(source_names, root)
        problems.extend(f"{name}: {reason}" for name, reason in sorted(results.items()) if reason != "ok")
    if merge_changed:
        try:
            files.check_document("merge", files.policy(root))
        except (Blocked, Conflict, files.RulesFileError, OSError) as error:
            problems.append(f"merge: refused ({type(error).__name__}): {error}")
    for name in pipeline_names:
        try:
            files.check_document("pipeline", files.pipeline(name, root))
        except (Blocked, Conflict, files.RulesFileError, OSError) as error:
            problems.append(f"pipeline:{name}: refused ({type(error).__name__}): {error}")
    return problems


def _contracts(body: object, name: str) -> dict[str, dict]:
    if not isinstance(body, dict):
        raise files.RulesFileError(f"{name}: source document must be a mapping")
    contracts = body.get("dataset_contracts") or {}
    if not isinstance(contracts, dict):
        raise files.RulesFileError(f"{name}: Dataset Contracts must be a mapping")
    found = {}
    for code, spec in contracts.items():
        contract = spec.get("contract") if isinstance(spec, dict) else None
        if not isinstance(code, str) or not isinstance(contract, dict):
            raise files.RulesFileError(f"{name}: Dataset Contract entries need a contract mapping")
        found[code] = contract
    return found


def read_contracts(path: Path) -> dict[str, dict]:
    """Read Dataset Contracts without expanding or validating unrelated source sections."""
    return _contracts(files.load(path), str(path))


def contract_identity_problems(source: str, before: dict[str, dict], after: dict[str, dict]) -> list[str]:
    problems = []
    for code in sorted(before.keys() & after.keys()):
        try:
            protected_change(before[code], after[code])
        except Conflict as error:
            problems.append(f"{source} {code}: {str(error).split(': ', 1)[-1]}; register a new source code")
    return problems


def _base_source(base: str, name: str) -> dict[str, dict] | None:
    path = f"rules/sources/{name}/source.yaml"
    result = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=False)
    if result.returncode:
        return None  # A valid base with no such source means this source is new.
    return _contracts(files.loads(result.stdout, path), path)


def _changed_source_names(paths: Iterable[str]) -> list[str]:
    return sorted({path.parts[2] for path in _rules_parts(paths)
                   if len(path.parts) == 4 and path.parts[1] == "sources"
                   and path.parts[3] == "source.yaml"})


def _changed_merge(paths: Iterable[str]) -> bool:
    return any(len(path.parts) >= 3 and path.parts[1] == "merge"
               and path.suffix in {".yaml", ".yml"} for path in _rules_parts(paths))


def _rule_map(policy: dict) -> dict[tuple[str, str, str], dict]:
    return {(kind, rule["rule_id"], str(rule.get("version"))): rule
            for kind, block in (policy.get("kinds") or {}).items()
            for rule in block.get("rules") or []}


def merge_identity_problems(before_policy: dict, after_policy: dict) -> list[str]:
    before = _rule_map(before_policy)
    after = _rule_map(after_policy)
    return [f"{kind}/{rule_id}@{version}: rule changed under the same version; use a new version"
            for (kind, rule_id, version), rule in sorted(after.items())
            if (kind, rule_id, version) in before and before[(kind, rule_id, version)] != rule]


def _merge_identity_problems(base: str, root: Path) -> list[str]:
    revision = subprocess.run(["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
                              capture_output=True, text=True, check=False)
    if revision.returncode:
        return [f"merge: base revision is unavailable ({base})"]
    with tempfile.TemporaryDirectory() as temporary:
        archive = subprocess.run(["git", "archive", base, "rules/merge"], capture_output=True, check=False)
        if archive.returncode:
            return ["merge: could not read the base merge Rules"]
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as source:
            source.extractall(temporary, filter="data")
        before_root = Path(temporary) / "rules"
        try:
            before = files.policy(before_root)
            after = files.policy(root)
            return merge_identity_problems(before, after)
        except (files.RulesFileError, OSError, KeyError, TypeError, AttributeError) as error:
            return [f"merge: identity comparison refused ({type(error).__name__})"]


def check_changed_rules(paths: Iterable[str], base: str, root: Path) -> list[str]:
    paths = list(paths)
    problems = check_changed_documents(paths, root)
    for name in _changed_source_names(paths):
        current_path = root / "sources" / name / "source.yaml"
        if not current_path.is_file():
            continue
        revision = subprocess.run(["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
                                  capture_output=True, text=True, check=False)
        if revision.returncode:
            problems.append(f"source:{name}: base revision is unavailable ({base})")
            continue
        try:
            before = _base_source(base, name)
            after = read_contracts(current_path)
        except (files.RulesFileError, OSError) as error:
            problems.append(f"source:{name}: Dataset Contract identity comparison refused ({type(error).__name__})")
            continue
        if before is not None:
            problems.extend(contract_identity_problems(name, before, after))
    if _changed_merge(paths) and not any(problem.startswith("merge:") for problem in problems):
        problems.extend(_merge_identity_problems(base, root))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check changed Rules documents and protected identities only")
    parser.add_argument("base", help="Git base revision to compare against")
    parser.add_argument("changed_paths", type=Path, help="newline-delimited changed paths from overlap_guard")
    parser.add_argument("--root", type=Path, default=files.ROOT, help="Rules directory")
    args = parser.parse_args(argv)
    try:
        paths = args.changed_paths.read_text(encoding="utf-8").splitlines()
        problems = check_changed_rules(paths, args.base, args.root)
    except OSError as error:
        print(f"rules_change_guard: cannot read changed paths ({type(error).__name__})", file=sys.stderr)
        return 1
    if problems:
        for problem in problems:
            print(f"rules_change_guard: {problem}", file=sys.stderr)
        return 1
    print("rules_change_guard: changed Rules documents and protected identities pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
