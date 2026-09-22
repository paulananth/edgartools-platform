"""PROTOTYPE — throwaway Source Contract runner (Source Contract map, ticket 07).

Not production code. It exists to answer one question: do the decisions in
tickets 04-06 hold on real sources? It knows file formats and primitives and
nothing about any source (acceptance check 3: grep this file for a source
name and find none).

Commands:
  prove   <source_dir> [--json] [--gate] [--proof-dir DIR]   Proving Run: validate → cases → checks → gate
  mapdoc  <source_dir>                                       generated Mapping Document (markdown)
  run     <source_dir> <artifact>... [--json]                parse artifacts, print silver rows
Exit codes: 0 proven, 1 test/check/gate failed, 2 contract invalid, 3 engine or custom-code bug.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import importlib.util
import io
import json
import os
import random
import re
import socket
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

ENGINE_VERSION = "prototype-0.1"
HERE = Path(__file__).resolve().parent
MISSING = object()


# ---------------------------------------------------------------- network guard (check 4)

# Python-level guard only: C libraries (libpq under psycopg2) open sockets below it.
# See the prototype README finding on where no-network must really live.
_REAL_CONNECT = socket.socket.connect
LOOPBACK_ALLOWED = False  # the merge harness turns this on for its throwaway Postgres


def _guarded_connect(self, address, *rest):
    host = address[0] if isinstance(address, tuple) else address
    if LOOPBACK_ALLOWED and host in ("127.0.0.1", "::1", "localhost"):
        return _REAL_CONNECT(self, address, *rest)
    raise RuntimeError(f"network access to {host!r} is refused by the Source Contract runner")


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
sys.modules.setdefault("source_engine", sys.modules[__name__])


# ---------------------------------------------------------------- errors

class ContractInvalid(Exception):
    def __init__(self, pointer: str, rule: str, message: str):
        super().__init__(message)
        self.pointer, self.rule, self.message = pointer, rule, message


class PathError(Exception):
    pass


class Reject(Exception):
    """Raised by custom code to reject one record with a reason (ticket 04 Q4)."""


# ---------------------------------------------------------------- custom-step API

_REGISTRY: dict[str, dict[str, Any]] = {}


def _register(kind: str, name: str, version: int):
    def deco(fn):
        _REGISTRY[f"{name}@{version}"] = {"kind": kind, "fn": fn}
        return fn
    return deco


def value_step(name: str, version: int):
    return _register("value", name, version)


def check_step(name: str, version: int):
    return _register("check", name, version)


def table_reader(name: str, version: int):
    return _register("table", name, version)


# ---------------------------------------------------------------- loading (Q0: strict YAML 1.2 → canonical JSON)

def load_contract(path: Path) -> tuple[dict, dict[str, int]]:
    yaml = YAML(typ="rt")
    yaml.version = (1, 2)
    from ruamel.yaml.error import MarkedYAMLError
    try:
        node = yaml.load(path.read_text())
    except MarkedYAMLError as e:  # check 9: YAML syntax errors name the line too
        mark = e.problem_mark or e.context_mark
        hint = " (a '*' or '&' in a path is YAML alias/anchor syntax — paths have no wildcards; see research 10)" \
            if "alias" in str(e.context or "") or "anchor" in str(e.context or "") else ""
        raise ContractInvalid(f"@line:{mark.line + 1}", "yaml-syntax", f"{e.context or ''} {e.problem}{hint}".strip())
    lines: dict[str, int] = {}

    def plain(n, ptr):
        if isinstance(n, CommentedMap):
            out = {}
            for k, v in n.items():
                p = f"{ptr}/{k}"
                try:
                    lines[p] = n.lc.key(k)[0] + 1
                except Exception:
                    pass
                out[str(k)] = plain(v, p)
            return out
        if isinstance(n, CommentedSeq):
            out = []
            for i, v in enumerate(n):
                p = f"{ptr}/{i}"
                try:
                    lines[p] = n.lc.item(i)[0] + 1
                except Exception:
                    pass
                out.append(plain(v, p))
            return out
        if isinstance(n, bool) or n is None or isinstance(n, (int, float)):
            return n
        return str(n)

    return plain(node, ""), lines


def canonical_json(doc: Any) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_of(doc: Any) -> str:
    return hashlib.sha256(canonical_json(doc).encode()).hexdigest()


def line_for(lines: dict[str, int], pointer: str) -> int | None:
    if pointer.startswith("@line:"):
        return int(pointer[6:])
    p = pointer
    while p:
        if p in lines:
            return lines[p]
        p = p.rsplit("/", 1)[0]
    return None


# ---------------------------------------------------------------- readers (formats, never sources)

class Node(dict):
    """A canonical-tree element. `.el` keeps the XML element for text_all."""
    el: ET.Element | None = None


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_DECL = re.compile(r"^<\?xml[^>]*\?>")


def _xml_to_tree(el: ET.Element) -> Node:
    node = Node()
    node.el = el
    for k, v in el.attrib.items():
        node[f"@{k}"] = v
    if el.text and el.text.strip():
        node["$"] = el.text
    for child in el:
        tag = child.tag.split("}", 1)[-1]
        sub = _xml_to_tree(child)
        if tag in node:
            if not isinstance(node[tag], list):
                node[tag] = [node[tag]]
            node[tag].append(sub)
        else:
            node[tag] = sub
    return node


def _sgml_header(text: str) -> dict[str, str]:
    head = text.split("<XML>", 1)[0] if "<XML>" in text else ""
    out = {}
    for line in head.splitlines():
        if ":" in line and not line.lstrip().startswith("<"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def read_artifact(read: dict, raw: bytes) -> list[tuple[Any, dict]]:
    """Returns [(document tree, header)] — one document per record."""
    fmt = read["format"]
    if fmt == "xml":
        text = raw.decode("utf-8", errors="replace")
        header = {}
        if read.get("envelope") == "sgml_text":
            header = _sgml_header(text)
            i, j = text.find("<XML>"), text.rfind("</XML>")
            if i >= 0 and j > i:
                text = text[i + 5 : j]
        text = _DECL.sub("", text.strip()).strip()
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            if read.get("on_parse_error") != "retry_without_control_chars":
                return []
            try:
                root = ET.fromstring(_CONTROL.sub("", text))
            except ET.ParseError:
                return []
        if read.get("root") and root.tag != read["root"]:
            return []
        return [(_xml_to_tree(root), header)]
    if fmt == "json":
        docs = []
        text = raw.decode("utf-8")
        records = [json.loads(l) for l in text.splitlines() if l.strip()] if read.get("records") == "jsonl" else [json.loads(text)]
        for rec in records:
            for key in (read.get("record_path") or "").split(".") if read.get("record_path") else []:
                rec = rec.get(key) if isinstance(rec, dict) else None
            if rec is not None:
                docs.append((rec, {}))
        return docs
    if fmt == "bytes":  # no engine parsing: every table uses a custom_reader (ticket 04 Q4)
        return [(None, {})]
    raise ContractInvalid("/read/format", "reader", f"unknown format {fmt!r}")


# ---------------------------------------------------------------- paths (Q1: restricted dotted paths)

_KEY = r"(\$|@?[A-Za-z_][A-Za-z0-9_\-]*(:[A-Za-z_][A-Za-z0-9_\-]*)?)"
PATH_RE = re.compile(rf"^(\.|{_KEY}(\.{_KEY})*)$")  # names, @attr, $, prefix:Name — nothing else


def resolve(node: Any, path: str) -> Any:
    if path == ".":
        return node
    cur = node
    parts = path.split(".")
    for i, key in enumerate(parts):
        if isinstance(cur, list):
            raise PathError(f"path {path!r} crosses a repeating group at {'.'.join(parts[:i]) or '.'}; use each")
        if key == "$" and cur is not MISSING and not isinstance(cur, dict):
            raise PathError(f"path {path!r}: '$' reads an element's text, but this value is a plain {type(cur).__name__}; use '.' for the value itself")
        if not isinstance(cur, dict) or key not in cur:
            return MISSING
        cur = cur[key]
    return cur


def as_list(v: Any) -> list:
    if v is MISSING or v is None:
        return []
    return v if isinstance(v, list) else [v]


# ---------------------------------------------------------------- evaluation

class Ctx:
    def __init__(self, doc, header, item, artifact_sha, engine, row, ordinal=None):
        self.doc, self.header, self.item = doc, header, item
        self.artifact_sha, self.engine, self.row, self.ordinal = artifact_sha, engine, row, ordinal
        self.lookup_cache: dict[str, Any] = {}


def _scope(ctx: Ctx, args: dict) -> Any:
    return ctx.doc if args.get("from") == "document" else ctx.item


def _leaf(ctx, args, *, need_leaf=True):
    v = resolve(_scope(ctx, args), args["path"])
    if isinstance(v, list):
        raise PathError(f"path {args['path']!r} ends at a repeating group; use each")
    if need_leaf and isinstance(v, dict):
        raise PathError(f"path {args['path']!r} ends at an element; add .$ or use text_all")
    return v


def p_text(ctx, a, _):
    v = _leaf(ctx, a)
    return a.get("default") if v is MISSING or v is None else str(v).strip()


def p_text_all(ctx, a, _):
    v = _leaf(ctx, a, need_leaf=False)
    if v is MISSING:
        return a.get("default")
    if isinstance(v, Node) and v.el is not None:
        return "".join(v.el.itertext()).strip()
    return str(v.get("$", "")).strip() if isinstance(v, dict) else str(v).strip()


def p_int(ctx, a, _):
    v = _leaf(ctx, a)
    try:
        return int(str(v).strip()) if v not in (MISSING, None, "") else a.get("default")
    except ValueError:
        return a.get("default")


def p_number(ctx, a, _):
    v = _leaf(ctx, a)
    try:
        return float(v) if v not in (MISSING, None, "") else a.get("default")
    except (TypeError, ValueError):
        return a.get("default")


def p_flag(ctx, a, _):
    v = _leaf(ctx, a)
    if v is MISSING or v is None:
        return a.get("default")
    return str(v).strip() in a["true_set"]


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def p_date_prefix(ctx, a, _):
    v = _leaf(ctx, a)
    if v is MISSING or v is None:
        return a.get("default")
    m = _DATE.match(str(v))
    return m.group(0) if m else a.get("default")


def p_value_with_footnotes(ctx, a, _):
    """Named convention (ticket 04 Q2): SEC's <x><value/><footnoteId id/></x> → 'value [F1,F2]'."""
    node = resolve(_scope(ctx, a), a["path"])
    if node is MISSING or not isinstance(node, dict):
        return a.get("default")
    val = node.get("value")
    value = (val.get("$") or "") if isinstance(val, dict) else ""
    ids = ",".join(fn.get("@id", "") for fn in as_list(node.get("footnoteId")) if fn.get("@id"))
    marker = f"[{ids}]" if ids else ""
    if value:
        return f"{value} {marker}" if marker else value
    return marker


