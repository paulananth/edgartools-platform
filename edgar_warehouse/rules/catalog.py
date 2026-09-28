"""The Data Catalog: every source, dataset and MDM field, published one way
from the rules to OpenMetadata (rules skill ticket 13).

Operator, 2026-09-28: the catalog server is OpenMetadata, "published one way
from the rules; nobody edits rules in it". So the rules are the only input,
and a publish makes the catalog equal to them: it creates or updates what the
rules name and deletes, inside its own service only, what they no longer name.

The catalog is one OpenMetadata database service, `edgartools-rules`:
- database `sources`: a schema per source; in it a table per feed (the files
  it captures) and a table per dataset (a Dataset Contract), whose columns are
  the source paths the dataset reads;
- database `mdm`, schema `clean`: a table per kind, whose columns are its MDM
  fields, each naming the datasets that fill it, first wins;
- lineage: feed to the datasets it captures, and dataset to kind, column by
  column (the source paths that fill each MDM field).

`plan` is pure: the rules in, the catalog as data out. `publish` sends it.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote as escape, urlencode
from urllib.request import Request, urlopen

from . import files
from .mapdoc import QUALITY_WORDS, _words, winners

SERVICE = "edgartools-rules"
SOURCES, MDM, CLEAN = "sources", "mdm", "clean"
TEXT = "STRING"  # the catalog shows what a value means, not a database type


def quote(name: str) -> str:
    """One part of an OpenMetadata fully qualified name: a name holding a dot
    is quoted, as the server's own `FullyQualifiedName.quoteName` does."""
    return f'"{name}"' if "." in name else name


def fqn(*parts: str) -> str:
    return ".".join(quote(p) for p in parts)


def rules_digest(root: Path) -> str:
    """Which rules the catalog shows: one sha256 over every rules file."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.yaml")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _paths(spec: Any) -> list[tuple[str, str]]:
    """(part, source path) for one mapped value: a path, or an address's parts."""
    if isinstance(spec, str):
        return [("", spec)]
    found = []
    for part, path in (spec.get("components") or {}).items():
        found.append((part, path["lines"] if isinstance(path, dict) else path))
    return found


def _kinds(adapter: dict, known: set[str]) -> list[str]:
    """The kinds a dataset's records become, among those with merge rules."""
    named = {adapter.get("kind"), (adapter.get("classification") or {}).get("kind"),
             *(adapter.get("kind_values") or {}).values()}
    return sorted(k for k in named if k in known)


def _dataset(source: str, code: str, contract: dict, kinds: list[str]) -> tuple[dict, list[dict]]:
    """A dataset's table, and its lineage to each kind it fills."""
    adapter = contract.get("adapter") or {}
    uses: dict[str, list[str]] = defaultdict(list)  # source path -> what it is used for
    to_field: dict[str, list[str]] = defaultdict(list)  # MDM field -> source paths
    for ident, path in (adapter.get("identifiers") or {}).items():
        uses[path].append(f"Identifier `{ident}`")
    for path in adapter.get("record_key") or []:
        uses[path].append("Record key")
    for section, used in (("fields", "MDM field"), ("matching", "Matching only")):
        for field, spec in (adapter.get(section) or {}).items():
            for part, path in _paths(spec):
                uses[path].append(f"{used} `{field}`" + (f" ({part})" if part else ""))
                if section == "fields":
                    to_field[field].append(path)
    if adapter.get("kind_field"):
        uses[adapter["kind_field"]].append("Decides the kind")
    critical = []
    for check in (contract.get("quality") or {}).get("checks") or []:
        if check.get("on_fail") == "exception":  # a critical data element
            field = str(check.get("value") or "").removeprefix("fields.")
            critical.append(f"`{field}`: {_words(QUALITY_WORDS, check.get('test'), check.get('args') or {})}")
    about = [f"Dataset Contract `{code}` from {contract.get('provider') or source}.",
             f"One record is: {contract.get('record_key') or 'not stated'}."]
    if kinds:
        about.append("Its records become: " + ", ".join(kinds) + ".")
    if critical:
        about.append("Critical data elements (a record missing one is an exception, never merged): "
                     + "; ".join(critical) + ".")
    if adapter.get("relationships"):
        about.append("It also carries relationships to other records.")
    table = {"name": code, "databaseSchema": fqn(SERVICE, SOURCES, source), "description": " ".join(about),
             "columns": [{"name": path, "dataType": TEXT, "description": "; ".join(used) + "."}
                         for path, used in sorted(uses.items())]}
    at = fqn(SERVICE, SOURCES, source, code)
    lineage = []
    for kind in kinds:
        columns = [{"fromColumns": [f"{at}.{quote(p)}" for p in sorted(set(paths))],
                    "toColumn": fqn(SERVICE, MDM, CLEAN, kind, field)}
                   for field, paths in sorted(to_field.items())]
        if columns:
            lineage.append({"from": at, "to": fqn(SERVICE, MDM, CLEAN, kind), "columns": columns,
                            "description": f"`{code}` fills these {kind} fields."})
    return table, lineage


