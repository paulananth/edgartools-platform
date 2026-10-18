"""Environment-backed database connections shared by MDM callers."""
from __future__ import annotations

import os

from sqlalchemy.engine import make_url

from .store import storage_adapter


def engine_from_env(name: str, *, restricted: bool = True):
    value = os.environ[name]
    return storage_adapter().connect(
        value, make_url(value).get_backend_name(),
        runtime_role=os.environ.get("MDM_APPLICATION_ROLE", "application") if restricted else None,
    )
