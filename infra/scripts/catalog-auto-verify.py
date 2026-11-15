#!/usr/bin/env python3
"""Read back catalog inventory and embeddings; optionally enable semantic compilation."""

import argparse
import http.cookiejar
import importlib.util
import json
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg

spec = importlib.util.spec_from_file_location(
    "readers", Path(__file__).with_name("catalog-readers.py")
)
readers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto-env", required=True, type=Path)
    parser.add_argument("--reader-env", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parents[1] / "catalog-sources.json",
    )
    parser.add_argument("--enable-compilation", action="store_true")
    args = parser.parse_args()
    try:
        env = readers.load_env(args.auto_env.expanduser())
        sources = readers.load_env(args.reader_env.expanduser())
        allowed = {
            source["variable"]
            for source in json.loads(args.config.read_text())["sources"]
        }
        source_keys = {key for key in sources if key.endswith("_DATABASE_URL")}
        if source_keys != allowed:
            raise ValueError(
                "Reader file differs from the approved source configuration"
            )
        if env.get("CONNECTION_STRINGS", "").split(",") != [
            sources[source["variable"]]
            for source in json.loads(args.config.read_text())["sources"]
        ]:
            raise ValueError("Consumer connections differ from approved readers")
        origin = env["APP_URL"].rstrip("/")
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

        def call(path, body=None, method=None):
            request = urllib.request.Request(
                origin + path,
                data=None if body is None else json.dumps(body).encode(),
                method=method,
                headers={"Content-Type": "application/json", "Origin": origin},
            )
            with opener.open(request, timeout=30) as response:
                return json.load(response)

        call(
            "/api/auth/sign-in/email",
            {
                "email": env["AUTO_ONTOLOGY_ADMIN_EMAIL"],
                "password": env["AUTO_ONTOLOGY_ADMIN_PASSWORD"],
            },
        )
        databases = call("/api/datasources/dbs")["data"]
        if {db["name"] for db in databases} != {
            unquote(urlsplit(sources[key]).path.lstrip("/")) for key in allowed
        }:
            raise ValueError(
                "Consumer catalog contains sources outside the approved scope"
            )
        confirmed = True
        for key, url in sorted(sources.items()):
            if not key.endswith("_DATABASE_URL"):
                continue
            readers.verify(url)
            name = unquote(urlsplit(url).path.lstrip("/"))
            match = [db for db in databases if db["name"] == name]
            if len(match) != 1:
                raise ValueError("Source database missing or ambiguous in catalog")
            tables = []
            for schema in call("/api/schemas/" + match[0]["id"])["schemas"]:
                tables.extend(call("/api/tables/" + schema["id"])["data"])
            target_columns = sum(
                call("/api/columns/" + table["id"])["total"] for table in tables
            )
            with (
                psycopg.connect(
                    url,
                    connect_timeout=10,
                    options="-c default_transaction_read_only=on",
                ) as connection,
                connection.cursor() as cur,
            ):
                cur.execute("""SELECT count(DISTINCT c.oid), count(a.attnum)
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
                    WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg\\_%'
                    AND NOT c.relispartition AND c.relkind IN ('r','p','v','m','f') AND has_table_privilege(c.oid,'SELECT')""")
                expected_tables, expected_columns = cur.fetchone()
            # This is the consumer's own local application store, never a source store.
            with (
                psycopg.connect(
                    host=env["POSTGRES_HOST"],
                    port=env["POSTGRES_PORT"],
                    dbname=env["POSTGRES_DATABASE"],
                    user=env["POSTGRES_USER"],
                    password=env["POSTGRES_PASSWORD"],
                    connect_timeout=10,
                    options="-c default_transaction_read_only=on",
                ) as connection,
                connection.cursor() as cur,
            ):
                cur.execute(
                    "SELECT count(*) FROM vdb.data_objects_layer WHERE database_name=%s AND embedding IS NOT NULL",
                    (name,),
                )
                embedded = cur.fetchone()[0]
            ok = (len(tables), target_columns) == (
                expected_tables,
                expected_columns,
            ) and embedded >= expected_tables + expected_columns
            confirmed = confirmed and ok
            print(
                json.dumps(
                    {
                        "source": key,
                        "tables": len(tables),
                        "columns": target_columns,
                        "expected_tables": expected_tables,
                        "expected_columns": expected_columns,
                        "embedded_rows": embedded,
                        "confirmed": ok,
                    }
                ),
                flush=True,
            )
        if args.enable_compilation:
            if not confirmed:
                raise ValueError("Complete catalog embeddings before compiling")
            call("/api/configurations/semantic-compilation", {"enabled": True}, "PUT")
        status = call("/api/semantic-compilation/status")
        print(
            json.dumps(
                {
                    "semantic_running": status.get("running"),
                    "semantic_success_recorded": bool(status.get("last_success_at")),
                    "semantic_failure_recorded": bool(status.get("last_failure_at")),
                }
            )
        )
        return 0 if confirmed else 1
    except Exception as error:  # noqa: BLE001 - prevent credential-bearing exceptions reaching stderr
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
