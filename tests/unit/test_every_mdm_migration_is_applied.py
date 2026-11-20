"""Every schema file is applied by `mdm init`.

A numbered file left out of `MIGRATIONS` is never applied, and nothing else notices.
"""
from pathlib import Path

from edgar_warehouse.mdm import store

FOLDER = Path(store.__file__).parent / "migrations"


def test_every_schema_file_is_applied_by_init():
    files = {path.name for path in FOLDER.glob("*.sql")}
    assert files - {store.BASELINE} - set(store.MIGRATIONS) == set()
    assert set(store.MIGRATIONS) <= files and store.BASELINE in files
