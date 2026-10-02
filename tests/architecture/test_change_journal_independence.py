"""Journal consumers depend on its envelope protocol; the journal imports no owner."""

import ast
import importlib.util
from pathlib import Path
import sys

import pytest

from tests.support.journal_isolation import isolated_package, run_isolated


ROOT = Path(__file__).resolve().parents[2]


def test_journal_imports_only_itself_pure_contracts_stdlib_and_sqlalchemy():
    offenders = []
    primitives = ROOT / "edgar_warehouse/control_contract.py"
    paths = [*(ROOT / "edgar_warehouse/change_journal").rglob("*.py"), primitives]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [importlib.util.resolve_name("." * node.level + (node.module or ""),
                                                    "edgar_warehouse.change_journal")
                         if node.level else node.module]
            else:
                continue
            for name in names:
                allowed = name.split(".")[0] in sys.stdlib_module_names
                if path != primitives:
                    allowed = (allowed
                               or name == "sqlalchemy" or name.startswith("sqlalchemy.")
                               or name == "edgar_warehouse.control_contract"
                               or name == "edgar_warehouse.change_journal"
                               or name.startswith("edgar_warehouse.change_journal."))
                if not allowed:
                    offenders.append((path.relative_to(ROOT).as_posix(), node.lineno, name))
    assert not offenders


def test_journal_starts_and_accepts_unseen_producer_without_domain_packages(tmp_path):
    root = isolated_package(tmp_path)
    result = run_isolated(root, '''
from edgar_warehouse.change_journal import envelope
from edgar_warehouse.change_journal.cli import build_parser
from edgar_warehouse.change_journal.database import migrate
from edgar_warehouse.control_contract import canonical

value = envelope(producer="unseen.producer", event_key="opaque-key", run_id="00000000-0000-0000-0000-000000000001",
    source="unseen.source", feed="unseen.feed", event_type="unseen.event", occurred_at="2026-10-02T00:00:00+00:00",
    evidence=[{"uri": "s3://evidence/opaque", "sha256": "a" * 64}])
assert 'unseen.producer' in canonical(value)
args = build_parser().parse_args(["events", "--source", "unseen.source", "--limit", "1"])
assert args.handler.__module__ == "edgar_warehouse.change_journal.cli"
assert not any(name.startswith(("edgar_warehouse.bookkeeping", "edgar_warehouse.mdm", "edgar_warehouse.rules",
                               "edgar_warehouse.acquisition", "edgar_warehouse.application")) for name in sys.modules)
print("isolated journal ready")
''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated journal ready"


def test_import_guard_rejects_a_deliberately_reintroduced_owner_dependency(tmp_path):
    root = isolated_package(tmp_path)
    store = root / "edgar_warehouse/change_journal/store.py"
    store.write_text(store.read_text() + "\nfrom edgar_warehouse.bookkeeping.clean.config import canonical\n")
    result = run_isolated(root, "import edgar_warehouse.change_journal")
    assert result.returncode != 0
    assert "Journal domain dependency forbidden: edgar_warehouse.bookkeeping" in result.stderr


def test_application_owns_recovery_routes_and_core_excludes_them():
    from edgar_warehouse.cli import build_parser
    from edgar_warehouse.change_journal.cli import build_parser as core_parser

    for command in (["recover", "bookkeeping", "run", "--limit", "1"],
                    ["recover", "mdm", "batch", "--worker", "worker"]):
        args = build_parser().parse_args(["change-journal", *command])
        assert args.handler.__module__ == "edgar_warehouse.application.journal_recovery"
    args = build_parser().parse_args(["change-journal", "events", "--limit", "1"])
    assert args.handler.__module__ == "edgar_warehouse.change_journal.cli"
    with pytest.raises(SystemExit) as found:
        core_parser().parse_args(["recover", "bookkeeping", "run"])
    assert found.value.code == 2
