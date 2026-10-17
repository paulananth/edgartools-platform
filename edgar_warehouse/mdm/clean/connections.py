"""Environment-backed database connections shared by MDM callers."""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event


def engine_from_env(name: str, *, restricted: bool = True):
    engine = create_engine(os.environ[name], pool_pre_ping=True)
    if restricted:
        role = os.environ.get("MDM_APPLICATION_ROLE", "application")
        quoted = engine.dialect.identifier_preparer.quote(role)

        @event.listens_for(engine, "connect")
        def select_role(dbapi_connection, _):
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {quoted}")
            dbapi_connection.commit()

    return engine
