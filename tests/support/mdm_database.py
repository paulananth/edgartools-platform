"""An MDM database beside the Bookkeeping test databases, for tests that run workers against MDM."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.mdm.store import register_policy
from tests.integration import test_mdm_postgres as core
from tests.support.relationship_types import with_relationship_types


@pytest.fixture
def mdm(databases):
    """An MDM database in the same server, migrated and registered."""
    name = f"mdm_worker_{uuid4().hex[:8]}"
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    admin = create_engine(databases.admin.url.set(database=name))
    app = create_engine(admin.url.set(username="clean_application", password="test"))
    reader = create_engine(admin.url.set(username="mdm_reader", password="test"))
    try:
        core.initialize_database(admin, app)
        migrate_guard(admin, runtime_role="clean_application")
        with admin.begin() as conn:
            policy = register_policy(conn, with_relationship_types({
                "version": 1, "required_consumers": ["export", "graph", "journal"], "automatic_rules": [],
                "fields": {"company": {"name": {"sources": ["fixture.primary", "fixture.secondary"]}}}}))
        with admin.begin() as conn:
            conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO mdm_reader")
            conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO mdm_reader")
            conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA public TO mdm_reader")
        yield SimpleNamespace(admin=admin, application=app, reader=reader, policy=policy)
    finally:
        admin.dispose()
        app.dispose()
        reader.dispose()
