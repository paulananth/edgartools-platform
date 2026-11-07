"""`edgar-warehouse context`: small, self-explaining answers for agents.

Profiling ticket 05; `docs/specs/agent-context/spec.md` §3. One command reads
MDM's context through read-only connections and answers in JSON of at most
8 KB: names first, what the thing is, where each value came from, and what an
agent can ask next. It names no identifier or relationship type, and no kind
beyond MDM's own storage (companies keep their own versioned table): the kinds
come from MDM, their meanings from `rules/context/definitions.yaml`.

A subject that is no master kind and not `relationship` is a code set: it is
read from RDM (`edgar_warehouse/rdm/context.py`, `RDM_DATABASE_URL`). The
subject `silver` is a silver table's spec (`edgar_warehouse/silver_writer/context.py`,
`SILVER_DATABASE_URL`).
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

LIMIT_BYTES = 8192
MAX_HOPS = 3
# The most links one relationship answer walks before it stops and says so.
WALK_CAP = 1000
# A string longer than this is clipped in an answer, and the answer says so.
CLIP = 1000
RELATED_INLINE = 10
SEARCH_MAX = 20
PROG = "edgar-warehouse context"
LOOKUPS = "edgar-warehouse mdm build-lookups"


class ContextError(Exception):
    """What was wrong, and the command that would work."""

    def __init__(self, message: str, command: str):
        super().__init__(message)
        self.command = command


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "context",
        help="Read context for an agent: an entity, its relationships, or a code, as JSON of at most 8 KB",
        description=(
            "Look up a master entity by its id or by <namespace>:<value>, search names, list an "
            "entity's relationships, or look up a code of a code set (or search its labels). Read only. "
            "Answers are JSON of at most 8 KB; follow next_step."
        ),
    )
    parser.add_argument("subject", help="A master kind (company, person, ...), 'relationship', 'silver', or a code set")
    parser.add_argument("key", nargs="?", help="An entity id, <namespace>:<value> for an identifier, or a code")
    parser.add_argument("--search", help="Words to find in names, in place of a key")
    parser.add_argument("--limit", type=int, default=5, help=f"How many search matches (1-{SEARCH_MAX})")
    parser.add_argument("--detail-key", nargs="+", metavar="NAME_OR_VALUE",
                        help="A configured detail key's name and values, in place of a key "
                             "(security: mic <MIC> <ticker>, or exchange <code> <ticker>): every master holding it")
    parser.add_argument("--as-of", help="Business time, for relationships and code sets (ISO time with a zone)")
    parser.add_argument("--as-at", help="Recording time, for code sets (ISO time with a zone)")
    parser.add_argument("--hops", type=int, default=1, help=f"Relationships: how far to walk (1-{MAX_HOPS})")
    parser.add_argument("--type", dest="relationship_type", default="", help="Relationships: one type only")
    parser.add_argument("--detail", choices=("brief", "full"), default="brief")
    parser.add_argument("--page", help="The next_page token of an earlier answer")
    parser.set_defaults(handler=_handle)


@dataclass(frozen=True)
class Store:
    """Where one kind of subject is read: its login's variable, whether that
    login reads as MDM's application role, and how to check the store."""

    name: str
    variable: str
    application_role: bool
    check: str
    reader: str  # module:class, imported only when used


# One entry per store (GoF consult, ticket 05 RDM part): silver specs add one.
STORES = {
    "MDM": Store("MDM", "MDM_DATABASE_URL", True, "edgar-warehouse mdm check-connectivity", "edgar_warehouse.context:Context"),
    "RDM": Store("RDM", "RDM_DATABASE_URL", False, "edgar-warehouse rdm migrate", "edgar_warehouse.rdm.context:CodeContext"),
    "SILVER": Store("silver", "SILVER_DATABASE_URL", False, "edgar-warehouse silver migrate",
                    "edgar_warehouse.silver_writer.context:TableContext"),
}


def store_for(subject: str) -> Store:
    """A master kind or `relationship` is MDM's, `silver` is the silver schema's; any other subject is a code set."""
    from edgar_warehouse.rules.files import context_subjects

    if subject == "silver":
        return STORES["SILVER"]
    return STORES["MDM" if subject in context_subjects() else "RDM"]


