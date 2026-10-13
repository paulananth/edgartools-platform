from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "edgar_warehouse"


def _python_sources() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


class BoundaryTests(unittest.TestCase):
    def test_httpx_only_lives_in_configured_provider_transport(self) -> None:
        offenders = [
            path
            for path in _python_sources()
            if "import httpx" in path.read_text(encoding="utf-8")
            and path != PACKAGE_ROOT / "workers" / "provider_transport.py"
        ]
        self.assertEqual(offenders, [])

    def test_old_sec_client_is_retired(self) -> None:
        self.assertFalse((PACKAGE_ROOT / 'infrastructure' / 'sec_client.py').exists())

    def test_no_local_silver_connection_is_reached_into(self) -> None:
        """The DuckDB engine is gone (silver-merge-engine-migration Ticket
        17); nothing may reach for a `db._conn` again."""
        offenders = [path for path in _python_sources() if "db._conn" in path.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [])

    def test_canonical_package_files_do_not_use_legacy_runtime_names(self) -> None:
        offenders = [
            path
            for path in _python_sources()
            if path.name != "runtime.py" and ("legacy" in path.name or "runtime" in path.name)
        ]
        self.assertEqual(offenders, [])
