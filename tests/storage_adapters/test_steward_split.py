"""A steward's split of a consolidation on the engine under test (ticket 142)."""

import os
import subprocess
import sys

import pytest

from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


def test_a_steward_splits_a_merge(database_factory, configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("SQL Server full normal workflow is deferred")
    with database_factory() as (owner, runtime, role):
        result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.steward_split_scenarios"],
            env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED": "1",
                 "READ_KIND": "invented-kind", "READ_RUNTIME_ROLE": role, "READ_BASE_CASE": "join",
                 "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                 "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False)},
            capture_output=True, text=True, timeout=120)
        if result.returncode:
            (configured_root / "steward-split-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
            print(result.stdout[-2000:], result.stderr[-3000:])
        assert result.returncode == 0, "the steward split proof failed"
        assert result.stdout.strip().endswith("steward split proof passed")
