"""The MDM store's PostgreSQL 16, one server for the whole session (ticket 98).

Every test still gets its own database, copied from a template migrated once
per server (test_clean_mdm_postgres.py); only the server and the template are
shared. A module with its own `postgres` fixture (a kept server) overrides it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from tests.integration.test_clean_mdm_postgres import TEMPLATE, Database, _template, _templates
from tests.support import pg16


@pytest.fixture(scope="session")
def postgres():
    # Docker in CI; PG16_SERVER=pgserver runs on a local PostgreSQL 16 (tests/support/pg16.py).
    with pg16.server() as server:
        admin = create_engine(server.url())
        app = None
        try:
            with admin.begin() as conn:
                conn.execute(
                    text(
                        "CREATE ROLE clean_application LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    )
                )
            app = create_engine(server.url(user="clean_application"))
            yield admin, app
        finally:
            if app is not None:
                app.dispose()
            admin.dispose()
            # A later server (a module's own) may be given the same port.
            _templates.pop(admin.url.port, None)


@pytest.fixture
def database(postgres):
    admin, app = postgres
    policy, registry = _template(admin, app)
    name = f"clean_{uuid4().hex[:12]}"
    server = admin.execution_options(isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name} TEMPLATE {TEMPLATE}"))
    admin_db = create_engine(admin.url.set(database=name))
    app_db = create_engine(app.url.set(database=name))
    try:
        yield Database(admin_db, app_db, policy, registry)
    finally:
        admin_db.dispose()
        app_db.dispose()
        with server.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
