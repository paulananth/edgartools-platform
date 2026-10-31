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
  fields, each naming the datasets that fill it in order (the first with a
  value wins);
- lineage: feed to the datasets it captures, and dataset to kind, column by
  column (the source paths that fill each MDM field);
- from a source's approved profile (`profile.yaml`, written by data-profiling's
  `catalog` from approved findings: names and counts only) and its registered
  silver specs (`silver-*.yaml`, which replace the profile's proposal of the
  same table), database `silver`: a schema per source, a table per part, a
  column per silver field, each with the data quality rules it needs; and
  database `rdm`, schema `code_sets`: a
  table per code set the data needs, with lineage from each silver table that
  uses it;
- one subject domain per mastered kind and per relationship endpoint, the
  glossaries for those domains, and Gold on the master store and Silver on
  the prepared store. A relationship type is that asset on its endpoint
  domains. A mention is not a relation.

`plan` is pure: the rules in, the catalog as data out. `publish` sends it.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote as escape, urlencode
from urllib.request import Request, urlopen

from edgar_warehouse.silver_writer import spec as silver_spec

from . import files
from .mapdoc import critical_elements, mapped, paths, relationship_rows, winners

SERVICE = "edgartools-rules"
PIPELINES_SERVICE = SERVICE + "-pipelines"
SOURCES, MDM, CLEAN = "sources", "mdm", "clean"
SILVER, RDM, CODE_SETS = "silver", "rdm", "code_sets"
TEXT = "STRING"  # the catalog shows what a value means, not a database type
# One relationship endpoint the rules name differently from its catalog domain.
ENDPOINT_CATALOG_NAME = {"venue": "market_venue"}
GOLD, SILVER_MARK = "Certification.Gold", "Certification.Silver"
# A silver field's logical type, as the catalog names it (OpenMetadata calls a 32-bit
# integer INT); any other type is text.
TYPES = {"BIGINT": "BIGINT", "INTEGER": "INT", "DOUBLE": "DOUBLE", "DECIMAL": "DECIMAL", "BOOLEAN": "BOOLEAN",
         "DATE": "DATE", "TIMESTAMP": "TIMESTAMP", "TIMESTAMP WITH TIME ZONE": "TIMESTAMP"}


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


def _kinds(adapter: dict, known: set[str]) -> list[str]:
    """The kinds a dataset's records become, among those with merge rules."""
    named = {adapter.get("kind"), (adapter.get("classification") or {}).get("kind"),
             *(adapter.get("kind_values") or {}).values()}
    return sorted(k for k in named if k in known)


def _classified(kinds: dict, code: str) -> set[str]:
    """The fields a kind's classification rule reads from this dataset."""
    read = set()
    for rules in kinds.values():
        for rule in rules.get("rules") or []:
            if rule.get("family") == "classification" and rule.get("source") == code:
                for step in rule.get("steps") or []:
                    read |= {(w.get("args") or {}).get("field") for w in step.get("when") or []}
    return read - {None}


def _dataset(source: str, code: str, contract: dict, kinds: list[str], fills: dict[str, set],
             classified: set[str]) -> tuple[dict, list[dict]]:
    """A dataset's table, and its lineage to each kind it fills. `fills`:
    kind -> the fields the merge takes from this dataset (`winners`)."""
    adapter = contract.get("adapter") or {}
    uses: dict[str, list[str]] = defaultdict(list)  # source path -> what it is used for
    to_field: dict[str, list[str]] = defaultdict(list)  # MDM field -> source paths
    for ident, path in (adapter.get("identifiers") or {}).items():
        uses[path].append(f"Identifier `{ident}`")
    for path in adapter.get("record_key") or []:
        uses[path].append("Record key")
    for section, used in (("fields", "MDM field"), ("matching", "Matching only")):
        for field, spec in mapped(adapter, section).items():
            for part, path in paths(spec):
                uses[path].append(f"{used} `{field}`" + (f" ({part})" if part else ""))
                if section == "fields":
                    to_field[field].append(path)
    if adapter.get("kind_field"):
        uses[adapter["kind_field"]].append("Decides the kind")
    for path in classified:
        uses[path].append("Read by the classification rule")
    critical = [f"`{field}`: {test}" for _, field, test in critical_elements(contract.get("quality") or {})]
    record = contract.get("record_key") or "one source record"
    subjects = " and ".join(_display(kind) for kind in kinds) or "no mastered subject"
    about = [f"One record is {record}.", f"These records become {subjects}."]
    for kind in kinds:
        filled = sorted(fills.get(kind, set()) & set(to_field))
        label = _display(kind)
        about.append(f"It supplies {len(filled)} {label} fields." if filled else f"It supplies no {label} fields.")
    if critical:
        about.append("A record missing a required item is held back and is not merged.")
    table = {"name": code, "displayName": _sentence(f"One record is {record}", 80),
             "databaseSchema": fqn(SERVICE, SOURCES, source), "description": " ".join(about),
             "columns": [{"name": path, "dataType": TEXT, "description": "; ".join(used) + "."}
                         for path, used in sorted(uses.items())]}
    at = fqn(SERVICE, SOURCES, source, code)
    lineage = []
    for kind in kinds:
        columns = [{"fromColumns": [f"{at}.{quote(p)}" for p in sorted(set(read))],
                    "toColumn": fqn(SERVICE, MDM, CLEAN, kind, field)}
                   for field, read in sorted(to_field.items()) if field in fills.get(kind, set())]
        if columns:
            lineage.append({"from": at, "to": fqn(SERVICE, MDM, CLEAN, kind), "columns": columns,
                            "description": f"`{code}` fills these {kind} fields."})
    return table, lineage


