"""Owner-maintained lookups over current masters: each configured index keeps a
retained summary per master, per-generation coverage and a resumable owner
rebuild. An index is data (its family, pin and how a master's body gives its
groups); its readers stay with it."""
from dataclasses import dataclass
from typing import Callable


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
        # An index nobody has built is not maintained by a merge: it would add every record's name fragments
        # (about 18 of 19 lookup entries a record) to each batch, and search refuses to answer until the owner
        # builds it anyway. The owner pass (`rebuild`) builds it once, in bulk, and from then on a merge keeps it.
        return {"config": index.pin, "generation": 0, "ready": False, "cursor": None}
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