def _handle(args: argparse.Namespace) -> int:
    import importlib

    store = store_for(args.subject)
    try:
        engine = _engine(store, args.subject)
        try:
            module, name = store.reader.split(":")
            answer = getattr(importlib.import_module(module), name)(engine).answer(args)
        finally:
            engine.dispose()
        code = 0
    except ContextError as error:
        answer, code = {"error": str(error), "try": error.command}, 2
    except Exception as error:  # noqa: BLE001 - a driver message can carry the database address
        answer = {
            "error": f"The {store.name} database could not be read ({type(error).__name__}).",
            "try": f"Check that {store.variable} is set and that {store.name} is migrated ({store.check}).",
        }
        code = 1
    print(json.dumps(answer, ensure_ascii=False))
    return code


def _engine(store: Store = STORES["MDM"], subject: str | None = None):
    import os

    from sqlalchemy import event

    from edgar_warehouse.database_connections import engine_from_env

    if not os.environ.get(store.variable):
        if store.name == "RDM" and subject:  # a misspelled kind lands here too
            from edgar_warehouse.rules.files import context_subjects

            kinds = context_subjects() - {"relationship"}

            raise ContextError(f"{subject!r} is not a master kind ({', '.join(sorted(kinds))}) or 'relationship'; "
                               f"as a code set it is read from RDM, and {store.variable} is not set.",
                               f"Set {store.variable} to a login that may read RDM, or name a kind.")
        raise ContextError(f"{store.variable} is not set.",
                           f"Set {store.variable} to a login that may read {store.name}, then run the command again.")
    engine = engine_from_env(store.variable,
        runtime_role=os.environ.get("MDM_APPLICATION_ROLE", "application") if store.application_role else None)

    @event.listens_for(engine, "connect")
    def read_only(dbapi_connection, _):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY" if engine.dialect.name == "mysql"
                           else "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        dbapi_connection.commit()

    return engine


def definitions() -> dict:
    from edgar_warehouse.rules import files

    return files.load(files.ROOT / "context" / "definitions.yaml")


def relationship_definitions() -> dict:
    """Each relationship type's plain words: its code's definition in the RDM code set the policy pins (ticket 132)."""
    from edgar_warehouse.rules import files

    return {row["code"]: row["definition"] for row in files.pinned_reference("mdm-relationship-types")
            if row["parent_code"] is None}


