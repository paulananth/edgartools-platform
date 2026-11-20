"""The mirror SQL is written from what a dbt project reads, bounded by the exposure list; nothing connects."""
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mirror_sql", ROOT / "skills/data-platform/scripts/exposure/mirror_sql.py")
mirror_sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror_sql)

EXPOSURE = {"layers": {"a": {"source_schema": "pub"}, "b": {"source_schema": "ref"}},
            "tables": [{"layer": "b", "table": "codes"}, {"layer": "a", "table": "thing"}]}
EXPOSURE["tables"].append({"layer": "a", "table": "unread"})
NAMES = {"mirror": {"database": "INVENTED_MIRROR"}}
READS = {"version": 2, "sources": [{"name": "a", "tables": [{"name": "thing"}]}, {"name": "b", "tables": [{"name": "codes"}]}]}


def test_create_lists_only_the_read_tables_under_their_layers_schema_and_names_the_configured_target():
    sql = mirror_sql.create(READS, EXPOSURE, NAMES, "m1", "inst", "data", "60 minutes", "ICEBERG")
    assert "target_database => 'INVENTED_MIRROR'" in sql and "postgres_tables => ['pub.thing', 'ref.codes']" in sql
    assert "unread" not in sql
    assert "target_table_type => 'ICEBERG'" in sql and "refresh_interval => '60 minutes'" in sql and "mirror_name => 'm1'" in sql


def test_retire_always_drops_the_target_with_the_mirror():
    assert mirror_sql.retire("old") == "CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('old', TRUE);\n"


def test_a_read_the_exposure_list_does_not_name_is_refused():
    reads = {"sources": [{"name": "a", "tables": [{"name": "working_table"}]}]}
    with pytest.raises(SystemExit, match="a.working_table"):
        mirror_sql.tables(reads, EXPOSURE)


def test_alter_adds_what_is_read_and_removes_what_nothing_reads():
    sql = mirror_sql.alter(READS, EXPOSURE, "m1", ["pub.thing", "pub.unread"])
    assert "add_tables => ['ref.codes']" in sql and "remove_tables => ['pub.unread']" in sql and "mirror_name => 'm1'" in sql


def test_alter_writes_nothing_when_the_mirror_holds_exactly_the_reads():
    assert mirror_sql.alter(READS, EXPOSURE, "m1", ["ref.codes", "pub.thing"]) == ""


def test_the_repository_gold_project_mirrors_the_masters_the_published_codes_and_every_silver_table_and_no_working_table():
    from edgar_warehouse.gold import views
    exposure = yaml.safe_load((ROOT / "rules/exposure.yaml").read_text())
    names = mirror_sql.tables(views.sources(), exposure)
    silver = sorted(f"silver.{t['table']}" for t in exposure["tables"] if t["layer"] == "silver")
    assert names == ["public.mastering_identifier", "public.mastering_master", "rdm.published_code"] + silver and len(names) == 19
