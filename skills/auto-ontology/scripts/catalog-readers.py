#!/usr/bin/env python3
"""Provision and verify restricted catalog readers; keep credentials in private files.

Run with uv run --no-project --with 'psycopg[binary]' --with pyyaml python.

A reader holds SELECT on exactly the tables of the exposure list (destination/authorised_data_sharing.yaml) and nothing else: no schema-wide or future-table
grant, so a table that is not on the list, such as a draft or a control table, is unreadable to it.
"""

import argparse
import json
import os
import secrets
import shlex
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import psycopg
import yaml
from psycopg import sql


def load_env(path):
    """Read trusted shell configuration without losing shell-escaped URL characters."""
    result = subprocess.run(
        ["bash", "-c", 'set -ae; source "$1" >/dev/null; env -0', "catalog", str(path)],
        capture_output=True,
        check=True,
    )
    return dict(
        item.decode().split("=", 1)
        for item in result.stdout.split(b"\0")
        if b"=" in item
    )


def save_env(path, updates):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    old = path.read_text().splitlines() if path.exists() else []
    remaining = dict(updates)
    lines = []
    for line in old:
        key = line.removeprefix("export ").split("=", 1)[0].strip()
        if key in updates:
            if key in remaining:
                lines.append(key + "=" + shlex.quote(remaining.pop(key)))
        else:
            lines.append(line)
    lines.extend(key + "=" + shlex.quote(value) for key, value in remaining.items())
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def pg_url(value):
    parsed = urlsplit(value)
    if not parsed.scheme.startswith("postgresql"):
        raise ValueError("A complete PostgreSQL URL is required")
    return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, ""))


EXPOSURE = Path(__file__).resolve().parents[3] / "destination" / "authorised_data_sharing.yaml"


def exposed(path, layer):
    """(schema, tables) of the exposure list's final tables of one store, in the store's own schema."""
    document = yaml.safe_load(Path(path).read_text())
    tables = sorted(item["table"] for item in document["tables"] if item["layer"] == layer)
    if not tables:
        raise ValueError("The exposure list names no table of this store")
    return document["layers"][layer]["source_schema"], tables


