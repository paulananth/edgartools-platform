"""Render every Gold object of destination/gold/gold.yaml as one CREATE VIEW statement.

One function per object kind, chosen by the object's `kind`. The dialect decides only how a structured body is read,
how a date is split and how a day is added; every other expression is portable, so a test can run the same views on
an invented fixture. Nothing here connects to a database or creates an object.
"""
from __future__ import annotations

import re
from pathlib import Path

from edgar_warehouse.rules import files

CONFIG = files.ROOT.parent / "destination" / "gold" / "gold.yaml"  # `destination` beside the rules folder, so an installed bundle reads its own copy

DIALECTS = {
    "snowflake": {
        "create": "CREATE OR REPLACE VIEW",
        "text": lambda body, path, body_type: f"{('PARSE_JSON(' + body + ')') if body_type == 'text' else body}:{path}::VARCHAR",
        "part": lambda part, expr: f"EXTRACT({part} FROM {expr})",
        "next_day": lambda expr: f"DATEADD(day, 1, {expr})",
        "date": lambda text: f"DATE '{text}'",
    },
    "sqlite": {
        "create": "CREATE VIEW",
        "text": lambda body, path, body_type: f"json_extract({body}, '$.{path}')",
        "part": lambda part, expr: f"CAST(strftime('{'%Y' if part == 'YEAR' else '%m'}', {expr}) AS INTEGER)",
        "next_day": lambda expr: f"date({expr}, '+1 day')",
        "date": lambda text: f"'{text}'",
    },
}


def load(path: Path = CONFIG) -> dict:
    """The Gold configuration, with the database names of rules/snowflake.yaml and a fact made from each silver spec."""
    config, names = files.load(path), files.load(files.ROOT / "snowflake.yaml")
    config["destination"] = dict(names["gold"])
    config["mirror"]["database"] = names["mirror"]["database"]
    config["objects"] += silver_facts(config) + code_set_views(config)
    return config


def code_set_views(config: dict) -> list[dict]:
    """One view per published code set: each folder of the published reference data names one, and holds its one
    version (a code set keeps no history; a retired code set has no folder, so no view)."""
    rule = config.get("code_sets")
    if not rule:
        return []
    items = []
    for folder in sorted(p for p in (files.ROOT / rule["published"]).iterdir() if p.is_dir()):
        versions = sorted(v.name for v in folder.iterdir() if v.is_dir())
        if len(versions) != 1:
            raise ValueError(f"code set {folder.name} holds {len(versions)} versions; a code set keeps exactly one")
        items.append({"name": rule["name"].format(code_set=re.sub(r"\W", "_", folder.name)), "kind": "code_set",
                      "code_set": folder.name, "version": versions[0], "source": rule["source"], "columns": rule["columns"],
                      "requirement": rule["requirement"], "grain": "one row per code of the code set's one published version"})
    return items


def silver_facts(config: dict) -> list[dict]:
    """One fact per silver table on the exposure list, made from its approved spec (its requirement): the spec's key,
    a dimension key per link, its business (as_of), event and recorded (as_at) time, and every other column carried. A table
    an explicit object already reads gives way to that object."""
    rule = config.get("silver_facts")
    if not rule:
        return []
    exposure = files.load(files.ROOT.parent / "destination" / rule["exposure"])
    dimensions = {item["master_kind"]: item["name"] for item in config["objects"] if item["kind"] == "dimension"}
    taken = {item.get("source") for item in config["objects"]}
    facts = []
    for entry in exposure["tables"]:
        source = f"{entry['layer']}.{entry['table']}"
        if entry["layer"] != "silver" or source in taken:
            continue
        spec = files.load(files.ROOT.parent / entry["requirement"])
        links = [{"column": link["mdm_id_column"], "dimension": dimensions[link["kind"]],
                  "role": link.get("to_part") or link["kind"]} for link in spec.get("links") or []]
        time = spec.get("time") or {}
        times = {"business": time.get("as_of"), "event": time.get("event_time"), "recorded": time.get("as_at")}
        used = set(spec["key"]) | {v for v in times.values() if v}
        facts.append({"name": f"fact_{entry['table']}", "kind": "fact", "source": source, "key": list(spec["key"]),
                      "links": links, "times": times, "carry": [c["name"] for c in spec["columns"] if c["name"] not in used],
                      "requirement": rule["requirement"], "spec": entry["requirement"], "grain": spec["grain"]})
    return facts


