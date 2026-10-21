"""The committed five-wheel bundle writes Silver without the checkout."""
import json

from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401
from tests.unit.test_silver_writer import a_spec


def test_installed_normal_silver_caller(installed, database_factory):
    python, root = installed
    with database_factory() as (owner, runtime, role):
        config = a_spec(table="invented_installed_rows", links=[])
        spec = root / "silver-spec.json"
        spec.write_text(json.dumps(config))
        rows = root / "silver-rows.jsonl"
        rows.write_text(json.dumps({"visit_id": 1, "member_id": "invented", "tags": ["invented"]}) + "\n")
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