def _profile(source: str, profile: dict) -> tuple[list[dict], dict[str, set]]:
    """A source's approved profile: a silver table per part, and which of its tables
    use each code set (for the rdm tables and their lineage)."""
    tables, uses = [], defaultdict(set)
    for part in profile.get("parts") or []:
        silver = part["silver"]
        rules = defaultdict(list)
        for rule in part.get("quality") or []:
            failed = f", {rule['failed_rows']} rows failed it when profiled" if rule["failed_rows"] else ""
            rules[rule["column"]].append(f"{rule['check']} ({rule['proposal']}{failed}): {rule['why']}")
        columns = []
        for field in silver["fields"]:
            about = [f"{'Nullable' if field['nullable'] else 'Always filled'}; sensitivity {field['sensitivity']}."]
            if field.get("code_set"):
                about.append(f"A code of RDM code set `{field['code_set']}`.")
                uses[field["code_set"]].add(fqn(SERVICE, SILVER, source, silver["table"]))
            about += [f"Data quality: {r}." for r in rules.get(field["name"], [])]
            columns.append({"name": field["name"], "dataType": TYPES.get(str(field["type"]).upper(), TEXT),
                            "description": " ".join(about)})
        about = [f"Part `{part['part']}` of `{profile['dataset']}`: {part['class']} data, {part['rows']} rows when "
                 f"profiled.", f"Key: {', '.join(silver['key']) or 'none found'}; load mode {silver['load_mode']}."]
        if part.get("kind"):
            about.append(f"MDM kind `{part['kind']}`.")
        about += [f"`{link['mdm_id_column']}` holds the MDM id of `{link['to_part']}` by `{link['source_key']}`."
                  for link in silver.get("links") or []]
        about += [f"Data quality: {r}." for r in rules.get(None, [])]
        tables.append({"name": silver["table"], "databaseSchema": fqn(SERVICE, SILVER, source),
                       "description": " ".join(about), "columns": columns})
    return tables, uses


def _registered(source: str, spec: dict) -> dict:
    """A silver table as `silver register` makes it from the source's spec
    (`silver-*.yaml`): its columns, the MDM id each link fills, the quality
    column its checks write and the load time it adds (`silver_spec.columns`)."""
    spec = silver_spec.check(spec)
    checks = defaultdict(list)
    for check in spec.get("checks") or []:
        checks[check.get("column")].append(f"{check['id']} ({check['on_fail']}): {check['why']}")
    columns = []
    for column in spec["columns"]:
        about = [column.get("definition") or "",
                 f"{'Nullable' if column['nullable'] else 'Always filled'}; sensitivity {column['sensitivity']}."]
        about += [f"Data quality: {c}." for c in checks.get(column["name"], [])]
        columns.append({"name": column["name"], "dataType": TYPES.get(str(column["type"]).upper(), TEXT),
                        "description": " ".join(a for a in about if a)})
    columns += [{"name": link["mdm_id_column"], "dataType": TEXT,
                 "description": f"The MDM id of the {link['kind']} `{', '.join(link['columns'])}` names, "
                                f"among the records of `{link['source_code']}`; empty until it is mastered."}
                for link in spec.get("links") or []]
    columns += [{"name": name, "dataType": TEXT, "description": "The data quality checks this row failed, by id "
                 "(each flagged, the row still landed); empty when it passed every one."}
                for name in silver_spec.quality_columns(spec)]
    columns += [{"name": name, "dataType": "TIMESTAMP", "description": "When the row's delivered values were last "
                 "written (the as-at time)."} for name in silver_spec.added_time(spec)]
    if [c["name"] for c in columns] != silver_spec.columns(spec):
        raise ValueError(f"The catalog must show every column {spec['table']} lands: {silver_spec.columns(spec)}")
    about = [spec.get("definition") or "", f"Grain: {spec['grain']}." if spec.get("grain") else "",
             f"Key: {', '.join(spec['key'])}; load mode {spec['load_mode']}."]
    about += [f"Data quality: {c}." for c in checks.get(None, [])]
    description = " ".join(a for a in about if a)
    return {"name": spec["table"], "displayName": _sentence(spec.get("definition") or spec["table"], 80),
            "databaseSchema": fqn(SERVICE, SILVER, source),
            "description": description, "columns": columns}


