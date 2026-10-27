"""What one batch reads and may write (ticket 77; operator, 2026-10-14:
"We are merging individual records for each kind or entity find a match if
not found insert").

A batch changes only the masters its records and decisions touch, and their
links. It reads, by key through an index:

1. **The affected masters** (`identities`): each record of the batch and each
   record or master a decision names, with the decisions that bind or merge
   them, until the identities are whole. Links are not followed.
2. **The links those masters start** (`links`): every source record of their members
   and the source records their stored links cite. The far end of a plain link is
   read as it is stored, never replayed.
3. **The links into a master whose identity changed** (new, merged, or a
   changed status, kind or profiles): every source record that links to its records.
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


# A link type walked whole: a parent chain, its cycles, a second parent, an
# ultimate parent or a succession depend on every link of the hierarchy.
WHOLE = ("hierarchy", "one_parent", "ultimate_parent", "ends_parent_links")
# What a link checks of its ends: a change re-checks the links into a master.
# Its records too: a record that joins or leaves moves the links naming it.
LINKED = ("canonical_id", "status", "kind", "profiles", "subjects", "quarantined")


def walks_whole(spec: dict | None) -> bool:
    return any((spec or {}).get(k) for k in WHOLE)


def anchors(decision: dict) -> set[str]:
    return {
        str(decision[k])
        for k in ("subject", "entity_id", "left", "right", "target", "decision_id")
        if decision.get(k)
    }


def link_ends(reading: dict) -> list[tuple[str | None, str, str | None]]:
    """Each link of a source record as (type, start, target): a link starts at
    the record itself unless it names another (`source_subject`)."""
    return [
        (r.get("type"), r.get("source_subject") or reading["subject"], r.get("target_subject"))
        for r in reading["relationships"]
    ]


def identity_changed(new: dict, old: dict | None) -> bool:
    return old is None or any(new.get(k) != old.get(k) for k in LINKED)


@dataclass
class Scope:
    """The rows a batch replays, and what it may write."""

    readings: dict[str, dict] = field(default_factory=dict)  # assertion_id -> body
    decisions: dict[str, dict] = field(default_factory=dict)  # decision_id -> body
    stored_decisions: set[str] = field(default_factory=set)
    identities: list[dict] = field(default_factory=list)
    subjects: set[str] = field(default_factory=set)  # the affected masters' records
    masters: set[str] = field(default_factory=set)  # the affected masters
    replayed: dict[str, str | None] = field(default_factory=dict)  # record -> master, or explicitly unbound
    bound: dict[str, str] = field(default_factory=dict)  # record -> master, as stored
    stored: dict[str, dict] = field(default_factory=dict)  # master -> body, as stored
    starts: set[str] = field(default_factory=set)  # masters whose outgoing links are whole
    changed: set[str] = field(default_factory=set)  # masters whose incoming links are whole
    links: set[str] = field(default_factory=set)  # the links this batch writes or retires
    read_subjects: set[str] = field(default_factory=set)
    generation: int | None = None

    def root(self, entity: str) -> str:
        return (self.stored.get(entity) or {}).get("canonical_id") or entity

    def master(self, subject: str | None) -> str | None:
        if subject in self.replayed:
            return self.replayed[subject]
        entity = self.bound.get(subject)
        return None if entity is None else self.root(entity)

    def owns_link(self, link: dict) -> bool:
        """A link whose source records were all read: one an affected master starts,
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
        """Every source record of these records (each version), and these source records."""
        subjects = sorted(set(subjects) - self.read_subjects)
        assertion_ids = sorted(set(assertion_ids) - set(self.readings))
        if not subjects and not assertion_ids:
            return
        for body in conn.source_readings(subjects, assertion_ids):
            self.readings[body["assertion_id"]] = body
        self.read_subjects.update(subjects)
        return


def identities(conn, assertions: list[dict], decisions: list[dict]) -> Scope:
    """Step 1: the affected masters, whole."""
    from .record_reads import read_affected_records

    frame=read_affected_records(conn.adapter,assertions,decisions,connection=conn.connection)
    return Scope(readings=frame["readings"],decisions=frame["decisions"],
                 stored_decisions=set(frame["decisions"]),identities=frame["identities"],
                 subjects=frame["subjects"],read_subjects=set(frame["subjects"]),
                 generation=frame["generation"])


def retirements(conn, sources=None) -> dict[str, dict]:
    """Every retired source's decision: a handful, read whole."""
    if sources is None:
        raise ValueError("Portable retirements require the affected source keys")
    return {body["decision_id"]:body for body in conn.retained_groups(
        conn.group("source_retirements", source) for source in sorted(set(sources))).values()}


def stored_masters(conn, ids) -> dict[str, dict]:
    """Masters as stored, by their indexed identifiers."""
    return conn.masters(ids)


def links(
    conn,
    scope: Scope,
    starts: set[str],
    changed: set[str],
    types: dict,
    batch: list[dict],
) -> None:
    """Steps 2-4: read what the links of `starts` (whole outgoing) and of
    `changed` (whole incoming) need, and walk each hierarchy they touch."""
    scope.starts = set(starts)
    scope.changed = set(changed)
    named_into: set[str] = set()
    walked: set[str] = set()
    while True:
        cited = conn.projections(starts=scope.starts)
        scope.read(
            conn,
            subjects=_members(conn, scope.starts),
            assertion_ids=[e["assertion_id"] for r in cited for e in r["body"].get("evidence", [])],
        )
        into = (_members(conn, scope.changed) | {s for s, m in scope.replayed.items() if m in scope.changed})
        if want := sorted(into - named_into):
            found = [
                {"body": body}
                for body in conn.retained_groups(
                    conn.group("related_readings", key) for key in want
                ).values()
            ]
            for r in found:
                scope.readings[r["body"]["assertion_id"]] = r["body"]
            named_into.update(want)
        # A source record read for its link is read whole: every version of its record.
        scope.read(conn, subjects={a["subject"] for a in scope.readings.values()})
        every = [*scope.readings.values(), *batch]
        _bind(conn, scope, every)
        # A link of the batch's own records (or of a retired source, or one a
        # decision names) starts at a master it only names (a link record of
        # another source): that master's links are whole too.
        own = [a for a in every if a["subject"] in scope.subjects] + batch
        grown = {scope.master(start) for a in own for _, start, _ in link_ends(a)} - {None}
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
    return conn.projections(starts=scope.starts,changed=scope.changed,reviews=keys)


def _members(conn, ids) -> set[str]:
    return conn.members(ids)


def _bind(conn, scope: Scope, readings: list[dict]) -> None:
    """Each record a link names, to its master as stored."""
    named = sorted(
        {end for a in readings for _, start, target in link_ends(a) for end in (start, target)}
        - {None} - set(scope.bound) - set(scope.replayed)
    )
    found=conn.bindings(named)
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
        step = [
            {"s": row["body"]["source_id"], "t": row["body"]["target_id"]}
            for row in conn.projections(starts=frontier, changed=frontier)
            if row["body"].get("type") in whole and not row["body"].get("retired")
        ]
        frontier = {x for r in step for x in (r["s"], r["t"])} - found
        found |= frontier
    return found
