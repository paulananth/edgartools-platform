from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "edgar_warehouse"


def _python_sources() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


class BoundaryTests(unittest.TestCase):
    def test_httpx_only_lives_in_sec_client(self) -> None:
        offenders = [
            path
            for path in _python_sources()
            if "import httpx" in path.read_text(encoding="utf-8")
            and path != PACKAGE_ROOT / "infrastructure" / "sec_client.py"
        ]
        self.assertEqual(offenders, [])

    def test_db_conn_only_lives_in_silver_support_session(self) -> None:
        allowed = {
            PACKAGE_ROOT / "silver_support" / "session.py",
            PACKAGE_ROOT / "silver_support" / "access.py",
        }
        offenders = [path for path in _python_sources() if "db._conn" in path.read_text(encoding="utf-8") and path not in allowed]
        self.assertEqual(offenders, [])

    def test_fsspec_only_lives_in_object_storage_adapter(self) -> None:
        allowed = PACKAGE_ROOT / "infrastructure" / "object_storage.py"
        offenders = [path for path in _python_sources() if "fsspec.filesystem" in path.read_text(encoding="utf-8") and path != allowed]
        self.assertEqual(offenders, [])

    def test_only_dataset_path_catalog_reads_packaged_path_templates(self) -> None:
        allowed = PACKAGE_ROOT / "infrastructure" / "dataset_path_catalog.py"
        offenders = [
            path
            for path in _python_sources()
            if "warehouse_paths.properties" in path.read_text(encoding="utf-8") and path != allowed
        ]
        self.assertEqual(offenders, [])

    def test_canonical_package_files_do_not_use_legacy_runtime_names(self) -> None:
        offenders = [
            path
            for path in _python_sources()
            if path.name != "runtime.py" and ("legacy" in path.name or "runtime" in path.name)
        ]
        self.assertEqual(offenders, [])

    def test_bronze_and_serving_modules_do_not_hardcode_warehouse_path_prefixes(self) -> None:
        targets = [
            PACKAGE_ROOT / "application" / "warehouse_orchestrator.py",
            PACKAGE_ROOT / "bronze_filing_artifacts.py",
            PACKAGE_ROOT / "filing_text_projection.py",
            PACKAGE_ROOT / "serving" / "gold_models.py",
            PACKAGE_ROOT / "infrastructure" / "run_manifest_builder.py",
        ]
        forbidden_fragments = (
            "reference/sec/",
            "submissions/sec/",
            "daily_index/sec/",
            "filings/sec/",
            "text/sec/",
            "gold/{table_name}/run_id=",
            "manifests/workflow_name=",
        )
        offenders = [
            path
            for path in targets
            if any(fragment in path.read_text(encoding="utf-8") for fragment in forbidden_fragments)
        ]
        self.assertEqual(offenders, [])

    def test_snowflake_publishers_only_live_in_target_module(self) -> None:
        offenders = []
        for path in _python_sources():
            text = path.read_text(encoding="utf-8")
            if path in {
                PACKAGE_ROOT / "serving" / "targets" / "snowflake.py",
                PACKAGE_ROOT / "application" / "workflows" / "serving_publish.py",
            }:
                continue
            if "def write_gold_to_snowflake_export" in text or "def write_ticker_reference_to_snowflake_export" in text:
                offenders.append(path)
        self.assertEqual(offenders, [])

    def test_filing_document_capture_does_not_import_parallel_sec_client(self) -> None:
        """Ticket 06: filing document/attachment network gateway is edgartools-only.

        bronze_filing_artifacts + filing_artifact_service must not reintroduce a
        parallel raw SEC client for this object class (download_sec_bytes / httpx).
        Catalogs and companyfacts may still use sec_client until ticket 07.
        """
        targets = [
            PACKAGE_ROOT / "bronze_filing_artifacts.py",
            PACKAGE_ROOT / "infrastructure" / "filing_artifact_service.py",
        ]
        forbidden = (
            "download_sec_bytes",
            "from edgar_warehouse.infrastructure.sec_client",
            "import httpx",
            "sec_client.download",
        )
        offenders: list[str] = []
        for path in targets:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden:
                if fragment in text:
                    offenders.append(f"{path.name}:{fragment}")
        self.assertEqual(offenders, [])

    def test_filing_document_gateway_marker_declares_edgartools_exclusive(self) -> None:
        """Ticket 06 regression: module must declare exclusive gateway identity so
        future reintroductions of a dual stack cannot silently drop the contract.
        """
        text = (PACKAGE_ROOT / "bronze_filing_artifacts.py").read_text(encoding="utf-8")
        self.assertIn("FILING_DOCUMENT_NETWORK_GATEWAY", text)
        self.assertIn('"edgartools"', text)

    def test_catalog_and_facts_use_edgartools_gateway_not_parallel_sec_client(self) -> None:
        """Ticket 07: catalogs + companyfacts network must not import download_sec_bytes
        from sec_client; they route through edgartools_sec_gateway.
        """
        targets = [
            PACKAGE_ROOT / "application" / "warehouse_orchestrator.py",
            PACKAGE_ROOT / "application" / "workflows" / "fundamentals_ingest.py",
            PACKAGE_ROOT / "infrastructure" / "edgartools_sec_gateway.py",
        ]
        forbidden_import = "from edgar_warehouse.infrastructure.sec_client import"
        offenders: list[str] = []
        for path in targets:
            text = path.read_text(encoding="utf-8")
            if path.name == "edgartools_sec_gateway.py":
                # Docstrings may mention sec_client; only ban a real import/call.
                if forbidden_import in text or "sec_client.download_sec_bytes(" in text:
                    offenders.append(f"{path.name}:imports/calls sec_client")
                continue
            if forbidden_import in text or "sec_client.download_sec_bytes(" in text:
                offenders.append(f"{path.name}:uses sec_client")
        self.assertEqual(offenders, [])

    def test_edgartools_gateway_registry_documents_cutover_inventory(self) -> None:
        """Ticket 07: architecture inventory of object classes on the edgartools path."""
        from edgar_warehouse.infrastructure.edgartools_sec_gateway import (
            CATALOG_AND_FACTS_NETWORK_GATEWAY,
            EDGARTOOLS_GATEWAY_OBJECT_CLASSES,
            NON_EDGARTOOLS_OBJECT_CLASSES,
        )

        self.assertEqual(CATALOG_AND_FACTS_NETWORK_GATEWAY, "edgartools")
        for required in (
            "company_tickers",
            "company_tickers_exchange",
            "submissions_main",
            "submissions_pagination",
            "daily_index",
            "companyfacts",
            "filing_document",
        ):
            self.assertIn(required, EDGARTOOLS_GATEWAY_OBJECT_CLASSES)
        self.assertIn("iapd_adv_bulk", NON_EDGARTOOLS_OBJECT_CLASSES)
        self.assertEqual(
            EDGARTOOLS_GATEWAY_OBJECT_CLASSES & NON_EDGARTOOLS_OBJECT_CLASSES,
            frozenset(),
        )
