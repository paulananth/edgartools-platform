"""A configured lookup from a detail row's key to every current master holding
it (ticket 138). The kind, detail list and keys are configuration
(`detail_lookups` in the engine catalog); lookup only, never matching."""
from . import master_index
from .record_reads import RecordReader
from .store import Conflict, digest


def configuration():
    from .catalog import CATALOG, assert_current
    assert_current()
    return CATALOG.get("detail_lookups")


def keys_of(body, spec):
    """Each configured key a master's detail rows state in full: [name, *values]."""
    found = set()
    for row in (body.get("details") or {}).get(spec["detail"], []):
        for name, fields in spec["keys"].items():
            values = [row.get(field) for field in fields]
            if all(isinstance(value, str) and value for value in values):
                found.add((name, *values))
    return sorted(list(key) for key in found)


def groups_for(pin, keys):
    return {RecordReader.group("master_detail_key", pin, *key) for key in keys}


def index_for(spec):
    pin = digest(spec)

    def derive(key, body):
        if body["kind"] != spec["kind"]:
            return None
        eligible = body.get("canonical_id") == key and not body.get("retired")
        keys = keys_of(body, spec) if eligible else []
        envelope = {"entity_id": key, "kind": body["kind"], "config": pin}
        return envelope, {**envelope, "keys": keys}, groups_for(pin, keys)

    def check(key, prior):
        if (set(prior) != {"entity_id", "kind", "config", "keys", "groups"}
                or prior["entity_id"] != key or prior["config"] != pin or prior["kind"] != spec["kind"]
                or not isinstance(prior["keys"], list)
                or any(not isinstance(k, list) or not k or any(not isinstance(v, str) for v in k)
                       for k in prior["keys"])
                or not isinstance(prior["groups"], list)):
            raise Conflict("Invalid retained detail lookup summary")
        if prior["groups"] != sorted(groups_for(pin, prior["keys"])):
            raise Conflict("Retained detail lookup groups differ from their keys")
        return set(prior["groups"])

    return master_index.Index("master_detail", "Detail lookup", pin, derive, check)


def normal_changes(adapter, conn, objects, generation):
    spec = configuration()
    if spec is None:
        return []
    return master_index.normal_changes(adapter, conn, objects, generation, [index_for(spec)])


def find(adapter, conn, name, values):
    """Every current master whose detail rows hold the configured key `name`
    with these values, in id order; never one picked."""
    spec = configuration()
    if spec is None:
        raise Conflict("Detail lookup has no configured index")
    if name not in spec["keys"] or len(values) != len(spec["keys"][name]):
        raise Conflict(f"Detail lookup {name!r} takes {spec['keys'].get(name, 'a configured key')}")
    index = index_for(spec)
    if not master_index.complete(adapter, conn, index, adapter.generation(connection=conn)):
        raise Conflict("Detail lookup requires a complete index for the current generation")
    key = [name, *values]
    group = RecordReader.group("master_detail_key", index.pin, *key)
    found = {}
    for (_group, identity), row in adapter.iter_type(group, lookup=True, connection=conn):
        if RecordReader._body(row) != {"entity_id": identity, "kind": spec["kind"], "config": index.pin}:
            raise Conflict("Invalid detail lookup candidate")
        found[identity] = None
    masters = adapter.read([("entity", identity) for identity in found], connection=conn)
    answer = []
    for identity in sorted(found):
        row = masters.get(("entity", identity))
        if row is None:
            raise Conflict("Detail lookup candidate has no current master")
        body = RecordReader._body(row)
        if (body.get("canonical_id") != identity or body.get("retired")
                or key not in keys_of(body, spec)):
            raise Conflict("Detail lookup candidate differs from its current master")
        answer.append({"entity_id": identity, "kind": spec["kind"], "status": body.get("status")})
    return answer


def rebuild(engine, *, limit=None, page_size=200, restart=False):
    """Quiescent, resumable owner pass. Overtaking requires explicit restart."""
    spec = configuration()
    if spec is None:
        raise Conflict("Detail lookup has no configured index")
    return master_index.rebuild(engine, index_for(spec), limit=limit, page_size=page_size, restart=restart)
