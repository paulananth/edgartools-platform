"""Actual Silver-facing master lookup after normal configured MDM saves."""

import copy
import os
import subprocess
import sys
from contextlib import nullcontext

import pytest

from edgar_warehouse.rules import files
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


@pytest.mark.parametrize("case", ["lookup", "waiting", "merge", "unicode", "chunks", "silver", "concurrent"])
@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"])
def test_normal_master_ids(case, kind, database_factory, configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("SQL Server full normal workflow is deferred")
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    if kind not in body["kinds"]:
        body["kinds"].append(kind)
    for declared in ("invented-kind", kind):
        body["accepted_bars"][declared] = copy.deepcopy(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    with database_factory() as (owner, runtime, role):
        with database_factory() if case == "silver" else nullcontext(None) as destination:
            env = {**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED": "1",
                   "READ_KIND": kind, "READ_ID_CASE": case, "READ_RUNTIME_ROLE": role,
                   "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                   "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False)}
            if destination:
                silver_owner, silver_runtime, silver_role = destination
                env.update(READ_SILVER_OWNER_URL=silver_owner.url.render_as_string(hide_password=False),
                           READ_SILVER_RUNTIME_URL=silver_runtime.url.render_as_string(hide_password=False),
                           READ_SILVER_ROLE=silver_role)
            result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.master_id_scenarios"],
                                    env=env, capture_output=True, text=True, timeout=90)
            if result.returncode:
                (configured_root / "master-id-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
            assert result.returncode == 0, "normal master-ID lookup failed; private diagnostic retained"
            assert result.stdout.strip().endswith("normal master-ID proof passed")
