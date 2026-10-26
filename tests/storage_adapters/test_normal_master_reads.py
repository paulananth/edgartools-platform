"""Historical master, alias and original field provenance through the public API."""

import copy
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


@pytest.mark.parametrize("case", ["current", "history", "producer", "alias", "profile", "details", "plans", "unknown", "bulk_provenance", "inspection", "forced_publication", "pages", "review_pages", "context_current", "context_links", "context_relationships", "context_concurrent", "context_times", "context_lookup", "context_search_gap", "recording_authority", "recorded_time"])
@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"])
def test_normal_master_reads(case, kind, database_factory, configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("SQL Server full normal workflow is deferred")
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    if case == "context_search_gap":
        body.pop("master_search", None)
    if kind not in body["kinds"]:
        body["kinds"].append(kind)
    for declared in ("invented-kind", kind):
        body["accepted_bars"][declared] = copy.deepcopy(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    body["profiles"]["invented-role"] = [kind]
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    definitions_path = configured_root / "context/definitions.yaml"
    definitions = files.load(definitions_path)
    definitions["kinds"][kind] = "Invented configured master for consumer qualification."
    definitions_path.write_text(files.dumps(definitions))
    with database_factory() as (owner, runtime, role):
        result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.master_read_scenarios"],
            env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED": "1",
                 "READ_KIND": kind, "READ_CONSUMER_CASE": case, "READ_RUNTIME_ROLE": role,
                 "READ_BASE_CASE": "details" if case == "details" else "links" if case in ("context_links", "context_relationships") else "join",
                 "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                 "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False)},
            capture_output=True, text=True, timeout=90)
        if result.returncode:
            (configured_root / "master-read-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
        assert result.returncode == 0, "normal master read failed; private diagnostic retained"
        assert result.stdout.strip().endswith("normal master read proof passed")
