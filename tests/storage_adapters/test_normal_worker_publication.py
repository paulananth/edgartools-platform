"""Normal configured worker and publication paths on selected storage."""
import copy
from contextlib import ExitStack
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"])
@pytest.mark.parametrize("case", ["authority", "publication", "merge_worker", "journal", "forced", "mapping_freeze", "review_recovery", "held_review"])
def test_normal_worker_publication(kind, case, database_factory, configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("SQL Server normal workflow remains deferred")
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    if kind not in body["kinds"]:
        body["kinds"].append(kind)
    body["accepted_bars"][kind] = copy.deepcopy(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    with ExitStack() as stack:
        owner, runtime, role = stack.enter_context(database_factory())
        journal = {}
        if case == "journal":
            journal_owner, journal_runtime, journal_role = stack.enter_context(database_factory())
            journal = {
                "READ_JOURNAL_OWNER_URL": journal_owner.url.render_as_string(hide_password=False),
                "READ_JOURNAL_RUNTIME_URL": journal_runtime.url.render_as_string(hide_password=False),
                "READ_JOURNAL_ROLE": journal_role,
            }
        result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.worker_publication_scenarios"],
            env={**os.environ, **journal, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED":"1",
                 "READ_KIND":kind, "READ_WORKER_CASE":case, "READ_RUNTIME_ROLE":role,
                 "READ_OWNER_URL":owner.url.render_as_string(hide_password=False),
                 "READ_RUNTIME_URL":runtime.url.render_as_string(hide_password=False)},
            capture_output=True, text=True, timeout=90)
        if result.returncode:
            (configured_root / "worker-publication-diagnostic.log").write_text(result.stdout+"\n"+result.stderr)
        assert result.returncode == 0, "normal worker/publication failed; private diagnostic retained"
        assert result.stdout.strip().endswith("normal worker publication proof passed")
