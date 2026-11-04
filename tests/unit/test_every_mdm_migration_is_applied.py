"""Every migration file is applied by `mdm migrate` or by the one owner-only step that names it.

Ticket 178 added migration 030 as a file but left it out of `MIGRATIONS`, so `mdm migrate`
never applied it and no test noticed.
"""
from pathlib import Path

from edgar_warehouse.mdm import registration, retirement, store

FOLDER = Path(store.__file__).parents[1] / "migrations"


def test_every_migration_file_is_applied_by_migrate_or_by_the_step_that_names_it():
    files = {path.name for path in FOLDER.glob("*.sql")}
    named_elsewhere = {retirement.MIGRATION, registration.MIGRATION}
    assert files - {store.BASELINE} - set(store.MIGRATIONS) - named_elsewhere == set()
    assert set(store.MIGRATIONS) <= files and named_elsewhere <= files
