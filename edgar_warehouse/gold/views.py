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
        "text": lambda body, path, body_type: f"{('PARSE_JSON(' + body + ')') if body_type == 'text' else body}"
                                              f"{'' if path.startswith('[') else ':'}{path}::VARCHAR",
        "each": lambda body, path, body_type, alias:
            f"LATERAL FLATTEN(input => {('PARSE_JSON(' + body + ')') if body_type == 'text' else body}"
            f"{(':' + path) if path else ''}) {alias}",
        "item": lambda alias, field: f"{alias}.value:{field}::VARCHAR",
        "part": lambda part, expr: f"EXTRACT({part} FROM {expr})",
        "next_day": lambda expr: f"DATEADD(day, 1, {expr})",
        "date": lambda text: f"DATE '{text}'",
        "column": lambda name: f'"{name.upper()}"',   # the mirror's columns are upper case; quoted, a reserved word is a column
    },
    "sqlite": {
        "create": "CREATE VIEW",
        "text": lambda body, path, body_type: f"json_extract({body}, '${'' if path.startswith('[') else '.'}{path}')",
        "each": lambda body, path, body_type, alias: f"json_each({body}{(chr(44) + chr(32) + repr('$.' + path)) if path else ''}) {alias}",
        "item": lambda alias, field: f"json_extract({alias}.value, '$.{field}')",
        "part": lambda part, expr: f"CAST(strftime('{'%Y' if part == 'YEAR' else '%m'}', {expr}) AS INTEGER)",
        "next_day": lambda expr: f"date({expr}, '+1 day')",
        "date": lambda text: f"'{text}'",
        "column": lambda name: f'"{name}"',
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
        links = [{"column": link["source_key"], "kinds": link["kinds"],
                  **{k: link[k] for k in ("source_code", "identifier", "venue") if link.get(k)},
                  "dimensions": [dimensions[k] for k in link["kinds"]], "role": link.get("to_part") or link["kinds"][0],
                  **({"inclusion": link["inclusion"]} if link.get("inclusion") is not None else {})}
                 for link in spec.get("links") or []]
        time = spec.get("time") or {}
        times = {"business": time.get("as_of"), "event": time.get("event_time"), "recorded": time.get("as_at")}
        used = set(spec["key"]) | {v for v in times.values() if v}
        facts.append({"name": f"fact_{entry['table']}", "kind": "fact", "source": source, "key": list(spec["key"]),
                      "links": links, "times": times,
                      "carry": [c["name"] for c in spec["columns"] if c["name"] not in used],
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

    def column(self, name: str, row: str = "s", renamed: dict | None = None) -> str:
        """A row's column, quoted, under the name the fact gives it."""
        written = f"{row}.{self.dialect['column'](name)}"
        return f"{written} AS {renamed[name]}" if renamed and name in renamed else written

    def dimension_key(self, link: dict) -> str:
        return self.config["silver_facts"]["dimension_key"].format(role=link["role"])

    def source_names(self, item: dict) -> dict[str, str]:
        """A fact's silver columns that carry a dimension key's name, each under its source-key name: the fact keeps both."""
        links = [*item.get("links", []), *([item["parent"]["single_link"]] if item.get("parent") else [])]
        role_of_key = {self.dimension_key(link): link["role"] for link in links}
        columns = [*item["key"], *item.get("measures", []), *item.get("carry", [])]
        return {c: self.config["silver_facts"]["source_key"].format(role=role_of_key[c]) for c in columns if c in role_of_key}

    def view(self, name: str) -> str:
        if self.dbt:
            return "{{ ref('" + name + "') }}"
        destination = self.config["destination"]
        return f"{destination['database']}.{destination['schema']}.{name}" if self.qualify else name

    def body(self, path: str, body: str = "body") -> str:
        return self.dialect["text"](body, path, self.config["mirror"]["body_type"])

    def code_set(self, code_set: str) -> str:
        """The Gold view of a published code set."""
        return self.view(self.config["code_sets"]["name"].format(code_set=re.sub(r"\W", "_", code_set)))


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


def link_type(link: dict) -> str:
    """How a link finds its master: by a Dataset Contract's record key (`source_code`), by an identifier its master
    holds (`identifier`), or by an identifier and, when several masters hold it, the row's Trading Venue (`venue`)."""
    if link.get("venue"):
        return "venue"
    return "identifier" if link.get("identifier") else "source_code"


def held_by(link: dict, ctx: Context, joins: str = "") -> str:
    """The identifier rows of the link's namespace, each joined to its master `k` when the master is of the link's
    kinds, then to `joins`."""
    kinds = ", ".join(literal(k) for k in link["kinds"])
    return (f"{ctx.mirror('mdm.mastering_identifier')} i JOIN {ctx.mirror(ctx.config['master']['source'])} k "
            f"ON k.entity_id = i.entity_id AND k.kind IN ({kinds}) {joins}WHERE i.namespace = {literal(link['identifier'])}")


def holders(link: dict, ctx: Context, masters: str) -> str:
    """The values of the link's identifier, each with its canonical master of the link's kinds; `masters` is the HAVING
    test on how many canonical masters hold it (an alias and the master it became are one)."""
    return (f"SELECT i.value AS value, MIN(k.canonical_id) AS master_id FROM {held_by(link, ctx)} "
            f"GROUP BY i.value HAVING COUNT(DISTINCT k.canonical_id) {masters}")


def wordings(ctx: Context) -> str:
    """Each venue wording with its operating MIC: the wording code set crosswalks a wording to its MIC (the crosswalk
    entry to the MIC code set), and a segment MIC's operating MIC is its parent."""
    venues, d = ctx.config["venues"], ctx.dialect
    crosswalk = d["each"]("w.crosswalk", "", ctx.config["mirror"]["body_type"], "x")
    return (f"SELECT w.code AS wording, COALESCE(o.parent_code, o.code) AS mic FROM {ctx.code_set(venues['wording'])} w, "
            f"{crosswalk} JOIN {ctx.code_set(venues['mic'])} o ON o.code = {d['item']('x', 'to_code')} "
            f"WHERE {d['item']('x', 'to_set')} = {literal(venues['mic'])}")


def venue_holders(link: dict, ctx: Context) -> str:
    """Each value of the link's identifier and operating MIC with the one master of the link's kinds listed there; of
    several there, the one holding a home identifier (the `US` ISIN)."""
    venues = ctx.config["venues"]
    home = venues["home"]
    homes = (f"SELECT DISTINCT hm.canonical_id AS master_id FROM {ctx.mirror('mdm.mastering_identifier')} h "
             f"JOIN {ctx.mirror(ctx.config['master']['source'])} hm ON hm.entity_id = h.entity_id "
             f"WHERE h.namespace = {literal(home['namespace'])} AND h.value LIKE {literal(home['prefix'] + '%')}")
    listed = (f"SELECT lm.canonical_id AS entity_id, COALESCE(o.parent_code, l.mic) AS mic FROM {ctx.view(venues['listings'])} l "
              f"JOIN {ctx.mirror(ctx.config['master']['source'])} lm ON lm.entity_id = l.entity_id "
              f"LEFT JOIN {ctx.code_set(venues['mic'])} o ON o.code = l.mic WHERE l.mic IS NOT NULL")
    joins = f"JOIN ({listed}) l ON l.entity_id = k.canonical_id LEFT JOIN ({homes}) hm ON hm.master_id = k.canonical_id "
    held = (f"SELECT DISTINCT i.value AS value, l.mic AS mic, k.canonical_id AS master_id, hm.master_id AS home_id "
            f"FROM {held_by(link, ctx, joins)}")
    return (f"SELECT v.value, v.mic, CASE WHEN COUNT(DISTINCT v.master_id) = 1 THEN MIN(v.master_id) "
            f"WHEN COUNT(DISTINCT v.home_id) = 1 THEN MIN(v.home_id) END AS master_id FROM ({held}) v GROUP BY v.value, v.mic")


def master_join(link: dict, ctx: Context, row: str, alias: str) -> tuple[str, str]:
    """How a silver row finds its master: (the joins, the column holding the master id). A source-code link joins
    `master_binding` on the row's own source key; an identifier link joins the one master of its kinds holding the value;
    a venue link, when several hold it, the one listed on the row's Trading Venue."""
    key = f"CAST({ctx.column(link['column'], row)} AS VARCHAR)"
    kind = link_type(link)
    if kind == "source_code":
        return (f"LEFT JOIN {ctx.mirror('silver.master_binding')} {alias} ON {alias}.source_code = {literal(link['source_code'])} "
                f"AND {alias}.source_key = {key}"), f"{alias}.master_id"
    one = f"LEFT JOIN ({holders(link, ctx, '= 1')}) {alias} ON {alias}.value = {key}"
    if kind == "identifier":
        return one, f"{alias}.master_id"
    return (f"{one}\nLEFT JOIN ({wordings(ctx)}) {alias}w ON {alias}w.wording = UPPER(TRIM({ctx.column(link['venue'], row)}))"
            f"\nLEFT JOIN ({venue_holders(link, ctx)}) {alias}v ON {alias}v.value = {key} AND {alias}v.mic = {alias}w.mic",
            f"COALESCE({alias}.master_id, {alias}v.master_id)")


def set_aside_lacks(link: dict, ctx: Context, value: str) -> str:
    """The condition that the Set Aside table does not hold `value` under the link's identifier namespace."""
    return (f"NOT EXISTS (SELECT 1 FROM {ctx.mirror(ctx.config['silver_facts']['set_aside'])} a "
            f"WHERE a.namespace = {literal(link['identifier'])} AND a.value = {value})")


def in_scope(link: dict, ctx: Context, row: str, alias: str) -> str:
    """The test's condition on a row beyond a filled key (company phase 2, decision 10): an identifier the Set Aside
    table holds is out of scope; for a venue link, so is a value several masters hold on a row whose wording maps to no
    MIC ("exchange not mapped"). A source-code link's key is no identifier, so the Set Aside table holds none of it."""
    if link_type(link) == "source_code":
        return ""
    key = f"CAST({ctx.column(link['column'], row)} AS VARCHAR)"
    scope = f" AND {set_aside_lacks(link, ctx, key)}"
    if link_type(link) == "venue":
        scope += f" AND NOT ({alias}w.mic IS NULL AND {key} IN (SELECT x.value FROM ({holders(link, ctx, '> 1')}) x))"
    return scope


def render_fact(item: dict, ctx: Context) -> str:
    """One row per silver row. Each link finds its master by a join on the row's source key, then resolves through
    the master view, so a merged-away id finds its survivor."""
    renamed = ctx.source_names(item)
    select, joins = [ctx.column(c, renamed=renamed) for c in item["key"]], []
    for n, link in enumerate(item.get("links", [])):
        alias = f"m{n}"
        found, master_id = master_join(link, ctx, "s", f"b{n}")
        joins += [found, f"LEFT JOIN {ctx.view('master')} {alias} ON {alias}.entity_id = {master_id}"]
        select.append(f"{link_key(link, ctx, alias)} AS {ctx.dimension_key(link)}")
    parent = item.get("parent")
    if parent:
        by = parent["by"]
        link = parent["single_link"]
        on = " AND ".join(f"{ctx.column(c, 'p')} = {ctx.column(c)}" for c in by)
        found, master_id = master_join(link, ctx, "q", "pb")
        joins.append(
            f"LEFT JOIN (SELECT {', '.join(ctx.column(c, 'q') for c in by)}, MIN({ctx.column(parent['times']['business'], 'q')}) AS business_date, "
            f"MAX({ctx.column(parent['times']['recorded'], 'q')}) AS recorded_date, COUNT(DISTINCT {master_id}) AS managers, "
            f"MIN({master_id}) AS single_id FROM {ctx.mirror(parent['source'])} q {found} "
            f"GROUP BY {', '.join(ctx.column(c, 'q') for c in by)}) p ON {on}")
        joins.append(f"LEFT JOIN {ctx.view('master')} pm ON pm.entity_id = p.single_id")
        select += ["p.business_date", "p.recorded_date",
                   f"CASE WHEN p.managers = 1 THEN COALESCE(pm.canonical_id, {literal(ctx.unknown)}) "
                   f"WHEN p.managers > 1 THEN {literal(ctx.not_applicable)} ELSE {literal(ctx.unknown)} END AS {ctx.dimension_key(link)}"]
    elif item.get("times"):
        select += [f"{ctx.column(column)} AS {role}_date" for role, column in item["times"].items() if column]
    select += [ctx.column(c, renamed=renamed) for c in item.get("measures", []) + item.get("carry", [])]
    return f"SELECT {', '.join(select)}\nFROM {ctx.mirror(item['source'])} s\n" + "\n".join(joins)


def render_detail(item: dict, ctx: Context) -> str:
    """One row per detail row of a kind's masters (a Security's listings), its named fields read from the body here."""
    d, body_type = ctx.dialect, ctx.config["mirror"]["body_type"]
    columns = ", ".join(f"{d['item']('l', c)} AS {c}" for c in item["columns"])
    return (f"SELECT m.entity_id, {columns}\n"
            f"FROM {ctx.mirror(ctx.config['master']['source'])} m, {d['each']('m.body', 'details.' + item['detail'], body_type, 'l')}\n"
            f"WHERE m.kind = {literal(item['master_kind'])}")


def render_code_set(item: dict, ctx: Context) -> str:
    """The codes of one code set's one published version."""
    return (f"SELECT {', '.join(item['columns'])}\nFROM {ctx.mirror(item['source'])}\n"
            f"WHERE code_set = {literal(item['code_set'])} AND version = {literal(item['version'])}")


RENDERERS = {"base": render_base, "dimension": render_dimension, "calendar": render_calendar, "fact": render_fact,
             "code_set": render_code_set, "detail": render_detail}
ORDER = {"base": 0, "code_set": 1, "detail": 1}  # what other views read first


def render(config: dict | None = None, dialect: str = "snowflake", qualify: bool = True) -> dict[str, str]:
    """{view name: CREATE VIEW statement}, in the order the views depend on each other (base before the rest)."""
    config = config or load()
    ctx = Context(config, dialect, qualify)
    order = sorted(config["objects"], key=lambda item: ORDER.get(item["kind"], 2))
    return {item["name"]: f"{ctx.dialect['create']} {ctx.view(item['name'])} AS\n{RENDERERS[item['kind']](item, ctx)}"
            for item in order}


def quality_tests(config: dict | None = None, dialect: str = "snowflake", qualify: bool = True,
                  dbt: bool = False) -> dict[str, str]:
    """{test name: query}, each query returning rows only on a defect (a dbt singular test), so Gold never shows a link
    turned empty in silence. Every fact link resolves at least its declared share of its filled keys in scope (`in_scope`;
    `inclusion`, 1.0 when none is declared); an identifier link also holds each value it reads on one master of its
    kinds; and `master_binding` gives each source key one master, so no join doubles a fact row."""
    config = config or load()
    ctx = Context(config, dialect, qualify, dbt)
    tests = {"master_binding_one_master_per_key": (
        f"SELECT source_code, source_key FROM {ctx.mirror('silver.master_binding')} "
        f"GROUP BY source_code, source_key HAVING COUNT(DISTINCT master_id) > 1")}
    for item in config["objects"]:
        pairs = [(item.get("source"), link) for link in item.get("links", [])]
        if "parent" in item:
            pairs.append((item["parent"]["source"], item["parent"]["single_link"]))
        for source, link in pairs:
            found, master_id = master_join(link, ctx, "s", "b")
            column, table = link["column"], source.split(".")[1]
            share = "1.0" if link.get("inclusion") is None else str(link["inclusion"])  # the declared share, never through a float
            tests[f"{table}_{column}_resolves"] = (
                f"SELECT t.n, t.found FROM (SELECT COUNT(*) AS n, COUNT({master_id}) AS found FROM {ctx.mirror(source)} s "
                f"{found} WHERE {ctx.column(column)} IS NOT NULL{in_scope(link, ctx, 's', 'b')}) t WHERE t.found < {share} * t.n")
            if link_type(link) == "identifier":
                tests[f"{table}_{column}_one_master"] = (
                    f"SELECT h.value FROM ({holders(link, ctx, '> 1')}) h "
                    f"WHERE h.value IN (SELECT CAST({ctx.column(column)} AS VARCHAR) FROM {ctx.mirror(source)} s) "
                    f"AND {set_aside_lacks(link, ctx, 'h.value')}")
    return tests


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
        links = [*item.get("links", []), *([item["parent"]["single_link"]] if item.get("parent") else [])]
        linked = ["silver.master_binding"] if links else []
        if any(link_type(link) != "source_code" for link in links):
            linked += [config["master"]["source"], "mdm.mastering_identifier", config["silver_facts"]["set_aside"]]
        for source in [item.get("source"), item.get("parent", {}).get("source"), *linked] + (
                [config["master"]["source"], "mdm.mastering_identifier"] if item["kind"] in ("base", "dimension", "detail") else []):
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
    checks = Path(folder) / "tests"
    checks.mkdir(exist_ok=True)
    for stale in checks.glob("*.sql"):
        stale.unlink()
    for name, query in quality_tests(config, dbt=True).items():
        (checks / f"{name}.sql").write_text(query + "\n")
    profiles = Path(folder) / "profiles.yml"
    if profiles.exists():
        profiles.write_text(profile(profiles.read_text(), config))
    return sorted(written)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3 or sys.argv[1] != "write":
        sys.exit("usage: python -m edgar_warehouse.gold.views write <dbt project folder>")
    print("\n".join(write_project(Path(sys.argv[2]))))