def _profiles(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Every source's silver schema and tables, a table per code set the profiled
    data needs, and lineage from each code set to the tables using it. A table
    the source registers (`silver-*.yaml`, what `silver register` makes) replaces
    its approved profile's proposal of the same name, so the catalog shows the
    table as it lands."""
    tables, lineage = [], []
    silver_schemas, code_sets, used_by = [], {}, defaultdict(set)
    registered = {}
    for path in sorted((root / "sources").glob("*/silver-*.yaml")):
        table = _registered(path.parent.name, files.load(path))
        registered[(table["databaseSchema"], table["name"])] = table
    for path in sorted((root / "sources").glob("*/profile.yaml")):
        profile, source = files.load(path), path.parent.name
        silver_schemas.append({"name": source, "database": fqn(SERVICE, SILVER),
                               "description": f"Silver tables of `{source}`, from its approved profile "
                                              f"(rules/sources/{source}/profile.yaml)."})
        found, uses = _profile(source, profile)
        tables += found
        for code_set in profile.get("code_sets") or []:
            known = code_sets.setdefault(code_set["code_set"], {"codes": 0, "columns": [], "existing": False})
            known["codes"] = max(known["codes"], code_set["codes"])
            known["columns"] += [f"{source}: {c}" for c in code_set["columns"]]
            known["existing"] |= code_set["existing"]
        for name, at in uses.items():
            used_by[name] |= at
    tables = [t for t in tables if (t["databaseSchema"], t["name"]) not in registered]
    tables += [registered[k] for k in sorted(registered)]
    profiled = {s["name"] for s in silver_schemas}
    for source in sorted({path.parent.name for path in (root / "sources").glob("*/silver-*.yaml")} - profiled):
        silver_schemas.append({"name": source, "database": fqn(SERVICE, SILVER),
                               "description": f"Silver tables of `{source}`, as registered "
                                              f"(rules/sources/{source}/silver-*.yaml)."})
    for name, known in sorted(code_sets.items()):
        tables.append({"name": name, "databaseSchema": fqn(SERVICE, RDM, CODE_SETS),
                       "description": f"RDM code set `{name}`" + (" (published)" if known["existing"] else
                                                                 " (proposed: a draft until approved in RDM)")
                       + f": {known['codes']} codes when profiled. Used by " + ", ".join(sorted(known["columns"])) + ".",
                       "columns": [{"name": "code", "dataType": TEXT, "description": "The code."},
                                   {"name": "label", "dataType": TEXT, "description": "What the code means."}]})
        lineage += [{"from": fqn(SERVICE, RDM, CODE_SETS, name), "to": at, "columns": [],
                     "description": f"Values of `{at}` are codes of `{name}`."} for at in sorted(used_by[name])]
    return silver_schemas, tables, lineage


def _feeds(body: dict) -> list[tuple[str, dict]]:
    """A source's declared feeds, by name."""
    return sorted(((body.get("acquisition") or {}).get("feeds") or {}).items())


def _pipelines(root: Path) -> list[dict]:
    """Native catalog pipelines for every declared source and standalone target."""
    result = []
    for folder, scope, filename in (("sources", "source", "source.yaml"),
                                    ("pipelines", "pipeline", "pipeline.yaml")):
        for path in sorted((root / folder).glob("*/" + filename)):
            body = files.load_source(path) if scope == "source" else files.load(path)
            for name, target in sorted(((body.get("bookkeeping") or {}).get("targets") or {}).items()):
                steps = target.get("steps") or []
                tasks = [{"name": step["name"], "taskType": step["operation"],
                          "description": f"Key: {step.get('key')}. Leases: {step.get('leases') or []}. "
                                         f"Checks: {step.get('checks') or []}.",
                          "downstreamTasks": [other["name"] for other in steps
                                              if step["name"] in (other.get("requires") or [])]}
                         for step in steps]
                result.append({"name": f"{scope}:{path.parent.name}:{name}", "service": PIPELINES_SERVICE,
                               "description": f"Configured {scope} `{path.parent.name}`, target `{name}`. "
                                              f"Definition only; approval, activation and runs are separate. "
                                              f"Run checks: {target.get('checks') or []}.",
                               "pipelineLocation": path.relative_to(root).as_posix(), "tasks": tasks})
    return result


def _service_lineage(pipelines: list[dict], tables: list[dict]) -> list[dict]:
    """The Lineage page draws a line only between services. Dataset edges stay
    inside one database service, so that page stays blank until a pipeline
    points at a table."""
    by_source: dict[str, list[str]] = defaultdict(list)
    for table in tables:
        schema = table["databaseSchema"]
        if ".sources." not in schema:
            continue
        source = schema.split(".sources.", 1)[1].strip('"')
        by_source[source].append(_table_name(table))
    edges = []
    for pipeline in pipelines:
        scope, _, rest = pipeline["name"].partition(":")
        source, _, target = rest.partition(":")
        if scope != "source" or not by_source.get(source):
            continue
        for table in by_source[source]:
            edges.append({"pipeline": fqn(PIPELINES_SERVICE, pipeline["name"]), "table": table,
                          "description": f"The {target} pipeline of {source} reads or writes this dataset."})
    return edges


def _relationships(root: Path, policy: dict) -> tuple[list[dict], list[dict]]:
    """Pinned type definitions and the declared datasets that supply them."""
    from .mapdoc import relationship_rows
    rows = relationship_rows(root, policy)
    roots = {r["code"]: r for r in rows if r.get("parent_code") is None}
    tables, lineage = [], []
    for name, row in sorted(roots.items()):
        props = row.get("properties") or {}
        capacities = [{"code": r["code"], "label": r["label"], "properties": r.get("properties") or {}}
                      for r in rows if r.get("parent_code") == name]
        origin = ", ".join(_display(ENDPOINT_CATALOG_NAME.get(code, code)) for code in (props.get("from") or []))
        destination = ", ".join(_display(ENDPOINT_CATALOG_NAME.get(code, code)) for code in (props.get("to") or []))
        roles = ", ".join(item["label"] for item in capacities if item.get("label"))
        text = row.get("definition") or row["label"]
        if origin or destination:
            text += f" From {origin or 'one subject'} to {destination or 'one subject'}."
        if roles:
            text += f" Roles: {roles}."
        tables.append({"name": name, "displayName": row.get("label") or _display(name),
                       "databaseSchema": fqn(SERVICE, MDM, "relationships"),
                       "description": text,
                       "columns": [{"name": key, "dataType": TEXT,
                                    "description": json.dumps(value, ensure_ascii=False, sort_keys=True)}
                                   for key, value in sorted(props.items())]})
    return tables, lineage


def _display(name: str) -> str:
    return " ".join(part.capitalize() for part in name.replace("-", " ").split("_"))


def _sentence(text: str, limit: int = 220) -> str:
    plain = " ".join(str(text).replace("`", "").split())
    sentence = plain.split(". ")[0].strip(" .")
    if len(sentence) > limit:
        sentence = sentence[: limit - 1].rstrip() + "…"
    return sentence


def _table_name(table: dict) -> str:
    return f"{table['databaseSchema']}.{quote(table['name'])}"


def _store(name: str) -> str:
    """The plan database in a table's fully qualified name."""
    return name[len(SERVICE) + 1:].split(".", 1)[0].strip('"')


def _context_terms(root: Path) -> list[tuple[str, str]]:
    """Bold terms in the two glossary sections of CONTEXT.md, when that file
    sits beside the rules. A copy of the rules alone has no second glossary."""
    path = root.parent / "CONTEXT.md"
    if not path.is_file():
        return []
    text = path.read_text()
    chunks = []
    for heading in ("### MDM identities and mastering", "### Data classes, reference data and agent context"):
        start = text.find(heading)
        if start < 0:
            continue
        rest = text[start + len(heading):]
        stop = rest.find("\n### ")
        chunks.append(rest if stop < 0 else rest[:stop])
    found = []
    for match in re.finditer(r"\*\*(.+?)\*\*:\n(.*?)(?=\n\*\*|\Z)", "\n".join(chunks), re.S):
        block = match.group(2).strip()
        definition, _, avoid = block.partition("_Avoid_:")
        description = " ".join(definition.split())
        if avoid.strip():
            description += "\n\nAvoid: " + " ".join(avoid.split())
        found.append((match.group(1).strip(), description))
    return found


def _meaning(root: Path, policy: dict, tables: list[dict], lineage: list[dict]) -> dict:
    """Subject domains, their glossaries, and store certifications. A
    relationship type is one asset. Its ends are not extra domain links."""
    rows = relationship_rows(root, policy)
    kinds = set((policy.get("kinds") or {}))
    ends = set()
    roots = []
    for row in rows:
        if row.get("parent_code"):
            continue
        roots.append(row)
        props = row.get("properties") or {}
        for code in (props.get("from") or []) + (props.get("to") or []):
            ends.add(ENDPOINT_CATALOG_NAME.get(code, code))
    names = sorted(kinds | ends)
    kind_tables = {fqn(SERVICE, MDM, CLEAN, kind): kind for kind in kinds}
    words = {heading: _sentence(description.split("Avoid:")[0], 240)
             for heading, description in _context_terms(root)}
    domains = []
    for name in names:
        display = _display(name)
        description = words.get(f"{display} Identity") or words.get(display)
        if not description and name in kinds:
            description = f"One {display} in the master data."
        if not description:
            description = f"A {display} that a relationship can point to."
        domains.append({"name": name, "displayName": display, "description": description,
                        "domainType": "Source-aligned"})
    by_display = sorted(domains, key=lambda domain: len(domain["displayName"]), reverse=True)

    def glossary_of(heading: str) -> str:
        for domain in by_display:
            display = domain["displayName"]
            if heading == display or heading == f"{display} Identity" or heading.startswith(display + " "):
                return domain["name"]
        return "shared"

    terms = [{"name": heading, "displayName": heading, "description": description,
              "glossary": glossary_of(heading)} for heading, description in _context_terms(root)]
    by_term = {term["name"]: term for term in terms}
    for row in roots:
        by_term[row["code"]] = {
            "name": row["code"], "displayName": row.get("label") or row["code"],
            "description": row.get("definition") or row["label"], "glossary": "shared",
            "table": fqn(SERVICE, MDM, "relationships", row["code"])}
    membership: dict[str, set[str]] = defaultdict(set)
    for name, kind in kind_tables.items():
        membership[name].add(kind)
    for edge in lineage:
        if edge["to"] in kind_tables:
            membership[edge["from"]].add(kind_tables[edge["to"]])
    present = {_table_name(table) for table in tables}
    for table in tables:
        name = _table_name(table)
        if table["name"] in {"company_fact", "company_line_item", "company_measure"}:
            membership[name].add("company")
        elif table["name"] == "openfigi_listing":
            membership[name].add("security")
    memberships = [{"table": name, "domains": sorted(domains_)} for name, domains_ in sorted(membership.items()) if name in present and domains_]
    certifications = []
    for table in tables:
        name = _table_name(table)
        store = _store(name)
        if store == MDM:
            certifications.append({"table": name, "tag": GOLD})
        elif store == SILVER:
            certifications.append({"table": name, "tag": SILVER_MARK})
    glossaries = [{"name": domain["name"], "displayName": domain["displayName"], "description":
                   "The words for this subject, taken from the platform glossary. A projection. Not an approval.",
                   "domains": [domain["name"]]} for domain in domains]
    glossaries.append({"name": "shared", "displayName": "Shared", "description":
                       "Words that apply to more than one subject, or to mastering and reference data, "
                       "taken from the platform glossary. A projection. Not an approval."})
    domain_lineage = []
    known = set(names)
    for row in roots:
        props = row.get("properties") or {}
        ends = []
        for code in (props.get("from") or []) + (props.get("to") or []):
            domain = ENDPOINT_CATALOG_NAME.get(code, code)
            if domain in known and domain not in ends:
                ends.append(domain)
        table = fqn(SERVICE, MDM, "relationships", row["code"])
        description = row["code"] + ": " + (row.get("definition") or row["label"])
        for domain in ends:
            domain_lineage.append({"domain": domain, "table": table, "description": description})
    def subject_assets(domain: str) -> list[str]:
        prefix = fqn(SERVICE, MDM, CLEAN, domain)
        return sorted(name for name, domains_ in membership.items()
                      if domain in domains_ and (name == prefix or f".{SOURCES}." in name) and name in present)
    facts = sorted(name for name in membership if name.endswith(("company_fact", "company_line_item", "company_measure")) and "company" in membership[name])
    listing = sorted(name for name in membership if name.endswith("openfigi_listing") and "security" in membership[name])
    company_assets = subject_assets("company")
    security_assets = sorted(set(subject_assets("security")) | set(listing))
    products = [
        {"name": "company_master", "displayName": "Company master", "domains": ["company"],
         "dataProductType": "DATASET",
         "description": "The mastered legal entity and the datasets that fill it.",
         "tables": company_assets,
         "inputs": [name for name in company_assets if f".{SOURCES}." in name]},
        {"name": "security_master", "displayName": "Security master", "domains": ["security"],
         "dataProductType": "DATASET",
         "description": "The mastered instrument, the datasets that fill it, and its registered listing.",
         "tables": security_assets,
         "inputs": [name for name in security_assets if f".{SOURCES}." in name]},
        {"name": "company_fundamentals", "displayName": "Company fundamentals", "domains": ["company"],
         "dataProductType": "DERIVED_DATA",
         "description": "Filed figures, standard line items, and fundamental measures for one subject.",
         "tables": facts,
         "inputs": [name for name in facts if name.endswith(("company_fact", "company_line_item"))]},
    ]
    return {"domains": domains, "glossaries": glossaries,
            "glossary_terms": [by_term[name] for name in sorted(by_term)],
            "memberships": memberships, "certifications": certifications,
            "domain_lineage": domain_lineage, "products": products}


def _rule_text(kind: str, rule: dict, version: str, path: str) -> str:
    parts = ["Correction, not a check. It changes a value. It is not a test result."
             if kind == "fix" else
             "Configured check. The catalog stores the definition only. It does not record a pass or a fail."]
    parts.append(f"Id `{rule.get('id')}`.")
    if rule.get("test"):
        parts.append(f"Test `{rule['test']}`.")
    if rule.get("check"):
        parts.append(f"Check `{rule['check']}`.")
    if rule.get("value"):
        parts.append(f"Value `{rule['value']}`.")
    if rule.get("column"):
        parts.append(f"Column `{rule['column']}`.")
    if rule.get("on_fail"):
        parts.append(f"On fail: {rule['on_fail']}.")
    if rule.get("why"):
        parts.append(str(rule["why"]))
    if rule.get("args"):
        parts.append("Arguments: " + json.dumps(rule["args"], sort_keys=True, ensure_ascii=False))
    if version:
        parts.append(f"Rules version `{version}`.")
    parts.append(f"Rules file `{path}`.")
    return " ".join(parts)


def _quality_case(table: str, columns: set[str], code: str, kind: str, rule: dict, version: str, path: str) -> dict:
    column = rule.get("column")
    if column in columns:
        link = f"<#E::table::{table}::columns::{column}>"
        definition = "edgartools-configured-column-check"
    else:
        link = f"<#E::table::{table}>"
        definition = "edgartools-configured-table-check"
    return {"name": f"{code}.{rule['id']}", "displayName": rule["id"], "description": _rule_text(kind, rule, version, path),
            "testDefinition": definition, "entityLink": link, "kind": kind}


def _quality(root: Path, tables: list[dict]) -> dict:
    """Configured checks and fixes. A profile proposal is not a case, and a
    case has no pass or fail result."""
    by_name = {_table_name(table): table for table in tables}
    cases = []
    for path in sorted((root / "sources").glob("*/source.yaml")):
        body = files.load_source(path)
        source = body.get("source") or path.parent.name
        for code, entry in sorted((body.get("mdm") or {}).items()):
            quality = ((entry.get("contract") or {}).get("quality") or {})
            table_name = fqn(SERVICE, SOURCES, source, code)
            table = by_name.get(table_name)
            if not table or not quality:
                continue
            columns = {column["name"] for column in table["columns"]}
            version, rules_path = quality.get("version") or "", path.parent.joinpath("quality.yaml").relative_to(root).as_posix()
            for kind, key in (("check", "checks"), ("fix", "fixes")):
                for rule in quality.get(key) or []:
                    cases.append(_quality_case(table_name, columns, code, kind, rule, version, rules_path))
    for path in sorted((root / "sources").glob("*/silver-*.yaml")):
        spec = files.load(path)
        table_name = fqn(SERVICE, SILVER, path.parent.name, spec["table"])
        table = by_name.get(table_name)
        if not table:
            continue
        columns = {column["name"] for column in table["columns"]}
        rules_path = path.relative_to(root).as_posix()
        for rule in spec.get("checks") or []:
            cases.append(_quality_case(table_name, columns, spec["table"], "check", rule, "", rules_path))
    definitions = [
        {"name": "edgartools-configured-table-check", "displayName": "Configured table check",
         "description": "A check or a correction from the rules. OpenMetadata does not execute it.",
         "entityType": "TABLE", "testPlatforms": ["Other"]},
        {"name": "edgartools-configured-column-check", "displayName": "Configured column check",
         "description": "A check on one column from the rules. OpenMetadata does not execute it.",
         "entityType": "COLUMN", "testPlatforms": ["Other"]}]
    return {"quality_definitions": definitions, "quality_cases": cases}


def plan(root: Path | None = None) -> dict:
    """The whole catalog the rules under `root` describe, sorted, so the same
    rules always give the same plan."""
    root = root or files.ROOT
    policy = files.policy(root)
    kinds = policy.get("kinds") or {}
    by_kind = winners(policy, root)
    schemas, tables, lineage = [], [], []
    silver_schemas, profiled, profiled_lineage = _profiles(root)
    tables += profiled
    lineage += profiled_lineage
    relationship_tables, relationship_lineage = _relationships(root, policy)
    tables += relationship_tables
    lineage += relationship_lineage
    bodies = [(path, files.load_source(path)) for path in sorted((root / "sources").glob("*/source.yaml"))]
    # A feed captures one bronze family; a source that declares no feed of its own
    # reads the files of each feed that captures its family (a second kind from
    # another source's files).
    captured: dict[str, list[tuple[str, str]]] = {}
    for path, body in bodies:
        for feed, spec in _feeds(body):
            if spec.get("family"):
                captured.setdefault(spec["family"], []).append((body.get("source") or path.parent.name, feed))
    for path, body in bodies:
        source = body.get("source") or path.parent.name
        mdm = body.get("mdm") or {}
        schemas.append({"name": source, "database": fqn(SERVICE, SOURCES),
                        "description": f"The source `{source}`: rules/sources/{path.parent.name}/."})
        for feed, spec in _feeds(body):
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
        family = (body.get("bronze") or {}).get("family")
        for owner, feed in (captured.get(family, []) if family and not _feeds(body) else []):
            for code in sorted(mdm):
                lineage.append({"from": fqn(SERVICE, SOURCES, owner, feed),
                                "to": fqn(SERVICE, SOURCES, source, code), "columns": [],
                                "description": f"Dataset `{code}` reads the {family} files feed `{feed}` "
                                               f"of `{owner}` captures."})
        for code, entry in sorted(mdm.items()):
            contract = entry.get("contract") or {}
            fills = {kind: {f for f, (sources, _) in by_field.items() if code in sources}
                     for kind, by_field in by_kind.items()}
            table, edges = _dataset(source, code, contract, _kinds(contract.get("adapter") or {}, set(kinds)),
                                    fills, _classified(kinds, code))
            tables.append(table)
            lineage += edges
    for kind, rules in sorted(kinds.items()):
        order = (rules.get("defaults") or {}).get("sources") or []
        columns = []
        for field, (sources, row) in sorted(by_kind.get(kind, {}).items()):
            _, _, which, at = row
            filled = ", then ".join(s for s in sources) or "no dataset yet"
            columns.append({"name": field, "dataType": TEXT, "description":
                            f"Filled by {filled}: the first with a value wins. "
                            f"Rule: {which} (rules/{at})."})
        tables.append({"name": kind, "displayName": _display(kind),
                       "databaseSchema": fqn(SERVICE, MDM, CLEAN), "columns": columns,
                       "description": f"One {_display(kind)} in the master data. "
                                      "The first dataset with a value fills each field."})
    return {
        "service": {"name": SERVICE, "serviceType": "CustomDatabase",
                    "description": "The Data Catalog, published one way from the rules; change the rules, "
                                   f"not this catalog. Rules digest: `{rules_digest(root)}`."},
        "databases": [
            {"name": SOURCES, "service": SERVICE, "description": "Every source: its feeds and datasets."},
            {"name": MDM, "service": SERVICE, "description": "MDM: every kind and its fields."},
            *([{"name": SILVER, "service": SERVICE,
                "description": "Silver: every registered or profiled table and its fields, with their data quality rules."},
               {"name": RDM, "service": SERVICE, "description": "RDM: the code sets the profiled data needs."}]
              if silver_schemas else [])],
        "schemas": schemas + [{"name": CLEAN, "database": fqn(SERVICE, MDM),
                               "description": "The kinds MDM masters."}]
                   + ([{"name": "relationships", "database": fqn(SERVICE, MDM),
                        "description": "Pinned relationship types. One asset per type. The ends stay on the type."}]
                      if relationship_tables else []) + silver_schemas
                   + ([{"name": CODE_SETS, "database": fqn(SERVICE, RDM), "description": "Code sets, by name."}]
                      if silver_schemas else []),
        "tables": tables,
        "lineage": lineage,
        "pipeline_service": {"name": PIPELINES_SERVICE, "serviceType": "CustomPipeline",
                             "description": f"Configured pipeline definitions; rules digest `{rules_digest(root)}`. "
                                            "This catalog does not enable schedules or run workloads."},
        "pipelines": _pipelines(root),
        "service_lineage": _service_lineage(_pipelines(root), tables),
        **_meaning(root, policy, tables, lineage),
        **_quality(root, tables),
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
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json-patch+json" if method == "PATCH" else "application/json"})
        try:
            with urlopen(request, timeout=120) as answer:
                text = answer.read()
        except HTTPError as error:
            if error.code == 404 and method in ("GET", "DELETE"):
                return None
            raise CatalogError(f"{method} {path}: {error.code} {error.read()[:500]!r}") from None
        except URLError as error:
            raise CatalogError(f"{method} {path}: the catalog server did not answer ({error.reason})") from None
        return json.loads(text) if text else None

    return call


def _listed(call: Call, path: str, params: dict, service: str = SERVICE) -> list[dict]:
    """Every entity the server lists, page by page, keeping only those inside
    our own service: a publish never touches another service, even when a
    server ignores the filter it was asked for."""
    found, after = [], None
    while True:
        page = call("GET", path, params={**params, "limit": 1000, **({"after": after} if after else {})}) or {}
        found += [e for e in page.get("data") or [] if e["fullyQualifiedName"].startswith(service + ".")]
        after = (page.get("paging") or {}).get("after")
        if not after:
            return found


def _description_equal(expected, actual):
    # The native Markdown API HTML-escapes characters once at rest.
    return expected == html.unescape(actual) if isinstance(expected, str) and isinstance(actual, str) else expected == actual


def _upsert(call: Call, endpoint: str, body: dict, expected_name: str | None = None) -> dict:
    """Reconcile rule-owned descriptions even when a bot PUT preserves them."""
    parent = body.get("databaseSchema") or body.get("database") or body.get("service")
    expected = expected_name or (parent + "." + quote(body["name"]) if parent else body["name"])
    answer = call("PUT", endpoint, body)
    if answer.get("fullyQualifiedName") != expected:
        kind = "table" if endpoint == "/tables" else "pipeline" if endpoint == "/pipelines" else endpoint
        raise CatalogError(f"The server named {kind} {expected} {answer.get('fullyQualifiedName')}")
    changes = []
    if "description" in body and not _description_equal(body["description"], answer.get("description")):
        changes.append({"op": "add", "path": "/description", "value": body["description"]})
    columns = {column["name"]: index for index, column in enumerate(answer.get("columns") or [])}
    for column in body.get("columns") or []:
        if column["name"] in columns and "description" in column:
            index = columns[column["name"]]
            if not _description_equal(column["description"], answer["columns"][index].get("description")):
                changes.append({"op": "add", "path": f"/columns/{index}/description", "value": column["description"]})
    if changes:
        updated = call("PATCH", endpoint + "/" + answer["id"], changes)
        if updated.get("fullyQualifiedName") != expected or updated.get("id") != answer["id"]:
            raise CatalogError(f"The server changed the identity of {expected}")
        answer = updated
    return answer


def _allow_several_domains(call: Call) -> None:
    """A relationship type belongs to every endpoint. The server's default
    refuses more than one domain, so that rule is switched off when a plan
    needs it. Other rules stay as the server has them."""
    page = call("GET", "/system/settings") or {}
    row = next((item for item in page.get("data") or [] if item.get("config_type") == "entityRulesSettings"), None)
    rules = ((row or {}).get("config_value") or {}).get("entitySemantics") or []
    changed = False
    for rule in rules:
        if rule.get("name") == "Multiple Domains are not allowed" and rule.get("enabled", True):
            rule["enabled"] = False
            changed = True
    if changed:
        call("PUT", "/system/settings", {"config_type": row["config_type"], "config_value": row["config_value"]})


def _validity_days(call: Call) -> int | None:
    page = call("GET", "/system/settings") or {}
    row = next((item for item in page.get("data") or [] if item.get("config_type") == "assetCertificationSettings"), None)
    period = ((row or {}).get("config_value") or {}).get("validityPeriod") or ""
    if period.startswith("P") and period.endswith("D") and period[1:-1].isdigit():
        return int(period[1:-1])
    return None


def _publish_vocabulary(plan: dict, call: Call) -> None:
    for domain in plan.get("domains") or []:
        _upsert(call, "/domains", domain)
    for glossary in plan.get("glossaries") or []:
        _upsert(call, "/glossaries", glossary)
    for term in plan.get("glossary_terms") or []:
        body = {key: term[key] for key in ("name", "displayName", "description", "glossary")}
        expected = f"{body['glossary']}.{quote(body['name'])}"
        answer = call("PUT", "/glossaryTerms", body) or {}
        if answer.get("fullyQualifiedName") != expected:
            raise CatalogError(f"The server named glossary term {expected} {answer.get('fullyQualifiedName')}")
        term["fullyQualifiedName"] = expected
    if any(len(item["domains"]) > 1 for item in plan.get("memberships") or []):
        _allow_several_domains(call)


def _drop_invented_domain_edges(plan: dict, call: Call) -> None:
    """A table on two domains makes the server draw a domain-to-domain edge.
    That edge is not a relationship type. Remove it."""
    for domain in plan.get("domains") or []:
        graph = call("GET", "/lineage/domain/name/" + escape(domain["name"], safe=""),
                     params={"upstreamDepth": 1, "downstreamDepth": 1}) or {}
        edges = (graph.get("upstreamEdges") or []) + (graph.get("downstreamEdges") or [])
        for edge in edges:
            details = edge.get("lineageDetails") or {}
            if details.get("source") != "ChildAssets":
                continue
            call("DELETE", f"/lineage/domain/{edge['fromEntity']}/domain/{edge['toEntity']}")


def _publish_marks(plan: dict, call: Call, ids: dict[str, str]) -> None:
    days = _validity_days(call)
    now = int(time.time() * 1000)
    for item in plan.get("certifications") or []:
        if days is None or item["table"] not in ids:
            continue
        call("PATCH", f"/tables/{ids[item['table']]}", [{
            "op": "add", "path": "/certification",
            "value": {"tagLabel": {"tagFQN": item["tag"], "source": "Classification",
                                   "labelType": "Manual", "state": "Confirmed"},
                      "appliedDate": now, "expiryDate": now + days * 24 * 60 * 60 * 1000}}])
    for term in plan.get("glossary_terms") or []:
        table = term.get("table")
        if table not in ids:
            continue
        call("PATCH", f"/tables/{ids[table]}", [{
            "op": "add", "path": "/tags/-",
            "value": {"tagFQN": term["fullyQualifiedName"], "source": "Glossary",
                      "labelType": "Manual", "state": "Suggested"}}])


def publish(plan: dict, call: Call) -> dict:
    """Make the catalog equal to `plan`: create or update everything it names,
    then delete, inside its own service only, the tables, schemas and lineage
    it no longer names. Publishing the same plan again changes nothing."""
    _upsert(call, "/services/databaseServices", plan["service"])
    _publish_vocabulary(plan, call)
    for database in plan["databases"]:
        _upsert(call, "/databases", database)
    for schema in plan["schemas"]:
        _upsert(call, "/databaseSchemas", schema)
    ids = {}  # a planned table's name -> its id
    domains_of = {item["table"]: item["domains"] for item in plan.get("memberships") or []}
    for table in plan["tables"]:
        body = dict(table)
        name = f"{table['databaseSchema']}.{quote(table['name'])}"
        if name in domains_of:
            body["domains"] = domains_of[name]
        name, answer = name, _upsert(call, "/tables", body)
        if table["databaseSchema"].endswith(".relationships"):
            # A put that omits domains leaves the old ends in place, and each
            # end is stored as another relationship. Clear them.
            call("PATCH", f"/tables/{answer['id']}", [{"op": "replace", "path": "/domains", "value": []}])
        if answer["fullyQualifiedName"] != name:  # lineage names columns by this name
            raise CatalogError(f"The server named table {name} {answer['fullyQualifiedName']}")
        ids[name] = answer["id"]
    for definition in plan.get("quality_definitions") or []:
        _upsert(call, "/dataQuality/testDefinitions", definition)
    for case in plan.get("quality_cases") or []:
        body = {key: case[key] for key in ("name", "displayName", "description", "testDefinition", "entityLink")}
        answer = call("PUT", "/dataQuality/testCases", body) or {}
        table = case["entityLink"].removeprefix("<#E::table::").split("::columns::")[0].removesuffix(">")
        column = ""
        if "::columns::" in case["entityLink"]:
            column = case["entityLink"].split("::columns::", 1)[1].removesuffix(">") + "."
        expected = f"{table}.{column}{quote(case['name'])}"
        if answer.get("fullyQualifiedName") != expected:
            raise CatalogError(f"The server named quality case {expected} {answer.get('fullyQualifiedName')}")
    _publish_marks(plan, call, ids)
    _drop_invented_domain_edges(plan, call)
    for product in plan.get("products") or []:
        answer = call("PUT", "/dataProducts", {key: product[key] for key in
                      ("name", "displayName", "description", "domains", "dataProductType")}) or {}
        if answer.get("fullyQualifiedName") not in (None, product["name"]):
            raise CatalogError(f"The server named data product {product['name']} {answer.get('fullyQualifiedName')}")
        assets = [{"id": ids[table], "type": "table"} for table in product["tables"] if table in ids]
        if assets:
            call("PUT", f"/dataProducts/{escape(product['name'], safe='')}/assets/add",
                 {"assets": assets, "dryRun": False})
        inputs = [{"id": ids[table], "type": "table"} for table in product.get("inputs") or [] if table in ids]
        if inputs:
            call("PUT", f"/dataProducts/{escape(product['name'], safe='')}/inputPorts/add",
                 {"assets": inputs, "dryRun": False})
    for edge in plan.get("domain_lineage") or []:
        call("PUT", "/lineage/domain/name/" + escape(edge["domain"], safe="")
             + "/table/name/" + escape(edge["table"], safe=""),
             {"description": edge["description"], "source": "Manual"})
    pipeline_ids = {}
    if plan.get("pipeline_service"):
        _upsert(call, "/services/pipelineServices", plan["pipeline_service"])
        for pipeline in plan.get("pipelines") or []:
            name = fqn(plan["pipeline_service"]["name"], pipeline["name"])
            answer = _upsert(call, "/pipelines", pipeline)
            if answer["fullyQualifiedName"] != name:
                raise CatalogError(f"The server named pipeline {name} {answer['fullyQualifiedName']}")
            pipeline_ids[name] = answer["id"]
    for edge in plan.get("service_lineage") or []:
        call("PUT", "/lineage/pipeline/name/" + escape(edge["pipeline"], safe="")
             + "/table/name/" + escape(edge["table"], safe=""),
             {"description": edge["description"], "source": "PipelineLineage"})
    service = plan["service"]["name"]
    removed = {"tables": 0, "schemas": 0, "databases": 0, "lineage": 0}
    for table in _listed(call, "/tables", {"service": service}, service):
        if table["fullyQualifiedName"] not in ids:
            call("DELETE", f"/tables/{table['id']}", params={"hardDelete": "true"})
            removed["tables"] += 1
    planned_schemas = {f"{s['database']}.{quote(s['name'])}" for s in plan["schemas"]}
    planned_databases = {fqn(service, d["name"]) for d in plan["databases"]}
    for database in _listed(call, "/databases", {"service": service}, service):
        if database["fullyQualifiedName"] not in planned_databases:
            call("DELETE", f"/databases/{database['id']}", params={"hardDelete": "true", "recursive": "true"})
            removed["databases"] += 1
            continue
        for schema in _listed(call, "/databaseSchemas", {"database": database["fullyQualifiedName"]}, service):
            if schema["fullyQualifiedName"] not in planned_schemas:
                call("DELETE", f"/databaseSchemas/{schema['id']}", params={"hardDelete": "true", "recursive": "true"})
                removed["schemas"] += 1
    ours = set(ids.values())
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
            stale = edge["fromEntity"] in ours and edge["fromEntity"] not in upstream[table_id]
            if edge["toEntity"] == table_id and stale:  # a link from another service is not ours to remove
                call("DELETE", f"/lineage/table/{edge['fromEntity']}/table/{table_id}")
                removed["lineage"] += 1
    if plan.get("pipeline_service"):
        pipeline_service = plan["pipeline_service"]["name"]
        for pipeline in _listed(call, "/pipelines", {"service": pipeline_service}, pipeline_service):
            if pipeline["fullyQualifiedName"] not in pipeline_ids:
                call("DELETE", f"/pipelines/{pipeline['id']}", params={"hardDelete": "true"})
                removed["pipelines"] = removed.get("pipelines", 0) + 1
    return {"service": service, "tables": len(plan["tables"]), "lineage": len(plan["lineage"]),
            "pipelines": len(pipeline_ids), "removed": removed}


def verify(plan: dict, call: Call) -> dict:
    """Read back the owned metadata and lineage; never repair while checking."""
    differences = []

    def compare(expected, actual, where):
        if where.endswith(".description") and isinstance(actual, str):
            actual = html.unescape(actual)
        if isinstance(expected, str) and isinstance(actual, dict) and "fullyQualifiedName" in actual:
            actual = actual["fullyQualifiedName"]
        if expected == [] and actual is None:
            actual = []
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                differences.append(where + ": missing object")
                return
            for key, value in expected.items():
                compare(value, actual.get(key), where + "." + key)
        elif isinstance(expected, list):
            if not isinstance(actual, list) or len(expected) != len(actual):
                differences.append(where + ": different list")
            else:
                for index, value in enumerate(expected):
                    compare(value, actual[index], f"{where}[{index}]")
        elif expected != actual:
            differences.append(where + ": differs")

    service = plan["service"]["name"]
    compare(plan["service"], call("GET", "/services/databaseServices/name/" + escape(service, safe="")), "service")
    identifiers = {}
    for collection, scope in (("databases", service), ("schemas", service),
                              ("tables", service), ("pipelines", plan.get("pipeline_service", {}).get("name"))):
        if scope is None:
            continue
        endpoint = "databaseSchemas" if collection == "schemas" else collection
        if collection == "schemas":
            listed = [row for database in plan["databases"] for row in _listed(
                call, "/databaseSchemas", {"database": fqn(service, database["name"])}, service)]
        else:
            listed = _listed(call, "/" + endpoint, {"service": scope}, scope)
        names = {r["fullyQualifiedName"]: r["id"] for r in listed}
        expected_names = set()
        for entry in plan.get(collection) or []:
            parent = entry.get("databaseSchema") or entry.get("database") or entry.get("service") or service
            name = parent + "." + quote(entry["name"])
            expected_names.add(name)
            compare(entry, call("GET", f"/{endpoint}/name/{escape(name, safe='')}",
                                params={"fields": "tasks"} if collection == "pipelines" else None), name)
        if set(names) != expected_names:
            differences.append(collection + ": different membership")
        if collection == "tables":
            identifiers = names
    if plan.get("pipeline_service"):
        compare(plan["pipeline_service"], call("GET", "/services/pipelineServices/name/"
                + escape(plan["pipeline_service"]["name"], safe="")), "pipeline_service")
    for name, table_id in identifiers.items():
        graph = call("GET", "/lineage/table/name/" + escape(name, safe=""),
                     params={"upstreamDepth": 1, "downstreamDepth": 0}) or {}
        actual = {edge["fromEntity"]: edge for edge in graph.get("upstreamEdges") or []
                  if edge["toEntity"] == table_id and edge["fromEntity"] in identifiers.values()}
        expected = {identifiers.get(edge["from"]): edge for edge in plan["lineage"] if edge["to"] == name}
        if set(actual) != set(expected):
            differences.append(name + ": different lineage")
        for source in actual.keys() & expected.keys():
            wanted = expected[source]
            details = actual[source].get("lineageDetails") or {}
            compare(wanted["description"], details.get("description"), name + ".lineage.description")
            compare(wanted["columns"], details.get("columnsLineage") or [], name + ".lineage.columns")
    return {"ok": not differences, "tables": len(plan["tables"]),
            "pipelines": len(plan.get("pipelines") or []), "differences": differences}
