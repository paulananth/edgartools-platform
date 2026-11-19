"""Environment-backed database connections shared by MDM callers."""
from __future__ import annotations

import os

from sqlalchemy.engine import make_url

from .store import storage_adapter


def mdm_engine(*, restricted: bool = True):
    return mdm_engine_from(os.environ, restricted=restricted)


def mdm_engine_from(environment, *, restricted: bool = True):
    """The MDM database under the selected duty's `DB_URL`, without changing the process environment."""
    from edgar_warehouse.database_connections import owner_url

    value = owner_url("mdm", environment)
    return storage_adapter().connect(
        value, make_url(value).get_backend_name(),
        runtime_role=(environment.get("MDM_APPLICATION_ROLE") or "application") if restricted else None,
    )
