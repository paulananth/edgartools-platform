"""Normal runtime source never calls a retired MDM SQL calculation."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_has_no_retired_routine_call():
    migration = (ROOT / "edgar_warehouse/mdm/migrations/028_retire_business_routines.sql").read_text()
    names = set(re.findall(r"mdm\.([a-z_]+)\(", migration.split("DROP FUNCTION IF EXISTS", 1)[1]))
    assert len(names) == 34
    call = re.compile(r"\bmdm\.(" + "|".join(sorted(names)) + r")\s*\(")
    offenders = []
    for path in (ROOT / "edgar_warehouse").rglob("*.py"):
        tree = ast.parse(path.read_text())
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.body and isinstance(n.body[0], ast.Expr)
                      and isinstance(n.body[0].value, ast.Constant)
                      and isinstance(n.body[0].value.value, str)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                for match in call.finditer(node.value):
                    offenders.append((str(path.relative_to(ROOT)), node.lineno, match.group(1)))
    assert offenders == []
