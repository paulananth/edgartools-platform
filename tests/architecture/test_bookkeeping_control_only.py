"""Bookkeeping is control only: it starts with every domain package blocked.

Gate 1 of `skills/bookkeeping/INDEPENDENCE.md` (mastering to-do 20a). The
check runs in a child process, so imports the test session already made
cannot hide a dependency.
"""
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]

# Domain code and parser libraries the control process must never load.
BLOCKED = ("edgar", "pyarrow", "lxml", "bs4", "source_contract",
           "edgar_warehouse.mdm", "edgar_warehouse.loaders", "edgar_warehouse.parsers",
           "edgar_warehouse.serving", "edgar_warehouse.application", "edgar_warehouse.acquisition",
           "edgar_warehouse.silver_landing_store", "edgar_warehouse.silver_schema",
           "edgar_warehouse.workers")

GUARD = f'''
import importlib.abc, sys
BLOCKED = {BLOCKED!r}

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if any(name == b or name.startswith(b + ".") for b in BLOCKED):
            raise ImportError("Bookkeeping control loaded a domain package: " + name)
        return None

sys.meta_path.insert(0, Guard())
'''


def run_guarded(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", GUARD + code], cwd=ROOT, capture_output=True, text=True)


def test_control_package_imports_no_domain_code():
    offenders = []
    for path in (ROOT / "edgar_warehouse/bookkeeping").rglob("*.py"):
        package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                         if node.level else node.module]
            else:
                continue
            offenders += [(path.relative_to(ROOT).as_posix(), node.lineno, name) for name in names
                          if any(name == b or name.startswith(b + ".") for b in BLOCKED)]
    assert not offenders


def test_control_starts_and_builds_every_command_with_domains_blocked():
    result = run_guarded('''
from edgar_warehouse.cli import main
from edgar_warehouse.bookkeeping.clean import cli, config, database, destinations, engine, feeds, artifacts
for command in ("claim", "verifications", "renew", "report", "fail", "admit", "status", "resume", "finalize"):
    try:
        main(["bookkeeping", command, "--help"])
    except SystemExit as exit:
        assert exit.code == 0, command
print("control ready")
''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("control ready")


def test_the_guard_catches_a_reintroduced_dependency():
    result = run_guarded("import edgar_warehouse.bookkeeping.clean.engine\nimport edgar_warehouse.mdm.clean.store")
    assert result.returncode != 0
    assert "Bookkeeping control loaded a domain package: edgar_warehouse.mdm" in result.stderr


def test_workers_never_reach_into_control_internals():
    """Workers speak only through the commands: no engine, database or SQL."""
    offenders = []
    for path in (ROOT / "edgar_warehouse/workers").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("edgar_warehouse.bookkeeping"):
                if node.module != "edgar_warehouse.bookkeeping.clean.artifacts":
                    offenders.append((path.name, node.module))
            if isinstance(node, ast.Import) and any(a.name.startswith("sqlalchemy") for a in node.names):
                offenders.append((path.name, "sqlalchemy"))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.name.startswith("edgar_warehouse.bookkeeping")
                            and alias.name != "edgar_warehouse.bookkeeping.clean.artifacts"):
                        offenders.append((path.name, alias.name))
    assert not offenders
