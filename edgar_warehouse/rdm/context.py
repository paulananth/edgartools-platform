"""`edgar-warehouse context <code_set>`: reference data for agents (profiling ticket 05, RDM part).

A code is looked up by its code set and code, or found with `--search` in its
labels and synonyms, through `rdm.code_context` and `rdm.code_search`. Each
answer says what the code means, where it sits in the hierarchy, which code
sets it maps to, and the version's pin, in JSON of at most 8 KB (the command's
own rules: `edgar_warehouse/context.py`).

Time: a version is the published one from its `valid_from` to its `valid_to`
(publish and replace times). `--as-at` reads the version current at that time
as it stood then. `--as-of` reads the same version and also checks the code's
own business dates (`code_valid_from`..`code_valid_to`).
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import date, datetime

from sqlalchemy import text

from edgar_warehouse.context import PROG, SEARCH_MAX, ContextError, fit, page_offset, parse_time

# Synonyms shown inline; the count says when there are more.
SYNONYMS_INLINE = 20
VIEW = "rdm.code_context WHERE code_set = '<code set>' AND code = '<code>'"


def _iso(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _flags(args) -> str:
    return "".join(f" --{flag} {shlex.quote(value)}" for flag, value in (("as-of", args.as_of), ("as-at", args.as_at)) if value)


class CodeContext:
    """Code sets, read from RDM through a read-only connection."""

    def __init__(self, engine):
        self.engine = engine

    def answer(self, args: argparse.Namespace) -> dict:
        command = f"{PROG} {args.subject} {shlex.quote(args.key) if args.key else ''}".strip()
        if args.as_of and args.as_at:
            raise ContextError("Give --as-of or --as-at, not both.", f"{command} --as-of <time>")
        if args.hops != 1 or args.relationship_type:
            raise ContextError("--hops and --type are for relationships; a code set has none.", command)
        with self.engine.connect() as conn:
            info = conn.execute(text("SELECT code_set, name, definition FROM rdm.code_set WHERE code_set = :s"),
                                {"s": args.subject}).mappings().first()
            if info is None:
                from edgar_warehouse.mdm.clean.evidence import KINDS

                raise ContextError(f"{args.subject!r} is neither a master kind ({', '.join(sorted(KINDS))}), "
                                   "'relationship', nor a code set RDM holds.", "edgar-warehouse rdm list")
            if args.search is not None:
                if args.key:
                    raise ContextError("Give a code or --search, not both.", f"{PROG} {args.subject} --search {shlex.quote(args.search)}")
                return self._search(conn, args, dict(info))
            if not args.key:
                raise ContextError(f"Name a code of {args.subject}, or search its labels.", f"{PROG} {args.subject} --search \"<words>\"")
            return self._code(conn, args, dict(info))

    @staticmethod
    def _version(conn, args) -> dict:
        """The version current at the time a flag names (now without one), and
        that time; a version retired before then, with no successor, is none."""
        flag, value = ("--as-of", args.as_of) if args.as_of else ("--as-at", args.as_at) if args.as_at else (None, None)
        moment = parse_time(value, flag, f"{PROG} {args.subject} {args.key or ''}".strip()) if value else None
        row = conn.execute(text(
            "SELECT version, sha256, valid_from, valid_to, status, approved_by, approved_at FROM rdm.code_set_version "
            "WHERE code_set = :s AND status IN ('published','retired') "
            "AND valid_from <= coalesce(:t, now()) AND (valid_to IS NULL OR valid_to > coalesce(:t, now())) "
            "ORDER BY valid_from DESC LIMIT 1"), {"s": args.subject, "t": moment}).mappings().first()
        if row is None:
            when = f" {flag} {value}" if value else " now"
            raise ContextError(f"{args.subject} has no published version{when}.", f"edgar-warehouse rdm describe {args.subject}")
        trust = {"source": "rdm", **{k: _iso(v) for k, v in row.items()}}
        if moment is not None:  # as it stood then: not yet replaced or retired
            trust.update(valid_to=None, status="published", read_at=moment.isoformat())
        return {"version": row["version"], "moment": moment, "trust": trust}

    def _code(self, conn, args, info: dict) -> dict:
        picked = self._version(conn, args)
        row = conn.execute(text("SELECT * FROM rdm.code_context WHERE code_set = :s AND version = :v AND code = :c"),
                           {"s": args.subject, "v": picked["version"], "c": args.key}).mappings().first()
        if row is None:
            raise ContextError(f"{args.subject} {picked['version']} has no code {args.key!r}.",
                               f"{PROG} {args.subject} --search {shlex.quote(args.key)}")
        if args.as_of and picked["moment"] is not None:
            day = picked["moment"].date()
            if (row["code_valid_from"] and day < row["code_valid_from"]) or (row["code_valid_to"] and day > row["code_valid_to"]):
                raise ContextError(f"{args.subject} {args.key} was not valid on {day} (valid "
                                   f"{_iso(row['code_valid_from']) or '…'} to {_iso(row['code_valid_to']) or '…'}).",
                                   f"{PROG} {args.subject} {shlex.quote(args.key)}")
        hints, usage = {}, []
        for r in conn.execute(text("SELECT kind, text FROM rdm.code_set_hint WHERE code_set = :s AND version = :v "
                                   "ORDER BY kind, ordinal"), {"s": args.subject, "v": picked["version"]}):
            hints.setdefault(r.kind, []).append(r.text)
        if args.detail == "full":
            usage = [dict(r) for r in conn.execute(text(
                "SELECT store, object, field, match, note FROM rdm.code_set_usage WHERE code_set = :s AND version = :v "
                "ORDER BY store, object, field"), {"s": args.subject, "v": picked["version"]}).mappings()]
        synonyms = list(row["synonyms"])
        answer = {
            "name": row["label"],
            "kind": "code",
            "code_set": args.subject,
            "key": args.key,
            "definition": row["definition"],
            "code_set_definition": info["definition"],
            "path": row["label_path"],
            "path_codes": row["path"],
            "level": row["level"],
            "depth": row["depth"],
            "parent_code": row["parent_code"],
            "code_status": row["code_status"],
            "code_valid_from": _iso(row["code_valid_from"]),
            "code_valid_to": _iso(row["code_valid_to"]),
            "synonyms": synonyms[:SYNONYMS_INLINE],
            "crosswalk": row["crosswalk"],
            "meaning": hints.get("meaning", []),
            "trust": picked["trust"],
            "truncated": False,
            "next_page": None,
            "next_step": f"edgar-warehouse rdm describe {args.subject}",
        }
        if len(synonyms) > SYNONYMS_INLINE:
            answer["synonyms_count"] = len(synonyms)
        if row["invalid_reason"]:
            answer["invalid_reason"] = row["invalid_reason"]
        if args.detail == "full":
            answer["used_in"] = usage
        command = f"{PROG} {args.subject} {shlex.quote(args.key)}{_flags(args)}" + (" --detail full" if args.detail == "full" else "")
        return fit(answer, "crosswalk", page_offset(args.page), command, VIEW)

    def _search(self, conn, args, info: dict) -> dict:
        if not 1 <= args.limit <= SEARCH_MAX:
            raise ContextError(f"--limit is 1 to {SEARCH_MAX}.", f"{PROG} {args.subject} --search {shlex.quote(args.search)} --limit 5")
        words = args.search.strip()
        if not words:
            raise ContextError("--search needs some words.", f"{PROG} {args.subject} --search \"<words>\"")
        picked = self._version(conn, args)
        rows = conn.execute(text("SELECT * FROM rdm.code_search(:w, :s, :v, :n)"),
                            {"w": words, "s": args.subject, "v": picked["version"], "n": args.limit}).mappings().all()
        matches = [{"name": r["label"], "code": r["code"], "path": r["label_path"], "matched_by": r["matched_by"]}
                   for r in rows]
        if not matches:
            print(json.dumps({"event": "context-search-miss", "code_set": args.subject, "words": words}), file=sys.stderr)
        answer = {
            "search": words,
            "code_set": args.subject,
            "definition": info["definition"],
            "matches": matches,
            "trust": picked["trust"],
            "truncated": False,
            "next_page": None,
            "next_step": (f"{PROG} {args.subject} <code>" if matches
                          else f"No {args.subject} label matches. Try fewer words, or edgar-warehouse rdm describe {args.subject}."),
        }
        return fit(answer, "matches", page_offset(args.page),
                   f"{PROG} {args.subject} --search {shlex.quote(words)} --limit {args.limit}{_flags(args)}", VIEW)
