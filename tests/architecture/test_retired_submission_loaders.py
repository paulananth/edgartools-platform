"""Historical submission loaders and landing APIs cannot re-enter runtime."""
import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RETIRED = ("edgar_warehouse.loaders", "edgar_warehouse.silver_landing_store")


def imports(node, package):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level:
            module = resolve_name("." * node.level + module, package)
        return [module, *(f"{module}.{a.name}" for a in node.names)]
    return []


@pytest.mark.parametrize("statement,package", [
    ("import edgar_warehouse.loaders.common", "edgar_warehouse"),
    ("from edgar_warehouse import loaders", "edgar_warehouse"),
    ("from edgar_warehouse import silver_landing_store", "edgar_warehouse"),
    ("from . import loaders", "edgar_warehouse"),
    ("from ..loaders import common", "edgar_warehouse.workers"),
    ("from ... import silver_landing_store", "edgar_warehouse.mdm.clean"),
])
def test_retirement_guard_detects_deliberately_reintroduced_imports(statement, package):
    names = imports(ast.parse(statement).body[0], package)
    assert any(name == old or name.startswith(old + ".") for old in RETIRED for name in names)


def test_retired_submission_modules_have_no_runtime_sources_or_consumers():
    assert not (ROOT / "edgar_warehouse/silver_landing_store.py").exists()
    assert not list((ROOT / "edgar_warehouse/loaders").rglob("*.py"))
    for folder in (ROOT / "edgar_warehouse", ROOT / "packages"):
        for path in folder.rglob("*.py"):
            parts = path.parent.relative_to(folder).parts
            package = ".".join(("edgar_warehouse", *parts)) if folder.name == "edgar_warehouse" else ".".join(parts)
            for node in ast.walk(ast.parse(path.read_text())):
                names = imports(node, package)
                assert not any(name == old or name.startswith(old + ".")
                               for old in RETIRED for name in names), path
