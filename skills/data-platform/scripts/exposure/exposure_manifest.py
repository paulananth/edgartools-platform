#!/usr/bin/env python3
"""The exposure manifest: the final tables every consumer may read, from an exposure list and the stores themselves.

Generic: it reads any exposure list in the shape below and any PostgreSQL stores it names; no table, schema or
database is written here. The list is the approval (data-platform FINAL-TABLES.md); this script only resolves it.

    version: <descriptive name>
    approval: {date: YYYY-MM-DD, words: [<the operator's words>]}
    target: {database: <Snowflake database>, verified: <false until the mirror is read back>}
    layers:
      <layer>: {connection: <environment variable naming the database that holds the store>, source_schema: <PostgreSQL schema>,
                target_schema: <Snowflake schema>, authority: <who owns the meaning>}
    tables:
    - layer: <layer>
      table: <PostgreSQL table>
      scope: current | history
      grain: <one row per ...>
      requirement: <the file or folder that states what the table must hold, pinned by its sha256>
      definition: <optional; else the table's comment in the store>
      columns: {<column>: <optional definition; else the column's comment>}
      lineage: [<layer>.<table> another listed table it is filled from]

Each listed table's columns, types and comments are read back from its store, so the manifest describes the
tables that exist, not a copy of their specs. A table or column the store lacks, or one with no definition in
either place, is refused. Identities are held as parts, never one dotted string. `config_sha256` binds the
manifest to the list and to the version of every requirement it names: given them, a consumer refuses a
manifest they no longer make.

    uv run --no-project --with pyyaml --with 'psycopg[binary]' python exposure_manifest.py generate \\
        --config destination/authorised_data_sharing.yaml --env <private env file> --out <manifest.json>
    ... exposure_manifest.py check --config destination/authorised_data_sharing.yaml --manifest <manifest.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 2
SCOPES = ("current", "history")

_TOP = {"manifest_version", "version", "approval", "target", "config_sha256", "tables", "digest"}
_TABLE = {"layer", "source", "physical", "business", "requirement", "columns", "lineage"}
_SOURCE = {"connection", "schema", "table"}
_PHYSICAL = {"database", "schema", "table", "verified"}
_BUSINESS = {"description", "grain", "authority", "scope"}
_COLUMN = {"name", "data_type", "nullable", "description"}
_REFERENCE = {"database", "schema", "table"}
_LAYER = {"connection", "source_schema", "target_schema", "authority"}
_ENTRY = {"layer", "table", "scope", "grain", "requirement", "definition", "columns", "lineage"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(data: str | bytes) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def _words(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be non-empty text")
    return " ".join(value.split())


def _name(value: Any, what: str) -> str:
    """One identifier part as written; the parts are never joined, so a dot or quote in one is refused."""
    text = _words(value, what)
    if any(c in text for c in '." ') or text != str(value).strip():
        raise ValueError(f"{what} must be one plain name, with no dot, quote or space")
    return text


def _setting(value: Any, what: str) -> str:
    """An environment variable's name. Its value is never echoed: a pasted address would carry a password."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", value):
        raise ValueError(f"{what} must name an environment variable (capitals, digits and _), never hold a value")
    return value


