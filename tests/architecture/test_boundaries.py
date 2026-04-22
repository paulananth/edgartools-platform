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
            if "import httpx" in path.read_text()
            and path != PACKAGE_ROOT / "infrastructure" / "sec_client.py"
        ]
        self.assertEqual(offenders, [])

    def test_db_conn_only_lives_in_silver_support_session(self) -> None:
        allowed = {
            PACKAGE_ROOT / "silver_support" / "session.py",
            PACKAGE_ROOT / "silver_support" / "access.py",
        }
        offenders = [path for path in _python_sources() if "db._conn" in path.read_text() and path not in allowed]
        self.assertEqual(offenders, [])

    def test_fsspec_only_lives_in_object_storage_adapter(self) -> None:
        allowed = PACKAGE_ROOT / "infrastructure" / "object_storage.py"
        offenders = [path for path in _python_sources() if "fsspec.filesystem" in path.read_text() and path != allowed]
        self.assertEqual(offenders, [])

    def test_only_dataset_path_catalog_reads_packaged_path_templates(self) -> None:
        allowed = PACKAGE_ROOT / "infrastructure" / "dataset_path_catalog.py"
        offenders = [
            path
            for path in _python_sources()
            if "warehouse_paths.properties" in path.read_text() and path != allowed
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
            if any(fragment in path.read_text() for fragment in forbidden_fragments)
        ]
        self.assertEqual(offenders, [])

    def test_snowflake_publishers_only_live_in_target_module(self) -> None:
        offenders = []
        for path in _python_sources():
            text = path.read_text()
            if path in {
                PACKAGE_ROOT / "serving" / "targets" / "snowflake.py",
                PACKAGE_ROOT / "application" / "workflows" / "serving_publish.py",
            }:
                continue
            if "def write_gold_to_snowflake_export" in text or "def write_ticker_reference_to_snowflake_export" in text:
                offenders.append(path)
        self.assertEqual(offenders, [])