class Context:
    """What every renderer needs: the configuration, the dialect and how to name a table."""

    def __init__(self, config: dict, dialect: str, qualify: bool, dbt: bool = False):
        self.config, self.dialect, self.qualify, self.dbt = config, DIALECTS[dialect], qualify, dbt
        self.objects = {item["name"]: item for item in config["objects"]}
        self.unknown, self.not_applicable = (config["members"][k] for k in ("unknown", "not_applicable"))

    def mirror(self, source: str) -> str:
        layer, table = source.split(".")
        if self.dbt:
            return "{{ source('" + layer + "', '" + table + "') }}"
        mirror = self.config["mirror"]
        return f"{mirror['database']}.{mirror['schemas'][layer]}.{table}" if self.qualify else table

    def view(self, name: str) -> str:
        if self.dbt:
            return "{{ ref('" + name + "') }}"
        destination = self.config["destination"]
        return f"{destination['database']}.{destination['schema']}.{name}" if self.qualify else name

    def body(self, path: str) -> str:
        return self.dialect["text"]("body", path, self.config["mirror"]["body_type"])


def literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def render_base(item: dict, ctx: Context) -> str:
    """Every master once: its kind, status and surviving id are columns; the name is read from the body here and nowhere
    else; an alias row names the master it became."""
    master = ctx.config["master"]
    names = ", ".join(ctx.body(master["name_value_path"].format(field=f)) for f in master["name_fields"])
    return (f"SELECT entity_id, canonical_id, kind, status,\n"
            f"       COALESCE({names}) AS name\n"
            f"FROM {ctx.mirror(master['source'])}")


def identifiers(item: dict, ctx: Context) -> tuple[str, str]:
    """One column per named namespace, from the identifier table; the smallest value if a master holds several."""
    if not item.get("identifiers"):
        return "", ""
    columns = ", ".join(f"MIN(CASE WHEN namespace = {literal(n)} THEN value END) AS {n}" for n in item["identifiers"])
    names = "".join(f", i.{n}" for n in item["identifiers"])
    return names, (f"LEFT JOIN (SELECT entity_id, {columns} FROM {ctx.mirror('mdm.mastering_identifier')} "
                   f"GROUP BY entity_id) i ON i.entity_id = m.entity_id")


def render_dimension(item: dict, ctx: Context) -> str:
    """The canonical masters of one kind, and the two reserved members."""
    names, join = identifiers(item, ctx)
    blank = "".join(f", CAST(NULL AS VARCHAR) AS {n}" for n in item.get("identifiers", []))
    members = "\nUNION ALL\n".join(
        f"SELECT {literal(key)} AS entity_id, {literal(item['master_kind'])} AS kind, {literal(label)} AS name, "
        f"CAST(NULL AS VARCHAR) AS status{blank}"
        for key, label in ((ctx.unknown, "Unknown"), (ctx.not_applicable, "Not applicable")))
    return (f"SELECT m.entity_id, m.kind, m.name, m.status{names}\n"
            f"FROM {ctx.view('master')} m {join}\n"
            f"WHERE m.kind = {literal(item['master_kind'])} AND m.canonical_id = m.entity_id\n"
            f"UNION ALL\n{members}")


def render_calendar(item: dict, ctx: Context) -> str:
    d = ctx.dialect
    return (f"WITH RECURSIVE spine(day) AS (\n  SELECT {d['date'](item['from'])}\n  UNION ALL\n"
            f"  SELECT {d['next_day']('day')} FROM spine WHERE day < {d['date'](item['to'])}\n)\n"
            f"SELECT day AS date_key, {d['part']('YEAR', 'day')} AS year, {d['part']('MONTH', 'day')} AS month FROM spine")


def link_key(link: dict, ctx: Context, alias: str, column: str | None = None) -> str:
    """The canonical master id the row's id resolved to; a missing id or one no master holds is the unknown member."""
    return f"COALESCE({alias}.canonical_id, {literal(ctx.unknown)})"


