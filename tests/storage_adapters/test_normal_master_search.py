"""Configured indexed master names through normal restricted-role callers."""
import copy
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"])
@pytest.mark.parametrize("case", ["ranking", "legacy_gap", "concurrent", "configuration", "maintenance", "pages"])
def test_normal_master_search(kind, case, database_factory, configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("SQL Server full normal workflow remains deferred")
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    for declared in ("invented-kind", "invented-other-kind"):
        if declared not in body["kinds"]:
            body["kinds"].append(declared)
    body["accepted_bars"][kind] = copy.deepcopy(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    body["master_search"] = {"version": "invented-master-search-v1",
        "name_fields": ["invented_display", "invented_name"], "position_weight": 0.1}
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    definitions = files.load(configured_root / "context/definitions.yaml")
    for declared in ("invented-kind", "invented-other-kind"):
        definitions["kinds"][declared] = "An invented master used for search qualification."
    (configured_root / "context/definitions.yaml").write_text(files.dumps(definitions))
    with database_factory() as (owner, runtime, role):
        result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.master_search_scenarios"],
            env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED": "1",
                 "READ_KIND": kind, "READ_SEARCH_CASE": case, "READ_RUNTIME_ROLE": role,
                 "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                 "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False)},
            capture_output=True, text=True, timeout=90)
        if result.returncode:
            (configured_root / "master-search-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
        assert result.returncode == 0, "normal master search failed; private diagnostic retained"
        assert result.stdout.strip().endswith("normal master search proof passed")
