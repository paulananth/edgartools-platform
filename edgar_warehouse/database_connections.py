"""Configuration-selected database connections, independent of any store."""
import os
from importlib import import_module

from sqlalchemy.engine import make_url


def storage_adapter():
    """Locate the canonical SQL adapter in a checkout or installed bundle."""
    from edgar_warehouse.rules.files import BUNDLE_DATA

    path = BUNDLE_DATA / "skills" / "mdm-engineering" / "scripts" / "database_adapter.py"
    package = "edgar_warehouse.bundle_data.skills" if path.is_file() else "skills"
    return import_module(f"{package}.mdm-engineering.scripts.database_adapter")


STORES = ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")


def store_url(store: str, environment=None):
    """The `DB_URL` of the duty's file with the store's own database: `DB_PREFIX` (optional, for isolated copies) and the store's
    name. A `DB_URL` that already names a database keeps it: that is one database holding the store (a test, a single-database
    deployment)."""
    if store not in STORES:
        raise ValueError(f"unknown store {store!r}")
    env = os.environ if environment is None else environment
    value = env.get("DB_URL")
    if not value:
        raise KeyError("DB_URL is not set: source the duty's file in the stores folder (its value is never printed)")
    url = make_url(value)
    return url if url.database else url.set(database=f"{env.get('DB_PREFIX', '')}{store}")


def owner_url(store: str, environment=None) -> str:
    return store_url(store, environment).render_as_string(hide_password=False)


def store_engine(store: str, *, runtime_role=None, environment=None):
    """An engine for one store, from `DB_URL` (whichever duty's file was sourced); credentials are never rendered."""
    value = owner_url(store, environment)
    return storage_adapter().connect(value, make_url(value).get_backend_name(), runtime_role=runtime_role)


owner_engine = store_engine  # the owner file's `DB_URL` is read the same way: the duty is the file, not the function
