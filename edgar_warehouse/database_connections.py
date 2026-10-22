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


def engine_from_env(name, *, runtime_role=None):
    """The URL selects the engine/driver; credentials are never rendered."""
    value = os.environ[name]
    return storage_adapter().connect(value, make_url(value).get_backend_name(), runtime_role=runtime_role)
