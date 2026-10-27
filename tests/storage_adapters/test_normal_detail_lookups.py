"""A configured detail lookup through normal restricted-role saves and the owner rebuild."""
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


@pytest.mark.parametrize("case", ["keys", "changes", "retired", "rebuild", "context"])
def test_normal_detail_lookup(case, database_factory, configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("SQL Server full normal workflow remains deferred")
    kind = "invented-kind"
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    for declared in (kind, "invented-other-kind"):
        if declared not in body["kinds"]:
            body["kinds"].append(declared)
    body["accepted_bars"][kind] = dict(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    body["detail_lookups"] = {"version": "invented-detail-lookup-v1", "kind": kind, "detail": "invented_rows",
        "keys": {"venue": ["invented_venue", "invented_symbol"], "code": ["invented_code", "invented_symbol"]}}
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    definitions = files.load(configured_root / "context/definitions.yaml")
    for declared in (kind, "invented-other-kind"):
        definitions["kinds"][declared] = "An invented master used for detail lookup qualification."
    (configured_root / "context/definitions.yaml").write_text(files.dumps(definitions))
    with database_factory() as (owner, runtime, role):
        result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.detail_lookup_scenarios"],
            env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED": "1",
                 "READ_KIND": kind, "READ_LOOKUP_CASE": case, "READ_RUNTIME_ROLE": role,
                 "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                 "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False)},
            capture_output=True, text=True, timeout=90)
        if result.returncode:
            (configured_root / "detail-lookup-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
        assert result.returncode == 0, "detail lookup failed; private diagnostic retained"
        assert result.stdout.strip().endswith("detail lookup proof passed")