def parse_time(value: str, flag: str, command: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        raise ContextError(f"{flag} needs an ISO time with a zone, not {value!r}.", f"{command} {flag} 2026-01-31T00:00:00+00:00")
    return moment.astimezone(UTC)


def page_offset(page: str | None) -> int:
    if page is None:
        return 0
    match = re.fullmatch(r"p(\d{1,6})", page)
    if not match:
        raise ContextError(f"--page {page!r} is not a next_page token.", "Pass the next_page value of the earlier answer, as given.")
    return int(match.group(1))


def _clip(value):
    if isinstance(value, str) and len(value) > CLIP:
        return value[:CLIP] + "…", True
    if isinstance(value, dict):
        clipped = False
        result = {}
        for key, item in value.items():
            result[key], cut = _clip(item)
            clipped |= cut
        return result, clipped
    if isinstance(value, list):
        pairs = [_clip(item) for item in value]
        return [p[0] for p in pairs], any(p[1] for p in pairs)
    return value, False


def _size(answer: dict) -> int:
    return len(json.dumps(answer, ensure_ascii=False).encode("utf-8"))


def fit(answer: dict, list_key: str, offset: int, command: str, view: str = "mastering_master WHERE entity_id = '<id>'") -> dict:
    """Cut the answer's one long list at a whole item so it stays within 8 KB.

    `command` is the command that asks for the next page, without --page.
    """
    answer, clipped = _clip(answer)
    if clipped:
        answer["clipped"] = True
    items = answer[list_key]
    if offset > len(items):
        raise ContextError(f"Page p{offset} is past the end ({len(items)} items).", command)
    rest = items[offset:]

    def page(n):
        more = offset + n < len(items)
        shown = {**answer, list_key: rest[:n], "truncated": more or answer.get("truncated", False),
                 "next_page": f"p{offset + n}" if more else None}
        if more:
            shown["next_step"] = f"{command} --page p{offset + n}"
        return shown

    low, high = 0, len(rest)
    while low < high:
        middle = (low + high + 1) // 2
        if _size(page(middle)) <= LIMIT_BYTES:
            low = middle
        else:
            high = middle - 1
    result = page(low)
    if _size(result) > LIMIT_BYTES or (low == 0 and rest):
        # A page with no item would point at itself: say so rather than loop.
        raise ContextError("The answer does not fit in 8 KB.",
                           f"Query the view instead, e.g. SELECT * FROM {view}.")
    return result


class Context:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def _store(self):
        from edgar_warehouse.mastering.store import open_store

        store = open_store(self.engine)
        try:
            yield store
        finally:
            store.rollback()
            store.close()

    @contextmanager
    def _silver(self):
        engine = _engine(STORES["SILVER"])
        try:
            with engine.connect() as connection:
                yield connection
        finally:
            engine.dispose()

    def answer(self, args: argparse.Namespace) -> dict:
        from edgar_warehouse.mdm.evidence import KINDS

        if args.as_at:
            raise ContextError("MDM keeps current masters, so --as-at reads code sets only.",
                               f"{PROG} {args.subject} {args.key or ''}".rstrip())
        if args.subject == "relationship":
            return self.relationships(args)
        if args.subject not in KINDS:
            raise ContextError(
                f"{args.subject!r} is not a master kind. Kinds: {', '.join(sorted(KINDS))}, or 'relationship'.",
                f"{PROG} {sorted(KINDS)[0]} --search \"<words>\"",
            )
        if args.as_of:
            raise ContextError("MDM keeps current masters, so --as-of reads relationships only.",
                               f"{PROG} relationship {args.key or '<entity_id>'} --as-of {args.as_of}")
        if getattr(args, "detail_key", None):
            if args.key or args.search is not None:
                raise ContextError("Give a key, --search or --detail-key, not two.", f"{PROG} {args.subject} --detail-key <name> <values>")
            return self.held(args)
        if args.search is not None:
            if args.key:
                raise ContextError("Give a key or --search, not both.", f"{PROG} {args.subject} --search {shlex.quote(args.search)}")
            return self.search(args)
        if not args.key:
            raise ContextError(f"Name the {args.subject}: an entity id or <namespace>:<value>.", f"{PROG} {args.subject} --search \"<words>\"")
        return self.entity(args)

    # -- Entities ------------------------------------------------------------

    def _resolve(self, store, kind: str | None, key: str) -> str:
        """The entity a key names: an id, or the one entity carrying an identifier."""
        from edgar_warehouse.mastering import lookups, reads
        from edgar_warehouse.rules import files

        if ":" not in key:
            return key
        namespace, value = key.split(":", 1)
        try:
            found = reads.carriers(store, files.policy(), kind, namespace, value)
        except lookups.NotBuilt as error:
            raise ContextError(str(error), LOOKUPS) from None
        if not found:
            raise ContextError(f"No {kind or 'entity'} carries {namespace}:{value}.",
                               f"{PROG} {kind or 'company'} --search \"<name>\"")
        if len(found) > 1:
            names = self._names(store, list(found))
            listed = "; ".join(f"{names.get(i, {}).get('name') or '(no name)'} ({i})" for i in sorted(found))
            raise ContextError(
                f"{namespace}:{value} is carried by {len(found)} entities: {listed}. "
                + ("It is a cross-reference id, lookup only: sharing it does not make them one entity."
                   if "cross_reference" in found.values() else "Pick one by its id."),
                f"{PROG} {kind or 'relationship'} {sorted(found)[0]}",
            )
        return next(iter(found))

    @staticmethod
    def _names(store, ids: list[str]) -> dict:
        return {key: {"name": _name(body), "kind": body["kind"]} for key, body in store.master_bodies(ids).items()}

    def entity(self, args: argparse.Namespace) -> dict:
        from edgar_warehouse.mastering import reads

        with self._store() as store, self._silver() as silver:
            entity_id = self._resolve(store, args.subject, args.key)
            try:
                body = reads.master(store, entity_id)
            except KeyError:
                raise ContextError(f"No {args.subject} {entity_id} in MDM.", f"{PROG} {args.subject} --search \"<name>\"") from None
            if body["kind"] != args.subject:
                raise ContextError(f"{entity_id} is a {body['kind']}, not a {args.subject}.", f"{PROG} {body['kind']} {entity_id}")
            canonical = body["entity_id"]
            records = [json.loads(record) for record in store.member_bodies([canonical])]
            splits = reads.splits_of(store, canonical)
            changed = store.master_file(canonical)
            related, related_count, cut = self._walk(store, silver, canonical, 1, self._at(args), "", RELATED_INLINE)
        full = args.detail == "full"
        fields = []
        for name, field in sorted(body.get("fields", {}).items()):
            if field.get("cleared"):
                continue
            item = {"field": name, "value": field.get("value"), "source": field["winner"].get("source_code")}
            if full:
                item["record_key"] = field["winner"].get("record_key")
                item["effective_at"] = field["winner"].get("effective_at")
            fields.append(item)
        cross_references: dict[str, set] = {}
        sources: dict[str, set] = {}
        for record in records:
            sources.setdefault(record["source_code"], set()).add(record["record_key"])
            for namespace, value in (record.get("cross_references") or {}).items():
                cross_references.setdefault(namespace, set()).add(value)
        answer = {
            "name": _name(body),
            "kind": body["kind"],
            "key": args.key,
            "entity_id": canonical,
            "status": body.get("status"),
            "definition": definitions().get("kinds", {}).get(body["kind"], ""),
            "fields": fields,
            "identifiers": body.get("identifiers", {}),
            "cross_references": {k: sorted(v) for k, v in sorted(cross_references.items())},
            "sources": {k: sorted(v) for k, v in sorted(sources.items())} if full else sorted(sources),
            "trust": {"file": changed, "policy_digest": _policy_digest(body), "status": body.get("status")},
        }
        if canonical != entity_id:
            answer["merged_from"] = entity_id
        if splits:  # a steward split a consolidation of this master; the pair is a Match Exclusion (ticket 142)
            answer["splits"] = splits
        answer["related"] = [_brief_link(link) for link in related]
        answer["related_count"] = f"{related_count}+" if cut else related_count
        answer["truncated"] = False
        answer["next_page"] = None
        answer["next_step"] = f"{PROG} relationship {canonical}" + (" --detail full" if not full else "")
        command = f"{PROG} {args.subject} {args.key}" + (f" --detail {args.detail}" if args.detail else "")
        return fit(answer, "fields", page_offset(args.page), command)

    def search(self, args: argparse.Namespace) -> dict:
        from edgar_warehouse.mastering import lookups

        if not 1 <= args.limit <= SEARCH_MAX:
            raise ContextError(f"--limit is 1 to {SEARCH_MAX}.", f"{PROG} {args.subject} --search {shlex.quote(args.search)} --limit 5")
        words = args.search.strip()
        if not words:
            raise ContextError("--search needs some words.", f"{PROG} {args.subject} --search \"<words>\"")
        with self._store() as store:
            try:
                rows = lookups.search(store, args.subject, words, args.limit)
            except lookups.NotBuilt as error:
                raise ContextError(str(error), LOOKUPS) from None
            trust = {"file": store.last_file()}
        matches = [{"name": r["name"], "kind": r["kind"], "entity_id": r["entity_id"], "status": r["status"],
                    "matched_by": r["matched_by"]} for r in rows]
        if not matches:
            print(json.dumps({"event": "context-search-miss", "kind": args.subject, "words": words}), file=sys.stderr)
        answer = {
            "search": words,
            "kind": args.subject,
            "definition": definitions().get("kinds", {}).get(args.subject, ""),
            "matches": matches,
            "trust": trust,
            "truncated": False,
            "next_page": None,
            "next_step": (f"{PROG} {args.subject} <entity_id>" if matches
                          else f"No {args.subject} name matches. Try fewer words, or {PROG} {args.subject} <namespace>:<value>."),
        }
        return fit(answer, "matches", page_offset(args.page), f"{PROG} {args.subject} --search {shlex.quote(words)} --limit {args.limit}")

    def held(self, args: argparse.Namespace) -> dict:
        """Every current master whose detail rows hold a configured key: never one picked."""
        from edgar_warehouse.mastering import lookups
        from edgar_warehouse.mdm import detail_lookups

        name, values = args.detail_key[0], args.detail_key[1:]
        again = f"{PROG} {args.subject} --detail-key {shlex.join(args.detail_key)}"
        spec = detail_lookups.configuration()
        if spec is None or spec["kind"] != args.subject:
            raise ContextError(f"No detail lookup is configured for {args.subject}.",
                               f"{PROG} {args.subject} <entity_id> or {PROG} {args.subject} <namespace>:<value>")
        if name not in spec["keys"] or len(values) != len(spec["keys"][name]):
            shapes = "; ".join(name + " " + " ".join(f"<{field}>" for field in fields)
                               for name, fields in sorted(spec["keys"].items()))
            raise ContextError(f"--detail-key takes a key name and its values: {shapes}.",
                               f"{PROG} {args.subject} --detail-key {sorted(spec['keys'])[0]} <values>")
        with self._store() as store:
            try:
                rows = lookups.holders_of_detail(store, name, values)
            except lookups.NotBuilt as error:
                raise ContextError(str(error), LOOKUPS) from None
            trust = {"file": store.last_file()}
        answer = {
            "detail_key": {"name": name, "values": values, "fields": spec["keys"][name]},
            "kind": args.subject,
            "definition": definitions().get("kinds", {}).get(args.subject, ""),
            "matches": rows,
            "trust": trust,
            "truncated": False,
            "next_page": None,
            "next_step": (f"{PROG} {args.subject} <entity_id>" if rows
                          else f"No {args.subject} holds it. Keys: {', '.join(sorted(spec['keys']))}."),
        }
        return fit(answer, "matches", page_offset(args.page), again)

    # -- Relationships -------------------------------------------------------

    @staticmethod
    def _at(args) -> datetime:
        return parse_time(args.as_of, "--as-of", f"{PROG} {args.subject} {args.key}") if args.as_of else datetime.now(UTC)

    def _walk(self, store, silver, start: str, hops: int, at: datetime, relationship_type: str, cap: int):
        """The links around one entity, both directions, up to `hops` away. A link counts when one of its
        periods holds at `at`; a calculated one with no periods always counts. Returns (links, count, cut)."""
        from edgar_warehouse.mastering.links import around

        seen_entities, seen_links, links = {start}, set(), []
        frontier, cut = [start], False
        for depth in range(1, hops + 1):
            if not frontier:
                break
            rows = [body for body in around(silver, frontier, relationship_type)
                    if _period(body, at) is not None or body["derived"] and not body["periods"]]
            following = []
            for body in rows[:cap - len(links) + 1]:
                relationship_id = body["relationship_id"]
                if relationship_id in seen_links:
                    continue
                if len(links) >= cap:
                    cut = True
                    break
                seen_links.add(relationship_id)
                links.append({"depth": depth, "relationship_id": relationship_id, "body": body})
                for end in (body["source_id"], body["target_id"]):
                    if end not in seen_entities:
                        seen_entities.add(end)
                        following.append(end)
            if cut:
                break
            frontier = following
        names = self._names(store, sorted({e for link in links for e in (link["body"]["source_id"], link["body"]["target_id"])}))
        for link in links:
            body = link["body"]
            link["from"] = {**names.get(body["source_id"], {"name": None, "kind": None}), "entity_id": body["source_id"]}
            link["to"] = {**names.get(body["target_id"], {"name": None, "kind": None}), "entity_id": body["target_id"]}
            link["period"] = _period(body, at)
        links.sort(key=lambda l: (l["depth"], l["body"]["type"], l["from"]["name"] or "", l["to"]["name"] or "", l["relationship_id"]))
        return links, len(links), cut

    def relationships(self, args: argparse.Namespace) -> dict:
        from edgar_warehouse.mastering import reads

        if not args.key:
            raise ContextError("Name the entity: its id or <namespace>:<value>.", f"{PROG} relationship <entity_id>")
        if not 1 <= args.hops <= MAX_HOPS:
            raise ContextError(f"--hops is 1 to {MAX_HOPS}.", f"{PROG} relationship {args.key} --hops 1")
        at = self._at(args)
        full = args.detail == "full"
        with self._store() as store, self._silver() as silver:
            try:
                entity_id = reads.master(store, self._resolve(store, None, args.key))["entity_id"]
            except KeyError:
                raise ContextError(f"No entity {args.key} in MDM.", f"{PROG} company --search \"<name>\"") from None
            names = self._names(store, [entity_id])
            links, count, cut = self._walk(store, silver, entity_id, args.hops, at, args.relationship_type, WALK_CAP)
            trust = {"file": store.last_file()}
            if full:
                _attach_sources(store, links)
        types = relationship_definitions()
        related = [_full_link(link) if full else _brief_link(link) for link in links]
        answer = {
            "name": names[entity_id]["name"],
            "kind": names[entity_id]["kind"],
            "key": args.key,
            "entity_id": entity_id,
            "at": at.isoformat(),
            "hops": args.hops,
            "definitions": {t: types.get(t, "") for t in sorted({link["body"]["type"] for link in links})},
            "related": related,
            "related_count": f"{count}+" if cut else count,
            "trust": trust,
            "truncated": cut,
            "next_page": None,
            "next_step": (f"Over {WALK_CAP} links: narrow it with --type <TYPE> or --hops 1, or query silver.relationship."
                          if cut else f"{PROG} <kind> <entity_id> for any entity listed"),
        }
        command = f"{PROG} relationship {args.key} --hops {args.hops}" + "".join(
            f" --{flag} {value}" for flag, value in (("type", args.relationship_type), ("as-of", args.as_of),
                                                     ("detail", args.detail)) if value)
        return fit(answer, "related", page_offset(args.page), command)


def _name(body: dict):
    from edgar_warehouse.mdm.master_search import configuration, configured_name
    spec = configuration()
    if spec is not None:
        return configured_name(body, spec)
    fields = body.get("fields", {})
    for name in ("name", "legal_name", "display_name"):
        value = fields.get(name, {}).get("value")
        if value:
            return value
    return None


def _period(body: dict, at: datetime) -> dict | None:
    for period in body.get("periods", []):
        start, end = period.get("valid_from"), period.get("valid_to")
        if start and datetime.fromisoformat(start) <= at and (end is None or datetime.fromisoformat(end) > at):
            return period
    return None


def _brief_link(link: dict) -> dict:
    body = link["body"]
    item = {"depth": link["depth"], "type": body.get("type"),
            "from": {"name": link["from"]["name"], "entity_id": link["from"]["entity_id"]},
            "to": {"name": link["to"]["name"], "entity_id": link["to"]["entity_id"]}}
    if body.get("capacity"):
        item["role"] = body["capacity"]
    if body.get("derived"):
        item["derived"] = True
    item["basis"] = "calculated" if body.get("derived") else "stated"
    return item


def _full_link(link: dict) -> dict:
    body, period = link["body"], link["period"] or {}
    return {**_brief_link(link), "relationship_id": link["relationship_id"],
            "from": link["from"], "to": link["to"], "scope": body.get("scope"),
            "valid_from": period.get("valid_from"), "valid_to": period.get("valid_to"),
            "valid_from_basis": period.get("valid_from_basis"), "last_seen": body.get("last_seen"),
            "sources": link.get("sources", []),
            # A succession that ended it; the chain a calculated link walked.
            **{key: period[key] for key in ("ended_by", "path") if period.get(key)}}


def _policy_digest(body: dict) -> str | None:
    """The matching rules a master's fields were chosen under."""
    return next((field["policy_digest"] for field in body.get("fields", {}).values() if field.get("policy_digest")), None)


def _attach_sources(store, links: list[dict]) -> None:
    """Each link's stating records (source code and record key)."""
    named = store.records_named({assertion for link in links for assertion in link["body"]["evidence"]})
    for link in links:
        stated = {named[assertion] for assertion in link["body"]["evidence"] if assertion in named}
        link["sources"] = [{"source_code": code, "record_key": key} for code, key in sorted(stated)]
