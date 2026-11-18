"""The exposure manifest reads each listed table back from a real PostgreSQL store: its columns, types and comments as
the catalog holds them. Every table and value here is invented."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from exposure_manifest import generate, validate_manifest  # noqa: E402

LIST = {
    "version": "invented-exposure",
    "approval": {"date": "2026-01-01", "words": ["Invented approval"]},
    "target": {"database": "INVENTED_MIRROR", "verified": False},
    "layers": {
        "silver": {
            "connection": "INVENTED_SILVER_URL",
            "source_schema": "silver",
            "target_schema": "SILVER",
            "authority": "silver",
        },
        "mdm": {
            "connection": "INVENTED_MDM_URL",
            "source_schema": "public",
            "target_schema": "MDM",
            "authority": "mdm",
        },
    },
    "tables": [
        {
            "layer": "silver",
            "table": "widget_sale",
            "scope": "history",
            "grain": "one row per sale",
            "requirement": "invented.yaml",
            "lineage": ["mdm.golden"],
        },
        {
            "layer": "mdm",
            "table": "golden",
            "scope": "current",
            "grain": "one row per MDM id",
            "requirement": "invented.yaml",
            "definition": "One invented golden record.",
            "columns": {"entity_id": "The invented MDM id.", "body": "The invented record."},
        },
    ],
}


@pytest.fixture
def store(postgres):
    admin, _ = postgres
    name = f"exposure_{uuid4().hex[:10]}"
    server = admin.execution_options(isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(admin.url.set(database=name))
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE SCHEMA silver")
        conn.exec_driver_sql(
            "CREATE TABLE silver.widget_sale (sale_id text NOT NULL, amount numeric(18,2), "
            "sold_at timestamp with time zone NOT NULL, PRIMARY KEY (sale_id))"
        )
        conn.exec_driver_sql("COMMENT ON TABLE silver.widget_sale IS 'One invented sale.'")
        for column, words in (("sale_id", "The sale id."), ("amount", "The amount."), ("sold_at", "When sold.")):
            conn.exec_driver_sql(f"COMMENT ON COLUMN silver.widget_sale.{column} IS '{words}'")
        conn.exec_driver_sql("CREATE TABLE silver.widget_draft (draft_id text)")
        conn.exec_driver_sql("CREATE TABLE golden (entity_id char(36) PRIMARY KEY, body text NOT NULL)")
    try:
        yield engine.url.render_as_string(hide_password=False)
    finally:
        engine.dispose()
        with server.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))


def write(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "exposure.yaml"
    path.write_text(yaml.safe_dump(body))
    return path


def test_each_listed_tables_columns_types_and_comments_come_from_its_store(store, tmp_path):
    env = {"INVENTED_SILVER_URL": store, "INVENTED_MDM_URL": store}
    config = write(tmp_path, LIST)
    manifest = generate(config, env)
    validate_manifest(manifest, config=config)
    sale, golden = (
        next(t for t in manifest["tables"] if t["source"]["table"] == n) for n in ("widget_sale", "golden")
    )
    assert [(c["name"], c["data_type"], c["nullable"], c["description"]) for c in sale["columns"]] == [
        ("sale_id", "text", False, "The sale id."),
        ("amount", "numeric(18,2)", True, "The amount."),
        ("sold_at", "timestamp with time zone", False, "When sold."),
    ]
    assert sale["business"]["description"] == "One invented sale."
    assert [(c["name"], c["data_type"]) for c in golden["columns"]] == [
        ("entity_id", "character(36)"),
        ("body", "text"),
    ]
    assert {t["source"]["table"] for t in manifest["tables"]} == {"widget_sale", "golden"}  # the draft is unlisted


def test_a_listed_table_its_store_lacks_is_refused(store, tmp_path):
    body = {
        **LIST,
        "tables": [
            *LIST["tables"],
            {
                "layer": "silver",
                "table": "widget_missing",
                "scope": "current",
                "grain": "one row per thing",
                "requirement": "invented.yaml",
            },
        ],
    }
    with pytest.raises(ValueError, match="widget_missing is not in its store"):
        generate(write(tmp_path, body), {"INVENTED_SILVER_URL": store, "INVENTED_MDM_URL": store})


def test_an_unset_or_unreachable_store_is_named_by_its_setting_never_its_address(store, tmp_path):
    config = write(tmp_path, LIST)
    with pytest.raises(ValueError, match="INVENTED_MDM_URL is not set"):
        generate(config, {"INVENTED_SILVER_URL": store})
    unreachable = "postgresql+psycopg2://invented_user:invented-secret@127.0.0.1:1/none"
    with pytest.raises(ValueError) as refused:
        generate(config, {"INVENTED_SILVER_URL": unreachable, "INVENTED_MDM_URL": store})
    assert "INVENTED_SILVER_URL" in str(refused.value) and "invented-secret" not in str(refused.value)
