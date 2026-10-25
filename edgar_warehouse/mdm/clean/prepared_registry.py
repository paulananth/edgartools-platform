"""Owner-approved references for the prepared store's existing registry."""

from sqlalchemy import func, select

from .store import Conflict, canonical, digest, storage_adapter

PREFIX = "mdm_store"
PROTOCOL = 6


def installed(conn):
    """Select governed storage only when its complete marker is present."""
    api = storage_adapter()
    version = api.storage_version(conn, prefix=PREFIX)
    if version < 5:
        return None
    adapter = api.Adapter(conn.engine, prefix=PREFIX, protocol=version)
    ledger = adapter.tables["migration"]
    count, ready = conn.execute(select(func.count(), func.min(ledger.c.complete))).one()
    if version > PROTOCOL or count != version or ready != 1:
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
                         runtime_host=application_host, prefix=PREFIX, protocol=PROTOCOL,
                         runtime_execute=False, defer_ready=True)
    adapter = api.Adapter(engine, prefix=PREFIX, protocol=PROTOCOL)
    with engine.begin() as conn:
        adapter.activate(conn, {"catalog": digest(catalog.CATALOG)}, exclusive=("catalog",))
    finish_indexes(engine)
    adapter.enable_runtime(application_role, runtime_host=application_host)
    return result


WAITING_INDEX = "waiting-review-index-v1"


def finish_indexes(engine):
    """Owner-only bounded backfill before runtime execution is enabled."""
    from .prepared import _changes
    from .record_reads import RecordReader
    from edgar_warehouse.rules.source_engine import prepare_scope_lookups

    api = storage_adapter().Adapter(engine, prefix=PREFIX, protocol=PROTOCOL)
    marker = ("derived-index", WAITING_INDEX)
    if api.read([marker], metadata=True):
        return
    generation, after = api.generation(), ""
    while True:
        with engine.begin() as conn:
            keys = api.record_keys("review", after=after, limit=200, connection=conn)
            if not keys:
                api.retain_metadata(*marker, {"version":WAITING_INDEX}, immutable=True)
                return
            saved = api.read([("review", key) for key in keys], connection=conn)
            if len(saved) != len(keys):
                raise Conflict("Review-index rebuild lost a retained review")
            _, additions = prepare_scope_lookups({"previous":[],
                "objects":[{"type":kind,"id":key,"body":RecordReader._body(row)}
                           for (kind,key),row in saved.items()],
                "identities":[],"previous_publications":{}})
            api.maintain_lookups(conn, expected_generation=generation,
                                changes=_changes(api, conn, additions))
            after = keys[-1]
