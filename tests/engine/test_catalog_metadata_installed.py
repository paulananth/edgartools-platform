"""The public metadata commands and generated workbooks ship in the bundle."""
import json

from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401


def test_catalog_plan_and_all_mapping_documents_work_outside_the_checkout(installed):
    python, root = installed
    result = _run(python, "-m", "edgar_warehouse.cli", "rules", "catalog", "plan", cwd=root)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["pipeline_service"]["serviceType"] == "CustomPipeline"
    assert plan["pipelines"] and all(p["tasks"] for p in plan["pipelines"])
    assert any(t["databaseSchema"].endswith(".relationships") for t in plan["tables"])
    check = _run(python, "-m", "edgar_warehouse.cli", "rules", "mapdoc", "check", cwd=root)
    assert check.returncode == 0, check.stdout + check.stderr
    refused = _run(python, "-m", "edgar_warehouse.cli", "rules", "catalog", "check", cwd=root,
                   env={"OPENMETADATA_URL": "", "OPENMETADATA_TOKEN": ""})
    assert refused.returncode == 2 and "OPENMETADATA_TOKEN" in refused.stderr
