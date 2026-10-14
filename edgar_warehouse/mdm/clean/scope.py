"""What one batch reads and may write (ticket 77; operator, 2026-10-14:
"We are merging individual records for each kind or entity find a match if
not found insert").

A batch changes only the masters its records and decisions touch, and their
links. It reads, by key through an index:

1. **The affected masters** (`identities`): each record of the batch and each
   record or master a decision names, with the decisions that bind or merge
   them, until the identities are whole. Links are not followed.
2. **The links those masters start** (`links`): the readings of their records
   and the readings their stored links cite. The far end of a plain link is
   read as it is stored, never replayed.
3. **The links into a master whose identity changed** (new, merged, or a
   changed status, kind or profiles): every reading that links to its records.
4. **A hierarchy whole**: a parent-type link walks its stored chain up and
   down, so cycles, a second parent and ultimate parents see all of it.

A stored row outside these is neither rewritten nor retired (`owns`,
`owns_link`).

Every list of keys is read one index probe per key: `unnest(keys) CROSS JOIN
LATERAL (... OFFSET 0)`. The `OFFSET 0` keeps PostgreSQL from folding the
probe into a join that reads a whole index, which it prefers on a small table
and which would grow with the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from .store import rows

# A link type walked whole: a parent chain, its cycles, a second parent, an
# ultimate parent or a succession depend on every link of the hierarchy.
WHOLE = ("hierarchy", "one_parent", "ultimate_parent", "ends_parent_links")
# What a link checks of its ends: a change re-checks the links into a master.
LINKED = ("canonical_id", "status", "kind", "profiles")


def walks_whole(spec: dict | None) -> bool:
    return any((spec or {}).get(k) for k in WHOLE)


def anchors(decision: dict) -> set[str]:
    return {
        str(decision[k])
        for k in ("subject", "entity_id", "left", "right", "target", "decision_id")
        if decision.get(k)
    }


def link_ends(reading: dict) -> list[tuple[str | None, str, str | None]]:
    """Each link of a reading as (type, start, target): a link starts at the
    reading's own record unless it names another (`source_subject`)."""
    return [
        (r.get("type"), r.get("source_subject") or reading["subject"], r.get("target_subject"))
        for r in reading["relationships"]
    ]


def identity_changed(new: dict, old: dict | None) -> bool:
    return old is None or any(new.get(k) != old.get(k) for k in LINKED)


def _uuids(keys) -> list[str]:
    found = []
    for key in keys:
        try:
            found.append(str(UUID(key)))
        except ValueError:
            pass
    return sorted(found)