def p_const(ctx, a, _):
    return a["value"]


def p_ordinal(ctx, a, _):
    return ctx.ordinal


def p_count(ctx, a, _):
    return len(as_list(resolve(_scope(ctx, a), a["each"])))


def p_header(ctx, a, _):
    return ctx.header.get(a["name"], a.get("default"))


def p_artifact(ctx, a, _):
    if a["name"] == "sha256":
        return ctx.artifact_sha
    raise PathError(f"unknown artifact attribute {a['name']!r}")


def p_join(ctx, a, _):
    items = as_list(resolve(_scope(ctx, a), a["each"]))
    if not items:
        return a.get("default")
    out = []
    for it in items:
        sub = Ctx(ctx.doc, ctx.header, it, ctx.artifact_sha, ctx.engine, ctx.row)
        out.append("".join(str(ctx.engine.eval(sub, part, f"{a['_ptr']}/parts") or "") for part in a["parts"]).strip())
    return a.get("separator", "").join(out)


def p_timestamp(ctx, a, _):
    v = _leaf(ctx, a)
    return a.get("default") if v is MISSING or v is None else str(v).strip()


# chain primitives take the previous value
def p_upper(ctx, a, v):
    return v.upper() if isinstance(v, str) else v


def p_strip_spaces(ctx, a, v):
    return v.replace(" ", "") if isinstance(v, str) else v


