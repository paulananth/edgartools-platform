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
# Two databases, each store in its own schema: what consumers read (one mirror carries it) and what runs the platform.
DATA_STORES = ("mdm", "rdm", "silver")
CONTROL_STORES = ("rules", "bookkeeping", "change_journal")
DATABASES = {"data": DATA_STORES, "control": CONTROL_STORES}  # the database each group of stores shares


def database_of(store: str) -> str:
    """The database that holds this store's schema: data or control."""
    for database, stores in DATABASES.items():
        if store in stores:
            return database
    raise ValueError(f"unknown store {store!r}")


def url_variable(store: str) -> str:
    """The duty file's variable that names this store's database: DATA_URL or CONTROL_URL."""
    return {"data": "DATA_URL", "control": "CONTROL_URL"}[database_of(store)]


def configured(store: str, environment=None) -> bool:
    """Whether the sourced duty file names this store's database."""
    return bool((os.environ if environment is None else environment).get(url_variable(store)))


def instance_url(environment=None, database: str = "postgres"):
    """The instance, not a store: the data URL with another database (monitoring, role guards, the reset, the audit)."""
    return store_url("mdm", environment).set(database=database)


def store_url(store: str, environment=None):
    """The URL of the database that holds this store: `DATA_URL` for mdm, rdm and silver, `CONTROL_URL` for rules,
    bookkeeping and change_journal, from the duty's file. Each must name its database; nothing is guessed."""
    variable = url_variable(store)
    env = os.environ if environment is None else environment
    value = env.get(variable)
    if not value:
        raise KeyError(f"{variable} is not set: source the duty's file in the stores folder (its value is never printed)")
    url = make_url(value)
    if not url.database:
        raise ValueError(f"{variable} must name its database")
    return url


def owner_url(store: str, environment=None) -> str:
    return store_url(store, environment).render_as_string(hide_password=False)


def store_engine(store: str, *, runtime_role=None, environment=None):
    """An engine for one store, from its group's URL in whichever duty's file was sourced; credentials are never rendered."""
    value = owner_url(store, environment)
    return storage_adapter().connect(value, make_url(value).get_backend_name(), runtime_role=runtime_role)


owner_engine = store_engine  # the owner file's URLs are read the same way: the duty is the file, not the function
