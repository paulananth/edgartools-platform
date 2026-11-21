"""The mirror SQL is written from the managed mirror record, bounded by the exposure list; nothing connects."""
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


MANAGED = {"mirror": "m1", "postgres_database": "data", "refresh_interval": "60 minutes", "target_table_type": "ICEBERG",
           "tables": [{"layer": "b", "table": "codes"}, {"layer": "a", "table": "thing"}]}


def test_create_lists_only_the_recorded_tables_under_their_layers_schema_and_names_the_configured_target():
    sql = mirror_sql.create(MANAGED, EXPOSURE, NAMES, "inst")
    assert "target_database => 'INVENTED_MIRROR'" in sql and "postgres_tables => ['pub.thing', 'ref.codes']" in sql
    assert "unread" not in sql
    assert "target_table_type => 'ICEBERG'" in sql and "refresh_interval => '60 minutes'" in sql and "mirror_name => 'm1'" in sql
    assert "postgres_instance => 'inst'" in sql and "postgres_database => 'data'" in sql


def test_retire_always_drops_the_target_with_the_mirror():
    assert mirror_sql.retire(MANAGED) == "CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('m1', TRUE);\n"


def test_release_keeps_the_target_and_gives_it_to_the_owner_role_without_copying_grants():
    sql = mirror_sql.release(MANAGED, {"owner": "INVENTED_OWNER", "mirror": {"database": "INVENTED_MIRROR"}})
    assert "DROP_MIRROR('m1', FALSE);" in sql and "TRUE" not in sql
    assert "GRANT OWNERSHIP ON DATABASE INVENTED_MIRROR TO ROLE INVENTED_OWNER;" in sql and "COPY CURRENT GRANTS" not in sql


def test_a_recorded_table_the_exposure_list_does_not_name_is_refused():
    managed = {**MANAGED, "tables": [{"layer": "a", "table": "working_table"}]}
    with pytest.raises(SystemExit, match="a.working_table"):
        mirror_sql.tables(managed, EXPOSURE)


def test_a_table_read_but_not_recorded_is_named():
    managed = {**MANAGED, "tables": [{"layer": "a", "table": "thing"}]}
    assert mirror_sql.unmirrored_reads(READS, managed) == ["b.codes"]
    assert mirror_sql.unmirrored_reads(READS, MANAGED) == []


def test_alter_adds_what_is_recorded_and_removes_what_is_not():
    sql = mirror_sql.alter(MANAGED, EXPOSURE, ["pub.thing", "pub.unread"])
    assert "add_tables => ['ref.codes']" in sql and "remove_tables => ['pub.unread']" in sql and "mirror_name => 'm1'" in sql


def test_alter_writes_nothing_when_the_mirror_holds_exactly_the_record():
    assert mirror_sql.alter(MANAGED, EXPOSURE, ["ref.codes", "pub.thing"]) == ""


def test_the_repository_record_lists_the_masters_the_published_codes_and_every_silver_table_and_no_working_table_and_gold_reads_only_those():
    from edgar_warehouse.gold import views
    exposure = yaml.safe_load((ROOT / "rules/exposure.yaml").read_text())
    managed = yaml.safe_load((ROOT / "sources/managed-mirror.yaml").read_text())
    names = mirror_sql.tables(managed, exposure)
    silver = sorted(f"silver.{t['table']}" for t in exposure["tables"] if t["layer"] == "silver")
    assert names == ["public.mastering_identifier", "public.mastering_master", "rdm.published_code"] + silver and len(names) == 19
    assert mirror_sql.unmirrored_reads(views.sources(), managed) == []
    assert managed["verified"] is False  # no mirror exists until a read-back says every table replicates
