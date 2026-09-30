"""The executable acquisition boundary is Company-only and uses fresh control."""
from pathlib import Path

import pytest

from edgar_warehouse.application.acquisition_command_registry import acquisition_command_registration
from edgar_warehouse.application.command_router import run_command
from edgar_warehouse.application.commands import COMMAND_REGISTRY
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.bookkeeping.clean.feeds import resolve_feed
from edgar_warehouse.cli import _runtime_parser, build_parser, main

ROOT = Path(__file__).resolve().parents[2]


def test_company_route_has_no_legacy_store_imports():
    for name in ("company.py", "engine.py", "runner.py", "cli.py"):
        source = (ROOT / "edgar_warehouse/bookkeeping/clean" / name).read_text()
        assert "from edgar_warehouse.acquisition." not in source
        assert "import edgar_warehouse.acquisition." not in source
    for name in ("capture.py", "source_evidence.py", "decisions.py"):
        source = (ROOT / "edgar_warehouse/change_journal" / name).read_text()
        assert "from edgar_warehouse.acquisition.ledger" not in source
    for directory in ("application", "bookkeeping/clean", "change_journal"):
        for path in (ROOT / "edgar_warehouse" / directory).rglob("*.py"):
            source = path.read_text()
            assert "from edgar_warehouse.acquisition.ledger" not in source, path
            assert "from edgar_warehouse.acquisition.registry_ledger" not in source, path
    assert "from edgar_warehouse.acquisition.registry_ledger" not in (
        ROOT / "edgar_warehouse/mdm/cli.py").read_text()


def test_retired_feeds_have_no_source_declaration_or_command():
    for source, feed in (("sec.adv", "adv_bulk"), ("sec.filings", "filing_artifact"),
                         ("sec.company-facts", "company_facts"),
                         ("sec.reference-catalogs", "reference_catalog"),
                         ("gleif", "level1"), ("gleif", "relationships"),
                         ("gleif", "reporting_exceptions")):
        with pytest.raises(ValueError):
            resolve_feed(ROOT / "rules", source, feed)
    for name in ("drive-submissions-discovery", "drive-company-facts-discovery",
                 "drive-reference-catalog-discovery", "drive-adv-bulk-dataset-discovery",
                 "bootstrap-full", "daily-incremental", "bootstrap-fundamentals",
                 "seed-universe", "fetch-adv-bulk", "fetch-firm-roster",
                 "parse-adv-bronze", "seed-bronze-batches"):
        assert acquisition_command_registration(name) is None
        assert name not in COMMAND_REGISTRY
        assert name not in _runtime_parser().format_help()
        with pytest.raises(WarehouseRuntimeError, match="Unsupported warehouse command"):
            run_command(name, None)
        with pytest.raises(WarehouseRuntimeError, match="Unsupported warehouse command"):
            warehouse_orchestrator.run_command(name, None)
        with pytest.raises(SystemExit, match="2"):
            main([name])
    for name in ("registry-open-draft", "registry-activate", "registry-status",
                 "registry-record-catchup"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["mdm", name])
