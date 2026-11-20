"""The Rules Database from the committed, independently installed five-wheel bundle."""
import json
import os

import pytest

from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401
from tests.storage_adapters.test_rules_runtime import pipeline


@pytest.mark.skipif(os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql",
                    reason="The Rules Database is qualified on PostgreSQL and MySQL")
def test_installed_rules_cli_records_and_reports_the_rules_a_run_used(installed, database_factory):
    python, root = installed
    with database_factory() as (owner, runtime, role):
        owner_env = {"CONTROL_URL": owner.url.set(drivername=owner.dialect.name).render_as_string(hide_password=False)}
        runtime_env = {"CONTROL_URL": runtime.url.set(drivername=runtime.dialect.name).render_as_string(hide_password=False)}
        init = '''
import sys
from edgar_warehouse.cli import main
assert main(["rules", "init", "--agent-role", sys.argv[1]]) == 0
'''
        use = '''
import json, sys
from edgar_warehouse.cli import main
from edgar_warehouse.rules import frozen
from edgar_warehouse.rules.db import Rules, get_engine
body = json.load(sys.stdin)
engine = get_engine()
try:
    rules = Rules(engine)
    export = frozen.of("pipeline", "invented.installed", body)
    rules.record(export)
    assert [row["digest"] for row in rules.history("pipeline", "invented.installed")] == [export["digest"]]
    assert main(["rules", "status", "--pipeline", "invented.installed"]) == 0
finally:
    engine.dispose()
print(json.dumps({"installed": True, "recorded": 1, "unchanged_upgrade": True}))
'''
        for env in (owner_env, owner_env):  # init, and again over a store that holds the schema: nothing changes
            done = _run(python, "-c", init, role, env=env, cwd=root)
            assert done.returncode == 0, "Installed Rules init failed; private diagnostic retained"
        result = _run(python, "-c", use, env=runtime_env, cwd=root, document=pipeline())
        if result.returncode:
            (root / "rules-private-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
        assert result.returncode == 0, "Installed Rules failed; private diagnostic retained"
        assert json.loads(result.stdout.splitlines()[-1]) == {"installed": True, "recorded": 1, "unchanged_upgrade": True}
