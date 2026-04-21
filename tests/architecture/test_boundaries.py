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

    def test_fsspec_only_lives_in_storage_adapter(self) -> None:
        allowed = PACKAGE_ROOT / "infrastructure" / "storage.py"
        offenders = [path for path in _python_sources() if "fsspec.filesystem" in path.read_text() and path != allowed]
        self.assertEqual(offenders, [])
