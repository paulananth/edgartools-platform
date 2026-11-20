"""The mirror SQL is written from the exposure list and the one file of database names; nothing connects."""
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mirror_sql", ROOT / "skills/data-platform/scripts/exposure/mirror_sql.py")
mirror_sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror_sql)

EXPOSURE = {"layers": {"a": {"source_schema": "pub"}, "b": {"source_schema": "ref"}},
            "tables": [{"layer": "b", "table": "codes"}, {"layer": "a", "table": "thing"}]}
NAMES = {"mirror": {"database": "INVENTED_MIRROR"}}


def test_create_lists_each_table_under_its_layers_schema_and_names_the_configured_target():
    sql = mirror_sql.create(EXPOSURE, NAMES, "m1", "inst", "data")
    assert "target_database => 'INVENTED_MIRROR'" in sql and "postgres_tables => ['pub.thing', 'ref.codes']" in sql
    assert "target_table_type => 'ICEBERG'" in sql and "refresh_interval => '60 minutes'" in sql and "mirror_name => 'm1'" in sql


def test_retire_always_drops_the_target_with_the_mirror():
    assert mirror_sql.retire("old") == "CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('old', TRUE);\n"


def test_the_repository_exposure_list_makes_nineteen_table_names():
    assert len(mirror_sql.tables(yaml.safe_load((ROOT / "rules/exposure.yaml").read_text()))) == 19
