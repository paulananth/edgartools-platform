"""Rules lifecycle from the committed, independently installed five-wheel bundle."""
import json
import os

import pytest

from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401
from tests.integration.test_rules_approval_postgres import pipeline


@pytest.mark.skipif(os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql",
                    reason="Full SQL Server Rules qualification follows PostgreSQL/MySQL")
def test_installed_rules_cli_lifecycle(installed, database_factory):
    python, root = installed
    with database_factory() as (_, _, approval_role):
        with database_factory() as (owner, runtime, role):
            config = root / "invented-pipeline.json"
            config.write_text(json.dumps(pipeline()))
            environment = {"RULES_MIGRATION_DATABASE_URL": owner.url.render_as_string(hide_password=False),
                           "RULES_DATABASE_URL": runtime.url.render_as_string(hide_password=False)}
            program = '''
import json, sys
from pathlib import Path
from edgar_warehouse.cli import main
from edgar_warehouse.rules.db import Rules, get_engine
from edgar_warehouse.rules import files
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
root, role, approval, database = json.load(sys.stdin)
root = Path(root)
assert main(["rules", "init", "--agent-role", role, "--approver-role", approval, "--database-name", database]) == 0
assert main(["rules", "save", "--pipeline", "invented.installed", "--version", "v1", str(root / "invented-pipeline.json")]) == 0
engine = get_engine()
try:
    rules = Rules(engine)
    row = rules.version("pipeline", "invented.installed", "v1")
    proof = Artifacts().put(root.as_uri(), {"digest": row["digest"], "passed": True, "batch_hash": "1" * 64})
    assert main(["rules", "record-proof", "--pipeline", "invented.installed", "--version", "v1",
                 "--proof-uri", proof["uri"], "--proof-sha256", proof["sha256"]]) == 0
    assert main(["rules", "pending"]) == 0
    evidence = rules.pending()[0]["evidence_hash"]
    assert main(["rules", "approve", "--pipeline", "invented.installed", "--version", "v1", "--evidence", evidence,
                 "--by", "invented operator", "--words", "Approve the tested pipeline"]) == 0
    assert main(["rules", "activate", "--pipeline", "invented.installed", "--version", "v1"]) == 0
    assert main(["rules", "status", "--pipeline", "invented.installed"]) == 0
    assert main(["rules", "export", "--pipeline", "invented.installed", "--version", "v1", "--output", str(root / "export.json")]) == 0
    assert files.load(root / "export.json") == files.load(root / "invented-pipeline.json")
    assert main(["rules", "migrate", "--agent-role", role, "--approver-role", approval, "--database-name", database]) == 0
    assert rules.version("pipeline", "invented.installed", "v1")["status"] == "active"
finally:
    engine.dispose()
print(json.dumps({"installed": True, "active": 1, "unchanged_upgrade": True}))
'''
            result = _run(python, "-c", program, env=environment, cwd=root,
                          document=[str(root), role, approval_role, owner.url.database])
            if result.returncode:
                (root / "rules-private-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
            assert result.returncode == 0, "Installed Rules failed; private diagnostic retained"
            assert json.loads(result.stdout.splitlines()[-1]) == {"installed": True, "active": 1, "unchanged_upgrade": True}
