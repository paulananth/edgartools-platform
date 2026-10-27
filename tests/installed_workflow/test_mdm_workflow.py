"""Normal callers from a committed installation, never checkout runtime imports."""
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import installed  # noqa: F401
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
# A case may establish several families; the manifest retains every case, not
# just a family-level success flag. Ordinary saves seed only through MergeStage.
CASES = {
    "merge": {
        "join": ["Q02", "Q04"], "list_join": ["Q04"], "rule_merge": ["Q04"], "cusip_first": ["Q04"], "issuer_only": ["Q04"], "newest": ["Q04"],
        "corrected": ["Q06", "Q09"], "released": ["Q09"], "quarantine": ["Q09"],
        "lifted": ["Q09"], "retired": ["Q09"], "assessment": ["Q11"],
        "stale_assessment": ["Q11"], "preview": ["Q12"], "collision": ["Q12"],
        "unchanged": ["Q06", "Q12"], "occurrence": ["Q06", "Q16"],
        "deferred": ["Q04", "Q15"], "competing": ["Q10"],
        "mint_competing": ["Q10"], "no_identity_stale": ["Q11"],
        "name_holder_first": ["Q05"], "name_candidate_first": ["Q05"],
        "name_held_value": ["Q05"], "cascade_holder_first": ["Q05"],
        "cascade_candidate_first": ["Q05"], "links": ["Q08"],
        "hierarchy": ["Q08"], "details": ["Q08"],
    },
    "reader": {name: ["Q17"] for name in (
        "current", "history", "producer", "alias", "details", "pages", "review_pages",
        "context_current", "context_links", "context_relationships", "context_concurrent",
        "context_times", "context_lookup")},
    "ids": {"silver": ["Q17"], "unicode": ["Q17"], "chunks": ["Q17"]},
    "search": {"words": ["Q18"], "changes": ["Q18"], "plans": ["Q18"], "rebuild": ["Q18"]},
    "worker": {"authority": ["Q13"], "publication": ["Q16"], "merge_worker": ["Q12", "Q15"],
        "journal": ["Q16"], "forced": ["Q16"], "mapping_freeze": ["Q06"],
        "review_recovery": ["Q15", "Q16"], "held_review": ["Q15"]},
}
CASES["reader"].update({"profile": ["Q07", "Q17"], "plans": ["Q18"],
    "bulk_provenance": ["Q18"], "inspection": ["Q18"], "recorded_time": ["Q18"],
    "recording_authority": ["Q18"]})

CASES["boundary"] = {"upgrade": ["Q03"], "upgrade_interrupted": ["Q03"],
    "exact_values": ["Q06"], "profiles_overrides_kind": ["Q07"],
    "identifier_holder_first":["Q04"], "identifier_candidate_first":["Q04","Q15"],
    "late_expiry": ["Q13"], "held_transaction": ["Q13"], "invalid_wire": ["Q13"],
    **{"fault_"+name:["Q14"] for name in ("current","history","evidence","lookup","batch","checkpoint","outbox","proposal","proposal_event")}}


GROUPS = {"merge": {"merge"}, "readers": {"reader", "ids", "search"},
          "boundaries": {"boundary"}, "workers": {"worker"}}
SHARD = os.environ.get("MDM_WORKFLOW_SHARD")
if SHARD is not None and SHARD not in GROUPS:
    raise ValueError("Unknown installed qualification group")
SELECTED = CASES if SHARD is None else {name: cases for name,cases in CASES.items() if name in GROUPS[SHARD]}


