"""Environment-backed database connections shared by MDM callers."""
from __future__ import annotations

import os

from sqlalchemy.engine import make_url

from .store import storage_adapter


def engine_from_env(name: str, *, restricted: bool = True):
    return engine_from_environment(name, os.environ, restricted=restricted)


def engine_from_environment(name: str, environment, *, restricted: bool = True):
    """Use the selected duty's explicit login without changing the process environment."""
    value = environment[name]
    return storage_adapter().connect(
        value, make_url(value).get_backend_name(),
        runtime_role=(environment.get("MDM_APPLICATION_ROLE") or "application") if restricted else None,
    )