def p_starts_with(ctx, a, v):
    return isinstance(v, str) and v.startswith(a["value"])


def p_empty_to_null(ctx, a, v):
    return None if v in ("", None) else v


def p_when(ctx, a, v):
    hit = isinstance(v, str) and (a["contains"].lower() in v.lower() if a.get("ignore_case") else a["contains"] in v)
    return ctx.engine.eval(ctx, a["then"], a["_ptr"] + "/then") if hit else v


def p_ref(ctx, a, _):
    return ctx.engine.lookup(ctx, a["lookup"])


def p_get(ctx, a, v):
    got = resolve(v, a["path"]) if isinstance(v, dict) else MISSING
    return a.get("default") if got is MISSING or got is None else got


def p_len(ctx, a, v):
    got = resolve(v, a["path"]) if isinstance(v, dict) else MISSING
    return len(got) if isinstance(got, list) else a.get("default")


def p_to_text(ctx, a, v):
    return a.get("default") if v is None else str(v)


# name: (fn, required args, optional args, takes_previous)
PRIMITIVES: dict[str, tuple] = {
    "text": (p_text, {"path"}, {"default", "from"}, False),
    "text_all": (p_text_all, {"path"}, {"default", "from"}, False),
    "int": (p_int, {"path"}, {"default", "from"}, False),
    "number": (p_number, {"path"}, {"default", "from"}, False),
    "flag": (p_flag, {"path", "true_set"}, {"default", "from"}, False),
    "date_prefix": (p_date_prefix, {"path"}, {"default", "from"}, False),
    "timestamp": (p_timestamp, {"path"}, {"default", "from"}, False),
    "value_with_footnotes": (p_value_with_footnotes, {"path"}, {"default", "from"}, False),
    "const": (p_const, {"value"}, set(), False),
    "ordinal": (p_ordinal, set(), set(), False),
    "count": (p_count, {"each"}, {"from"}, False),
    "header": (p_header, {"name"}, {"default"}, False),
    "artifact": (p_artifact, {"name"}, set(), False),
    "join": (p_join, {"each", "parts"}, {"from", "separator", "default"}, False),
    "ref": (p_ref, {"lookup"}, set(), False),
    "upper": (p_upper, set(), set(), True),
    "strip_spaces": (p_strip_spaces, set(), set(), True),
    "starts_with": (p_starts_with, {"value"}, set(), True),
    "empty_to_null": (p_empty_to_null, set(), set(), True),
    "when": (p_when, {"contains", "then"}, {"ignore_case"}, True),
    "get": (p_get, {"path"}, {"default"}, True),
    "len": (p_len, {"path"}, {"default"}, True),
    "to_text": (p_to_text, set(), {"default"}, True),
}
PATH_ARGS = {"path", "each"}


# ---------------------------------------------------------------- the engine

