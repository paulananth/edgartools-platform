"""Configured master-name references, coverage and owner-controlled rebuilding."""
import json

from . import master_index
from .record_reads import RecordReader
from .store import Conflict, digest


def configuration():
    from .catalog import CATALOG, assert_current
    assert_current()
    return CATALOG.get("master_search")


def prepare(operation, **values):
    import edgar_control
    return json.loads(edgar_control.prepare_text_search(json.dumps(
        {"operation": operation, **values}, ensure_ascii=False, allow_nan=False)))


def name_index(body, spec):
    return prepare("index", fields=spec["name_fields"], body={"fields": {
        field: body.get("fields", {}).get(field, {}) for field in spec["name_fields"]}})


def configured_name(body, spec):
    return prepare("name", fields=spec["name_fields"], body={"fields": {
        field: body.get("fields", {}).get(field, {}) for field in spec["name_fields"]}})


def groups_for(pin, kind, named, *, eligible=True):
    groups = set()
    if eligible:
        groups.add(RecordReader.group("master_name_scope", pin, kind))
        for family in ("words", "fragments"):
            groups.update(RecordReader.group("master_name_" + family, pin, kind, token)
                          for token in named[family])
    return groups


def index_for(spec):
    """The name index as data for master_index: its family, pin and groups."""
    pin = digest(spec)

    def derive(key, body):
        named = name_index(body, spec)
        eligible = body.get("canonical_id") == key and not body.get("retired")
        envelope = {"entity_id": key, "kind": body["kind"], "name": named["name"] if eligible else None,
                    "config": pin}
        return envelope, {**envelope, "eligible": eligible}, groups_for(pin, body["kind"], named, eligible=eligible)

    def check(key, prior):
        if (prior.get("entity_id") != key or prior.get("config") != pin
                or not isinstance(prior.get("groups"), list)
                or any(not isinstance(group, str) for group in prior["groups"])):
            raise Conflict("Invalid retained name-index references")
        if (set(prior) != {"entity_id", "config", "kind", "name", "groups", "eligible"}
                or not isinstance(prior["kind"], str)
                or type(prior["eligible"]) is not bool
                or prior["name"] is not None and not isinstance(prior["name"], str)):
            raise Conflict("Invalid retained name-index summary")
        previous_name = name_index({"fields": {spec["name_fields"][0]: {"value": prior["name"]}}}, spec)
        if prior["groups"] != sorted(groups_for(pin, prior["kind"], previous_name, eligible=prior["eligible"])):
            raise Conflict("Retained name-index groups differ from their original name")
        return set(prior["groups"])

    return master_index.Index("master_name", "Name-index", pin, derive, check)


def normal_changes(adapter, conn, objects, generation):
    spec = configuration()
    if spec is None:
        return []
    return master_index.normal_changes(adapter, conn, objects, generation, [index_for(spec)])


def search(adapter, conn, kind, words, limit):
    spec = configuration()
    if spec is None:
        raise Conflict("Name search has no configured index")
    generation, pin = adapter.generation(connection=conn), digest(spec)
    if not master_index.complete(adapter, conn, index_for(spec), generation):
        raise Conflict("Name search requires a complete index for the current generation")
    plan = prepare("query", words=words)
    scope = RecordReader.group("master_name_scope", pin, kind)
    word_groups = [[RecordReader.group("master_name_words", pin, kind, token) for token in alternative]
                   for alternative in plan["alternatives"]]
    fragment_groups = [RecordReader.group("master_name_fragments", pin, kind, token)
                       for token in plan["fragments"]]
    ranked, bodies = [], {}
    probes = [([scope] if plan["scope"] else []), *word_groups, fragment_groups]
    for groups in (groups for groups in probes if groups):
        page = []

        def collect(anchor_rows):
            envelopes = {}
            for identity, row in anchor_rows:
                body = RecordReader._body(row)
                if (set(body) != {"entity_id", "kind", "name", "config"}
                        or body.get("entity_id") != identity or body.get("kind") != kind
                        or body.get("config") != pin
                        or body.get("name") is not None and not isinstance(body.get("name"), str)):
                    raise Conflict("Invalid name-index candidate")
                envelopes[identity] = body
            references = adapter.read([(group, key) for group in groups[1:] for key in envelopes],
                                      lookup=True, connection=conn)
            candidates = []
            for key, envelope in envelopes.items():
                complete = True
                for group in groups[1:]:
                    row = references.get((group, key))
                    if row is None:
                        complete = False
                    elif RecordReader._body(row) != envelope:
                        raise Conflict("Name-index candidates disagree")
                if complete:
                    candidates.append(key)
            masters = adapter.read([("entity", key) for key in candidates], connection=conn)
            rows, current = [], {}
            for key in candidates:
                row = masters.get(("entity", key))
                if row is None:
                    raise Conflict("Name-index candidate has no current master")
                body = RecordReader._body(row)
                name = configured_name(body, spec)
                if (body.get("entity_id") != key or body.get("canonical_id") != key
                        or body.get("kind") != kind or body.get("retired") or name != envelopes[key]["name"]):
                    raise Conflict("Name-index candidate differs from its current master")
                rows.append({"id": key, "name": name})
                current[key] = body
            return rows, current

        for (_group, identity), row in adapter.iter_type(groups[0], lookup=True, connection=conn):
            page.append((identity, row))
            if len(page) == 200:
                rows, current = collect(page)
                ranked = prepare("rank", words=words, rows=[*ranked, *rows], limit=limit,
                                 position_weight=spec["position_weight"])
                bodies = {row["id"]: current.get(row["id"], bodies.get(row["id"])) for row in ranked}
                page.clear()
        if page:
            rows, current = collect(page)
            ranked = prepare("rank", words=words, rows=[*ranked, *rows], limit=limit,
                             position_weight=spec["position_weight"])
            bodies = {row["id"]: current.get(row["id"], bodies.get(row["id"])) for row in ranked}
    return [{"entity_id": row["id"], "kind": kind, "name": row["name"],
             "status": bodies[row["id"]].get("status"), "matched_by": row["matched_by"]} for row in ranked]


def rebuild(engine, *, limit=None, page_size=200, restart=False):
    """Quiescent, resumable owner pass. Overtaking requires explicit restart."""
    spec = configuration()
    if spec is None:
        raise Conflict("Name search has no configured index")
    return master_index.rebuild(engine, index_for(spec), limit=limit, page_size=page_size, restart=restart)