def verify(url, expected=None):
    with (
        psycopg.connect(
            url,
            connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        ) as connection,
        connection.cursor() as cur,
    ):
        cur.execute(
            "SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        if cur.fetchone()[0]:
            raise ValueError("Catalog reader has administrative privileges")
        cur.execute("""SELECT count(*) FILTER (WHERE has_table_privilege(c.oid,'SELECT')),
            count(*) FILTER (WHERE has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'))
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            AND n.nspname NOT LIKE 'pg\\_%' AND c.relkind IN ('r','p','v','m','f')""")
        readable, writable = cur.fetchone()
        if expected is not None:
            cur.execute("""SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg\\_%'
                AND c.relkind IN ('r','p','v','m','f') AND has_table_privilege(c.oid,'SELECT')
                AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid=c.oid AND d.deptype='e')""")  # an extension's own views are not the list's
            if {row[0] for row in cur.fetchall()} != set(expected):
                raise ValueError("Catalog reader can read tables other than the exposure list, or lacks one")
        cur.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        if not cur.fetchone()[0] or writable or not readable:
            raise ValueError(
                "Catalog reader needs TLS, readable relations and zero write privileges"
            )
        return {
            "readable_relations": readable,
            "writable_relations": writable,
            "tls": True,
        }


def owner_url(owner, store):
    """The owner file's URL of the database that holds the source's store (edgar_warehouse.database_connections)."""
    from edgar_warehouse.database_connections import store_url

    return store_url(store, owner).render_as_string(hide_password=False)


def shared_password(saved, role):
    """The password saved for `role` in any source's URL, or None: one reader login serves every store, so its second source reuses it."""
    for value in saved.values():
        found = urlsplit(value)
        if found.password and unquote(found.username or "") == role:
            return unquote(found.password)
    return None


def provision(source, owner, reader_file, exposure=EXPOSURE):
    key = source["variable"]
    schema, tables = exposed(exposure, source["store"])
    expected = [f"{schema}.{table}" for table in tables]
    endpoint = pg_url(owner_url(owner, source["store"]))
    parsed = urlsplit(endpoint)
    saved = load_env(reader_file) if reader_file.exists() else {}
    if key in saved:
        previous = urlsplit(saved[key])
        if (
            previous.hostname,
            previous.port,
            previous.path,
            previous.query,
            unquote(previous.username or ""),
        ) != (parsed.hostname, parsed.port, parsed.path, parsed.query, source["role"]):
            raise ValueError("Saved reader differs from the selected source or role")
        try:
            return saved[key], verify(saved[key], expected)
        except psycopg.OperationalError:
            # A previous transaction may have rolled back after the local save.
            pass
    role = source["role"]
    known = shared_password(saved, role)  # one login serves every store: its password is the one already saved for it
    password = known or secrets.token_urlsafe(36)
    new_url = urlunsplit(
        (
            "postgresql",
            quote(role, safe="")
            + ":"
            + quote(password, safe="")
            + "@"
            + parsed.netloc.rsplit("@", 1)[-1],
            parsed.path,
            parsed.query,
            "",
        )
    )
    # Save before database changes so a partial grant remains recoverable.
    save_env(reader_file, {key: new_url})
    with (
        psycopg.connect(endpoint, connect_timeout=10) as connection,
        connection.cursor() as cur,
    ):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
        exists = bool(cur.fetchone())
        if exists and not known:
            raise ValueError(
                "Reader role already exists without saved credentials; refusing to adopt it"
            )
        if not exists:  # a login made for an earlier store of this run is reused, not made again
            cur.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
            cur.execute(
                sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(
                    sql.Identifier(role)
                )
            )
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(unquote(parsed.path.lstrip("/"))),
                sql.Identifier(role),
            )
        )
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
        for table in tables:  # table by table: no schema-wide or future-table grant
            cur.execute(sql.SQL("GRANT SELECT ON TABLE {}.{} TO {}").format(
                sql.Identifier(schema), sql.Identifier(table), sql.Identifier(role)))
    return new_url, verify(new_url, expected)


def prepare_models(auto_env):
    values = load_env(auto_env)
    default = values.get("DEFAULT_MODELS_API_KEY", "")

    def placeholder(value):
        return any(
            part in value.lower()
            for part in ("your-api-key", "your_api_key", "placeholder")
        )

    if not default or placeholder(default):
        raise ValueError("Configure the default model credential privately")
    updates = {
        key: default
        for key, value in values.items()
        if key.endswith("_API_KEY") and placeholder(value)
    }
    values.update(updates)
    endpoint = values.get("EMBED_ENDPOINT") or values["DEFAULT_MODELS_ENDPOINT"]
    body = {
        "model": values["EMBED_MODEL"],
        "input": ["Catalog connectivity check"],
        "input_type": "passage",
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/embeddings",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (values.get("EMBED_API_KEY") or default),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not result.get("data") or not result["data"][0].get("embedding"):
        raise ValueError("Model probe returned no embedding")
    if updates:
        save_env(auto_env, updates)
    print(
        json.dumps(
            {
                "embedding_probe": "confirmed",
                "placeholder_overrides_replaced": len(updates),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--owner-env", required=True, type=Path)
    parser.add_argument("--reader-env", required=True, type=Path)
    parser.add_argument("--auto-env", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        if args.auto_env:
            prepare_models(args.auto_env.expanduser())
        owner = load_env(args.owner_env.expanduser())
        urls = []
        for source in config["sources"]:
            url, result = provision(source, owner, args.reader_env.expanduser())
            urls.append(url)
            print(json.dumps({"source": source["variable"], **result}), flush=True)
        if args.auto_env:
            save_env(args.auto_env.expanduser(), {"CONNECTION_STRINGS": ",".join(urls)})
            print(json.dumps({"configured_sources": len(urls)}))
    except Exception as error:  # noqa: BLE001 - prevent credential-bearing exceptions reaching stderr
        # Driver/HTTP exceptions may include passwords, addresses or source records.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