@pytest.fixture(scope="module")
def proof_install(installed):
    python, root = installed
    # pytest belongs to the test harness, not to the shipped runtime dependency set.
    done = subprocess.run(["uv", "pip", "install", "--python", str(python), "pytest"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, "installing the isolated assertion helper failed"
    harness = root / "qualification-harness" / os.environ["SKILL_ADAPTER_TEST_ENGINE"]
    shutil.copytree(ROOT / "tests", harness / "tests", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    # The existing assertion-fixture module reads this frozen test asset at
    # import time. Copy the asset, never add the checkout to isolated sys.path.
    asset = Path(".scratch/company-mastering/research/08-rules.json")
    destination = harness / asset
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / asset, destination)
    assert hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256((ROOT / asset).read_bytes()).digest()
    return python, root, harness


def configure(root, kind):
    body = files.load(root / "mastering/engine-v1.yaml")
    for name in ("invented-kind", "invented-other-kind"):
        if name not in body["kinds"]:
            body["kinds"].append(name)
        body["accepted_bars"][name] = copy.deepcopy(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    body["profiles"]["invented-role"] = [kind]
    body["master_search"] = {"version": "invented-master-search-v1",
        "name_fields": ["invented_display", "invented_name"], "position_weight": 0.1}
    (root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    path = root / "context/definitions.yaml"
    definitions = files.load(path)
    for name in ("invented-kind", "invented-other-kind"):
        definitions["kinds"][name] = "Invented qualification master."
    path.write_text(files.dumps(definitions))


LAUNCHER = '''
import hashlib, importlib, importlib.metadata, json, os, pathlib, runpy, sys
install = pathlib.Path(os.environ["WORKFLOW_INSTALL"]).resolve()
expected = os.environ["WORKFLOW_REVISION"]
for distribution in ("edgartools-data", "edgartools-bookkeeping", "edgartools-change-journal", "source-contract", "edgartools-control-core"):
    info = json.loads(importlib.metadata.distribution(distribution).read_text("direct_url.json"))
    assert info["vcs_info"]["commit_id"] == expected
for name in ("edgar_warehouse", "source_contract", "edgar_control"):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(install)
sys.path.insert(0, os.environ["WORKFLOW_HARNESS"])
surface = os.environ["WORKFLOW_SURFACE"]
module = {"merge":"record_read_scenarios", "reader":"master_read_scenarios", "ids":"master_id_scenarios", "search":"master_search_scenarios", "worker":"worker_publication_scenarios"}.get(surface)
runpy.run_module("tests.storage_adapters." + module if module else "tests.installed_workflow.normal_workflow_cases", run_name="__main__")
for name, module in tuple(sys.modules.items()):
    if name.split(".")[0] in {"edgar_warehouse", "source_contract", "edgar_control"} and getattr(module, "__file__", None):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(install), name
print(json.dumps({"case":os.environ["WORKFLOW_CASE"], "kind":os.environ["READ_KIND"], "families":json.loads(os.environ["WORKFLOW_FAMILIES"]), "revision":expected, "installed":True, "passed":True}))
'''


@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"])
@pytest.mark.parametrize("surface,case,families", [
    (surface, case, ["Q01", *families]) for surface, cases in SELECTED.items() for case, families in cases.items()
], ids=[surface+"-"+case for surface, cases in SELECTED.items() for case in cases])
def test_installed_workflow(surface, case, families, kind, proof_install, database_factory, configured_root):
    assert os.environ.get("SKILL_ADAPTER_TEST_ENGINE") in {"postgresql", "mysql"}
    python, root, harness = proof_install
    configure(configured_root, kind)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    started = time.monotonic()
    with ExitStack() as stack:
        owner, runtime, role = stack.enter_context(database_factory())
        env = {**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_PREPARED": "1",
            "READ_KIND": kind, "READ_CASE": case, "READ_CONSUMER_CASE": case,
            "READ_ID_CASE": case, "READ_SEARCH_CASE": case, "READ_WORKER_CASE": case,
            "READ_BASE_CASE": "details" if case == "details" else "links" if case in ("context_links", "context_relationships") else "join",
            "READ_RUNTIME_ROLE": role, "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
            "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False),
            "WORKFLOW_INSTALL": str(root), "WORKFLOW_HARNESS": str(harness),
            "WORKFLOW_REVISION": revision, "WORKFLOW_SURFACE": surface,
            "WORKFLOW_CASE": surface+"-"+case, "WORKFLOW_FAMILIES": json.dumps(families)}
        if surface == "worker" and case == "journal" or surface == "ids" and case == "silver":
            other_owner, other_runtime, other_role = stack.enter_context(database_factory())
            prefix = "JOURNAL" if surface == "worker" else "SILVER"
            env.update({f"READ_{prefix}_OWNER_URL":other_owner.url.render_as_string(hide_password=False),
                f"READ_{prefix}_RUNTIME_URL":other_runtime.url.render_as_string(hide_password=False),
                f"READ_{prefix}_ROLE":other_role})
        done = subprocess.run([str(python), "-I", "-c", LAUNCHER], cwd=root, env=env,
                              capture_output=True, text=True, timeout=180)
        diagnostic = configured_root / "installed-workflow-diagnostic.log"
        if done.returncode:
            diagnostic.write_text(done.stdout+"\n"+done.stderr)
        assert done.returncode == 0, "installed workflow failed; private diagnostic retained"
        result = json.loads(done.stdout.splitlines()[-1])
        assert result == {"case":surface+"-"+case, "kind":kind, "families":families,
                          "revision":revision, "installed":True, "passed":True}
    (configured_root / "installed-workflow-outcome.json").write_text(json.dumps({**result,
        "engine":os.environ["SKILL_ADAPTER_TEST_ENGINE"], "cleanup_verified":True,
        "elapsed_seconds":round(time.monotonic()-started,3),
        "configuration_sha256":hashlib.sha256((configured_root / "mastering/engine-v1.yaml").read_bytes()).hexdigest()}))


@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"] if SHARD in (None, "workers") else [])
def test_installed_separate_workers(kind, proof_install, database_factory, configured_root):
    """Retain the separate SELECT-only verifier and actual worker processes."""
    from tests.storage_adapters.test_installed_worker import test_installed_worker_recovery

    python, root, _ = proof_install
    started = time.monotonic()
    test_installed_worker_recovery(kind, (python, root), database_factory, configured_root)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (configured_root / "installed-workflow-outcome.json").write_text(json.dumps({
        "case":"separate-worker-processes", "kind":kind, "revision":revision,
        "families":["Q01","Q04","Q15","Q16"], "installed":True, "passed":True,
        "engine":os.environ["SKILL_ADAPTER_TEST_ENGINE"], "cleanup_verified":True,
        "elapsed_seconds":round(time.monotonic()-started,3),
        "configuration_sha256":hashlib.sha256((configured_root / "mastering/engine-v1.yaml").read_bytes()).hexdigest()}))
