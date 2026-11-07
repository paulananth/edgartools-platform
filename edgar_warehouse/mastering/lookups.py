"""Name search, detail keys and cross-references, built after a load from the masters that changed.

Every lookup is a row (token, master id): a token is the digest of what it finds. The pin is the digest of the
configuration, so a changed configuration starts again from the first file and a reader refuses until it is built.
"""

from __future__ import annotations

import hashlib
import json

from edgar_warehouse.mdm import detail_lookups, master_search
from edgar_warehouse.mdm.store import digest

from .store import blocks

PAGE = 1000
SCAN = 5000


class NotBuilt(Exception):
    """The lookups have not reached the last file."""


def _pin() -> str:
    return digest({"names": master_search.configuration(), "details": detail_lookups.configuration()})


def _token(pin: str, *parts: str) -> str:
    return hashlib.sha256(json.dumps([pin, *parts], ensure_ascii=False).encode()).hexdigest()


def tokens_of(pin: str, body: dict, records: list[dict]) -> set[str]:
    """What finds one master. A merged-away master finds nothing."""
    if body["canonical_id"] != body["entity_id"]:
        return set()
    kind, tokens = body["kind"], set()
    names, details = master_search.configuration(), detail_lookups.configuration()
    if names is not None:
        named = master_search.name_index(body, names)
        tokens.add(_token(pin, "scope", kind))
        tokens |= {_token(pin, "words", kind, word) for word in named["words"]}
    if details is not None and kind == details["kind"]:
        tokens |= {_token(pin, "detail", *key) for key in detail_lookups.keys_of(body, details)}
    for record in records:
        tokens |= {_token(pin, "cross", *item) for item in record["cross_references"].items()}
    return tokens


def build(store, progress=lambda built: None) -> dict:
    """Bring the lookups up to the last file. Each page commits with its progress, so a stopped build resumes."""
    pin, built = _pin(), 0
    last = store.last_file()
    reached = store.lookup_progress(pin)
    while rows := store.changes(reached[0], reached[1], PAGE):
        bodies = {entity: json.loads(body) for _, entity, body in rows}
        records: dict = {}
        for entity, body in store.cross_referenced(bodies):
            records.setdefault(entity, []).append(json.loads(body))
        reached = (rows[-1][0], rows[-1][1])
        store.save_lookups(pin, list(bodies), [(token, entity) for entity, body in bodies.items()
                                               for token in tokens_of(pin, body, records.get(entity, []))], reached)
        store.commit()
        built += len(bodies)
        progress(built)
    if reached[0] < last:
        store.save_lookups(pin, [], [], (last, ""))
        store.commit()
    return {"masters": built, "file": max(reached[0], last)}


def _ready(store) -> str:
    pin = _pin()
    if store.lookup_progress(pin)[0] < store.last_file():
        raise NotBuilt("The lookups have not reached the last load: build them first")
    return pin


def search(store, kind: str, words: str, limit: int) -> list[dict]:
    """Best name matches of one kind."""
    pin, spec = _ready(store), master_search.configuration()
    plan = master_search.prepare("query", words=words)
    probes = [
        [_token(pin, "scope", kind)] if plan["scope"] else [],
        *[[_token(pin, "words", kind, word) for word in alternative] for alternative in plan["alternatives"]],
    ]
    ranked: list = []
    bodies: dict = {}
    for probe in filter(None, probes):
        for block in blocks(store.holding_all(probe)):
            found = store.master_bodies(block)
            rows = [{"id": key, "name": master_search.configured_name(body, spec)} for key, body in found.items()]
            ranked = master_search.prepare("rank", words=words, rows=[*ranked, *rows], limit=limit,
                                           position_weight=spec["position_weight"])
            bodies = {row["id"]: found.get(row["id"]) or bodies[row["id"]] for row in ranked}
    if plan["fragments"] and not ranked:
        found = _named_like(store, kind, words, spec)
        ranked = master_search.prepare("rank", words=words, rows=[
            {"id": key, "name": name} for key, (name, _) in found.items()], limit=limit,
            position_weight=spec["position_weight"])
        bodies = {key: body for key, (_, body) in found.items()}
    return [{"entity_id": row["id"], "kind": kind, "name": row["name"], "status": bodies[row["id"]].get("status"),
             "matched_by": row["matched_by"]} for row in ranked]


def _named_like(store, kind: str, words: str, spec: dict) -> dict:
    """Part of a word: a scan of the masters, since an index of every part costs more than the rare search saves."""
    wanted, found = words.strip().casefold(), {}
    for key, text in store.masters_containing(wanted, SCAN):
        body = json.loads(text)
        name = master_search.configured_name(body, spec)
        if body["kind"] == kind and body["canonical_id"] == key and name and wanted in name.casefold():
            found[key] = (name, body)
    return found


def holders_of_detail(store, name: str, values: list[str]) -> list[dict]:
    """Every master holding a configured detail key, in id order; never one picked."""
    pin, spec = _ready(store), detail_lookups.configuration()
    found = store.holding_all([_token(pin, "detail", name, *values)])
    bodies = store.master_bodies(found)
    return [{"entity_id": key, "kind": spec["kind"], "status": bodies[key].get("status")} for key in found]


def cross_referencing(store, namespace: str, value: str) -> list[str]:
    return store.holding_all([_token(_ready(store), "cross", namespace, value)])
