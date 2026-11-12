"""Every schema file is applied by `mdm migrate` or by the one owner-only step that names it.

A numbered file left out of `MIGRATIONS` is never applied, and nothing else notices.
"""
from pathlib import Path

from edgar_warehouse.mdm import registration, store

FOLDER = Path(store.__file__).parent / "migrations"


def test_every_schema_file_is_applied_by_migrate_or_by_the_step_that_names_it():
    files = {path.name for path in FOLDER.glob("*.sql")}
    named_elsewhere = {registration.MIGRATION}
    assert files - {store.BASELINE} - set(store.MIGRATIONS) - named_elsewhere == set()
    assert set(store.MIGRATIONS) <= files and named_elsewhere <= files and store.BASELINE in files
