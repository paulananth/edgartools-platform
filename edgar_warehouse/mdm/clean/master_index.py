"""Owner-maintained lookups over current masters: each configured index keeps a
retained summary per master, per-generation coverage and a resumable owner
rebuild. An index is data (its family, pin and how a master's body gives its
groups); its readers stay with it."""
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select

from .record_reads import RecordReader
from .store import Conflict, canonical


@dataclass(frozen=True)
class Index:
    """`derive(key, body)` gives a master's (envelope, summary, groups), or None
    when the index holds nothing for it; `check(key, summary)` re-derives the
    groups a retained summary wrote, refusing one it did not write."""
    family: str
    title: str
    pin: str
    derive: Callable
    check: Callable


def state_key(index):
    return RecordReader.group(index.family + "_state", index.pin), "coverage"


def summary_type(index):
    return RecordReader.group(index.family + "_record", index.pin)


def state(adapter, conn, index, generation):
    key = state_key(index)
    row = adapter.read([key], lookup=True, connection=conn).get(key)
    if row is None:
        return {"config": index.pin, "generation": 0, "ready": generation == 0, "cursor": None}
    body = RecordReader._body(row)
    if (set(body) != {"config", "generation", "ready", "cursor"} or body["config"] != index.pin
            or type(body["generation"]) is not int or body["generation"] < 0
            or body["generation"] > generation
            or type(body["ready"]) is not bool
            or body["cursor"] is not None and not isinstance(body["cursor"], str)):
        raise Conflict(f"Invalid {index.title.lower()} coverage")
    if (body["ready"] and body["cursor"] is not None
            or not body["ready"] and not body["cursor"]):
        raise Conflict(f"Invalid {index.title.lower()} progress")
    return body


def complete(adapter, conn, index, generation):
    coverage = state(adapter, conn, index, generation)
    return coverage["ready"] and coverage["generation"] == generation


def entries(adapter, conn, objects, index):
    """Prepare opaque additions/removals from authoritative scoped masters."""
    masters = {key: body for (kind, key), body in objects.items() if kind == "entity"}
    retained = summary_type(index)
    summaries = adapter.read([(retained, key) for key in masters], lookup=True, connection=conn)
    changes = []
    for key, body in masters.items():
        old = summaries.get((retained, key))
        prior = index.check(key, RecordReader._body(old)) if old else set()
        if body.get("entity_id") != key or not isinstance(body.get("kind"), str):
            raise Conflict(f"{index.title} master differs from its key")
        derived = index.derive(key, body)
        if derived is None and old is None:
            continue
        envelope, summary, groups = derived or (None, None, set())
        for group in sorted(prior - groups):
            changes.append({"type": group, "id": key, "removed": True})
        for group in sorted(groups):
            changes.append({"type": group, "id": key, "body_json": canonical(envelope)})
        if summary is None:
            changes.append({"type": retained, "id": key, "removed": True})
        else:
            changes.append({"type": retained, "id": key,
                            "body_json": canonical({**summary, "groups": sorted(groups)})})
    return changes


def normal_changes(adapter, conn, objects, generation, indexes):
    """Each complete index's changes for a batch and its next coverage; an
    incomplete one writes nothing, so a gap is never concealed."""
    changes = []
    for index in indexes:
        if not complete(adapter, conn, index, generation):
            continue
        kind, key = state_key(index)
        changes += [*entries(adapter, conn, objects, index), {"type": kind, "id": key,
            "body_json": canonical({"config": index.pin, "generation": generation + 1,
                                    "ready": True, "cursor": None})}]
    return changes


def rebuild(engine, index, *, limit=None, page_size=200, restart=False):
    """Quiescent, resumable owner pass. Overtaking requires explicit restart."""
    from .prepared import _changes
    from .prepared_registry import installed

    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("Rebuild limit must be a positive integer")
    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise ValueError("Rebuild page size must be 1 to 1000")
    if type(restart) is not bool:
        raise ValueError("Rebuild restart must be a boolean")
    processed, pinned_generation = 0, None
    while True:
        with engine.begin() as conn:
            adapter = installed(conn)
            if adapter is None:
                raise Conflict(f"{index.title} rebuilding requires governed prepared storage")
            gate = adapter.tables["gate"]
            generation = conn.scalar(select(gate.c.generation).where(gate.c.id == 1).with_for_update())
            if pinned_generation is not None and generation != pinned_generation:
                raise Conflict(f"{index.title} rebuild was overtaken; restart the quiescent pass")
            pinned_generation = generation
            coverage = state(adapter, conn, index, generation)
            if coverage["ready"] and coverage["generation"] == generation:
                return {"generation": generation, "processed": processed, "ready": True}
            if coverage["cursor"] is not None and coverage["generation"] != generation and not restart:
                raise Conflict(f"{index.title} rebuild progress is stale; use --restart")
            cursor = coverage["cursor"] if coverage["generation"] == generation and not restart else None
            restart = False
            size = min(page_size, limit - processed) if limit is not None else page_size
            keys = adapter.record_keys("entity", after=cursor or "", limit=size + 1, connection=conn)
            more, selected = len(keys) > size, keys[:size]
            objects = {key: RecordReader._body(row) for key, row in adapter.read(
                [("entity", key) for key in selected], connection=conn).items()}
            if len(objects) != len(selected):
                raise Conflict(f"{index.title} rebuild lost an authoritative master")
            kind, key = state_key(index)
            updated = {"config": index.pin, "generation": generation, "ready": not more,
                       "cursor": selected[-1] if more else None}
            additions = [*entries(adapter, conn, objects, index),
                         {"type": kind, "id": key, "body_json": canonical(updated)}]
            adapter.maintain_lookups(conn, expected_generation=generation,
                                    changes=_changes(adapter, conn, additions))
            processed += len(selected)
        if not more or limit is not None and processed >= limit:
            return {"generation": generation, "processed": processed, "ready": not more}