@dataclass
class Scope:
    """The rows a batch replays, and what it may write."""

    readings: dict[str, dict] = field(default_factory=dict)  # assertion_id -> body
    decisions: dict[str, dict] = field(default_factory=dict)  # decision_id -> body
    stored_decisions: set[str] = field(default_factory=set)
    identities: list[dict] = field(default_factory=list)
    subjects: set[str] = field(default_factory=set)  # the affected masters' records
    masters: set[str] = field(default_factory=set)  # the affected masters
    replayed: dict[str, str] = field(default_factory=dict)  # record -> master, replayed
    bound: dict[str, str] = field(default_factory=dict)  # record -> master, as stored
    stored: dict[str, dict] = field(default_factory=dict)  # master -> body, as stored
    starts: set[str] = field(default_factory=set)  # masters whose outgoing links are whole
    changed: set[str] = field(default_factory=set)  # masters whose incoming links are whole
    links: set[str] = field(default_factory=set)  # the links this batch writes or retires
    read_subjects: set[str] = field(default_factory=set)

    def root(self, entity: str) -> str:
        return (self.stored.get(entity) or {}).get("canonical_id") or entity

    def master(self, subject: str | None) -> str | None:
        if subject in self.replayed:
            return self.replayed[subject]
        entity = self.bound.get(subject)
        return None if entity is None else self.root(entity)

    def owns_link(self, link: dict) -> bool:
        """A link whose readings were all read: one an affected master starts,
        or one into a master whose identity changed."""
        return link["source_id"] in self.starts or link["target_id"] in self.changed

    def owns(self, review: dict) -> bool:
        """A review this batch decides: about an affected master or record, a
        decision it read, or a link it owns."""
        link = review.get("relationship")
        if link is not None:
            start = link.get("source_subject") or review.get("subject")
            return (
                start in self.subjects
                or self.master(start) in self.starts
                or self.master(link.get("target_subject")) in self.changed
            )
        if review.get("edges"):
            # A hierarchy finding (a cycle, two parents): its chain is read
            # whole whenever any of its Companies is.
            return bool(set(review.get("entities", [])) & self.starts)
        if review.get("relationship_id"):
            return review["relationship_id"] in self.links
        return (
            review.get("entity_id") in self.masters
            or review.get("subject") in self.subjects
            or review.get("decision_id") in self.decisions
            or bool(set(review.get("entities", [])) & self.starts)
        )

    def read(self, conn, *, subjects=(), assertion_ids=()) -> None:
        """Every reading of these records (each version), and these readings."""
        subjects = sorted(set(subjects) - self.read_subjects)
        assertion_ids = sorted(set(assertion_ids) - set(self.readings))
        if not subjects and not assertion_ids:
            return
        for r in rows(
            conn,
            """SELECT r.body FROM unnest(CAST(:subjects AS text[])) k(key) CROSS JOIN LATERAL (
                 SELECT body FROM mdm.source_reading WHERE body->>'subject' = k.key OFFSET 0) r
               UNION ALL
               SELECT r.body FROM unnest(CAST(:ids AS text[])) k(key) CROSS JOIN LATERAL (
                 SELECT body FROM mdm.source_reading WHERE assertion_id = k.key OFFSET 0) r""",
            subjects=subjects,
            ids=assertion_ids,
        ):
            self.readings[r["body"]["assertion_id"]] = r["body"]
        self.read_subjects.update(subjects)


def identities(conn, assertions: list[dict], decisions: list[dict]) -> Scope:
    """Step 1: the affected masters, whole."""
    scope = Scope()
    keys = {a["subject"] for a in assertions} | {k for d in decisions for k in anchors(d)}
    retiring = sorted({d["source_code"] for d in decisions if d["operation"] == "retire_source"})
    if retiring:
        # Every record of a source being retired is the batch's own work.
        for r in rows(
            conn,
            "SELECT body FROM mdm.source_reading WHERE source_code=ANY(CAST(:codes AS text[]))",
            codes=retiring,
        ):
            scope.readings[r["body"]["assertion_id"]] = r["body"]
            keys.add(r["body"]["subject"])
    named: set[str] = set()
    while want := sorted(keys - named):
        for r in rows(
            conn,
            """SELECT body FROM mdm.decision
            WHERE decision_id IN (SELECT id FROM mdm.decisions_naming(CAST(:keys AS text[])) id)""",
            keys=want,
        ):
            scope.decisions[r["body"]["decision_id"]] = r["body"]
            keys.update(anchors(r["body"]))
        named.update(want)
    scope.stored_decisions = set(scope.decisions)
    ids = set(_uuids(keys))
    scope.subjects = keys - ids - set(scope.decisions) - {d["decision_id"] for d in decisions}
    scope.read(conn, subjects=scope.subjects)
    scope.identities = rows(
        conn,
        """SELECT i.entity_id::text, i.kind, i.published_at::text
        FROM unnest(CAST(:ids AS uuid[])) k(id) CROSS JOIN LATERAL (
            SELECT * FROM mdm.master_entity WHERE entity_id = k.id OFFSET 0) i""",
        ids=sorted(ids),
    )
    return scope