def plan(root: Path | None = None) -> dict:
    """The whole catalog the rules under `root` describe, sorted, so the same
    rules always give the same plan."""
    root = root or files.ROOT
    policy = files.policy(root)
    kinds = policy.get("kinds") or {}
    by_kind = winners(policy, root)
    schemas, tables, lineage = [], [], []
    for path in sorted((root / "sources").glob("*/source.yaml")):
        body = files.load_source(path)
        source = body.get("source") or path.parent.name
        mdm = body.get("mdm") or {}
        schemas.append({"name": source, "database": fqn(SERVICE, SOURCES),
                        "description": f"The source `{source}`: rules/sources/{path.parent.name}/."})
        for feed, spec in sorted(((body.get("acquisition") or {}).get("feeds") or {}).items()):
            required = (spec.get("completeness") or {}).get("required") or []
            columns = [{"name": key, "dataType": TEXT, "description": "Names one captured file."}
                       for key in spec.get("scope") or []]
            columns += [{"name": key, "dataType": TEXT, "description": "Must be present in a captured file."}
                        for key in required if key not in (spec.get("scope") or [])]
            tables.append({"name": feed, "databaseSchema": fqn(SERVICE, SOURCES, source), "columns": columns,
                           "description": f"Feed `{feed}`: the {spec.get('family')} files captured from "
                                          + ", ".join(spec.get("url_prefixes") or []) + "."})
            for code in spec.get("datasets") or []:
                if code in mdm:
                    lineage.append({"from": fqn(SERVICE, SOURCES, source, feed),
                                    "to": fqn(SERVICE, SOURCES, source, code), "columns": [],
                                    "description": f"Dataset `{code}` reads the files feed `{feed}` captures."})
        for code, entry in sorted(mdm.items()):
            contract = entry.get("contract") or {}
            table, edges = _dataset(source, code, contract, _kinds(contract.get("adapter") or {}, set(kinds)))
            tables.append(table)
            lineage += edges
    for kind, rules in sorted(kinds.items()):
        order = (rules.get("defaults") or {}).get("sources") or []
        columns = []
        for field, (sources, row) in sorted(by_kind.get(kind, {}).items()):
            _, winner, which, at = row
            filled = ", ".join(f"`{s}`" for s in sources) or "no dataset yet"
            columns.append({"name": field, "dataType": TEXT, "description":
                            f"Filled by {filled}, first wins. Winner: `{winner or 'none'}`. "
                            f"Rule: {which} (rules/{at})."})
        tables.append({"name": kind, "databaseSchema": fqn(SERVICE, MDM, CLEAN), "columns": columns,
                       "description": f"The MDM kind `{kind}`, rules version `{rules.get('version')}`. "
                                      "Preferred datasets, first wins: " + ", ".join(f"`{s}`" for s in order)
                                      + f". Rules: rules/merge/kinds/{kind}.yaml."})
    return {
        "service": {"name": SERVICE, "serviceType": "CustomDatabase",
                    "description": "The Data Catalog, published one way from the rules; change the rules, "
                                   f"not this catalog. Rules digest: `{rules_digest(root)}`."},
        "databases": [
            {"name": SOURCES, "service": SERVICE, "description": "Every source: its feeds and datasets."},
            {"name": MDM, "service": SERVICE, "description": "Clean MDM: every kind and its fields."}],
        "schemas": schemas + [{"name": CLEAN, "database": fqn(SERVICE, MDM),
                               "description": "The kinds Clean MDM masters."}],
        "tables": tables,
        "lineage": lineage,
    }


