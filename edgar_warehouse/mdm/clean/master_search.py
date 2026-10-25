"""Configured master-name references, coverage and owner-controlled rebuilding."""
import json

from sqlalchemy import select

from .record_reads import RecordReader
from .store import Conflict, canonical, digest


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


def state_key(pin):
    return RecordReader.group("master_name_state", pin), "coverage"


def groups_for(pin, kind, named, *, eligible=True):
    groups = set()
    if eligible:
        groups.add(RecordReader.group("master_name_scope", pin, kind))
        for family in ("words", "fragments"):
            groups.update(RecordReader.group("master_name_" + family, pin, kind, token)
                          for token in named[family])
    return groups


def state(adapter, conn, pin, generation):
    key = state_key(pin)
    row = adapter.read([key], lookup=True, connection=conn).get(key)
    if row is None:
        return {"config": pin, "generation": 0, "ready": generation == 0, "cursor": None}
    body = RecordReader._body(row)
    if (set(body) != {"config", "generation", "ready", "cursor"} or body["config"] != pin
            or type(body["generation"]) is not int or body["generation"] < 0
            or body["generation"] > generation
            or type(body["ready"]) is not bool
            or body["cursor"] is not None and not isinstance(body["cursor"], str)):
        raise Conflict("Invalid name-index coverage")
    if (body["ready"] and body["cursor"] is not None
            or not body["ready"] and not body["cursor"]):
        raise Conflict("Invalid name-index progress")
    return body


def entries(adapter, conn, objects, spec):
    """Prepare opaque additions/removals from authoritative scoped masters."""
    pin = digest(spec)
    masters = {key: body for (kind, key), body in objects.items() if kind == "entity"}
    summary_type = RecordReader.group("master_name_record", pin)
    summaries = adapter.read([(summary_type, key) for key in masters], lookup=True, connection=conn)
    changes = []
    for key, body in masters.items():
        old = summaries.get((summary_type, key))
        prior = RecordReader._body(old) if old else {"entity_id": key, "config": pin, "groups": []}
        if (prior.get("entity_id") != key or prior.get("config") != pin
                or not isinstance(prior.get("groups"), list)
                or any(not isinstance(group, str) for group in prior["groups"])):
            raise Conflict("Invalid retained name-index references")
        if old:
            if (set(prior) != {"entity_id", "config", "kind", "name", "groups", "eligible"}
                    or not isinstance(prior["kind"], str)
                    or type(prior["eligible"]) is not bool
                    or prior["name"] is not None and not isinstance(prior["name"], str)):
                raise Conflict("Invalid retained name-index summary")
            previous_name = name_index({"fields": {spec["name_fields"][0]: {"value": prior["name"]}}}, spec)
            if prior["groups"] != sorted(groups_for(pin, prior["kind"], previous_name, eligible=prior["eligible"])):
                raise Conflict("Retained name-index groups differ from their original name")
        if body.get("entity_id") != key or not isinstance(body.get("kind"), str):
            raise Conflict("Name-index master differs from its key")
        named = name_index(body, spec)
        eligible = body.get("canonical_id") == key and not body.get("retired")
        name = named["name"] if eligible else None
        groups = groups_for(pin, body["kind"], named, eligible=eligible)
        for group in sorted(set(prior["groups"]) - groups):
            changes.append({"type": group, "id": key, "removed": True})
        envelope = {"entity_id": key, "kind": body["kind"], "name": name, "config": pin}
        for group in sorted(groups):
            changes.append({"type": group, "id": key, "body_json": canonical(envelope)})
        changes.append({"type": summary_type, "id": key,
                        "body_json": canonical({**envelope, "groups": sorted(groups), "eligible": eligible})})
    return changes


def normal_changes(adapter, conn, objects, generation):
    spec = configuration()
    if spec is None:
        return []
    pin = digest(spec)
    coverage = state(adapter, conn, pin, generation)
    if not coverage["ready"] or coverage["generation"] != generation:
        return []  # A compatible writer must never conceal an earlier gap.
    kind, key = state_key(pin)
    return [*entries(adapter, conn, objects, spec), {"type": kind, "id": key,
        "body_json": canonical({"config": pin, "generation": generation + 1, "ready": True, "cursor": None})}]


def search(adapter, conn, kind, words, limit):
    spec = configuration()
    if spec is None:
        raise Conflict("Name search has no configured index")
    generation, pin = adapter.generation(connection=conn), digest(spec)
    coverage = state(adapter, conn, pin, generation)
    if not coverage["ready"] or coverage["generation"] != generation:
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
    from .prepared import _changes
    from .prepared_registry import installed

    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("Rebuild limit must be a positive integer")
    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise ValueError("Rebuild page size must be 1 to 1000")
    if type(restart) is not bool:
        raise ValueError("Rebuild restart must be a boolean")
    spec = configuration()
    if spec is None:
        raise Conflict("Name search has no configured index")
    pin, processed, pinned_generation = digest(spec), 0, None
    while True:
        with engine.begin() as conn:
            adapter = installed(conn)
            if adapter is None:
                raise Conflict("Name-index rebuilding requires governed prepared storage")
            gate = adapter.tables["gate"]
            generation = conn.scalar(select(gate.c.generation).where(gate.c.id == 1).with_for_update())
            if pinned_generation is not None and generation != pinned_generation:
                raise Conflict("Name-index rebuild was overtaken; restart the quiescent pass")
            pinned_generation = generation
            coverage = state(adapter, conn, pin, generation)
            if coverage["ready"] and coverage["generation"] == generation:
                return {"generation": generation, "processed": processed, "ready": True}
            if coverage["cursor"] is not None and coverage["generation"] != generation and not restart:
                raise Conflict("Name-index rebuild progress is stale; use --restart")
            cursor = coverage["cursor"] if coverage["generation"] == generation and not restart else None
            restart = False
            size = min(page_size, limit - processed) if limit is not None else page_size
            keys = adapter.record_keys("entity", after=cursor or "", limit=size + 1, connection=conn)
            more, selected = len(keys) > size, keys[:size]
            objects = {key: RecordReader._body(row) for key, row in adapter.read(
                [("entity", key) for key in selected], connection=conn).items()}
            if len(objects) != len(selected):
                raise Conflict("Name-index rebuild lost an authoritative master")
            kind, key = state_key(pin)
            updated = {"config": pin, "generation": generation, "ready": not more,
                       "cursor": selected[-1] if more else None}
            additions = [*entries(adapter, conn, objects, spec),
                         {"type": kind, "id": key, "body_json": canonical(updated)}]
            adapter.maintain_lookups(conn, expected_generation=generation,
                                    changes=_changes(adapter, conn, additions))
            processed += len(selected)
        if not more or limit is not None and processed >= limit:
            return {"generation": generation, "processed": processed, "ready": not more}
