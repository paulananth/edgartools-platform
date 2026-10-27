"""Shared fixture builders; retired calculation tests are catalogued in ticket 08."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.clean.store import (
    Store,
    migrate,
    register_policy,
)
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
            {
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
            },
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


def request(db, **changes):
    return {
        "batch_id": "batch-1",
        "expected_generation": 0,
        "consumer": "mastering/company",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "policy_digest": db.policy,
        "assertions": [],
        "identities": [],
        "decisions": [],
        "projections": [
            {
                "object_type": "review",
                "object_id": "review-1",
                "body": {"reason": "needs evidence"},
            }
        ],
        **changes,
    }


class Destination:
    def __init__(self):
        self.objects = {}
        self.fail = True

    def publish(self, key, payload, expected_hash):
        previous = self.objects.setdefault(key, (payload, expected_hash))
        assert previous == (payload, expected_hash)
        if self.fail:
            self.fail = False
            raise OSError("external success followed by lost acknowledgement")

    def verify(self, key, payload, expected_hash):
        assert self.objects[key] == (payload, expected_hash)
        return expected_hash


from edgar_warehouse.mdm.clean.evidence import assertion, decision
from edgar_warehouse.mdm.clean.merge import MergeStage

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


def identity_and_binding(a, entity_id=None, *, published_at=AT):
    entity_id = entity_id or str(uuid4())
    return {"entity_id": entity_id, "kind": a["kind"], "published_at": published_at}, decision(
        "bind",
        actor="steward",
        reason="fixture source reviewed",
        at=AT,
        subject=a["subject"],
        entity_id=entity_id,
        evidence=[a["assertion_id"]],
    )


def apply(db, n, **kw):
    return MergeStage(Store(db.application)).apply(
        batch_id=f"work-{n}",
        run_id=kw.pop("run_id", str(uuid4())),
        policy_digest=db.policy,
        consumer="fixture",
        expected_checkpoint=n - 1,
        checkpoint=n,
        as_of=AS_OF,
        **kw,
    )


def documents(db, kind):
    """Read fixture objects through the public, generation-pinned contract."""
    from edgar_warehouse.mdm.clean.consumer import ContractReader

    reader, after, found, generation = ContractReader(db.application), "", {}, None
    while True:
        page = reader.snapshot_page(kind, after=after, generation=generation, limit=1000)
        generation = page["generation"]
        found.update((row["object_id"], row["body"]) for row in page["items"])
        after = page["next_after"]
        if after is None:
            return found


def assessment_command(db, **changes):
    a = source()
    identity, binding = identity_and_binding(a)
    return {
        "batch_id": "assessed-company",
        "run_id": str(uuid4()),
        "policy_digest": db.policy,
        "consumer": "assessed-company",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "as_of": AS_OF,
        "assertions": [a],
        "identities": [identity],
        "decisions": [binding],
        **changes,
    }


def family_metadata(family, publication="p1"):
    # Synthetic proof checks persistence/fencing, not live source completeness.
    return {
        "source_family": "fixture",
        "publication_family": family,
        "committed_publication": publication,
        "continuity_proof": {"rule_version": "fixture-1", "inventory_digest": "a" * 64},
    }


# --- Company mastering ticket 01: a mapping may be corrected ------------------
# Real PG16 against migration 031. A re-read of one publication under a
# corrected mapping must add a row beside its predecessor: before the ticket's
# amendments a changed reading raised on the revision guard and an unchanged
# one collided on assertion_id, so neither could ever be stored.


def reread(a, *, mapping_version, **changes):
    """The same record and publication, read again under a later mapping."""
    return assertion(
        source_code=a["source_code"],
        record_key=a["record_key"],
        publication_key=a["publication_key"],
        revision=a["revision"],
        effective_at=a["effective_at"],
        kind=a["kind"],
        fields=changes.pop("fields", a["fields"]),
        mapping_version=mapping_version,
        **changes,
    )


def register_reading(database, code, body):
    with database.admin.begin() as conn:
        register_dataset(conn, code, database.registry, body)
    with database.application.connect() as conn:
        return conn.scalar(
            text(
                "SELECT max(mapping_version) FROM mdm.dataset_mapping WHERE source_code=:c"
            ),
            {"c": code},
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


def current_records(db):
    """Inspect the small fixture's stored pointers, then validate through its reader."""
    import json
    from sqlalchemy import select
    from edgar_warehouse.mdm.clean.record_reads import for_connection

    with db.application.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        reader = for_connection(conn)
        table = reader.adapter.tables["lookup"]
        subjects = [json.loads(body)["subject"] for body in conn.scalars(
            select(table.c.body).where(table.c.type_bytes == b"source-record"))]
        return reader.current(subjects)


def bindings(db, source_code=None, *, by_subject=False):
    """Fixture bindings through the configured canonical master lookup."""
    from edgar_warehouse.silver_writer.writer import MdmIds

    records = [r for r in current_records(db).values()
               if source_code is None or r["source_code"] == source_code]
    groups = {(r["source_code"], r["kind"]) for r in records}
    found = {}
    for code, kind in groups:
        selected = [r for r in records if (r["source_code"], r["kind"]) == (code, kind)]
        ids = MdmIds(db.application)(code, kind, {r["record_key"] for r in selected})
        found.update((r["subject"] if by_subject else r["record_key"], ids.get(r["record_key"])) for r in selected)
    return found