# --- publishing -------------------------------------------------------------------

class CatalogError(RuntimeError):
    """The catalog server refused a request."""


Call = Callable[..., Any]  # call(method, path, body=None, params=None) -> the JSON answer, or None if not found


def connect(url: str, token: str) -> Call:
    """Requests to one OpenMetadata server's API, as a bot. The token goes in
    a header only; an error names the request and the server's answer."""
    base = url.rstrip("/") + "/api/v1"

    def call(method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
        query = "?" + urlencode(params) if params else ""
        request = Request(base + path + query, method=method,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=120) as answer:
                text = answer.read()
        except HTTPError as error:
            if error.code == 404 and method in ("GET", "DELETE"):
                return None
            raise CatalogError(f"{method} {path}: {error.code} {error.read()[:500]!r}") from None
        return json.loads(text) if text else None

    return call


def _listed(call: Call, path: str, params: dict) -> list[dict]:
    found, after = [], None
    while True:
        page = call("GET", path, params={**params, "limit": 1000, **({"after": after} if after else {})}) or {}
        found += page.get("data") or []
        after = (page.get("paging") or {}).get("after")
        if not after:
            return found


def publish(plan: dict, call: Call) -> dict:
    """Make the catalog equal to `plan`: create or update everything it names,
    then delete, inside its own service only, the tables, schemas and lineage
    it no longer names. Publishing the same plan again changes nothing."""
    call("PUT", "/services/databaseServices", plan["service"])
    for database in plan["databases"]:
        call("PUT", "/databases", database)
    for schema in plan["schemas"]:
        call("PUT", "/databaseSchemas", schema)
    ids = {}  # a planned table's name -> its id
    for table in plan["tables"]:
        name, answer = f"{table['databaseSchema']}.{quote(table['name'])}", call("PUT", "/tables", table)
        if answer["fullyQualifiedName"] != name:  # lineage names columns by this name
            raise CatalogError(f"The server named table {name} {answer['fullyQualifiedName']}")
        ids[name] = answer["id"]
    service = plan["service"]["name"]
    removed = {"tables": 0, "schemas": 0, "databases": 0, "lineage": 0}
    for table in _listed(call, "/tables", {"service": service}):
        if table["fullyQualifiedName"] not in ids:
            call("DELETE", f"/tables/{table['id']}", params={"hardDelete": "true"})
            removed["tables"] += 1
    planned_schemas = {f"{s['database']}.{quote(s['name'])}" for s in plan["schemas"]}
    planned_databases = {fqn(service, d["name"]) for d in plan["databases"]}
    for database in _listed(call, "/databases", {"service": service}):
        if database["fullyQualifiedName"] not in planned_databases:
            call("DELETE", f"/databases/{database['id']}", params={"hardDelete": "true", "recursive": "true"})
            removed["databases"] += 1
            continue
        for schema in _listed(call, "/databaseSchemas", {"database": database["fullyQualifiedName"]}):
            if schema["fullyQualifiedName"] not in planned_schemas:
                call("DELETE", f"/databaseSchemas/{schema['id']}", params={"hardDelete": "true", "recursive": "true"})
                removed["schemas"] += 1
    upstream: dict[str, set] = defaultdict(set)
    for edge in plan["lineage"]:
        to, source = ids[edge["to"]], ids[edge["from"]]
        upstream[to].add(source)
        details = {"description": edge["description"], "columnsLineage": edge["columns"]}
        call("PUT", "/lineage", {"edge": {"fromEntity": {"id": source, "type": "table"},
                                          "toEntity": {"id": to, "type": "table"},
                                          "description": edge["description"], "lineageDetails": details}})
    for name, table_id in sorted(ids.items()):
        graph = call("GET", f"/lineage/table/name/{escape(name, safe='')}", params={"upstreamDepth": 1, "downstreamDepth": 0}) or {}
        for edge in graph.get("upstreamEdges") or []:
            if edge["toEntity"] == table_id and edge["fromEntity"] not in upstream[table_id]:
                call("DELETE", f"/lineage/table/{edge['fromEntity']}/table/{table_id}")
                removed["lineage"] += 1
    return {"service": service, "tables": len(plan["tables"]), "lineage": len(plan["lineage"]), "removed": removed}
