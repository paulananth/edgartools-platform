"""The normal proposal/read phase on governed stores; writes remain a later gate."""

import copy
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import installed  # noqa: F401
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401

CASES = (
    ["deferred"]
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql"
    else [
        "join",
        "issuer_only",
        "corrected",
        "released",
        "quarantine",
        "lifted",
        "newest",
        "scope",
        "retired",
        "write_gate",
        "prepare_join",
        "prepare_no_identity",
        "prepare_new_identity",
        "name_holder_first",
        "name_candidate_first",
        "name_held_value",
        "cascade_holder_first",
        "cascade_candidate_first",
    ]
)


@pytest.mark.parametrize("case", CASES)
def test_normal_record_read_phase(case, database_factory, configured_root):
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    body["accepted_bars"]["invented-kind"] = copy.deepcopy(
        body["accepted_bars"]["company"]
    )
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            from edgar_warehouse.mdm.clean.merge import MergeStage

            with pytest.raises(ValueError, match="PostgreSQL and MySQL"):
                MergeStage.propose_on(
                    runtime, policy_digest="invented", as_of="2026-01-01T00:00:00Z"
                )
            return
        env = {
            **os.environ,
            "EDGAR_RULES_ROOT": str(configured_root),
            "READ_CASE": case,
            "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
            "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False),
            "READ_RUNTIME_ROLE": role,
        }
        result = subprocess.run(
            [sys.executable, "-m", "tests.storage_adapters.record_read_scenarios"],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode:
            # Driver diagnostics stay private; they may include connection details.
            (configured_root / "read-phase-diagnostic.log").write_text(
                result.stdout + "\n" + result.stderr
            )
        assert result.returncode == 0, (
            "normal read phase failed; private diagnostic retained"
        )


def test_installed_normal_read_phase(installed, database_factory, configured_root):
    """The installed normal read API and native scope indexes need no checkout."""
    python, root = installed
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    body["accepted_bars"]["invented-kind"] = copy.deepcopy(
        body["accepted_bars"]["company"]
    )
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("SQL Server normal read phase follows the two-engine gate")
        code = """
import os
from pathlib import Path
from edgar_warehouse.database_connections import engine_from_env
from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, migrate, register_policy
from edgar_warehouse.rules.source_engine import prepare_scope_lookups
from edgar_warehouse.database_connections import storage_adapter
assert "bundle_data" in str(Path(storage_adapter().__file__).resolve())
owner=engine_from_env("READ_OWNER_URL")
runtime=engine_from_env("READ_RUNTIME_URL")
migrate(owner,application_role=os.environ["READ_RUNTIME_ROLE"])
rule={"rule_id":"invented-bind","version":"1","family":"binding",
      "applies_to_verdict":"invented-kind","emits":["bind"],"on_no_match":"mint",
      "source":"invented.authority","when":[
          {"primitive":"identifier_match@1","args":{"namespace":"invented_number"}},
          {"primitive":"identifier_cardinality@1","args":{"namespace":"invented_number"}}]}
policy={"version":"invented-installed-read","required_consumers":["invented-export"],
        "kinds":{"invented-kind":{"version":"1","rules":[rule],
          "defaults":{"sources":["invented.authority"],"allow_unknown_effective":True},
          "identifiers":{"invented_number":CONTRACT}}},
        "automatic_rules":[{"kind":"invented-kind","family":"binding",
          "rule_id":"invented-bind","rule_version":"1","verdict":"bind",
          "activation":"deterministic"}]}
with owner.begin() as conn: pin=register_policy(conn,policy)
record=assertion(source_code="invented.authority",record_key="one",publication_key="one",
                 revision=1,effective_at="2026-01-01T00:00:00Z",kind="invented-kind",
                 identifiers={"invented_number":"171"},fields={})
stage=MergeStage(Store(runtime,read_only=True))
proposal=stage.propose(policy_digest=pin,as_of="2026-03-01T00:00:00Z",assertions=[record])
assert len(proposal["identities"])==len(proposal["decisions"])==1
assert not stage.read_scope([],[]).subjects
publications,entries=prepare_scope_lookups({"previous":[],"identities":[],
    "previous_publications":{},"objects":[{"type":"relationship","id":"invented-link",
      "body":{"relationship_id":"invented-link","source_id":"one","target_id":"two"}}]})
assert not publications and len(entries)==2
print("installed normal read phase passed")
"""
        from tests.mdm.test_clean_activation import CIK_CONTRACT

        contract = {
            **CIK_CONTRACT,
            "authority": "invented-issuer",
            "sources": ["invented.authority"],
            "normalizer": "normalize_identifier@crd-v1",
        }
        result = subprocess.run(
            [str(python), "-I", "-c", "CONTRACT=" + repr(contract) + "\n" + code],
            cwd=root,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "EDGAR_RULES_ROOT": str(configured_root),
                "READ_OWNER_URL": owner.url.render_as_string(hide_password=False),
                "READ_RUNTIME_URL": runtime.url.render_as_string(hide_password=False),
                "READ_RUNTIME_ROLE": role,
            },
            timeout=90,
        )
        if result.returncode:
            (configured_root / "installed-read-diagnostic.log").write_text(
                result.stdout + "\n" + result.stderr
            )
        assert result.returncode == 0, (
            "installed normal read phase failed; private diagnostic retained"
        )
        assert result.stdout.strip().endswith("installed normal read phase passed")
