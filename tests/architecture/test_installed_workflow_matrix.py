"""Every installed proof family and surface has a required CI group."""
import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_installed_workflow_matrix_has_no_missing_family_or_unrun_surface():
    tree = ast.parse((ROOT / "tests/installed_workflow/test_mdm_workflow.py").read_text())
    declarations = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id in {"CASES", "GROUPS"}
                   or isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == "CASES"
                   for target in node.targets):
                declarations.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Subscript) and isinstance(func.value.value, ast.Name) and func.value.value.id == "CASES":
                declarations.append(node)
    scope = {}
    exec(compile(ast.Module(body=declarations, type_ignores=[]), "case-manifest", "exec"), scope)
    cases, groups = scope["CASES"], scope["GROUPS"]
    assert {family for items in cases.values() for families in items.values() for family in families} | {"Q01"} == {f"Q{n:02}" for n in range(1,19)}
    assert set().union(*groups.values()) == set(cases)
    assert sum(map(len,groups.values())) == len(cases), "A surface must run in exactly one CI group"
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    job = ci["installed-workflow"]
    assert set(job["strategy"]["matrix"]["group"]) == set(groups)
    assert job["env"]["MDM_WORKFLOW_SHARD"] == "${{ matrix.group }}"
    assert "installed-workflow" in ci["ci-gate"]["needs"]