def _flag(value: Any, what: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{what} must be true or false")
    return value


def _keys(value: Any, expected: set, what: str, *, optional: set = frozenset()) -> dict:
    if not isinstance(value, dict) or not (expected - optional) <= set(value) <= expected:
        raise ValueError(
            f"{what} must hold {sorted(expected - optional)}"
            + (f" and may hold {sorted(optional)}" if optional else "")
        )
    return value


def requirement_digests(config: dict, root: Path) -> dict[str, str]:
    """Each table's requirement file (or every file of a requirement folder) by its sha256, read under `root`."""
    found = {}
    for entry in config.get("tables") or []:
        path = _words(entry.get("requirement"), f"{entry.get('table')} requirement")
        where = Path(root) / path
        if where.is_file():
            found[path] = _sha256(where.read_bytes())
        elif where.is_dir():
            found[path] = _sha256(
                _canonical(
                    [
                        [str(f.relative_to(where)), _sha256(f.read_bytes())]
                        for f in sorted(where.rglob("*"))
                        if f.is_file()
                    ]
                )
            )
        else:
            raise ValueError(f"{entry.get('table')} names a requirement that does not exist: {path}")
    return found


def config_sha256(path: Path, root: Path | None = None) -> str:
    """The list's own bytes and the version of every requirement it names: either changing makes a manifest stale."""
    root = Path.cwd() if root is None else Path(root)
    return _sha256(_canonical([_sha256(Path(path).read_bytes()), requirement_digests(load_config(path), root)]))


def load_config(path: Path) -> dict:
    import yaml

    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    target = config.get("target")
    if isinstance(target, dict) and "names" in target:  # the list says which file holds the mirror's database name
        names = yaml.safe_load((Path(path).parent / target.pop("names")).read_text(encoding="utf-8"))
        target.setdefault("database", names["mirror"]["database"])
    return config


def requested(config: dict) -> dict[str, dict]:
    """For each layer: its connection setting, its schema and the tables the list names in it."""
    layers = config.get("layers") or {}
    found = {
        name: {
            "connection": _setting(body.get("connection"), f"{name} connection"),
            "schema": _name(body.get("source_schema"), f"{name} source schema"),
            "tables": [],
        }
        for name, body in layers.items()
    }
    for entry in config.get("tables") or []:
        layer = entry.get("layer")
        if layer not in found:
            raise ValueError(f"table {entry.get('table')!r} names an undeclared layer {layer!r}")
        found[layer]["tables"].append(_name(entry.get("table"), "a table"))
    return found


def read_store(connection, schema: str, tables: list[str]) -> dict[str, dict]:
    """Each table's comment and columns (name, type, nullable, comment), as the PostgreSQL catalog holds them."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select c.relname, obj_description(c.oid, 'pg_class'), a.attname, format_type(a.atttypid, a.atttypmod),"
            " not a.attnotnull, col_description(c.oid, a.attnum)"
            " from pg_class c join pg_namespace n on n.oid = c.relnamespace"
            " join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped"
            " where n.nspname = %s and c.relname = any(%s) and c.relkind in ('r', 'p')"
            " order by c.relname, a.attnum",
            (schema, list(tables)),
        )
        found: dict[str, dict] = {}
        for table, comment, column, data_type, nullable, column_comment in cursor.fetchall():
            entry = found.setdefault(table, {"comment": comment, "columns": []})
            entry["columns"].append(
                {"name": column, "data_type": data_type, "nullable": nullable, "comment": column_comment}
            )
    return found


def _table(entry: dict, layer: dict, layer_name: str, target: dict, stored: dict, requirements: dict) -> dict:
    _keys(entry, _ENTRY, "a table entry", optional={"definition", "columns", "lineage"})
    table = _name(entry["table"], "a table")
    if table not in stored:
        raise ValueError(f"{layer_name}.{table} is not in its store (schema {layer['source_schema']})")
    if entry["scope"] not in SCOPES:
        raise ValueError(f"{table} scope must be one of {SCOPES}")
    held = stored[table]
    defined = entry.get("columns") or {}
    unknown = set(defined) - {c["name"] for c in held["columns"]}
    if unknown:
        raise ValueError(f"{table} defines columns its store does not have: {sorted(unknown)}")
    columns = []
    for column in held["columns"]:
        words = defined.get(column["name"]) or column["comment"]
        columns.append(
            {
                "name": column["name"],
                "data_type": column["data_type"],
                "nullable": column["nullable"],
                "description": _words(words, f"{table}.{column['name']} definition (the list or the store)"),
            }
        )
    return {
        "layer": layer_name,
        "source": {"connection": layer["connection"], "schema": layer["source_schema"], "table": table},
        "physical": {
            "database": target["database"],
            "schema": layer["target_schema"],
            "table": table.upper(),
            "verified": target["verified"],
        },
        "business": {
            "description": _words(entry.get("definition") or held["comment"], f"{table} definition"),
            "grain": _words(entry["grain"], f"{table} grain"),
            "authority": layer["authority"],
            "scope": entry["scope"],
        },
        "requirement": {
            "path": _words(entry["requirement"], f"{table} requirement"),
            "sha256": _words(requirements.get(entry["requirement"]), f"{table} requirement's sha256"),
        },
        "columns": columns,
        "lineage": [],
    }


def build_manifest(
    config: dict, stores: dict[str, dict], *, config_digest: str, requirements: dict[str, str]
) -> dict:
    """The manifest from a parsed exposure list, each layer's store readback (`read_store`) and each requirement's
    sha256 (`requirement_digests`)."""
    _keys(config, {"version", "approval", "target", "layers", "tables"}, "the exposure list")
    target = _keys(config["target"], {"database", "verified"}, "target")
    target = {
        "database": _name(target["database"], "the target database"),
        "verified": _flag(target["verified"], "target verified"),
    }
    approval = _keys(config["approval"], {"date", "words"}, "approval")
    if not isinstance(approval["words"], list) or not approval["words"]:
        raise ValueError("the exposure list must hold the operator's words that approved it")
    layers = {}
    for name, body in config["layers"].items():
        _keys(body, _LAYER, f"layer {name}")
        layers[_name(name, "a layer")] = {
            key: (_setting if key == "connection" else _name)(body[key], f"{name} {key}") for key in _LAYER
        }
    tables, by_name = [], {}
    for entry in config["tables"] or []:
        layer = entry.get("layer")
        if layer not in layers:
            raise ValueError(f"table {entry.get('table')!r} names an undeclared layer {layer!r}")
        built = _table(entry, layers[layer], layer, target, stores.get(layer) or {}, requirements)
        key = (layer, built["source"]["table"])
        if key in by_name:
            raise ValueError(f"{layer}.{key[1]} is listed twice")
        by_name[key] = built
        tables.append((entry, built))
    for entry, built in tables:
        for reference in entry.get("lineage") or []:
            layer, _, table = _words(reference, "a lineage reference").partition(".")
            if (layer, table) == (built["layer"], built["source"]["table"]):
                raise ValueError(f"{built['source']['table']} names itself as its lineage")
            if (layer, table) not in by_name:
                raise ValueError(
                    f"{built['source']['table']} names lineage {reference!r} that the list does not expose"
                )
            built["lineage"].append({k: by_name[(layer, table)]["physical"][k] for k in _REFERENCE})
        built["lineage"].sort(key=_canonical)
    physical = [tuple(t["physical"][k].upper() for k in _REFERENCE) for _, t in tables]
    if len(set(physical)) != len(physical):
        raise ValueError("two listed tables share one Snowflake identity")
    unsigned = {
        "manifest_version": MANIFEST_VERSION,
        "version": _words(config["version"], "the version"),
        "approval": {
            "date": _words(str(approval["date"]), "the approval date"),
            "words": [_words(w, "approval words") for w in approval["words"]],
        },
        "target": target,
        "config_sha256": config_digest,
        "tables": sorted((t for _, t in tables), key=lambda t: (t["layer"], t["source"]["table"])),
    }
    manifest = {**unsigned, "digest": _sha256(_canonical(unsigned))}
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict, *, config: Path | None = None, root: Path | None = None) -> None:
    """Refuse a manifest of another version, a changed one, one of the wrong shape, or, given its exposure list, one
    that list no longer makes. A valid manifest is a consistent list; the list's approval is what authorizes."""
    _keys(manifest, _TOP, "the manifest")
    if manifest["manifest_version"] != MANIFEST_VERSION:
        raise ValueError("unsupported manifest version")
    unsigned = {k: v for k, v in manifest.items() if k != "digest"}
    if manifest["digest"] != _sha256(_canonical(unsigned)):
        raise ValueError("manifest digest does not match its contents")
    _keys(manifest["approval"], {"date", "words"}, "approval")
    _keys(manifest["target"], {"database", "verified"}, "target")
    if not isinstance(manifest["tables"], list):
        raise ValueError("manifest tables must be a list")
    for table in manifest["tables"]:
        _keys(table, _TABLE, "a table")
        _keys(table["source"], _SOURCE, "a table's source")
        _keys(table["physical"], _PHYSICAL, "a table's physical identity")
        _keys(table["business"], _BUSINESS, "a table's business meaning")
        _keys(table["requirement"], {"path", "sha256"}, "a table's requirement")
        if table["business"]["scope"] not in SCOPES:
            raise ValueError("a table's scope must be current or history")
        if not isinstance(table["columns"], list) or not table["columns"]:
            raise ValueError(f"{table['source']['table']} has no columns")
        for column in table["columns"]:
            _keys(column, _COLUMN, "a column")
        for reference in table["lineage"]:
            _keys(reference, _REFERENCE, "a lineage reference")
    if config is not None and manifest["config_sha256"] != config_sha256(config, root):
        raise ValueError(
            "the manifest is stale: its exposure list or a requirement it names changed since it was generated"
        )


def generate(config_path: Path, env: dict[str, str], root: Path | None = None) -> dict:
    """Read each layer's store through the connection setting the list names (from `env`), then build."""
    import psycopg

    config = load_config(config_path)
    stores = {}
    for layer, wanted in requested(config).items():
        if not wanted["tables"]:
            continue
        url = env.get(wanted["connection"])
        if url and "://" in url and "+" in url.split("://", 1)[0]:
            url = "postgresql://" + url.split("://", 1)[1]  # an SQLAlchemy address names its driver; libpq does not
        if not url:
            raise ValueError(f"{wanted['connection']} is not set: source the private env file for {layer}")
        try:
            with psycopg.connect(url, connect_timeout=10) as connection:
                connection.read_only = True
                stores[layer] = read_store(connection, wanted["schema"], wanted["tables"])
        except psycopg.Error as error:  # its message can carry the address: name the setting only
            raise ValueError(
                f"the {layer} store ({wanted['connection']}) could not be read: {type(error).__name__}"
            ) from None
    root = Path.cwd() if root is None else Path(root)
    return build_manifest(
        config, stores, config_digest=config_sha256(config_path, root), requirements=requirement_digests(config, root)
    )


def _env(path: str | None) -> dict[str, str]:
    """The environment, plus a private env file's settings when given (sourced by the shell, never printed)."""
    if not path:
        return dict(os.environ)
    done = subprocess.run(
        ["bash", "-c", 'set -a; . "$1" >/dev/null; env -0', "exposure", path], capture_output=True, check=True
    )
    return dict(item.decode().split("=", 1) for item in done.stdout.split(b"\0") if b"=" in item)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    making = commands.add_parser("generate", help="Read the stores and write the manifest")
    making.add_argument("--config", required=True, type=Path)
    making.add_argument("--root", type=Path, default=Path.cwd(), help="The folder requirement paths are under")
    making.add_argument("--env", help="A private env file with the stores' connection settings")
    making.add_argument("--out", required=True, type=Path)
    checking = commands.add_parser("check", help="Refuse a manifest that is malformed or stale")
    checking.add_argument("--config", required=True, type=Path)
    checking.add_argument("--root", type=Path, default=Path.cwd(), help="The folder requirement paths are under")
    checking.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.config, _env(args.env), args.root)
            args.out.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
            )
            print(json.dumps({"tables": len(manifest["tables"]), "digest": manifest["digest"]}))
        else:
            validate_manifest(
                json.loads(args.manifest.read_text(encoding="utf-8")), config=args.config, root=args.root
            )
            print("current")
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
