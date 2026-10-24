"""Owner-approved references for the prepared store's existing registry."""

from sqlalchemy import func, select

from .store import Conflict, canonical, digest, storage_adapter

PREFIX = "mdm_store"


def installed(conn):
    """Select governed storage only when its complete marker is present."""
    api = storage_adapter()
    if api.storage_version(conn, prefix=PREFIX) < 5:
        return None
    adapter = api.Adapter(conn.engine, prefix=PREFIX, protocol=5)
    ledger = adapter.tables["migration"]
    count, ready = conn.execute(select(func.count(), func.min(ledger.c.complete))).one()
    if count != 5 or ready != 1:
        raise Conflict("Prepared storage owner installation is incomplete")
    return adapter


def approve_policy(conn, key):
    adapter = installed(conn)
    if adapter is not None:
        adapter.admit_pin(conn, "policy", key)


def mapping_pin(code, version):
    return "mapping/" + canonical([code, version])


def schema_pin(code, schema):
    return "schema/" + canonical([code, schema])


def approve_mapping(conn, code, version, body):
    adapter = installed(conn)
    if adapter is not None:
        adapter.admit_pin(conn, mapping_pin(code, version), digest(body))
        # Deferred records name their schema, not a mapping revision. Retain
        # approval of each registered schema without resolving the latest map.
        schema = body.get("schema_version")
        adapter.admit_pin(conn, schema_pin(code, schema), digest([code, schema]))


def initialize(engine, *, application_role, application_host="%"):
    """Install pending capabilities, then approve the catalog and open runtime."""
    from . import catalog

    catalog.assert_current()
    api = storage_adapter()
    result = api.migrate(engine, runtime_role=application_role,
                         runtime_host=application_host, prefix=PREFIX, protocol=5,
                         runtime_execute=False, defer_ready=True)
    adapter = api.Adapter(engine, prefix=PREFIX, protocol=5)
    with engine.begin() as conn:
        adapter.activate(conn, {"catalog": digest(catalog.CATALOG)}, exclusive=("catalog",))
    adapter.enable_runtime(application_role, runtime_host=application_host)
    return result