class Engine:
    def __init__(self, source_dir: Path, families: dict):
        self.dir = source_dir
        self.contract, self.lines = load_contract(source_dir / "contract.yaml")
        self.families = families
        self.digest = digest_of(self.contract)
        self.custom_digest = None
        self.rejects: list[dict] = []
        self.type_errors: list[dict] = []
        self._lookup_memo: dict[tuple, Any] = {}
        self._load_custom()

    # ---- validation (check 9: every error names a line and a rule)
    def validate(self) -> None:
        import jsonschema
        schema = json.loads((HERE / "contract.schema.json").read_text())
        errs = sorted(jsonschema.Draft202012Validator(schema).iter_errors(self.contract), key=lambda e: list(e.absolute_path))
        if errs:
            e = errs[0]
            ptr = "/" + "/".join(str(p) for p in e.absolute_path)
            raise ContractInvalid(ptr, f"schema:{e.validator}", e.message)
        for tname, table in self.contract["read"]["tables"].items():
            base = f"/read/tables/{tname}"
            if ("custom_reader" in table) == ("columns" in table):
                raise ContractInvalid(base, "one-row-source", "a table has either columns or a custom_reader, not both or neither")
            if "custom_reader" in table:
                step = table["custom_reader"].get("step")
                if step not in _REGISTRY or _REGISTRY[step]["kind"] != "table":
                    raise ContractInvalid(base + "/custom_reader/step", "custom-declared", f"no table reader {step!r} in custom.py")
                if tname not in self.contract["silver"]:
                    raise ContractInvalid(base, "silver-declared", f"table {tname!r} has no silver declaration")
                continue
            if "each" in table:
                self._check_path(table["each"], base + "/each")
            silver_cols = self.contract["silver"][tname]["columns"] if tname in self.contract["silver"] else None
            if silver_cols is None:
                raise ContractInvalid(base, "silver-declared", f"table {tname!r} has no silver declaration")
            missing = set(silver_cols) - set(table["columns"])
            extra = set(table["columns"]) - set(silver_cols)
            if missing or extra:
                raise ContractInvalid(base + "/columns", "silver-matches-read",
                                      f"read and silver disagree: missing {sorted(missing)} extra {sorted(extra)}")
            for cname, expr in table["columns"].items():
                self._check_expr(expr, f"{base}/columns/{cname}")
        seen: dict[str, int] = {}
        for ci, ch in enumerate(self.contract.get("checks") or []):
            lab = check_label(ch)
            if lab in seen:
                raise ContractInvalid(f"/checks/{ci}", "check-label-unique",
                                      f"checks {seen[lab]} and {ci} are both named {lab!r} in the gate; give one a label: argument")
            seen[lab] = ci
        gate = self.contract.get("gate") or {}
        known = {"rejected", "type_errors", "deferred"} | {f"rows.{t}" for t in self.contract["silver"]} \
            | {f"check.{check_label(ch)}" for ch in (self.contract.get("checks") or [])}
        for lname in (gate.get("limits") or {}):
            if lname not in known:
                hint = difflib.get_close_matches(lname, known, n=1)
                raise ContractInvalid(f"/gate/limits/{lname}", "limit-known",
                                      f"no metric named {lname!r}" + (f" — did you mean {hint[0]!r}?" if hint else f"; metrics: {sorted(known)}"))
        for lname, spec in (self.contract.get("lookups") or {}).items():
            if spec.get("family") not in self.families:
                raise ContractInvalid(f"/lookups/{lname}/family", "family-known", f"unknown artifact family {spec.get('family')!r}")

    def _check_path(self, path, ptr):
        if not isinstance(path, str) or not PATH_RE.match(path):
            raise ContractInvalid(ptr, "path-syntax", f"{path!r} is not a dotted path (names joined by '.', no wildcards, filters or quoting)")

    def _check_expr(self, expr, ptr):
        if isinstance(expr, str):
            return  # a column reference (custom inputs)
        if not isinstance(expr, dict) or len(expr) != 1:
            raise ContractInvalid(ptr, "one-call", "a column is exactly one primitive call, a steps list, or a custom step")
        (name, args), = expr.items()
        if name == "steps":
            for i, step in enumerate(args):
                self._check_expr(step, f"{ptr}/steps/{i}")
            return
        if name == "custom":
            step = args.get("step")
            if step not in _REGISTRY or _REGISTRY[step]["kind"] != "value":
                raise ContractInvalid(ptr + "/custom/step", "custom-declared", f"no value step {step!r} in custom.py")
            for k, v in (args.get("inputs") or {}).items():
                self._check_expr(v, f"{ptr}/custom/inputs/{k}")
            return
        if name not in PRIMITIVES:
            hint = difflib.get_close_matches(name, PRIMITIVES, n=1)
            raise ContractInvalid(ptr, "primitive-known", f"unknown primitive {name!r}" + (f" — did you mean {hint[0]!r}?" if hint else ""))
        _, req, opt, _ = PRIMITIVES[name]
        args = args or {}
        for k in args:
            if k not in req | opt:
                hint = difflib.get_close_matches(k, req | opt, n=1)
                raise ContractInvalid(f"{ptr}/{name}/{k}", "argument-known",
                                      f"unknown argument {k!r} for primitive {name}" + (f" — did you mean {hint[0]!r}?" if hint else ""))
        for k in req - set(args):
            raise ContractInvalid(f"{ptr}/{name}", "argument-required", f"primitive {name} needs {k!r}")
        if "path" in req and "default" not in args and name not in ("value_with_footnotes",):
            raise ContractInvalid(f"{ptr}/{name}", "explicit-default", f"primitive {name} reads a path and needs an explicit default")
        for k in PATH_ARGS & set(args):
            self._check_path(args[k], f"{ptr}/{name}/{k}")
        if name == "join":
            for i, part in enumerate(args["parts"]):
                self._check_expr(part, f"{ptr}/join/parts/{i}")
        if name == "when":
            self._check_expr(args["then"], f"{ptr}/when/then")

    # ---- custom code (ticket 04 Q4: declared imports, purity)
    def _load_custom(self):
        path = self.dir / "custom.py"
        if not path.exists():
            return
        src = path.read_text()
        self.custom_digest = hashlib.sha256(src.encode()).hexdigest()
        from importlib.metadata import packages_distributions
        dists = packages_distributions()  # module name → distribution names, e.g. a module shipped by a differently named package
        declared = set(self.contract.get("requires") or [])
        allowed = set(sys.stdlib_module_names) | {"source_engine", "source_contract"} | {m for m, d in dists.items() if declared & set(d)}
        for node in ast.walk(ast.parse(src)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for n in names:
                root = n.split(".")[0]
                if root not in allowed:
                    raise ContractInvalid("/requires", "custom-imports-declared", f"custom.py imports {n!r}, not listed in requires")
        sys.modules.setdefault("source_engine", sys.modules[__name__])
        spec = importlib.util.spec_from_file_location(f"custom_{self.dir.name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # ---- evaluation
    def eval(self, ctx: Ctx, expr: Any, ptr: str, prev: Any = None) -> Any:
        if isinstance(expr, str):
            return ctx.row[expr]
        (name, args), = expr.items()
        if name == "steps":
            v = None
            for i, step in enumerate(args):
                v = self.eval(ctx, step, f"{ptr}/steps/{i}", v)
            return v
        if name == "custom":
            fn = _REGISTRY[args["step"]]["fn"]
            inputs = {k: self.eval(ctx, v, f"{ptr}/custom/inputs/{k}") for k, v in (args.get("inputs") or {}).items()}
            out = fn(**inputs)
            if self.purity_check and fn(**inputs) != out:
                raise RuntimeError(f"custom step {args['step']} is not deterministic")
            return out
        fn = PRIMITIVES[name][0]
        a = dict(args or {})
        a["_ptr"] = f"{ptr}/{name}"
        return fn(ctx, a, prev)

    purity_check = False
    fixture_mode = False

    def lookup(self, ctx: Ctx, name: str) -> dict:
        spec = self.contract["lookups"][name]
        key = self.eval(ctx, spec["key"], f"/lookups/{name}/key")
        as_of = self.eval(ctx, spec["select"]["as_of"], f"/lookups/{name}/select/as_of") if "as_of" in spec.get("select", {}) else None
        memo = (name, key, as_of, self.fixture_mode)
        family = self.families[spec["family"]]
        fx = self.dir / "fixtures" / "families" / spec["family"]
        if self.fixture_mode:  # test cases read the source folder's own fixtures, never machine bronze
            family = {"root": str(fx), "file": "{int}.json", "dated": False}
        if memo not in self._lookup_memo:
            self._lookup_memo[memo] = resolve_lookup(family, key, spec.get("select", {}), as_of)
        return self._lookup_memo[memo]

    def parse(self, raw: bytes) -> dict[str, list[dict]]:
        sha = hashlib.sha256(raw).hexdigest()
        out: dict[str, list[dict]] = {t: [] for t in self.contract["read"]["tables"]}
        for doc, header in read_artifact(self.contract["read"], raw):
            for tname, table in self.contract["read"]["tables"].items():
                if "custom_reader" in table:
                    step = table["custom_reader"]["step"]
                    fn = _REGISTRY[step]["fn"]
                    try:
                        rows = list(fn(raw))
                        if self.purity_check and list(fn(raw)) != rows:
                            raise RuntimeError(f"table reader {step} is not deterministic")
                    except Reject as r:
                        self.rejects.append({"table": tname, "artifact": sha, "reason": str(r)})
                        continue
                    declared = set(self.contract["silver"][tname]["columns"])
                    for row in rows:
                        extra = set(row) - declared
                        bad = (next(iter(extra)), f"table reader {step} returned undeclared column {next(iter(extra))!r}") if extra \
                            else self._check_types(tname, row)
                        if bad:
                            self.type_errors.append({"table": tname, "column": bad[0], "message": bad[1], "artifact": sha,
                                                     "pointer": f"/read/tables/{tname}/custom_reader" if extra else f"/silver/{tname}/columns/{bad[0]}"})
                            continue
                        out[tname].append(row)
                    continue
                items = [doc] if table.get("each", ".") == "." else as_list(resolve(doc, table["each"]))
                has = (table.get("where") or {}).get("has") or []
                items = [it for it in items if all(isinstance(it, dict) and h in it for h in has)]
                for ordinal, it in enumerate(items, start=1):
                    row: dict[str, Any] = {}
                    ctx = Ctx(doc, header, it, sha, self, row, ordinal)
                    try:
                        for cname, expr in table["columns"].items():
                            row[cname] = self.eval(ctx, expr, f"/read/tables/{tname}/columns/{cname}")
                    except Reject as r:
                        self.rejects.append({"table": tname, "artifact": sha, "reason": str(r)})
                        continue
                    bad = self._check_types(tname, row)
                    if bad:
                        self.type_errors.append({"table": tname, "column": bad[0], "message": bad[1], "artifact": sha,
                                                 "pointer": f"/silver/{tname}/columns/{bad[0]}"})
                        continue
                    out[tname].append(row)
        return out

    def parse_fixtures(self, fixture) -> dict[str, list[dict]]:
        """A case's fixture is one file or a list of files; rows are concatenated in order."""
        out: dict[str, list[dict]] = {t: [] for t in self.contract["read"]["tables"]}
        for f in ([fixture] if isinstance(fixture, str) else fixture):
            path = self.dir / f
            if not path.is_file():
                raise ContractInvalid("/tests", "fixture-exists", f"fixture {f!r} does not exist in the source folder")
            for t, rows in self.parse(path.read_bytes()).items():
                out[t].extend(rows)
        return out

    def _check_types(self, tname, row):
        for col, typ in self.contract["silver"][tname]["columns"].items():
            nullable = typ.endswith("?")
            base = typ.rstrip("?")
            v = row.get(col)
            if v is None:
                if not nullable:
                    return col, f"silver {tname}.{col} is {typ} but the row has null"
                continue
            ok = {"string": isinstance(v, str), "bigint": isinstance(v, int) and not isinstance(v, bool),
                  "double": isinstance(v, float), "boolean": isinstance(v, bool), "date": isinstance(v, str) and bool(_DATE.match(v)),
                  "timestamp": isinstance(v, str)}.get(base)
            if not ok:
                return col, f"silver {tname}.{col} is {typ} but the row has {type(v).__name__} {v!r}"
        return None

    # ---- mapping (Clean MDM's own normalize; the adapter block unchanged)
    def to_assertions(self, silver: dict[str, list[dict]]) -> list[dict]:
        ds = self.contract.get("dataset")
        if not ds:
            return []
        from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
        out = []
        for row in silver[ds["table"]]:
            pub = {"artifact_sha256": "prototype", "member": ds["table"], "publication_key": "prototype-publication",
                   "revision": 0, "effective_at": None}
            try:
                out.append(normalize(row, source_code=self.contract["source"], contract=ds["contract"], publication=pub))
            except UnsupportedRecord as e:
                out.append({"deferred": e.reason, "row": row})
        return out


def resolve_lookup(family: dict, key: Any, select: dict, as_of: str | None) -> dict:
    """Local, never fetches. Dated layouts honour as_of + earliest_after (ticket 04 Q3)."""
    empty = {"found": False, "artifact_sha256": "", "payload": None, "selected": None}
    if key is None:
        return empty
    root = Path(family["root"])
    if family.get("dated"):
        d = root / family["dir"].format(int=int(key), pad10=f"{int(key):010d}")
        if not d.exists():
            return empty
        copies = sorted((p.parent.relative_to(d).as_posix().replace("/", "-"), p) for p in d.rglob(family["file"].format(int=int(key), pad10=f"{int(key):010d}")))
        if not copies:
            return empty
        if as_of:
            day = str(as_of).replace("-", "")[:8]
            before = [c for c in copies if c[0].replace("-", "") <= day]
            after = [c for c in copies if c[0].replace("-", "") > day]
            date, path = before[-1] if before else (after[0] if select.get("fallback") == "earliest_after" and after else (None, None))
            if path is None:
                return empty
        else:
            date, path = copies[-1]
    else:
        path, date = root / family["file"].format(int=int(key), pad10=f"{int(key):010d}"), "undated"
        if not path.exists():
            return empty
    raw = path.read_bytes()
    return {"found": True, "artifact_sha256": hashlib.sha256(raw).hexdigest(), "payload": json.loads(raw), "selected": date}


# ---------------------------------------------------------------- checks (ticket 05 Q3)

def run_check(engine: Engine, check: dict, silver: dict[str, list[dict]]) -> list[dict]:
    (name, a), = check.items()
    rows = silver.get(a["table"], [])
    key = engine.contract["silver"][a["table"]].get("key") or []
    k = lambda r: {c: r.get(c) for c in key}
    v: list[dict] = []
    if name == "not_null":
        v = [{"row": k(r), "message": f"{a['column']} is null"} for r in rows if r.get(a["column"]) in (None, "")]
    elif name == "unique":
        seen = {}
        for r in rows:
            t = tuple(r.get(c) for c in a["columns"])
            if t in seen:
                v.append({"row": k(r), "message": f"duplicate {dict(zip(a['columns'], t))}"})
            seen[t] = 1
    elif name == "in_set":
        v = [{"row": k(r), "message": f"{a['column']}={r.get(a['column'])!r} not in set"} for r in rows if r.get(a["column"]) not in a["values"]]
    elif name == "pattern":
        rx = re.compile(a["regex"])
        v = [{"row": k(r), "message": f"{a['column']}={r.get(a['column'])!r} does not match {a['regex']}"} for r in rows
             if r.get(a["column"]) is not None and not rx.search(str(r.get(a["column"])))]
    elif name == "row_count":
        if len(rows) < a.get("min", 0):
            v = [{"row": {}, "message": f"{len(rows)} rows < min {a['min']}"}]
    elif name == "custom_check":
        fn = _REGISTRY[a["step"]]["fn"]
        for r in rows:
            msg = fn(**{c: r.get(c) for c in a["inputs"]})
            if msg:
                v.append({"row": k(r), "message": msg})
    else:
        raise ContractInvalid("/checks", "check-known", f"unknown check {name!r}")
    return v


def check_label(check: dict) -> str:
    (name, a), = check.items()
    if a.get("label"):
        return a["label"]
    return f"{name}({a.get('step') or a.get('column') or ','.join(a.get('columns', [])) or a['table']})"


# ---------------------------------------------------------------- Proving Run (ticket 05)

def _match(expected: dict, actual: dict) -> list[dict]:
    diffs = []
    for col, exp in expected.items():
        act = actual.get(col, MISSING)
        if act is MISSING or act != exp:
            diffs.append({"column": col, "expected": exp, "actual": None if act is MISSING else act})
    return diffs


def prove(engine: Engine, *, gate: bool, bronze_root: Path | None) -> dict:
    c = engine.contract
    failures: list[dict] = []
    results = {"source": c["source"], "version": c["version"], "digest": engine.digest, "engine": ENGINE_VERSION,
               "custom_digest": engine.custom_digest, "cases": 0, "failures": failures}
    engine.purity_check = engine.fixture_mode = True
    fixture_digests = {}
    for i, case in enumerate(c.get("tests") or []):
        ptr = f"/tests/{i}"
        results["cases"] += 1
        engine.type_errors.clear()
        silver = engine.parse_fixtures(case["fixture"])
        for f in ([case["fixture"]] if isinstance(case["fixture"], str) else case["fixture"]):
            fixture_digests[f] = hashlib.sha256((engine.dir / f).read_bytes()).hexdigest()
        for te in engine.type_errors:
            failures.append({"kind": "silver-type", "pointer": te["pointer"], "case": case["case"], "message": te["message"],
                             "fixture": case["fixture"]})
        for tname, exp_rows in (case.get("expect", {}).get("silver") or {}).items():
            act_rows = silver.get(tname, [])
            if len(exp_rows) != len(act_rows):
                failures.append({"kind": "case", "pointer": f"{ptr}/expect/silver/{tname}", "case": case["case"],
                                 "message": f"{tname}: expected {len(exp_rows)} rows, got {len(act_rows)}", "fixture": case["fixture"]})
                continue
            for j, (e, a) in enumerate(zip(exp_rows, act_rows)):
                d = _match(e, a)
                if d:
                    failures.append({"kind": "case", "pointer": f"{ptr}/expect/silver/{tname}/{j}", "case": case["case"],
                                     "table": tname, "row": j + 1, "diff": d, "context": {k: a.get(k) for k in e}, "fixture": case["fixture"]})
        exp_mdm = case.get("expect", {}).get("mdm")
        if exp_mdm is not None:
            got = engine.to_assertions(silver)
            if len(got) != len(exp_mdm):
                failures.append({"kind": "case", "pointer": f"{ptr}/expect/mdm", "case": case["case"],
                                 "message": f"expected {len(exp_mdm)} assertions, got {len(got)}", "fixture": case["fixture"]})
            for j, (e, a) in enumerate(zip(exp_mdm, got)):
                if "deferred" in e or "deferred" in a:  # a deferred record: compare its reason only
                    d = _match({"deferred": e.get("deferred")}, {"deferred": a.get("deferred")})
                    if d:
                        failures.append({"kind": "case", "pointer": f"{ptr}/expect/mdm/{j}", "case": case["case"], "table": "mdm",
                                         "row": j + 1, "diff": d, "fixture": case["fixture"]})
                    continue
                flat = {"kind": a.get("kind"), **{f"identifiers.{k}": v for k, v in a.get("identifiers", {}).items()},
                        **{f"fields.{k}": (f.get("value") if f.get("op") == "value" else None) for k, f in a.get("fields", {}).items()}}
                want = {"kind": e.get("kind"), **{f"identifiers.{k}": v for k, v in (e.get("identifiers") or {}).items()},
                        **{f"fields.{k}": v for k, v in (e.get("fields") or {}).items()}}
                d = _match(want, flat)
                if d:
                    failures.append({"kind": "case", "pointer": f"{ptr}/expect/mdm/{j}", "case": case["case"], "table": "mdm",
                                     "row": j + 1, "diff": d, "fixture": case["fixture"]})
        for ci, check in enumerate(c.get("checks") or []):
            vs = run_check(engine, check, silver)
            if vs:
                failures.append({"kind": "check-in-case", "pointer": f"/checks/{ci}", "case": case["case"], "check": check_label(check),
                                 "violations": len(vs), "limit": 0, "sample": vs[:3]})
    merge_cases = [(i, case) for i, case in enumerate(c.get("tests") or []) if case.get("expect", {}).get("merge")]
    if merge_cases:  # only now start Postgres (ticket 05 Q2: parse and mapping cases run without a database)
        import merge_harness
        policy, _ = load_contract(HERE.parent / "policies" / "mastering-policy.yaml")
        t0 = time.time()
        with merge_harness.Postgres() as pg:
            for i, case in merge_cases:
                fails, stats = merge_harness.run_merge_case(engine, case, policy, pg)
                for f in fails:
                    failures.append({"kind": "case", "pointer": f"/tests/{i}{f['pointer']}", "case": case["case"], "table": "merge",
                                     "row": int(f["pointer"].rsplit("/", 1)[1]) + 1, "diff": f["diff"], "fixture": case["fixture"]})
        results["merge"] = {"cases": len(merge_cases), "seconds": round(time.time() - t0, 1), **stats,
                            "limit": "bound checks a declared binding: automatic rules are refused today (store.py:160-161)"}
    results["fixture_digests"] = fixture_digests
    engine.purity_check = engine.fixture_mode = False
    if gate and not failures:
        results["gate"] = run_gate(engine, bronze_root, failures)
    results["state"] = "proven" if not failures and gate and c.get("gate") else "draft"
    if not failures and not c.get("gate"):
        results["note"] = "cases passed; the contract declares no gate, so it cannot become proven"
    if results["state"] == "draft" and not failures and c.get("gate") and not gate:
        results["note"] = "cases passed; the gate was not run, so the version stays draft"
    return results


def run_gate(engine: Engine, bronze_root: Path | None, failures: list[dict]) -> dict:
    g = engine.contract["gate"]
    fam = engine.families[g["batch"]["family"]]
    root = Path(fam["root"])
    files = sorted(p for p in root.glob(fam.get("glob", "*")) if p.is_file())
    sel = g["batch"].get("select", "all")
    if isinstance(sel, dict) and "sample" in sel:
        random.Random(sel["sample"]["seed"]).shuffle(files)
        files = sorted(files[: sel["sample"]["size"]])
    batch_hash = hashlib.sha256("\n".join(hashlib.sha256(p.read_bytes()).hexdigest() for p in files).encode()).hexdigest()
    engine.rejects.clear()
    engine.type_errors.clear()
    silver: dict[str, list[dict]] = {t: [] for t in engine.contract["read"]["tables"]}
    t0 = time.time()
    for p in files:
        for t, rows in engine.parse(p.read_bytes()).items():
            silver[t].extend(rows)
    limits = g.get("limits") or {}
    metrics = []

    def judge(label, value, pct_base, ptr):
        lim = limits.get(label, {})
        pct = 100.0 * value / pct_base if pct_base else 0.0
        if "max_pct" in lim:
            ok, shown = pct <= lim["max_pct"], f"{pct:.3f}% (limit {lim['max_pct']}%)"
        elif "max" in lim:
            ok, shown = value <= lim["max"], f"{value} (limit {lim['max']})"
        elif "min" in lim:
            ok, shown = value >= lim["min"], f"{value} (min {lim['min']})"
        else:
            ok, shown = value == 0, f"{value} (limit 0)"
        metrics.append({"metric": label, "value": value, "pct": round(pct, 4), "limit": lim or {"max": 0}, "why": lim.get("why"), "ok": ok})
        if not ok:
            failures.append({"kind": "gate", "pointer": f"/gate/limits/{label}" if label in limits else "/gate", "metric": label, "message": shown})

    base_rows = sum(len(r) for r in silver.values())
    judge("rejected", len(engine.rejects), base_rows + len(engine.rejects), "/gate")
    judge("type_errors", len(engine.type_errors), base_rows + len(engine.type_errors), "/gate")
    ds = engine.contract.get("dataset")
    if ds:
        mapped = engine.to_assertions(silver)
        judge("deferred", sum(1 for a in mapped if "deferred" in a), len(mapped), "/gate")
    for t, rows in silver.items():
        lim = limits.get(f"rows.{t}")
        if lim:
            judge(f"rows.{t}", len(rows), 0, "/gate")
    for ci, check in enumerate(engine.contract.get("checks") or []):
        vs = run_check(engine, check, silver)
        (_, a), = check.items()
        judge(f"check.{check_label(check)}", len(vs), len(silver.get(a["table"], [])), f"/checks/{ci}")
    return {"artifacts": len(files), "batch_hash": batch_hash, "rows": {t: len(r) for t, r in silver.items()},
            "seconds": round(time.time() - t0, 1), "metrics": metrics}


# ---------------------------------------------------------------- Mapping Document (check 6, check 11)

def _describe(expr) -> tuple[str, bool]:
    if isinstance(expr, str):
        return f"column `{expr}`", False
    (name, a), = expr.items()
    if name == "custom":
        return f"**custom** `{a['step']}`", True
    if name == "steps":
        parts = [_describe(s) for s in a]
        return " → ".join(p for p, _ in parts), any(c for _, c in parts)
    a = a or {}
    arg = a.get("path") or a.get("each") or a.get("name") or a.get("lookup") or ("" if "value" not in a else repr(a["value"]))
    where = " (from the document)" if a.get("from") == "document" else ""
    return f"`{name}`" + (f" `{arg}`" if arg else "") + where, False


def mapdoc(engine: Engine) -> str:
    c = engine.contract
    ds = (c.get("dataset") or {})
    adapter = (ds.get("contract") or {}).get("adapter") or {}
    targets: dict[tuple[str, str], str] = {}
    policy_fields: set[str] = set()  # fields whose survivorship lists this source (Rules Database stand-in)
    pol = HERE.parent / "policies" / "mastering-policy.yaml"
    if pol.exists():
        kinds = {adapter.get("kind")} | set((adapter.get("kind_values") or {}).values())
        for kind, fields in (load_contract(pol)[0].get("fields") or {}).items():
            if kind in kinds:
                policy_fields |= {f for f, spec in fields.items() if c["source"] in (spec.get("sources") or [])}
    for col in adapter.get("record_key", []):
        targets[(ds.get("table"), col)] = "record key"
    for ns, col in (adapter.get("identifiers") or {}).items():
        targets[(ds.get("table"), col)] = f"identifier `{ns}`"
    for f, col in (adapter.get("fields") or {}).items():
        label = f"field `{f}`" if f in policy_fields else f"field `{f}` — **evidence only**: the Mastering Policy gives `{c['source']}` no rank for it"
        targets[(ds.get("table"), col)] = (targets.get((ds.get("table"), col), "") + " " + label).strip()
    if adapter.get("kind_field"):
        targets[(ds.get("table"), adapter["kind_field"])] = "identity kind"
    lines = [f"# Mapping Document — `{c['source']}` v{c['version']}", "",
             f"Generated from `contract.yaml` (digest `{engine.digest[:12]}`). Do not edit by hand.", ""]
    total = custom = 0
    for t, table in c["read"]["tables"].items():
        if "custom_reader" in table:
            cols = c["silver"][t]["columns"]
            total += len(cols)
            custom += len(cols)
            lines += [f"## `{t}`  (rows from **custom** table reader `{table['custom_reader']['step']}`)", "",
                      "| Silver column | Type | From the Bronze Artifact | Into MDM |", "|---|---|---|---|"]
            lines += [f"| `{col}` | {typ} | **custom** | {targets.get((t, col), 'evidence only' if t == ds.get('table') else '—')} |"
                      for col, typ in cols.items()] + [""]
            continue
        lines += [f"## `{t}`  (one row per `{table.get('each', '.')}`)", "",
                  "| Silver column | Type | From the Bronze Artifact | Into MDM |", "|---|---|---|---|"]
        for col, expr in table["columns"].items():
            desc, is_custom = _describe(expr)
            total += 1
            custom += is_custom
            mdm = targets.get((t, col), "evidence only" if t == ds.get("table") else "—")
            lines.append(f"| `{col}` | {c['silver'][t]['columns'][col]} | {desc} | {mdm} |")
        lines.append("")
    kind = adapter.get("kind") or f"from `{adapter.get('kind_field')}`"
    lines += [f"**MDM kind:** {kind}.  **Custom:** {custom} of {total} columns ({100.0 * custom / total:.1f}%)."]
    return "\n".join(lines)


# ---------------------------------------------------------------- output (ticket 05 Q5)

def render(results: dict, engine: Engine) -> str:
    rel = f"{engine.dir.name}/contract.yaml"
    out = []
    for f in results["failures"]:
        line = line_for(engine.lines, f["pointer"])
        head = f"FAIL  {rel}:{line}"
        if f["kind"] == "case" and "diff" in f:
            out.append(f"{head}  case \"{f['case']}\"\n      {f['table']}  row {f['row']}")
            out.append(f"        {'column':28} {'expected':24} actual")
            for d in f["diff"]:
                out.append(f"        {d['column']:28} {str(d['expected']):24} {d['actual']}   ✗")
            out.append(f"      fixture: {f['fixture']}")
        elif f["kind"] in ("check-in-case",):
            out.append(f"{head}  check {f['check']}  {f['violations']} violations (limit 0)  case \"{f['case']}\"")
            for s in f["sample"]:
                out.append(f"      {s['row']}  {s['message']}")
        else:
            out.append(f"{head}  {f.get('case') or f.get('metric') or ''}  {f.get('message', '')}")
    g = results.get("gate")
    if g:
        out.append(f"gate: {g['artifacts']} artifacts, rows {g['rows']}, {g['seconds']}s, batch {g['batch_hash'][:12]}")
        for m in g["metrics"]:
            out.append(f"  {'ok ' if m['ok'] else 'FAIL'} {m['metric']:48} {m['value']:>8}  {m['pct']:.3f}%  limit {m['limit']}" + (f"  why: {m['why']}" if m.get("why") else ""))
    n_fail = len(results["failures"])
    out.append(f"prove {results['source']}@{results['version']}: {results['cases']} cases, {n_fail} failures  →  version {results['state']}"
               + (f"  ({results['note']})" if results.get("note") else ""))
    return "\n".join(out)


def load_families() -> dict:
    y = YAML(typ="safe")
    fams = y.load((HERE.parent / "families.local.yaml").read_text())
    for f in fams.values():
        f["root"] = os.path.expandvars(os.path.expanduser(f["root"]))
    return fams


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="source")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prove"); p.add_argument("source_dir"); p.add_argument("--json", action="store_true")
    p.add_argument("--gate", action="store_true"); p.add_argument("--proof-dir")
    m = sub.add_parser("mapdoc"); m.add_argument("source_dir")
    r = sub.add_parser("run"); r.add_argument("source_dir"); r.add_argument("artifacts", nargs="+")
    args = ap.parse_args(argv)
    src = Path(args.source_dir).resolve()
    try:
        engine = Engine(src, load_families())
        engine.validate()
    except ContractInvalid as e:
        try:
            eng_lines = load_contract(src / "contract.yaml")[1]
        except ContractInvalid:
            eng_lines = {}
        rec = {"kind": "invalid", "file": f"{src.name}/contract.yaml", "line": line_for(eng_lines, e.pointer), "pointer": e.pointer, "rule": e.rule, "message": e.message}
        print(json.dumps(rec) if getattr(args, "json", False) else f"INVALID {rec['file']}:{rec['line']}  {e.pointer}  [{e.rule}]\n      {e.message}")
        return 2
    try:
        if args.cmd == "mapdoc":
            print(mapdoc(engine))
            return 0
        if args.cmd == "run":
            for a in args.artifacts:
                print(json.dumps(engine.parse(Path(a).read_bytes()), default=str, indent=1))
            return 0
        results = prove(engine, gate=args.gate, bronze_root=None)
    except ContractInvalid as e:
        print(f"INVALID {src.name}/contract.yaml:{line_for(engine.lines, e.pointer)}  {e.pointer}  [{e.rule}]  {e.message}")
        return 2
    except Exception as e:  # engine or custom-code bug: fail closed
        import traceback
        print(f"BUG  {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 3
    for f in results["failures"]:
        f["file"], f["line"] = f"{src.name}/contract.yaml", line_for(engine.lines, f["pointer"])
    if args.proof_dir:
        d = Path(args.proof_dir) / results["source"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{results['version']}-{engine.digest[:12]}.proof.json").write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps(results, default=str) if args.json else render(results, engine))
    return 0 if results["state"] == "proven" or (not results["failures"] and not args.gate) else 1


if __name__ == "__main__":
    sys.exit(main())
