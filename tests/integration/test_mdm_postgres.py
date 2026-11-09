"""Shared fixture builders; retired calculation tests are catalogued in ticket 08."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.store import migrate, register_policy
from tests.support.relationship_types import with_relationship_types
from tests.support.rules_authority import register_dataset


@dataclass
class Database:
    admin: object
    application: object
    policy: str
    registry: str


# A server's first test migrates a template database once (checking a second
# migration installs nothing); every test then gets its own copy of it, which
# Postgres makes in well under a second (the fixtures are in conftest.py).
# Migrating per test cost about 3.4 seconds each (company mastering ticket 23).
TEMPLATE = "clean_template"
_templates: dict[str, tuple[str, str]] = {}


def server_key(admin) -> str:
    """One server: its host, port and socket (a local socket server has no port)."""
    return admin.url.set(database="", password=None).render_as_string()


def _template(admin, app) -> tuple[str, str]:
    server = server_key(admin)
    if server not in _templates:
        with admin.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
            conn.execute(text(f"CREATE DATABASE {TEMPLATE}"))
        admin_t = create_engine(admin.url.set(database=TEMPLATE))
        app_t = create_engine(app.url.set(database=TEMPLATE))
        try:
            built = initialize_database(admin_t, app_t)
        finally:
            # A template is copied only while nobody is connected to it.
            admin_t.dispose()
            app_t.dispose()
        _templates[server] = (built.policy, built.registry)
    return _templates[server]


def initialize_database(admin, app):
    with admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS mdm CASCADE"))
        version = str(uuid4())
    assert migrate(admin, application_role="clean_application")["installed"]
    assert not migrate(admin, application_role="clean_application")["installed"]
    with admin.begin() as conn:
        policy = register_policy(
            conn,
            with_relationship_types({
                "version": 1,
                "required_consumers": ["export", "graph"],
                "automatic_rules": [],
                "fields": {
                    "company": {
                        "name": {"sources": ["fixture.primary", "fixture.secondary"]},
                        "address": {
                            "sources": ["fixture.primary", "fixture.secondary"]
                        },
                    }
                },
            }),
        )
        for code in ["fixture.primary", "fixture.secondary"]:
            register_dataset(
                conn,
                code,
                version,
                {
                    "provider": "test",
                    "family": "fixture",
                    "publication_families": ["golden_copy", "opencorporates"],
                    "schema_version": "1",
                    "record_key": "key",
                    "publication_key": "version",
                    "effective_time": "effective_at",
                    "semantics": "patch",
                },
            )
    return Database(admin, app, policy, version)


from edgar_warehouse.mdm.evidence import assertion

AS_OF = "2026-09-18T00:00:00+00:00"
AT = "2026-01-01T00:00:00+00:00"


def source(key="c1", source_code="fixture.primary", revision=1, **kw):
    return assertion(
        source_code=source_code,
        record_key=key,
        publication_key=f"p{revision}",
        revision=revision,
        effective_at=kw.pop("effective_at", AT),
        kind=kw.pop("kind", "company"),
        fields=kw.pop("fields", {"name": "Acme"}),
        **kw,
    )


def contract_body(**changes):
    return {
        "provider": "test",
        "family": "fixture",
        "publication_families": ["golden_copy", "opencorporates"],
        "schema_version": "1",
        "record_key": "key",
        "publication_key": "version",
        "effective_time": "effective_at",
        "semantics": "patch",
        **changes,
    }
