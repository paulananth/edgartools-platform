"""The PostgreSQL schema audit distinguishes extension objects from application objects."""

from __future__ import annotations

import psycopg2
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "access-audit" / "scripts"))

from audit_platforms import postgres  # noqa: E402
from tests.support.pg16 import server


def test_public_schema_audit_ignores_extension_objects_and_flags_application_objects():
    with server() as instance:
        admin = psycopg2.connect(instance.url(driver="postgresql"))
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                for database in ("data", "control", "config"):
                    cursor.execute(f"CREATE DATABASE {database}")
        finally:
            admin.close()

        env = {"DATA_URL": instance.url("data", driver="postgresql")}

        def schema_result():
            evidence = postgres.collect(env)
            return next(control for control in postgres.controls(evidence) if control["id"] == "SCH.postgres")

        assert schema_result()["result"] == "PASS"

        for database in ("data", "control", "config"):
            with psycopg2.connect(instance.url(database, driver="postgresql")) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("CREATE EXTENSION pg_stat_statements")

        extension_only = schema_result()
        assert extension_only["result"] == "PASS"
        assert extension_only["evidence"]["public_objects"] == {"data": 0, "control": 0, "config": 0}

        for database in ("data", "control", "config"):
            with psycopg2.connect(instance.url(database, driver="postgresql")) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE public.application_table (id bigint)")
                    cursor.execute("CREATE VIEW public.application_view AS SELECT id FROM public.application_table")
                    cursor.execute("CREATE SEQUENCE public.application_sequence")
                    cursor.execute(
                        "CREATE FUNCTION public.application_function() RETURNS bigint "
                        "LANGUAGE sql IMMUTABLE AS 'SELECT 1::bigint'"
                    )

        application_objects = schema_result()
        assert application_objects["result"] == "FAIL"
        assert all(count > 0 for count in application_objects["evidence"]["public_objects"].values())