def retirements(conn) -> dict[str, dict]:
    """Every retired source's decision: a handful, read whole."""
    return {
        r["body"]["decision_id"]: r["body"]
        for r in rows(conn, "SELECT body FROM mdm.decision WHERE operation='retire_source'")
    }


def stored_masters(conn, ids) -> dict[str, dict]:
    """Masters as stored, by id (`current_entity`: Companies and every kind)."""
    return {
        r["object_id"]: r["body"]
        for r in rows(
            conn,
            """SELECT e.object_id, e.body FROM unnest(CAST(:ids AS text[])) k(id) CROSS JOIN LATERAL (
                SELECT object_id, body FROM mdm.current_entity WHERE object_id = k.id OFFSET 0) e""",
            ids=sorted(set(ids)),
        )
    }


def links(conn, scope: Scope, starts: set[str], changed: set[str], types: dict, batch: list[dict]) -> None:
    """Steps 2-4: read what the links of `starts` (whole outgoing) and of
    `changed` (whole incoming) need, and walk each hierarchy they touch."""
    scope.starts = set(starts)
    scope.changed = set(changed)
    named_into: set[str] = set()
    walked: set[str] = set()
    while True:
        cited = rows(
            conn,
            """SELECT c.body FROM unnest(CAST(:ids AS text[])) k(id) CROSS JOIN LATERAL (
                SELECT body FROM mdm.current_record
                WHERE object_type='relationship' AND body->>'source_id' = k.id OFFSET 0) c""",
            ids=sorted(scope.starts),
        )
        scope.read(
            conn,
            subjects=_members(conn, scope.starts),
            assertion_ids=[e["assertion_id"] for r in cited for e in r["body"].get("evidence", [])],
        )
        into = (_members(conn, scope.changed) | {s for s, m in scope.replayed.items() if m in scope.changed})
        if want := sorted(into - named_into):
            for r in rows(
                conn,
                """SELECT body FROM mdm.source_reading WHERE assertion_id IN (
                    SELECT id FROM mdm.readings_naming(CAST(:keys AS text[])) id)""",
                keys=want,
            ):
                scope.readings[r["body"]["assertion_id"]] = r["body"]
            named_into.update(want)
        # A reading read for its link is read whole: every version of its record.
        scope.read(conn, subjects={a["subject"] for a in scope.readings.values()})
        every = [*scope.readings.values(), *batch]
        _bind(conn, scope, every)
        # A link of the batch's own records starts at a master it only names
        # (a link record of another source): that master's links are whole too.
        grown = {scope.master(start) for a in batch for _, start, _ in link_ends(a)} - {None}
        # A hierarchy link touching a start or a changed master: walk it whole.
        touched = {
            end
            for a in every
            for kind, start, target in link_ends(a)
            if walks_whole(types.get(kind))
            for end in ({scope.master(start), scope.master(target)} - {None})
            if {scope.master(start), scope.master(target)} & (scope.starts | scope.changed)
        }
        grown |= _chain(conn, touched - walked, types)
        walked |= touched
        if grown <= scope.starts:
            return
        scope.starts |= grown


