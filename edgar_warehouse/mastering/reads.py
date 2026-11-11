"""What readers ask of the masters: a source key's master, a master by id, the masters carrying an identifier."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict

from edgar_warehouse.mdm.evidence import subject_key
from edgar_warehouse.mdm.primitives import prepare_matching_value

from . import lookups


def master_ids(store, source_code: str, keys) -> dict:
    """Each source key's current master; a key with no master is left out. A source gives one kind."""
    subjects = {subject_key(source_code, key): key for key in keys}
    return {subjects[subject]: entity for subject, entity in store.bound(subjects).items()}


def master(store, requested: str) -> dict:
    """The current master behind an id: a merged-away id answers with the master it joined."""
    key, seen = requested, set()
    while key not in seen:
        seen.add(key)
        body = store.master_bodies([key]).get(key)
        if body is None:
            raise KeyError(requested)
        if body["canonical_id"] == key:
            return body
        key = body["canonical_id"]
    raise ValueError(f"Merged masters point at each other: {requested}")


def carriers(store, policy: dict, kind: str | None, namespace: str, value: str) -> dict:
    """The masters carrying `namespace:value`, each marked as an identifier or a cross-reference (lookup only)."""
    values = {value} if value else set()
    for block in policy["kinds"].values():
        contract = block.get("identifiers", {}).get(namespace)
        normalized = prepare_matching_value(contract["normalizer"], value, block) if contract else None
        if normalized:
            values.add(normalized)
    found = {entity: "identifier" for entity in (store.identifier_holders(namespace, sorted(values)) if values else [])}
    found = found or {entity: "cross_reference" for entity in lookups.cross_referencing(store, namespace, value)}
    bodies = store.master_bodies(found)
    return {entity: how for entity, how in found.items() if kind is None or bodies[entity]["kind"] == kind}


def splits_of(store, entity: str) -> list[dict]:
    """The splits a master came out of: each merge of it with another master that was later reversed.
    Each is also a Match Exclusion of the pair."""
    decisions = store.decisions_about([entity])
    reversed_by = {d["target"]: d for d in decisions if d["operation"] == "reverse"}
    found = [{"merge": d["decision_id"], "split_from": d["right"] if d["left"] == entity else d["left"],
              "by": reversed_by[d["decision_id"]]["actor"], "reason": reversed_by[d["decision_id"]]["reason"],
              "at": reversed_by[d["decision_id"]]["at"], "excluded": True}
             for d in decisions if d["operation"] == "merge" and d["decision_id"] in reversed_by]
    return sorted(found, key=lambda item: (item["at"], item["merge"]))


def explained(store, *, page: int = 20_000) -> dict:
    """Counts only (ticket 209): how each stored source record that has a golden record is explained, for every
    source and kind at once. A record is explained by a bind decision (a name match, an exact-name creation, a
    steward), by being the one record of its golden record that joined nothing (it created it), or by an identifier it shares with
    another record of the same golden record (a plain identifier join writes no decision). The rest is
    `unexplained`, and its count per source is named: it must be none."""
    decided, made = set(), set()  # subjects a bind decision names, and those it says created their golden record
    for subject, body in store.rows("select left_id,body from mastering_decision where operation='bind'"):
        decided.add(subject)
        if json.loads(body).get("reason", "").endswith(" created"):
            made.add(subject)
    total, by_source, last = Counter(), defaultdict(Counter), ""
    while True:
        rows = store.rows("select entity_id,subject,source_code,body from mastering_record where entity_id is not null "
                          "and entity_id > %s order by entity_id limit %s", [last, page])
        if not rows:
            break
        # A golden record's records are read together: stop the page at a whole group, and read the group at the next one.
        edge = rows[-1][0]
        if len(rows) == page:
            rows = [row for row in rows if row[0] != edge]
            last = rows[-1][0] if rows else edge
            if not rows:  # one golden record holds a whole page: read it by itself
                rows = store.rows("select entity_id,subject,source_code,body from mastering_record where entity_id=%s",
                                  [edge])
                last = edge
        else:
            last = edge
        groups = defaultdict(list)
        for entity, subject, source, body in rows:
            found = (json.loads(body).get("identifiers") or {}).items()
            groups[entity].append((subject, source, {(ns, v) for ns, vs in found
                                                     for v in (vs if isinstance(vs, list) else [vs]) if v}))
        for members in groups.values():
            anchors = []
            for number, (subject, source, identifiers) in enumerate(members):
                total["records_bound"] += 1
                if subject in decided:
                    total["by_decision"] += 1
                    by_source[source]["by_decision"] += 1
                elif any(identifiers & other for at, (_, _, other) in enumerate(members) if at != number):
                    total["by_identifier"] += 1
                    by_source[source]["by_identifier"] += 1
                else:
                    anchors.append(source)
            # One record of a golden record has nothing to join by: the one that created it, unless a decision says
            # another record did.
            creator = any(subject in made for subject, _, _ in members)
            for position, source in enumerate(anchors):
                how = "created" if position == 0 and not creator else "unexplained"
                total[how] += 1
                by_source[source][how] += 1
    return {**{key: total[key] for key in ("records_bound", "by_decision", "created", "by_identifier", "unexplained")},
            "unexplained_by_source": {source: found["unexplained"] for source, found in sorted(by_source.items())
                                      if found["unexplained"]}}


def counts(store) -> dict:
    """What a store holds, in counts and one digest: `rules test` compares two passes with it."""
    masters, holders, digest = Counter(), defaultdict(set), hashlib.sha256()
    for entity, text in store.rows("select entity_id,body from mastering_master order by entity_id"):
        digest.update(f"{entity}:{text}\n".encode())
        body = json.loads(text)
        if body["canonical_id"] == entity:
            masters[body["kind"]] += 1
            for namespace, values in body.get("identifiers", {}).items():
                for value in values:
                    holders[namespace, value].add(entity)
    grouped = {part: dict(store.rows(statement)) for part, statement in (
        ("stage_records", "select source_code,count(*) from mastering_record group by source_code"),
        ("set_aside", "select reason,count(*) from mastering_deferred group by reason"),
        ("open_reviews", "select reason,count(*) from mastering_review where open_review=1 group by reason"),
        ("decisions", "select operation,count(*) from mastering_decision group by operation"))}
    on_two = Counter(namespace for (namespace, _), owners in holders.items() if len(owners) > 1)
    return {"masters": dict(masters), **grouped, "identifiers_on_two_masters": dict(on_two),
            "explained": explained(store), "current_records_sha256": digest.hexdigest()}
