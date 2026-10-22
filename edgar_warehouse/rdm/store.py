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

from sqlalchemy import case, select

from edgar_warehouse.control_contract import Blocked
from .storage import clock, lock_code_set, public_columns, scope, tables, transaction

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
    return _prepare(codes, levels)["canonical"].encode("utf-8")


def sha256(codes: list[dict], levels: dict[int, str] | None = None) -> str:
    return _prepare(codes, levels)["sha256"]


def _prepare(codes, levels=None, *, samples=0, prepare=True):
    """Only transport and date normalization; Rust owns deterministic decisions."""
    import edgar_control

    try:
        return json.loads(edgar_control.prepare_reference_version(json.dumps(
            {"codes": codes, "levels": levels or {}, "samples": samples, "prepare": prepare},
            ensure_ascii=False, allow_nan=False, default=_plain)))
    except ValueError as exc:
        raise Blocked(str(exc)) from exc


def paths(codes: list[dict], levels: dict[int, str]) -> list[dict]:
    """Each code's path, label path, level and depth, from its one parent.
    A parent missing from the version, or a cycle, refuses the version."""
    return _prepare(codes, levels)["paths"]


def read_published(folder: Path, code_set: str, version: str, pin: str) -> list[dict]:
    """A published version's codes from its files, refused unless they are the pinned bytes."""
    data = (Path(folder) / code_set / version / "canonical.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != pin:
        raise Blocked(f"Reference data {code_set} {version} differs from its pinned sha256")
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


class RDM:
    """The rdm database, through the runtime login."""

    def __init__(self, engine, *, reserved_subjects=None):
        self.engine = engine
        if reserved_subjects is None:
            from edgar_warehouse.rules.files import context_subjects

            reserved_subjects = context_subjects()
        self.reserved_subjects = frozenset(reserved_subjects)
        self.tables = tables(engine.dialect.name)

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
        if key in self.reserved_subjects:
            raise Blocked(f"{key!r} names a master kind or relationships; give the code set another id")
        given = {**{k: "" for k in DRAFT_FIELDS["code_set"]}, **{k: v for k, v in code_set.items() if v is not None}}
        with transaction(self.engine) as conn:
            catalog = self.tables["code_set"]
            names = ("code_set", "name", "definition", "authority", "steward")
            held = conn.execute(select(*(catalog.c[n] for n in names)).where(
                scope(conn, catalog, code_set=key))).mappings().first()
            if held is None:
                if not str(given["name"]).strip():
                    raise Blocked(f"Code set {key} is new: give it a name in plain words")
                conn.execute(catalog.insert().values(**given))
            elif set(code_set) != {"code_set"} and {k: given[k] for k in held} != dict(held):
                raise Blocked(f"Code set {key} is already held with other words; a code set's words never change "
                              "(name only code_set, and put changed meaning in the version's hints)")
            conn.execute(self.tables["code_set_version"].insert().values(
                code_set=key, version=version, supersedes=supersedes, created_by=created_by,
                evidence=evidence or {}))
            values = {"code_set": key, "version": version}
            if codes:
                code_table = self.tables["code"]
                conn.execute(code_table.insert(),
                             [{"definition": "", "parent_code": None, "valid_from": None, "valid_to": None,
                               "status": "valid", "invalid_reason": None, **row, **values, "parent_code": None}
                              for row in codes])
                # Insert every code before setting parents: this retains cyclic
                # drafts and permits child-first inputs without deferred FKs.
                parents = [row for row in codes if row.get("parent_code") is not None]
                for start in range(0, len(parents), 1000):
                    found = {r["code"]: r["parent_code"] for r in parents[start:start + 1000]}
                    conn.execute(code_table.update().where(scope(conn, code_table, **values),
                        code_table.c.code.in_(found)).values(parent_code=case(found, value=code_table.c.code)))
            if labels:
                conn.execute(self.tables["code_label"].insert(),
                             [{"language": "en", "source": "", **row, **values} for row in labels])
            if levels:
                conn.execute(self.tables["level"].insert(),
                             [{"definition": "", **row, **values} for row in levels])
            if crosswalk:
                conn.execute(self.tables["crosswalk_row"].insert(),
                             [{"from_set": key, "from_version": version, **row, "evidence": row.get("evidence") or {}}
                              for row in crosswalk])
            if usage:
                conn.execute(self.tables["code_set_usage"].insert(),
                             [{"match": "exact", "note": "", **row, **values} for row in usage])
            if hints:
                conn.execute(self.tables["code_set_hint"].insert(),
                             [{**row, **values, "ordinal": n} for kind in {h["kind"] for h in hints}
                              for n, row in enumerate((h for h in hints if h["kind"] == kind), 1)])
            return self._version(conn, key, version)

    def describe(self, code_set: str, version: str | None = None, samples: int = 10) -> dict:
        """What an agent needs before using a code set, in at most DESCRIBE_LIMIT
        bytes: its definition, the version (the current published one unless
        named) and its pin, where its values live and how to compare them, the
        hints, counts, the code sets it maps to, and a few codes."""
        with transaction(self.engine, write=False) as conn:
            catalog = self.tables["code_set"]
            info = conn.execute(select(*(catalog.c[n] for n in
                ("code_set", "name", "definition", "authority", "steward"))).where(
                    scope(conn, catalog, code_set=code_set))).mappings().first()
            if info is None:
                raise Blocked(f"Unknown code set {code_set}; `rdm list` names them all")
            versions = self.tables["code_set_version"]
            version = version or conn.scalar(select(versions.c.version).where(
                scope(conn, versions, code_set=code_set)).order_by(
                    case(((versions.c.status == "published") & versions.c.valid_to.is_(None), 1), else_=0).desc(),
                    versions.c.created_at.desc(), versions.c.version.desc()).limit(1))
            if version is None:
                raise Blocked(f"Code set {code_set} has no version yet")
            row = self._version(conn, code_set, version)
            values = {"code_set": code_set, "version": version}
            used = self.tables["code_set_usage"]
            usage = [dict(r) for r in conn.execute(select(*(used.c[n] for n in
                ("store", "object", "field", "match", "note"))).where(scope(conn, used, **values)).order_by(
                    used.c.store, used.c.object, used.c.field)).mappings()]
            hints: dict[str, list] = {}
            hint = self.tables["code_set_hint"]
            for r in conn.execute(select(hint.c.kind, hint.c.text).where(scope(conn, hint, **values)).order_by(
                    hint.c.kind, hint.c.ordinal)):
                hints.setdefault(r.kind, []).append(r.text)
            codes, _ = self._content(conn, code_set, version)
            summary = _prepare(codes, samples=samples, prepare=False)
        answer = {**dict(info), "version": version, "status": row["status"], "sha256": row["sha256"],
                  "valid_from": row["valid_from"], "valid_to": row["valid_to"], "approved_by": row["approved_by"],
                  "used_in": usage, "hints": hints, **{name: summary[name] for name in ("counts", "maps_to", "sample_codes")}}
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
        with transaction(self.engine) as conn:
            lock_code_set(conn, code_set)
            table = self.tables["code_set_version"]
            done = conn.execute(table.update().where(scope(conn, table, code_set=code_set, version=version),
                table.c.status == "draft").values(status="approved", approved_by=by, approved_words=words)).rowcount
            if done != 1:
                raise Blocked(f"{code_set} {version} is not a draft")
            return self._version(conn, code_set, version)

    def publish(self, code_set: str, version: str, *, out: Path) -> dict:
        """Publish an approved version: write its paths and sha256, close the
        version it replaces, and write its files under `out` for consumers,
        before the commit (a failed write publishes nothing)."""
        with transaction(self.engine) as conn:
            lock_code_set(conn, code_set)
            table = self.tables["code_set_version"]
            row = conn.execute(select(table.c.status, table.c.supersedes).where(
                scope(conn, table, code_set=code_set, version=version)).with_for_update()).mappings().first()
            if row is None or row["status"] != "approved":
                raise Blocked(f"{code_set} {version} is not an approved version")
            current = conn.scalar(select(table.c.version).where(scope(conn, table, code_set=code_set),
                table.c.status == "published", table.c.valid_to.is_(None)).with_for_update())
            replaced = conn.scalar(select(table.c.version).where(scope(conn, table, code_set=code_set),
                table.c.status.in_(("published", "retired"))).order_by(table.c.valid_from.desc()).limit(1))
            if replaced != row["supersedes"]:
                raise Blocked(f"{code_set} {version} must supersede {replaced or 'nothing'}, the version it replaces")
            codes, levels = self._content(conn, code_set, version)
            prepared = _prepare(codes, levels)
            found = prepared["paths"]
            if found:
                conn.execute(self.tables["code_path"].insert(),
                             [{"code_set": code_set, "version": version, **p} for p in found])
            digest = prepared["sha256"]
            now = clock(conn)
            if current:
                conn.execute(table.update().where(scope(conn, table, code_set=code_set, version=current)).values(valid_to=now))
            conn.execute(table.update().where(scope(conn, table, code_set=code_set, version=version)).values(
                status="published", sha256=digest, valid_from=now))
            published = self._version(conn, code_set, version)
            self._write(Path(out) / code_set / version, codes, levels, found, published)
        return {"code_set": code_set, "version": version, "sha256": digest, "codes": len(codes),
                "superseded": current}

    def retire(self, code_set: str, version: str) -> dict:
        """Retire a published version on the operator's word: kept, never
        deleted, so every pin stays resolvable; its successor supersedes it."""
        with transaction(self.engine) as conn:
            lock_code_set(conn, code_set)
            table = self.tables["code_set_version"]
            done = conn.execute(table.update().where(scope(conn, table, code_set=code_set, version=version),
                table.c.status == "published").values(status="retired")).rowcount
            if done != 1:
                raise Blocked(f"{code_set} {version} is not a published version")
            return self._version(conn, code_set, version)

    def verify(self, code_set: str, version: str) -> dict:
        """Whether a published version's stored sha256 is its rows' canonical sha256."""
        with transaction(self.engine, write=False) as conn:
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
        with transaction(self.engine, write=False) as conn:
            catalog, version = self.tables["code_set"], self.tables["code_set_version"]
            # Catalog enumeration is intentional. Correlated version probes use
            # each code set's index; no per-code or per-version round trips.
            newest = select(version.c.version).where(scope(conn, version, code_set=catalog.c.code_set)).order_by(
                version.c.created_at.desc(), version.c.version.desc()).limit(1).correlate(catalog).scalar_subquery()
            status = select(version.c.status).where(scope(conn, version, code_set=catalog.c.code_set)).order_by(
                version.c.created_at.desc(), version.c.version.desc()).limit(1).correlate(catalog).scalar_subquery()
            published = version.alias("published")
            return [dict(r) for r in conn.execute(select(*(catalog.c[n] for n in
                ("code_set", "name", "definition", "authority", "steward")),
                published.c.version.label("published_version"), published.c.sha256.label("published_sha256"),
                newest.label("newest_version"), status.label("newest_status")).select_from(catalog.outerjoin(
                    published, scope(conn, published, code_set=catalog.c.code_set)
                    & (published.c.status == "published") & published.c.valid_to.is_(None))).order_by(catalog.c.code_set)).mappings()]

    def codes(self, code_set: str, version: str) -> list[dict]:
        with transaction(self.engine, write=False) as conn:
            import edgar_control

            rows = self._content(conn, code_set, version)[0]
            ordered = json.loads(edgar_control.order_reference_rows(json.dumps(
                rows, ensure_ascii=False, allow_nan=False, default=_plain)))
            originals = {row["code"]: row for row in rows}
            return [originals[row["code"]] for row in ordered]

    def version(self, code_set: str, version: str) -> dict:
        with transaction(self.engine, write=False) as conn:
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
        table = tables(conn.dialect.name)["code_set_version"]
        row = conn.execute(select(*public_columns(table)).where(
            scope(conn, table, code_set=code_set, version=version))).mappings().first()
        if row is None:
            raise Blocked(f"Unknown reference data version {code_set} {version}")
        return dict(row)

    @staticmethod
    def _content(conn, code_set: str, version: str) -> tuple[list[dict], dict[int, str]]:
        values = {"code_set": code_set, "version": version}
        models = tables(conn.dialect.name)
        table = models["code"]
        codes = {r["code"]: {**r, "labels": [], "crosswalk": []} for r in conn.execute(select(
            *(table.c[n] for n in CODE_COLUMNS)).where(scope(conn, table, **values)).order_by(table.c.code)).mappings()}
        table = models["code_label"]
        for r in conn.execute(select(*(table.c[n] for n in ("code", "language", "label", "kind", "source"))).where(
                scope(conn, table, **values))).mappings():
            codes[r["code"]]["labels"].append({k: r[k] for k in ("language", "label", "kind", "source")})
        table = models["crosswalk_row"]
        for r in conn.execute(select(*(table.c[n] for n in
                ("from_code", "to_set", "to_version", "to_code", "match_type"))).where(
                scope(conn, table, from_set=code_set, from_version=version))).mappings():
            codes[r["from_code"]]["crosswalk"].append({k: r[k] for k in ("to_set", "to_version", "to_code", "match_type")})
        table = models["level"]
        levels = {r.depth: r.name for r in conn.execute(select(table.c.depth, table.c.name).where(
            scope(conn, table, **values)))}
        return list(codes.values()), levels
