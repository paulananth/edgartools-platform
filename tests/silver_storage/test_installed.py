"""The committed five-wheel bundle writes Silver without the checkout."""
import json

import pytest

from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401
from tests.unit.test_silver_writer import a_spec


@pytest.mark.parametrize("mode", ["append", "upsert", "snapshot"])
def test_installed_normal_silver_caller(installed, database_factory, mode):
    python, root = installed
    with database_factory() as (owner, runtime, role):
        config = a_spec(table="invented_installed_rows", links=[], load_mode=mode)
        config["columns"][2]["type"] = "DECIMAL(30,8)"
        config["columns"].append({"name": "duration", "type": "INTERVAL", "nullable": True})
        spec = root / "silver-spec.json"
        spec.write_text(json.dumps(config))
        rows = root / "silver-rows.jsonl"
        rows.write_text('{"visit_id":1,"member_id":"invented","amount":12345678901234567890.12345678,'
                        '"visited_on":"2026-10-01","duration":"2 days 01:02:03.123456",'
                        '"tags":{"fraction":0.123456789012345678901234567890123,"tiny":1e-600}}\n')
        environment = {"SILVER_MIGRATION_DATABASE_URL": owner.url.render_as_string(hide_password=False),
                       "SILVER_DATABASE_URL": runtime.url.render_as_string(hide_password=False),
                       "MDM_DATABASE_URL": ""}
        program = '''
import json, sys
from edgar_warehouse.cli import main
command = json.load(sys.stdin)
sys.exit(main(command))
'''
        commands = [["silver", "init", "--runtime-role", role],
                    ["silver", "register", str(spec), "--runtime-role", role],
                    ["silver", "land", config["table"], str(rows)],
                    ["silver", "land", config["table"], str(rows)],
                    ["silver", "describe", config["table"]]]
        reports = []
        for command in commands:
            result = _run(python, "-c", program, env=environment, cwd=root, document=command)
            assert result.returncode == 0, "Installed Silver caller failed; connection details withheld"
            reports.append(json.loads(result.stdout))
        assert reports[1]["created"]
        assert (reports[2]["inserted"], reports[3]["inserted"], reports[3]["changed"]) == (1, 0, 0)
        assert reports[4]["key"] == ["visit_id"] and reports[4]["kind"] == "silver table"

        proof = _run(python, "-c", """
import json, sys
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import inspect, select
from edgar_warehouse.database_connections import engine_from_env
from edgar_warehouse.silver_writer.relational import DatabaseSink
from edgar_warehouse.silver_writer.tables import data_table
engine = engine_from_env("SILVER_DATABASE_URL")
try:
    spec = DatabaseSink(engine).spec("invented_installed_rows")
    table = data_table(spec, engine.dialect.name)
    with engine.connect() as conn:
        row = conn.execute(select(table)).mappings().one()
        assert row["amount"] == Decimal("12345678901234567890.12345678")
        assert row["tags"] == {"fraction":Decimal("0.123456789012345678901234567890123"),"tiny":Decimal("1e-600")}
        assert row["duration"] == timedelta(days=2,hours=1,minutes=2,seconds=3,microseconds=123456)
        indexes = inspect(conn).get_indexes(table.name, schema=table.schema)
        assert any(index["column_names"] == spec["partition"] for index in indexes)
    print("installed exact transport and partition proof passed")
finally:
    engine.dispose()
""", env=environment, cwd=root)
        assert proof.returncode == 0, "Installed Silver readback failed; private connection details withheld"
        assert proof.stdout.strip() == "installed exact transport and partition proof passed"