def render_fact(item: dict, ctx: Context) -> str:
    """One row per silver row. Each link resolves through the master view, so a merged-away id finds its survivor."""
    select, joins = [f"s.{c}" for c in item["key"]], []
    for n, link in enumerate(item.get("links", [])):
        alias = f"m{n}"
        joins.append(f"LEFT JOIN {ctx.view('master')} {alias} ON {alias}.entity_id = s.{link['column']}")
        select.append(f"{link_key(link, ctx, alias)} AS {link['role']}_key")
    parent = item.get("parent")
    if parent:
        by = parent["by"]
        link = parent["single_link"]
        on = " AND ".join(f"p.{c} = s.{c}" for c in by)
        group = ", ".join(by)
        joins.append(
            f"LEFT JOIN (SELECT {group}, MIN({parent['times']['business']}) AS business_date, "
            f"MAX({parent['times']['recorded']}) AS recorded_date, COUNT(DISTINCT {link['column']}) AS managers, "
            f"MIN({link['column']}) AS single_id FROM {ctx.mirror(parent['source'])} GROUP BY {group}) p ON {on}")
        joins.append(f"LEFT JOIN {ctx.view('master')} pm ON pm.entity_id = p.single_id")
        select += ["p.business_date", "p.recorded_date",
                   f"CASE WHEN p.managers = 1 THEN COALESCE(pm.canonical_id, {literal(ctx.unknown)}) "
                   f"WHEN p.managers > 1 THEN {literal(ctx.not_applicable)} ELSE {literal(ctx.unknown)} END AS {link['role']}_key"]
    elif item.get("times"):
        select += [f"s.{column} AS {role}_date" for role, column in item["times"].items() if column]
    select += [f"s.{c}" for c in item.get("measures", []) + item.get("carry", [])]
    return f"SELECT {', '.join(select)}\nFROM {ctx.mirror(item['source'])} s\n" + "\n".join(joins)


def render_code_set(item: dict, ctx: Context) -> str:
    """The codes of one code set's one published version."""
    return (f"SELECT {', '.join(item['columns'])}\nFROM {ctx.mirror(item['source'])}\n"
            f"WHERE code_set = {literal(item['code_set'])} AND version = {literal(item['version'])}")


RENDERERS = {"base": render_base, "dimension": render_dimension, "calendar": render_calendar, "fact": render_fact,
             "code_set": render_code_set}


def render(config: dict | None = None, dialect: str = "snowflake", qualify: bool = True) -> dict[str, str]:
    """{view name: CREATE VIEW statement}, in the order the views depend on each other (base before the rest)."""
    config = config or load()
    ctx = Context(config, dialect, qualify)
    order = sorted(config["objects"], key=lambda item: item["kind"] != "base")
    return {item["name"]: f"{ctx.dialect['create']} {ctx.view(item['name'])} AS\n{RENDERERS[item['kind']](item, ctx)}"
            for item in order}


def render_models(config: dict | None = None) -> dict[str, str]:
    """{model file name: dbt model text}. Snowflake writes go through dbt: each model is one view, reads the mirror
    through `source` and the other Gold views through `ref`, so dbt orders the build and the destination is dbt's."""
    config = config or load()
    ctx = Context(config, "snowflake", qualify=True, dbt=True)
    return {f"{item['name']}.sql": "{{ config(materialized='view') }}\n" + RENDERERS[item["kind"]](item, ctx) + "\n"
            for item in config["objects"]}


def sources(config: dict | None = None) -> dict:
    """The dbt sources file: the mirror's database, and each layer's schema with the tables the views read."""
    config = config or load()
    mirror, read = config["mirror"], {}
    for item in config["objects"]:
        for source in [item.get("source"), item.get("parent", {}).get("source")] + (
                [config["master"]["source"], "mdm.mastering_identifier"] if item["kind"] in ("base", "dimension") else []):
            if source:
                layer, table = source.split(".")
                read.setdefault(layer, set()).add(table)
    return {"version": 2, "sources": [
        {"name": layer, "database": mirror["database"], "schema": mirror["schemas"][layer],
         "tables": [{"name": table} for table in sorted(tables)]} for layer, tables in sorted(read.items())]}


def profile(text: str, config: dict | None = None) -> str:
    """The dbt profile text with the destination database and schema taken from the configuration."""
    config = config or load()
    for key in ("database", "schema"):
        text = re.sub(rf"(?m)^(\s+{key}: ).*$", lambda m: m.group(1) + config["destination"][key], text)
    return text


def write_project(folder: Path, config: dict | None = None) -> list[str]:
    """Write the dbt models, sources and profile into `folder`: the models written. Only dbt_project.yml is committed alone."""
    models = Path(folder) / "models"
    models.mkdir(parents=True, exist_ok=True)
    for stale in models.glob("*.sql"):  # a view dropped from the configuration is dropped from the project
        stale.unlink()
    written = []
    for name, text in render_models(config).items():
        (models / name).write_text(text)
        written.append(name)
    (models / "sources.yml").write_text(files.dumps(sources(config)))
    profiles = Path(folder) / "profiles.yml"
    if profiles.exists():
        profiles.write_text(profile(profiles.read_text(), config))
    return sorted(written)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3 or sys.argv[1] != "write":
        sys.exit("usage: python -m edgar_warehouse.gold.views write <dbt project folder>")
    print("\n".join(write_project(Path(sys.argv[2]))))
