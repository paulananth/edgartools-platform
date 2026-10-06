"""`edgar-warehouse context`: small, self-explaining answers for agents.

Profiling ticket 05; `docs/specs/agent-context/spec.md` §3. One command reads
MDM's context through read-only connections and answers in JSON of at most
8 KB: names first, what the thing is, where each value came from, and what an
agent can ask next. It names no kind, identifier or relationship type: the
kinds come from MDM, their meanings from `rules/context/definitions.yaml`.

Reference data (`rdm.code_context`) and silver table specs join this command
with phase B (tickets 02 and 06).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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


class ContextError(Exception):
    """What was wrong, and the command that would work."""

    def __init__(self, message: str, command: str):
        super().__init__(message)
        self.command = command


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "context",
        help="Read MDM context for an agent: an entity or its relationships, as JSON of at most 8 KB",
        description=(
            "Look up a master entity by its id or by <namespace>:<value>, search names, or list an "
            "entity's relationships. Read only. Answers are JSON of at most 8 KB; follow next_step."
        ),
    )
    parser.add_argument("subject", help="A master kind (company, person, ...) or 'relationship'")
    parser.add_argument("key", nargs="?", help="An entity id, or <namespace>:<value> for an identifier")
    parser.add_argument("--search", help="Words to find in names, in place of a key")
    parser.add_argument("--limit", type=int, default=5, help=f"How many search matches (1-{SEARCH_MAX})")
    parser.add_argument("--as-of", help="Business time: what was true then (ISO time with a zone)")
    parser.add_argument("--as-at", help="Recording time: what MDM had recorded by then (ISO time with a zone)")
    parser.add_argument("--hops", type=int, default=1, help=f"Relationships: how far to walk (1-{MAX_HOPS})")
    parser.add_argument("--type", dest="relationship_type", default="", help="Relationships: one type only")
    parser.add_argument("--detail", choices=("brief", "full"), default="brief")
    parser.add_argument("--page", help="The next_page token of an earlier answer")
    parser.set_defaults(handler=_handle)


def _handle(args: argparse.Namespace) -> int:
    try:
        engine = _engine()
        try:
            answer = Context(engine).answer(args)
        finally:
            engine.dispose()
        code = 0
    except ContextError as error:
        answer, code = {"error": str(error), "try": error.command}, 2
    except Exception as error:  # noqa: BLE001 - a driver message can carry the database address
        answer = {
            "error": f"The MDM database could not be read ({type(error).__name__}).",
            "try": "Check that MDM_DATABASE_URL is set and that MDM is migrated (edgar-warehouse mdm check-connectivity).",
        }
        code = 1
    print(json.dumps(answer, ensure_ascii=False))
    return code


def _engine():
    import os

    from sqlalchemy import event

    from edgar_warehouse.mdm.clean.cli import engine_from_env

    if not os.environ.get("MDM_DATABASE_URL"):
        raise ContextError("MDM_DATABASE_URL is not set.", "Set MDM_DATABASE_URL to a login that may read MDM, then run the command again.")
    engine = engine_from_env("MDM_DATABASE_URL")

    @event.listens_for(engine, "connect")
    def read_only(dbapi_connection, _):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        dbapi_connection.commit()

    return engine


def definitions() -> dict:
    from edgar_warehouse.rules import files

    return files.load(files.ROOT / "context" / "definitions.yaml")


def _time(value: str, flag: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        raise ContextError(f"{flag} needs an ISO time with a zone, not {value!r}.", f"{flag} 2026-01-31T00:00:00+00:00")
    return moment.astimezone(UTC)


def _offset(page: str | None) -> int:
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


def fit(answer: dict, list_key: str, offset: int, command: str) -> dict:
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
                           "Query the view instead, e.g. SELECT * FROM mdm.entity_context WHERE entity_id = '<id>'.")
    return result


class Context:
    def __init__(self, engine):
        self.engine = engine

    def answer(self, args: argparse.Namespace) -> dict:
        from edgar_warehouse.mdm.clean.evidence import KINDS

        if args.as_of and args.as_at:
            raise ContextError("Give --as-of or --as-at, not both.", f"{PROG} {args.subject} {args.key or ''} --as-of <time>".replace("  ", " "))
        if args.subject == "relationship":
            return self.relationships(args)
        if args.subject not in KINDS:
            raise ContextError(
                f"{args.subject!r} is not a master kind. Kinds: {', '.join(sorted(KINDS))}, or 'relationship'.",
                f"{PROG} {sorted(KINDS)[0]} --search \"<words>\"",
            )
        if args.search is not None:
            if args.key:
                raise ContextError("Give a key or --search, not both.", f"{PROG} {args.subject} --search \"{args.search}\"")
            return self.search(args)
        if not args.key:
            raise ContextError(f"Name the {args.subject}: an entity id or <namespace>:<value>.", f"{PROG} {args.subject} --search \"<words>\"")
        return self.entity(args)

    # -- Entities ------------------------------------------------------------

    def _resolve(self, conn, kind: str | None, key: str) -> str:
        """The entity a key names: an id, or the one entity carrying an identifier."""
        from sqlalchemy import text

        if ":" not in key:
            return key
        namespace, value = key.split(":", 1)
        found = {r[0]: "identifier" for r in conn.execute(text(
            """SELECT DISTINCT coalesce(e.canonical_id, s.entity_id::text)
                 FROM mdm.stage_record s
                 LEFT JOIN mdm.current_entity e ON e.object_id = s.entity_id::text
                WHERE s.reading -> 'identifiers' @> jsonb_build_object(CAST(:ns AS text), CAST(:v AS text))
                  AND s.entity_id IS NOT NULL AND (CAST(:k AS text) IS NULL OR s.kind = :k)"""),
            {"ns": namespace, "v": value, "k": kind})}
        if not found:
            found = {r[0]: "cross_reference" for r in conn.execute(text(
                """SELECT DISTINCT entity_id FROM mdm.cross_reference_lookup(:ns, :v)
                    WHERE bound_entity_id IS NOT NULL AND (CAST(:k AS text) IS NULL OR kind = :k)"""),
                {"ns": namespace, "v": value, "k": kind})}
        subject = kind or "relationship"
        if not found:
            raise ContextError(f"No {kind or 'entity'} carries {namespace}:{value}.",
                               f"{PROG} {kind or 'company'} --search \"<name>\"")
        if len(found) > 1:
            names = self._names(conn, list(found))
            listed = "; ".join(f"{names.get(i, {}).get('name') or '(no name)'} ({i})" for i in sorted(found))
            raise ContextError(
                f"{namespace}:{value} is carried by {len(found)} entities: {listed}. "
                + ("It is a cross-reference id, lookup only: sharing it does not make them one entity."
                   if "cross_reference" in found.values() else "Pick one by its id."),
                f"{PROG} {subject} {sorted(found)[0]}",
            )
        return next(iter(found))

    @staticmethod
    def _names(conn, ids: list[str]) -> dict:
        from sqlalchemy import text

        if not ids:
            return {}
        return {r[0]: {"name": r[1], "kind": r[2]} for r in conn.execute(text(
            "SELECT object_id, mdm.entity_name(body), kind FROM mdm.current_entity WHERE object_id = ANY(:ids)"),
            {"ids": ids})}

    @staticmethod
    def _generation(conn, args) -> int | None:
        from sqlalchemy import text

        if args.as_at:
            moment, flag = _time(args.as_at, "--as-at"), "--as-at"
            generation = conn.scalar(text("SELECT max(generation) FROM mdm.batch WHERE created_at <= :t"), {"t": moment})
        elif args.as_of:
            moment, flag = _time(args.as_of, "--as-of"), "--as-of"
            generation = conn.scalar(text(
                "SELECT max(generation) FROM mdm.batch WHERE (effects ->> 'as_of')::timestamptz <= :t"), {"t": moment})
        else:
            return None
        if generation is None:
            raise ContextError(f"MDM holds nothing {flag} {args.as_at or args.as_of}.", f"{PROG} {args.subject} {args.key}")
        return generation

    def entity(self, args: argparse.Namespace) -> dict:
        from sqlalchemy import text

        from edgar_warehouse.mdm.clean.consumer import ContractReader

        with self.engine.connect() as conn:
            entity_id = self._resolve(conn, args.subject, args.key)
            generation = self._generation(conn, args)
        try:
            read = ContractReader(self.engine).entity(entity_id, generation=generation)
        except KeyError:
            raise ContextError(
                f"No {args.subject} {entity_id} in MDM" + (" at that time." if generation else "."),
                f"{PROG} {args.subject} --search \"<name>\"",
            ) from None
        body = read["identity"]
        if body.get("kind") != args.subject:
            raise ContextError(f"{entity_id} is a {body.get('kind')}, not a {args.subject}.", f"{PROG} {body.get('kind')} {entity_id}")
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
        canonical = read["canonical_id"]
        with self.engine.connect() as conn:
            subjects = body.get("subjects", [])
            records = conn.execute(text(
                """SELECT source_code, record_key, coalesce(reading -> 'cross_references', '{}'::jsonb)
                     FROM mdm.stage_record WHERE subject = ANY(:s) ORDER BY source_code, record_key"""),
                {"s": subjects}).all()
            recorded_at = conn.scalar(text("SELECT created_at FROM mdm.batch WHERE generation = :g"),
                                      {"g": read["projection"]["generation"]})
            related, related_count, cut = ([], 0, False) if args.as_at else self._walk(
                conn, canonical, 1, self._at(args), "", RELATED_INLINE)
        cross_references: dict[str, set] = {}
        sources: dict[str, list] = {}
        for source_code, record_key, crossed in records:
            sources.setdefault(source_code, []).append(record_key)
            for namespace, value in crossed.items():
                cross_references.setdefault(namespace, set()).add(value)
        projection = read["projection"]
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
            "sources": sources if full else sorted(sources),
            "trust": {
                "generation": projection["generation"],
                "recorded_at": recorded_at.isoformat() if recorded_at else None,
                "as_of": projection.get("as_of"),
                "policy_digest": projection.get("policy_digest"),
                "run_id": projection.get("origin_run_id"),
                "status": body.get("status"),
            },
        }
        if canonical != entity_id:
            answer["merged_from"] = entity_id
        if args.as_at:
            answer["related_note"] = "Relationships are not read at a past recording time; ask without --as-at, or with --as-of."
        else:
            answer["related"] = [_brief_link(link) for link in related]
            answer["related_count"] = f"{related_count}+" if cut else related_count
        answer["truncated"] = False
        answer["next_page"] = None
        answer["next_step"] = f"{PROG} relationship {canonical}" + (" --detail full" if not full else "")
        command = f"{PROG} {args.subject} {args.key}" + "".join(
            f" --{flag} {value}" for flag, value in (("as-of", args.as_of), ("as-at", args.as_at), ("detail", args.detail)) if value)
        return fit(answer, "fields", _offset(args.page), command)

    def search(self, args: argparse.Namespace) -> dict:
        from sqlalchemy import text

        if args.as_of or args.as_at:
            raise ContextError("Search reads current names; look the entity up by its id with --as-of or --as-at.",
                               f"{PROG} {args.subject} --search \"{args.search}\"")
        if not 1 <= args.limit <= SEARCH_MAX:
            raise ContextError(f"--limit is 1 to {SEARCH_MAX}.", f"{PROG} {args.subject} --search \"{args.search}\" --limit 5")
        words = args.search.strip()
        if not words:
            raise ContextError("--search needs some words.", f"{PROG} {args.subject} --search \"<words>\"")
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM mdm.entity_search(:w, :k, :n)"),
                                {"w": words, "k": args.subject, "n": args.limit}).mappings().all()
        matches = [{"name": r["name"], "kind": r["kind"], "entity_id": r["entity_id"], "status": r["status"],
                    "matched_by": r["matched_by"]} for r in rows]
        if not matches:
            print(json.dumps({"event": "context-search-miss", "kind": args.subject, "words": words}), file=sys.stderr)
        answer = {
            "search": words,
            "kind": args.subject,
            "definition": definitions().get("kinds", {}).get(args.subject, ""),
            "matches": matches,
            "truncated": False,
            "next_page": None,
            "next_step": (f"{PROG} {args.subject} <entity_id>" if matches
                          else f"No {args.subject} name matches. Try fewer words, or {PROG} {args.subject} <namespace>:<value>."),
        }
        return fit(answer, "matches", 0, f"{PROG} {args.subject} --search \"{words}\" --limit {args.limit}")

    # -- Relationships -------------------------------------------------------

    @staticmethod
    def _at(args) -> datetime:
        return _time(args.as_of, "--as-of") if args.as_of else datetime.now(UTC)

    def _walk(self, conn, start: str, hops: int, at: datetime, relationship_type: str, cap: int):
        """The links around one entity, both directions, up to `hops` away.

        One query per hop finds the links through the link-start and link-end
        indexes. A stated link counts when one of its periods holds at `at`; a
        derived one always counts. Returns (links, count, cut).
        """
        from sqlalchemy import text

        seen_entities, seen_links, links = {start}, set(), []
        frontier, cut = [start], False
        for depth in range(1, hops + 1):
            if not frontier:
                break
            rows = conn.execute(text(
                """SELECT object_id, body FROM mdm.current_record
                    WHERE object_type = 'relationship'
                      AND (body ->> 'source_id' = ANY(:ids) OR body ->> 'target_id' = ANY(:ids))
                      AND coalesce(body -> 'retired', 'false'::jsonb) = 'false'::jsonb
                      AND (coalesce((body ->> 'derived')::boolean, false) OR mdm.relationship_holds(body, :at))
                      AND (:t = '' OR body ->> 'type' = :t)
                    ORDER BY object_id LIMIT :cap"""),
                {"ids": frontier, "at": at, "t": relationship_type, "cap": cap - len(links) + 1}).all()
            following = []
            for relationship_id, body in rows:
                if relationship_id in seen_links:
                    continue
                if len(links) >= cap:
                    cut = True
                    break
                seen_links.add(relationship_id)
                links.append({"depth": depth, "relationship_id": relationship_id, "body": body})
                for end in (body.get("source_id"), body.get("target_id")):
                    if end and end not in seen_entities:
                        seen_entities.add(end)
                        following.append(end)
            if cut:
                break
            frontier = following
        names = self._names(conn, sorted({e for link in links for e in (link["body"].get("source_id"), link["body"].get("target_id")) if e}))
        for link in links:
            body = link["body"]
            link["from"] = {**names.get(body.get("source_id"), {"name": None, "kind": None}), "entity_id": body.get("source_id")}
            link["to"] = {**names.get(body.get("target_id"), {"name": None, "kind": None}), "entity_id": body.get("target_id")}
            link["period"] = _period(body, at)
        links.sort(key=lambda l: (l["depth"], l["body"].get("type", ""), l["from"]["name"] or "", l["to"]["name"] or "", l["relationship_id"]))
        return links, len(links), cut

    def relationships(self, args: argparse.Namespace) -> dict:
        if args.as_at:
            raise ContextError(
                "Relationships are not read at a past recording time yet. --as-of reads what held at a business "
                "time; the view mdm.relationship_context lists every period.",
                f"{PROG} relationship {args.key or '<entity>'} --as-of {args.as_at}",
            )
        if not args.key:
            raise ContextError("Name the entity: its id or <namespace>:<value>.", f"{PROG} relationship <entity_id>")
        if not 1 <= args.hops <= MAX_HOPS:
            raise ContextError(f"--hops is 1 to {MAX_HOPS}.", f"{PROG} relationship {args.key} --hops 1")
        at = self._at(args)
        with self.engine.connect() as conn:
            entity_id = self._resolve(conn, None, args.key)
            names = self._names(conn, [entity_id])
            if entity_id not in names:
                raise ContextError(f"No entity {entity_id} in MDM.", f"{PROG} company --search \"<name>\"")
            links, count, cut = self._walk(conn, entity_id, args.hops, at, args.relationship_type, WALK_CAP)
        types = definitions().get("relationships", {})
        full = args.detail == "full"
        related = [_full_link(link) if full else _brief_link(link) for link in links]
        answer = {
            "name": names[entity_id]["name"],
            "kind": names[entity_id]["kind"],
            "key": args.key,
            "entity_id": entity_id,
            "at": at.isoformat(),
            "hops": args.hops,
            "definitions": {t: types.get(t, "") for t in sorted({link["body"].get("type") for link in links})},
            "related": related,
            "related_count": f"{count}+" if cut else count,
            "truncated": cut,
            "next_page": None,
            "next_step": (f"Over {WALK_CAP} links: narrow it with --type <TYPE> or --hops 1, or query mdm.relationship_context."
                          if cut else f"{PROG} <kind> <entity_id> for any entity listed"),
        }
        command = f"{PROG} relationship {args.key} --hops {args.hops}" + "".join(
            f" --{flag} {value}" for flag, value in (("type", args.relationship_type), ("as-of", args.as_of), ("detail", args.detail)) if value)
        return fit(answer, "related", _offset(args.page), command)


def _name(body: dict):
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
    return item


def _full_link(link: dict) -> dict:
    body, period = link["body"], link["period"] or {}
    return {**_brief_link(link), "relationship_id": link["relationship_id"],
            "from": link["from"], "to": link["to"], "scope": body.get("scope"),
            "valid_from": period.get("valid_from"), "valid_to": period.get("valid_to"),
            "valid_from_basis": period.get("valid_from_basis"), "last_seen": body.get("last_seen")}
