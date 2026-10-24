"""Normal MergeStage callers on each governed store, with invented configuration."""

import copy
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import installed  # noqa: F401
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


@pytest.mark.parametrize("case", ["join", "issuer_only", "corrected", "released", "quarantine",
                                  "lifted", "newest", "scope", "retired", "assessment",
                                  "stale_assessment", "preview", "collision", "rollback",
                                  "unchanged", "occurrence", "deferred", "competing", "mint_competing", "no_identity_stale",
                                  "name_holder_first", "name_candidate_first", "name_held_value",
                                  "cascade_holder_first", "cascade_candidate_first", "links", "hierarchy", "details"])
@pytest.mark.parametrize("kind", ["invented-kind", "invented-other-kind"])
def test_normal_prepared_merge(case, kind, database_factory, configured_root):
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    if kind not in body["kinds"]:
        body["kinds"].append(kind)
    for declared in ("invented-kind", kind):
        body["accepted_bars"][declared] = copy.deepcopy(body["accepted_bars"]["company"])
    body["pair_comparisons"]["invented-comparison"]["eligibility_kind"] = kind
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            from edgar_warehouse.mdm.clean.store import migrate
            with pytest.raises(ValueError, match="PostgreSQL"):
                migrate(owner, application_role=role, prepared=True)
            return
        env = {**os.environ, "EDGAR_RULES_ROOT": str(configured_root), "READ_CASE": case, "READ_KIND": kind,
               "READ_PREPARED": "1", "READ_RUNTIME_ROLE": role,
               "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
               "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False)}
        result = subprocess.run([sys.executable, "-m", "tests.storage_adapters.record_read_scenarios"],
                                env=env, capture_output=True, text=True, timeout=90)
        if result.returncode:
            (configured_root / "prepared-merge-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
        assert result.returncode == 0, "normal prepared merge failed; private diagnostic retained"


def test_installed_normal_prepared_merge(installed, database_factory, configured_root):
    """Committed five-wheel installation saves and replays outside the checkout."""
    import json
    from uuid import uuid4

    from tests.mdm.test_clean_activation import CIK_CONTRACT
    from tests.support.rules_authority import authority

    python, root = installed
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    body["accepted_bars"]["invented-kind"] = copy.deepcopy(body["accepted_bars"]["company"])
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    contract = {**CIK_CONTRACT, "authority": "invented-issuer", "sources": ["invented.authority"],
                "normalizer": "normalize_identifier@crd-v1"}
    source = {"provider": "fixture", "family": "fixture", "schema_version": "1",
              "record_key": "key", "publication_key": "version", "effective_time": "effective_at",
              "semantics": "patch"}
    envelope = authority("invented.authority", source, str(uuid4()))
    code = '''
import json, os
from pathlib import Path
from uuid import uuid4
import source_contract
from sqlalchemy import func, select
from edgar_warehouse.database_connections import engine_from_env, storage_adapter
from edgar_warehouse.mdm.clean import prepared
from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import Store, migrate, register_policy, register_dataset
assert Path(prepared.__file__).resolve().is_relative_to(Path(INSTALL).resolve())
assert Path(source_contract.__file__).resolve().is_relative_to(Path(INSTALL).resolve())
assert "bundle_data" in str(Path(storage_adapter().__file__).resolve())
owner, runtime = engine_from_env("READ_OWNER_URL"), engine_from_env("READ_RUNTIME_URL")
migrate(owner, application_role=os.environ["READ_RUNTIME_ROLE"], prepared=True)
rule={"rule_id":"invented-bind","version":"1","family":"binding",
      "applies_to_verdict":"invented-kind","emits":["bind"],"on_no_match":"mint",
      "source":"invented.authority","when":[
          {"primitive":"identifier_match@1","args":{"namespace":"invented_number"}},
          {"primitive":"identifier_cardinality@1","args":{"namespace":"invented_number"}}]}
policy={"version":"invented-installed-save","required_consumers":["invented-export"],
        "kinds":{"invented-kind":{"version":"1","rules":[rule],
          "defaults":{"sources":["invented.authority"],"allow_unknown_effective":True},
          "identifiers":{"invented_number":CONTRACT}}},
        "automatic_rules":[{"kind":"invented-kind","family":"binding",
          "rule_id":"invented-bind","rule_version":"1","verdict":"bind",
          "activation":"deterministic"}]}
with owner.begin() as conn:
    pin=register_policy(conn,policy)
    register_dataset(conn,"invented.authority",SOURCE,rules_authority=AUTHORITY)
stage=MergeStage(Store(runtime))
record=assertion(source_code="invented.authority",record_key="one",publication_key="one",
    revision=1,effective_at="2026-01-01T00:00:00Z",kind="invented-kind",
    identifiers={"invented_number":"171"},fields={"invented_amount":10**80+1})
command={"batch_id":"invented-installed-save","run_id":str(uuid4()),"policy_digest":pin,
    "consumer":"invented-proof","expected_checkpoint":0,"checkpoint":1,
    "as_of":"2026-03-01T00:00:00Z","assertions":[record]}
api=storage_adapter().Adapter(runtime,prefix="mdm_store",protocol=5)
assert stage.apply(**{**command,"preview":True})["preview"] and api.generation()==0
assessment=stage.assess(**command,automatic=stage.propose(**command))
producer=str(uuid4())
result=stage.apply_assessment(assessment["assessment_id"],run_id=producer)
assert result["generation"]==1 and not result["duplicate"]
pointer=RecordReader(api).current([record["subject"]])[record["subject"]]
master=json.loads(bytes(api.read([("entity",pointer["entity_id"])])["entity",pointer["entity_id"]]["body"]))
assert master["fields"]["invented_amount"]["value"]==10**80+1
def counts():
    with runtime.connect() as conn:
        return {name:conn.scalar(select(func.count()).select_from(api.tables[name]))
                for name in ("batch","current","history","evidence","lookup","checkpoint","outbox")}
before=counts()
assert stage.apply(**{**command,"run_id":str(uuid4())})["duplicate"]
assert api.generation()==1 and counts()==before
print(json.dumps({"independent_install":True,"preview_rolled_back":True,
                  "assessment_applied":True,"duplicate_unchanged":True,"identities":1}))
'''
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("SQL Server installed writes follow the two-engine gate")
        result = subprocess.run(
            [str(python), "-I", "-c", "\n".join([
                "INSTALL=" + repr(str(root)), "CONTRACT=" + repr(contract),
                "SOURCE=" + repr(source), "AUTHORITY=" + repr(envelope), code])],
            cwd=root, env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root),
                          "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                          "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False),
                          "READ_RUNTIME_ROLE": role},
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode:
            (configured_root / "installed-save-diagnostic.log").write_text(result.stdout + "\n" + result.stderr)
        assert result.returncode == 0, "installed normal save failed; private diagnostic retained"
        proof = json.loads(result.stdout.splitlines()[-1])
        assert proof == {"independent_install": True, "preview_rolled_back": True,
                         "assessment_applied": True, "duplicate_unchanged": True, "identities": 1}
