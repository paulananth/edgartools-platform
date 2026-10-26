"""Committed five-wheel workers, separate verifier login, no checkout imports."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import installed  # noqa: F401
from tests.mdm.test_clean_activation import CIK_CONTRACT
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401
from tests.support.rules_authority import authority
from tests.support.reading import reading


@pytest.mark.parametrize("kind",["invented-kind","invented-other-kind"])
def test_installed_worker_recovery(kind,installed,database_factory,configured_root):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("Full SQL Server workflow remains deferred")
    python,root = installed
    body = files.load(configured_root/"mastering/engine-v1.yaml")
    if kind not in body["kinds"]:
        body["kinds"].append(kind)
    body["accepted_bars"][kind] = copy.deepcopy(body["accepted_bars"]["company"])
    (configured_root/"mastering/engine-v1.yaml").write_text(files.dumps(body))
    sources = ["invented.alpha","invented.beta"]
    contracts = {}
    for source in sources:
        value = {"provider":"fixture","family":"fixture","schema_version":"1",
            "record_key":"key","publication_key":"version","effective_time":"effective_at",
            "semantics":"patch","adapter":{"version":"invented-v1","kind":kind,
                "record_key":["key"],"reading":reading({"invented_value":"invented_value"})}}
        contracts[source] = {"body":value,"authority":authority(source,value,str(uuid4()))}
    spec = {"kind":kind,"sources":sources,"contracts":contracts,
            "identifier":{**CIK_CONTRACT,"authority":"invented-issuer","sources":[sources[0]],
                          "normalizer":"normalize_identifier@crd-v1"}}
    program = Path(__file__).with_name("installed_worker_scenario.py").read_text()
    with ExitStack() as stack:
        # Drop the business databases before removing the verifier's role.
        _,reader,reader_role = stack.enter_context(database_factory())
        owner,runtime,role = stack.enter_context(database_factory())
        journal_owner,journal_runtime,journal_role = stack.enter_context(database_factory())
        env = {**os.environ,"EDGAR_RULES_ROOT":str(configured_root),"WORKER_INSTALL":str(root),
            "READ_OWNER_URL":owner.url.render_as_string(hide_password=False),
            "READ_RUNTIME_URL":runtime.url.render_as_string(hide_password=False),"READ_RUNTIME_ROLE":role,
            "READ_VERIFIER_URL":reader.url.set(database=owner.url.database).render_as_string(hide_password=False),
            "READ_VERIFIER_ROLE":reader_role,
            "READ_JOURNAL_OWNER_URL":journal_owner.url.render_as_string(hide_password=False),
            "READ_JOURNAL_RUNTIME_URL":journal_runtime.url.render_as_string(hide_password=False),
            "READ_JOURNAL_ROLE":journal_role,
            "READ_JOURNAL_VERIFIER_URL":reader.url.set(database=journal_owner.url.database).render_as_string(hide_password=False)}
        result = subprocess.run([str(python),"-I","-c",program],input=json.dumps(spec),env=env,cwd=root,
                                capture_output=True,text=True,timeout=180)
        if result.returncode:
            (configured_root/"installed-worker-diagnostic.log").write_text(result.stdout+"\n"+result.stderr)
        assert result.returncode == 0, "independently installed worker failed; private diagnostic retained"
        assert json.loads(result.stdout.splitlines()[-1]) == {
            "installed":True,"separate_reader":True,"sources":2,"commits":2,
            "journal_events":2,"lost_ack":True,"delivery_recovery":True,"forced":True,"zero_work":True}