def stored_links_and_reviews(conn, scope: Scope) -> list[dict]:
    """The stored links and reviews this batch may rewrite or retire, each
    read through its index."""
    keys = sorted(scope.masters | scope.starts | scope.changed | scope.read_subjects | scope.subjects)
    found = rows(
        conn,
        """SELECT c.* FROM unnest(CAST(:starts AS text[])) k(key) CROSS JOIN LATERAL (
            SELECT object_type, object_id, body FROM mdm.current_record
            WHERE object_type='relationship' AND body->>'source_id'=k.key OFFSET 0) c
        UNION ALL SELECT c.* FROM unnest(CAST(:changed AS text[])) k(key) CROSS JOIN LATERAL (
            SELECT object_type, object_id, body FROM mdm.current_record
            WHERE object_type='relationship' AND body->>'target_id'=k.key OFFSET 0) c
        UNION ALL SELECT c.* FROM unnest(CAST(:keys AS text[])) k(key) CROSS JOIN LATERAL (
            SELECT object_type, object_id, body FROM mdm.current_record
            WHERE object_type='review' AND body->>'entity_id'=k.key OFFSET 0) c
        UNION ALL SELECT c.* FROM unnest(CAST(:keys AS text[])) k(key) CROSS JOIN LATERAL (
            SELECT object_type, object_id, body FROM mdm.current_record
            WHERE object_type='review' AND body->>'subject'=k.key OFFSET 0) c
        UNION ALL SELECT c.* FROM unnest(CAST(:keys AS text[])) k(key) CROSS JOIN LATERAL (
            SELECT object_type, object_id, body FROM mdm.current_record
            WHERE object_type='review' AND body->'affected_subjects' ? k.key OFFSET 0) c""",
        starts=sorted(scope.starts),
        changed=sorted(scope.changed),
        keys=keys,
    )
    return list({(r["object_type"], r["object_id"]): r for r in found}.values())


def _members(conn, ids) -> set[str]:
    return {
        r["subject"]
        for r in rows(
            conn,
            """SELECT s.subject FROM unnest(CAST(:ids AS uuid[])) k(id) CROSS JOIN LATERAL (
                SELECT subject FROM mdm.stage_record WHERE entity_id = k.id OFFSET 0) s""",
            ids=_uuids(ids),
        )
    }


def _bind(conn, scope: Scope, readings: list[dict]) -> None:
    """Each record a link names, to its master as stored."""
    named = sorted(
        {end for a in readings for _, start, target in link_ends(a) for end in (start, target)}
        - {None} - set(scope.bound) - set(scope.replayed)
    )
    found = {
        r["subject"]: r["entity_id"]
        for r in rows(
            conn,
            """SELECT s.subject, s.entity_id::text AS entity_id FROM unnest(CAST(:keys AS text[])) k(key)
            CROSS JOIN LATERAL (
                SELECT subject, entity_id FROM mdm.stage_record
                WHERE subject = k.key AND entity_id IS NOT NULL OFFSET 0) s""",
            keys=named,
        )
    }
    scope.stored.update(stored_masters(conn, set(found.values()) - set(scope.stored)))
    # A merged-away master points at its survivor; read the survivor too.
    survivors = {b.get("canonical_id") for b in scope.stored.values()} - set(scope.stored) - {None}
    scope.stored.update(stored_masters(conn, survivors))
    # A record whose master is not stored stays unbound (an unresolved end).
    scope.bound.update({s: e for s, e in found.items() if scope.root(e) in scope.stored})


def _chain(conn, seeds: set[str], types: dict) -> set[str]:
    """Every master a stored hierarchy link joins to the seeds, both ways."""
    whole = sorted(k for k, spec in types.items() if walks_whole(spec))
    found, frontier = set(seeds), set(seeds)
    while frontier and whole:
        step = rows(
            conn,
            """SELECT c.s, c.t FROM unnest(CAST(:ids AS text[])) k(id) CROSS JOIN LATERAL (
                SELECT body->>'source_id' AS s, body->>'target_id' AS t FROM mdm.current_record
                WHERE object_type='relationship' AND body->>'source_id' = k.id
                  AND body->>'type' = ANY(CAST(:types AS text[])) OFFSET 0) c
            UNION
            SELECT c.s, c.t FROM unnest(CAST(:ids AS text[])) k(id) CROSS JOIN LATERAL (
                SELECT body->>'source_id' AS s, body->>'target_id' AS t FROM mdm.current_record
                WHERE object_type='relationship' AND body->>'target_id' = k.id
                  AND body->>'type' = ANY(CAST(:types AS text[])) OFFSET 0) c""",
            ids=sorted(frontier),
            types=whole,
        )
        frontier = {x for r in step for x in (r["s"], r["t"])} - found
        found |= frontier
    return found
