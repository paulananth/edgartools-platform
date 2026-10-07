"""Code set versions: drafted, approved in the operator's words, published once.

A version's canonical form is UTF-8 JSON Lines, one object per code sorted by
code, holding everything a consumer reads of it: the code's own columns, the
name of its level, its labels and its crosswalk rows (docs/specs/rdm/spec.md
§4). Its sha256 is the pin a consumer records as {code_set, version, sha256}.
A version's usage and hints guide agents; they are frozen with it but are not
in the pin.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked

CODE_COLUMNS = ("code", "label", "definition", "parent_code", "valid_from", "valid_to", "status", "invalid_reason")
# A crosswalk target RDM does not hold (an outside standard) carries this version.
OUTSIDE = "outside"
# An answer for an agent stays within this many bytes of JSON, as `context` does.
DESCRIBE_LIMIT = 8192


def _plain(value):
    return value.isoformat() if isinstance(value, date) else value


# What each list of a draft may hold; a key outside these refuses the draft.
DRAFT_FIELDS = {
    "code_set": {"code_set", "name", "definition", "authority", "steward"},
    "codes": set(CODE_COLUMNS),
    "labels": {"code", "language", "label", "kind", "source"},
    "levels": {"depth", "name", "definition"},
    "crosswalk": {"from_code", "to_set", "to_version", "to_code", "match_type", "evidence"},
    "usage": {"store", "object", "field", "match", "note"},
    "hints": {"kind", "text"},
}


def canonical(codes: list[dict], levels: dict[int, str] | None = None) -> bytes:
    """The canonical bytes of a version's codes (each with `labels` and
    `crosswalk`) and its level names."""
    level = {p["code"]: p["level"] for p in paths(codes, levels or {})}
    lines = []
    for row in sorted(codes, key=lambda r: r["code"]):
        body = {k: _plain(row.get(k)) for k in CODE_COLUMNS}
        body["level"] = level[row["code"]]
        body["labels"] = sorted([l["language"], l["kind"], l["label"]] for l in row.get("labels") or [])
        body["crosswalk"] = sorted([x["to_set"], x["to_version"], x["to_code"], x["match_type"]]
                                   for x in row.get("crosswalk") or [])
        lines.append(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return "".join(lines).encode("utf-8")


def sha256(codes: list[dict], levels: dict[int, str] | None = None) -> str:
    return hashlib.sha256(canonical(codes, levels)).hexdigest()


def _escape(code: str) -> str:
    return code.replace("\\", "\\\\").replace("/", "\\/")


def paths(codes: list[dict], levels: dict[int, str]) -> list[dict]:
    """Each code's path, label path, level and depth, from its one parent.
    A parent missing from the version, or a cycle, refuses the version."""
    by_code = {row["code"]: row for row in codes}
    found = []
    for row in codes:
        chain, seen = [row], {row["code"]}
        while chain[-1].get("parent_code") is not None:
            parent = by_code.get(chain[-1]["parent_code"])
            if parent is None:
                raise Blocked(f"Code {chain[-1]['code']!r} names a parent the version lacks")
            if parent["code"] in seen:
                raise Blocked(f"The hierarchy has a cycle through code {parent['code']!r}")
            seen.add(parent["code"])
            chain.append(parent)
        chain.reverse()
        found.append({"code": row["code"], "path": "/".join(_escape(r["code"]) for r in chain),
                      "label_path": " > ".join(r["label"] for r in chain),
                      "level": levels.get(len(chain)), "depth": len(chain)})
    return found


def read_published(folder: Path, code_set: str, version: str, pin: str) -> list[dict]:
    """A published version's codes from its files, refused unless they are the pinned bytes."""
    data = (Path(folder) / code_set / version / "canonical.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != pin:
        raise Blocked(f"Reference data {code_set} {version} differs from its pinned sha256")
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


class RDM:
    """The rdm database, through the runtime login."""

    def __init__(self, engine):
        self.engine = engine

    def draft(self, code_set: dict, version: str, codes: list[dict], *, created_by: str,
              evidence: dict | None = None, supersedes: str | None = None, labels: list[dict] = (),
              levels: list[dict] = (), crosswalk: list[dict] = (), usage: list[dict] = (),
              hints: list[dict] = ()) -> dict:
        """Write a new draft version: its codes, labels, level names and crosswalk
        rows, and the semantic layer an agent reads: where its values are used and
        hints in plain words."""
        parts = {"codes": codes, "labels": labels, "levels": levels, "crosswalk": crosswalk, "usage": usage,
                 "hints": hints}
        if not isinstance(code_set, dict) or set(code_set) - DRAFT_FIELDS["code_set"] or "code_set" not in code_set:
            raise Blocked(f"code_set is an object with code_set and only {sorted(DRAFT_FIELDS['code_set'])}")
        for name, rows in parts.items():
            for row in rows:
                if not isinstance(row, dict) or set(row) - DRAFT_FIELDS[name]:
                    raise Blocked(f"Each of {name} is an object with only {sorted(DRAFT_FIELDS[name])}: {row!r}")
        named = {(l["code"], l.get("language", "en")): l["label"] for l in labels if l.get("kind") == "preferred"}
        for row in codes:
            if named.get((row["code"], "en"), row["label"]) != row["label"]:
                raise Blocked(f"Code {row['code']!r}: its preferred English label differs from its label")
        labels = [*labels, *({"code": r["code"], "label": r["label"], "kind": "preferred", "source": "code label"}
                             for r in codes if (r["code"], "en") not in named)]
        key = code_set["code_set"]
        from edgar_warehouse.mdm.clean.evidence import KINDS

        if key in KINDS or key == "relationship":  # `context <subject>` reads these from MDM
            raise Blocked(f"{key!r} names a master kind or relationships; give the code set another id")
        given = {**{k: "" for k in DRAFT_FIELDS["code_set"]}, **{k: v for k, v in code_set.items() if v is not None}}
        with self.engine.begin() as conn:
            held = conn.execute(text("SELECT code_set,name,definition,authority,steward FROM rdm.code_set "
                                     "WHERE code_set=:s"), {"s": key}).mappings().first()
            if held is None:
                if not str(given["name"]).strip():
                    raise Blocked(f"Code set {key} is new: give it a name in plain words")
                if not conn.execute(text("INSERT INTO rdm.code_set(code_set,name,definition,authority,steward) "
                                         "VALUES(:code_set,:name,:definition,:authority,:steward) ON CONFLICT DO NOTHING"),
                                    given).rowcount:
                    raise Blocked(f"Code set {key} was drafted by someone else just now; draft again")
            elif set(code_set) != {"code_set"} and {k: given[k] for k in held} != dict(held):
                raise Blocked(f"Code set {key} is already held with other words; a code set's words never change "
                              "(name only code_set, and put changed meaning in the version's hints)")
            conn.execute(text("INSERT INTO rdm.code_set_version(code_set,version,supersedes,created_by,evidence) "
                              "VALUES(:s,:v,:p,:c,CAST(:e AS jsonb))"),
                         {"s": key, "v": version, "p": supersedes, "c": created_by, "e": json.dumps(evidence or {})})
            scope = {"code_set": key, "version": version}
            if codes:
                conn.execute(text("INSERT INTO rdm.code(code_set,version,code,label,definition,parent_code,valid_from,"
                                  "valid_to,status,invalid_reason) VALUES(:code_set,:version,:code,:label,:definition,"
                                  ":parent_code,:valid_from,:valid_to,:status,:invalid_reason)"),
                             [{"definition": "", "parent_code": None, "valid_from": None, "valid_to": None,
                               "status": "valid", "invalid_reason": None, **row, **scope} for row in codes])
            if labels:
                conn.execute(text("INSERT INTO rdm.code_label(code_set,version,code,language,label,kind,source) "
                                  "VALUES(:code_set,:version,:code,:language,:label,:kind,:source)"),
                             [{"language": "en", "source": "", **row, **scope} for row in labels])
            if levels:
                conn.execute(text("INSERT INTO rdm.level(code_set,version,depth,name,definition) "
                                  "VALUES(:code_set,:version,:depth,:name,:definition)"),
                             [{"definition": "", **row, **scope} for row in levels])
            if crosswalk:
                conn.execute(text("INSERT INTO rdm.crosswalk_row(from_set,from_version,from_code,to_set,to_version,"
                                  "to_code,match_type,evidence) VALUES(:s,:v,:from_code,:to_set,:to_version,:to_code,"
                                  ":match_type,CAST(:evidence AS jsonb))"),
                             [{"s": key, "v": version, **row, "evidence": json.dumps(row.get("evidence") or {})}
                              for row in crosswalk])
            if usage:
                conn.execute(text("INSERT INTO rdm.code_set_usage(code_set,version,store,object,field,match,note) "
                                  "VALUES(:code_set,:version,:store,:object,:field,:match,:note)"),
                             [{"match": "exact", "note": "", **row, **scope} for row in usage])
            if hints:
                conn.execute(text("INSERT INTO rdm.code_set_hint(code_set,version,kind,ordinal,text) "
                                  "VALUES(:code_set,:version,:kind,:ordinal,:text)"),
                             [{**row, **scope, "ordinal": n} for kind in {h["kind"] for h in hints}
                              for n, row in enumerate((h for h in hints if h["kind"] == kind), 1)])
            return self._version(conn, key, version)

    def describe(self, code_set: str, version: str | None = None, samples: int = 10) -> dict:
        """What an agent needs before using a code set, in at most DESCRIBE_LIMIT
        bytes: its definition, the version (the current published one unless
        named) and its pin, where its values live and how to compare them, the
        hints, counts, the code sets it maps to, and a few codes."""
        with self.engine.connect() as conn:
            info = conn.execute(text("SELECT code_set,name,definition,authority,steward FROM rdm.code_set "
                                     "WHERE code_set=:s"), {"s": code_set}).mappings().first()
            if info is None:
                raise Blocked(f"Unknown code set {code_set}; `rdm list` names them all")
            version = version or conn.scalar(text(
                "SELECT version FROM rdm.code_set_version WHERE code_set=:s ORDER BY (status='published' AND valid_to "
                "IS NULL) DESC, created_at DESC LIMIT 1"), {"s": code_set})
            if version is None:
                raise Blocked(f"Code set {code_set} has no version yet")
            row = self._version(conn, code_set, version)
            scope = {"s": code_set, "v": version}
            usage = [dict(r) for r in conn.execute(text(
                "SELECT store,object,field,match,note FROM rdm.code_set_usage WHERE code_set=:s AND version=:v "
                "ORDER BY store,object,field"), scope).mappings()]
            hints: dict[str, list] = {}
            for r in conn.execute(text("SELECT kind,text FROM rdm.code_set_hint WHERE code_set=:s AND version=:v "
                                       "ORDER BY kind,ordinal"), scope):
                hints.setdefault(r.kind, []).append(r.text)
            counts = dict(conn.execute(text(
                "SELECT count(*) AS codes, count(*) FILTER (WHERE status='invalid') AS invalid, "
                "count(parent_code) AS with_parent FROM rdm.code WHERE code_set=:s AND version=:v"), scope).mappings().one())
            maps_to = [dict(r) for r in conn.execute(text(
                "SELECT to_set,to_version,match_type,count(*) AS rows FROM rdm.crosswalk_row WHERE from_set=:s AND "
                "from_version=:v GROUP BY 1,2,3 ORDER BY 1,2,3"), scope).mappings()]
            some = [dict(r) for r in conn.execute(text(
                "SELECT code,label,parent_code FROM rdm.code WHERE code_set=:s AND version=:v ORDER BY code LIMIT :n"),
                {**scope, "n": samples}).mappings()]
        answer = {**dict(info), "version": version, "status": row["status"], "sha256": row["sha256"],
                  "valid_from": row["valid_from"], "valid_to": row["valid_to"], "approved_by": row["approved_by"],
                  "used_in": usage, "hints": hints, "counts": counts, "maps_to": maps_to, "sample_codes": some}
        # Over the limit, drop sample codes first, then the longest list's last
        # entries, and say so; never a cut string.
        def size():
            return len(json.dumps(answer, default=str, ensure_ascii=False).encode())

        while size() > DESCRIBE_LIMIT:
            answer["truncated"] = True
            lists = [answer["sample_codes"], answer["used_in"], answer["maps_to"], *answer["hints"].values()]
            longest = max(lists, key=lambda l: len(json.dumps(l, default=str)))
            if not longest:
                raise Blocked(f"Code set {code_set}'s own words exceed {DESCRIBE_LIMIT} bytes")
            longest.pop()
        return answer

    def approve(self, code_set: str, version: str, *, by: str, words: str) -> dict:
        """Record the operator's approval of a draft, in their name and exact words."""
        with self.engine.begin() as conn:
            done = conn.execute(text("UPDATE rdm.code_set_version SET status='approved', approved_by=:b, "
                                     "approved_words=:w WHERE code_set=:s AND version=:v AND status='draft'"),
                                {"s": code_set, "v": version, "b": by, "w": words}).rowcount
            if done != 1:
                raise Blocked(f"{code_set} {version} is not a draft")
            return self._version(conn, code_set, version)

    def publish(self, code_set: str, version: str, *, out: Path) -> dict:
        """Publish an approved version: write its paths and sha256, close the
        version it replaces, and write its files under `out` for consumers,
        before the commit (a failed write publishes nothing)."""
        with self.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('rdm.publish:' || :s))"), {"s": code_set})
            row = conn.execute(text("SELECT status,supersedes FROM rdm.code_set_version WHERE code_set=:s AND version=:v "
                                    "FOR UPDATE"), {"s": code_set, "v": version}).mappings().first()
            if row is None or row["status"] != "approved":
                raise Blocked(f"{code_set} {version} is not an approved version")
            current = conn.scalar(text("SELECT version FROM rdm.code_set_version WHERE code_set=:s AND "
                                       "status='published' AND valid_to IS NULL FOR UPDATE"), {"s": code_set})
            replaced = conn.scalar(text(  # the newest version ever published, current or retired
                "SELECT version FROM rdm.code_set_version WHERE code_set=:s AND status IN ('published','retired') "
                "ORDER BY valid_from DESC LIMIT 1"), {"s": code_set})
            if replaced != row["supersedes"]:
                raise Blocked(f"{code_set} {version} must supersede {replaced or 'nothing'}, the version it replaces")
            codes, levels = self._content(conn, code_set, version)
            found = paths(codes, levels)
            if found:
                conn.execute(text("INSERT INTO rdm.code_path(code_set,version,code,path,label_path,level,depth) "
                                  "VALUES(:s,:v,:code,:path,:label_path,:level,:depth)"),
                             [{"s": code_set, "v": version, **p} for p in found])
            digest = sha256(codes, levels)
            now = conn.scalar(text("SELECT clock_timestamp()"))
            if current:
                conn.execute(text("UPDATE rdm.code_set_version SET valid_to=:t WHERE code_set=:s AND version=:v"),
                             {"t": now, "s": code_set, "v": current})
            conn.execute(text("UPDATE rdm.code_set_version SET status='published', sha256=:h, valid_from=:t "
                              "WHERE code_set=:s AND version=:v"), {"h": digest, "t": now, "s": code_set, "v": version})
            published = self._version(conn, code_set, version)
            self._write(Path(out) / code_set / version, codes, levels, found, published)
        return {"code_set": code_set, "version": version, "sha256": digest, "codes": len(codes),
                "superseded": current}

    def retire(self, code_set: str, version: str) -> dict:
        """Retire a published version on the operator's word: kept, never
        deleted, so every pin stays resolvable; its successor supersedes it."""
        with self.engine.begin() as conn:
            done = conn.execute(text("UPDATE rdm.code_set_version SET status='retired' WHERE code_set=:s "
                                     "AND version=:v AND status='published'"), {"s": code_set, "v": version}).rowcount
            if done != 1:
                raise Blocked(f"{code_set} {version} is not a published version")
            return self._version(conn, code_set, version)

    def verify(self, code_set: str, version: str) -> dict:
        """Whether a published version's stored sha256 is its rows' canonical sha256."""
        with self.engine.connect() as conn:
            row = self._version(conn, code_set, version)
            codes, levels = self._content(conn, code_set, version)
        found = sha256(codes, levels)
        return {"code_set": code_set, "version": version, "stored": row["sha256"], "computed": found,
                "matches": row["sha256"] == found}

    @staticmethod
    def _write(folder: Path, codes: list[dict], levels: dict[int, str], found: list[dict], version: dict) -> None:
        """The version as silver-shaped JSON Lines until the silver writer exists (spec §6)."""
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "canonical.jsonl").write_bytes(canonical(codes, levels))
        scope = {"code_set": version["code_set"], "version": version["version"]}
        by_code = {p["code"]: p for p in found}

        def lines(rows):
            return "".join(json.dumps({**scope, **r}, sort_keys=True, ensure_ascii=False, default=_plain) + "\n" for r in rows)

        ordered = sorted(codes, key=lambda r: r["code"])
        (folder / "rdm_code.jsonl").write_text(lines(
            {**{k: _plain(c[k]) for k in CODE_COLUMNS}, **{k: v for k, v in by_code[c["code"]].items() if k != "code"}}
            for c in ordered), encoding="utf-8")
        (folder / "rdm_code_label.jsonl").write_text(lines(
            {"code": c["code"], **l} for c in ordered for l in sorted(c["labels"], key=lambda l: (l["language"], l["label"]))),
            encoding="utf-8")
        (folder / "rdm_crosswalk.jsonl").write_text(lines(
            {"from_code": c["code"], **x} for c in ordered
            for x in sorted(c["crosswalk"], key=lambda x: (x["to_set"], x["to_version"], x["to_code"]))), encoding="utf-8")
        (folder / "pin.json").write_text(json.dumps(
            {**scope, "sha256": version["sha256"]}, sort_keys=True) + "\n", encoding="utf-8")

    def code_sets(self) -> list[dict]:
        """Every code set, with its current published version and its newest version."""
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(
                "SELECT s.code_set, s.name, s.definition, s.authority, s.steward, "
                "p.version AS published_version, p.sha256 AS published_sha256, "
                "n.version AS newest_version, n.status AS newest_status "
                "FROM rdm.code_set s "
                "LEFT JOIN rdm.code_set_version p ON p.code_set = s.code_set AND p.status = 'published' AND p.valid_to IS NULL "
                "LEFT JOIN LATERAL (SELECT version, status FROM rdm.code_set_version v WHERE v.code_set = s.code_set "
                "ORDER BY created_at DESC LIMIT 1) n ON true ORDER BY s.code_set")).mappings()]

    def codes(self, code_set: str, version: str) -> list[dict]:
        with self.engine.connect() as conn:
            return self._content(conn, code_set, version)[0]

    def version(self, code_set: str, version: str) -> dict:
        with self.engine.connect() as conn:
            return self._version(conn, code_set, version)

    def diff(self, code_set: str, old: str, new: str) -> dict:
        """What changed between two versions: codes added, removed, relabelled and moved."""
        before = {r["code"]: r for r in self.codes(code_set, old)}
        after = {r["code"]: r for r in self.codes(code_set, new)}
        both = sorted(before.keys() & after.keys())
        return {"code_set": code_set, "from": old, "to": new,
                "added": sorted(after.keys() - before.keys()),
                "removed": sorted(before.keys() - after.keys()),
                "relabelled": [{"code": c, "from": before[c]["label"], "to": after[c]["label"]}
                               for c in both if before[c]["label"] != after[c]["label"]],
                "moved": [{"code": c, "from": before[c]["parent_code"], "to": after[c]["parent_code"]}
                          for c in both if before[c]["parent_code"] != after[c]["parent_code"]]}

    @staticmethod
    def _version(conn, code_set: str, version: str) -> dict:
        row = conn.execute(text("SELECT * FROM rdm.code_set_version WHERE code_set=:s AND version=:v"),
                           {"s": code_set, "v": version}).mappings().first()
        if row is None:
            raise Blocked(f"Unknown reference data version {code_set} {version}")
        return dict(row)

    @staticmethod
    def _content(conn, code_set: str, version: str) -> tuple[list[dict], dict[int, str]]:
        scope = {"s": code_set, "v": version}
        codes = {r["code"]: {**r, "labels": [], "crosswalk": []} for r in conn.execute(text(
            f"SELECT {','.join(CODE_COLUMNS)} FROM rdm.code WHERE code_set=:s AND version=:v ORDER BY code"),
            scope).mappings()}
        for r in conn.execute(text("SELECT code,language,label,kind,source FROM rdm.code_label "
                                   "WHERE code_set=:s AND version=:v"), scope).mappings():
            codes[r["code"]]["labels"].append({k: r[k] for k in ("language", "label", "kind", "source")})
        for r in conn.execute(text("SELECT from_code,to_set,to_version,to_code,match_type FROM rdm.crosswalk_row "
                                   "WHERE from_set=:s AND from_version=:v"), scope).mappings():
            codes[r["from_code"]]["crosswalk"].append({k: r[k] for k in ("to_set", "to_version", "to_code", "match_type")})
        levels = {r.depth: r.name for r in conn.execute(text(
            "SELECT depth,name FROM rdm.level WHERE code_set=:s AND version=:v"), scope)}
        return list(codes.values()), levels
