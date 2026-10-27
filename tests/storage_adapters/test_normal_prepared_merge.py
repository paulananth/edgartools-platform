"""Normal MergeStage callers on each governed store, with invented configuration."""

import copy
import os
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import installed  # noqa: F401
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


CASES = ["scope", "rollback"]
# Other merge cases run through the independently installed workflow matrix.
KINDS = ["invented-kind", "invented-other-kind"]
if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
    CASES, KINDS = ["deferred"], ["invented-kind"]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("kind", KINDS)
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


@pytest.mark.parametrize("kind,source_code", [
    ("invented-kind", "invented.authority"),
    ("invented-other-kind", "invented.other-authority"),
])
def test_installed_normal_prepared_merge(kind, source_code, installed, database_factory, configured_root):
    """Committed five-wheel installation saves and replays outside the checkout."""
    import json
    from uuid import uuid4

    from tests.mdm.test_clean_activation import CIK_CONTRACT
    from tests.support.rules_authority import authority
    from tests.support.reading import reading

    python, root = installed
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    if kind not in body["kinds"]:
        body["kinds"].append(kind)
    body["accepted_bars"][kind] = copy.deepcopy(body["accepted_bars"]["company"])
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    definitions = files.load(configured_root / "context/definitions.yaml")
    definitions["kinds"][kind] = "Invented installed master."
    (configured_root / "context/definitions.yaml").write_text(files.dumps(definitions))
    contract = {**CIK_CONTRACT, "authority": "invented-issuer", "sources": [source_code],
                "normalizer": "normalize_identifier@crd-v1"}
    source = {"provider": "fixture", "family": "fixture", "schema_version": "1",
              "record_key": "key", "publication_key": "version", "effective_time": "effective_at",
              "semantics": "patch"}
    configured = reading({"invented_amount": "invented_amount", "name": "name"})
    configured["read"]["tables"]["mapped"]["columns"]["details"] = {
        "object": {"fields": {"invented_rows": {"value": {"path": "rows"}}}}}
    source["adapter"] = {"version": "invented-installed-details", "kind": kind,
        "record_key": ["key"], "reading": configured, "detail_keys": {"invented_rows": "row_id"}}
    envelope = authority(source_code, source, str(uuid4()))
    code = '''
import json, os
import inspect
from pathlib import Path
from uuid import uuid4
import source_contract
import edgar_control
from sqlalchemy import func, select
from edgar_warehouse.database_connections import engine_from_env, storage_adapter
from edgar_warehouse.mdm.clean import prepared
from edgar_warehouse.mdm.clean.evidence import assertion, decision
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import Store, migrate, register_policy, register_dataset
from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.silver_writer.writer import MdmIds
from edgar_warehouse.context import Context
assert Path(prepared.__file__).resolve().is_relative_to(Path(INSTALL).resolve())
assert Path(source_contract.__file__).resolve().is_relative_to(Path(INSTALL).resolve())
assert Path(edgar_control.__file__).resolve().is_relative_to(Path(INSTALL).resolve())
assert hasattr(edgar_control,"prepare_text_search")
for implementation in (ContractReader, MdmIds, Context):
    assert Path(inspect.getfile(implementation)).resolve().is_relative_to(Path(INSTALL).resolve())
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
policy["relationships"]={"version":"invented-installed-links","types":{
    "invented_link":{"from":["invented-kind"],"to":["invented-kind"]}}}
with owner.begin() as conn:
    pin=register_policy(conn,policy)
    register_dataset(conn,"invented.authority",SOURCE,rules_authority=AUTHORITY)
stage=MergeStage(Store(runtime))
record=assertion(source_code="invented.authority",record_key="one",publication_key="one",
    revision=1,effective_at="2026-01-01T00:00:00Z",kind="invented-kind",
    identifiers={"invented_number":"171"},
    fields={"invented_amount":10**80+1,"invented_text":"INVENTED 雪 💠 é","name":"INVENTED ROOT"},
    details={"invented_rows":[{"key":"invented-row","amount":10**80+7}]})
command={"batch_id":"invented-installed-save","run_id":str(uuid4()),"policy_digest":pin,
    "consumer":"invented-proof","expected_checkpoint":0,"checkpoint":1,
    "as_of":"2026-03-01T00:00:00Z","assertions":[record]}
api=storage_adapter().Adapter(runtime,prefix="mdm_store",protocol=6)
assert stage.apply(**{**command,"preview":True})["preview"] and api.generation()==0
assessment=stage.assess(**command,automatic=stage.propose(**command))
producer=str(uuid4())
result=stage.apply_assessment(assessment["assessment_id"],run_id=producer)
assert result["generation"]==1 and not result["duplicate"]
pointer=RecordReader(api).current([record["subject"]])[record["subject"]]
master=json.loads(bytes(api.read([("entity",pointer["entity_id"])])["entity",pointer["entity_id"]]["body"]))
assert master["fields"]["invented_amount"]["value"]==10**80+1
reader=ContractReader(runtime)
read=reader.entity(pointer["entity_id"])
assert read["identity"]==master and reader.entity(pointer["entity_id"],generation=1)==read
assert read["projection"]["origin_run_id"]==producer
assert read["field_provenance"]["invented_amount"]["evidence"]==record
assert read["identity"]["fields"]["invented_text"]["value"]=="INVENTED 雪 💠 é"
assert read["identity"]["details"]["invented_rows"]==[
    {"key":"invented-row","amount":10**80+7,"sources":["invented.authority"]}]
assert MdmIds(runtime)("invented.authority","invented-kind",{"one","missing"})=={"one":pointer["entity_id"]}
page=reader.snapshot_page("entity",generation=1,limit=1)
assert page["items"][0]["body"]==master and page["next_after"] is None
from argparse import Namespace
context=Context(runtime).answer(Namespace(subject="invented-kind",key="invented_number:171",
    search=None,as_of=None,as_at="2030-01-01T00:00:00Z",detail="full",page=None))
assert context["entity_id"]==pointer["entity_id"]
assert context["trust"]["recorded_at"]==read["projection"]["recorded_at"]
assert context["sources"]=={"invented.authority":["one"]}
def searched(words):
    return Context(runtime).answer(Namespace(subject="invented-kind",key=None,search=words,limit=5,
        as_of=None,as_at=None,detail="full",page=None))["matches"]
assert searched("root")[0]["entity_id"]==pointer["entity_id"]
def counts():
    with runtime.connect() as conn:
        return {name:conn.scalar(select(func.count()).select_from(api.tables[name]))
                for name in ("batch","current","history","evidence","lookup","checkpoint","outbox")}
before=counts()
assert stage.apply(**{**command,"run_id":str(uuid4())})["duplicate"]
assert api.generation()==1 and counts()==before
position=1
def save(**parts):
    global position
    position+=1
    return stage.apply(batch_id="invented-installed-reader-"+str(position),run_id=str(uuid4()),
        policy_digest=pin,consumer="invented-proof",expected_checkpoint=position-1,
        checkpoint=position,as_of="2026-03-01T00:00:00Z",**parts)
updated_record=assertion(source_code="invented.authority",record_key="one",publication_key="two",
    revision=2,effective_at="2026-01-02T00:00:00Z",kind="invented-kind",
    identifiers={"invented_number":"171"},fields={"invented_amount":10**80+2,"name":"INVENTED UPDATED"},
    details={"invented_rows":[{"key":"invented-row","amount":10**80+8}]})
save(assertions=[updated_record])
updated=reader.entity(pointer["entity_id"])
assert updated["identity"]["fields"]["invented_amount"]["value"]==10**80+2
assert updated["field_provenance"]["invented_amount"]["evidence"]==updated_record
assert updated["identity"]["details"]["invented_rows"]==[
    {"key":"invented-row","amount":10**80+8,"sources":["invented.authority"]}]
assert reader.entity(pointer["entity_id"],generation=1)==read
assert searched("root")==[] and searched("updated")[0]["entity_id"]==pointer["entity_id"]
opaque_key="INVENTED-雪-"+"x"*5000
other_record=assertion(source_code="invented.authority",record_key=opaque_key,publication_key="one",
    revision=1,effective_at="2026-01-01T00:00:00Z",kind="invented-kind",
    identifiers={},fields={"invented_amount":10**80+3})
other_id=str(uuid4())
from datetime import datetime, timedelta
floor=RecordReader(api).publications(["invented-kind"])["invented-kind"]["published_at"]
identity={"entity_id":other_id,"kind":"invented-kind",
    "published_at":(datetime.fromisoformat(floor)+timedelta(microseconds=1)).isoformat()}
bind=decision("bind",actor="fixture",reason="invented installed identity",at="2026-01-01T00:00:00Z",
    subject=other_record["subject"],entity_id=other_id,evidence=[other_record["assertion_id"]])
save(assertions=[other_record],identities=[identity],decisions=[bind])
other_before=reader.entity(other_id)
merge=decision("merge",actor="fixture",reason="invented installed duplicate",at="2026-02-01T00:00:00Z",
    left=pointer["entity_id"],right=other_id)
save(decisions=[merge])
merged=reader.entity(other_id)
assert merged["canonical_id"]==pointer["entity_id"]
assert reader.entity(other_id,generation=other_before["generation"])==other_before
assert MdmIds(runtime)("invented.authority","invented-kind",{"one",opaque_key})=={
    "one":pointer["entity_id"],opaque_key:pointer["entity_id"]}
alias_args=Namespace(subject="invented-kind",key=other_id,search=None,as_of=None,as_at=None,detail="full",page=None)
assert Context(runtime).answer(alias_args)["merged_from"]==other_id
save(decisions=[decision("reverse",actor="fixture",reason="invented installed reversal",
    at="2026-02-02T00:00:00Z",target=merge["decision_id"])])
assert reader.entity(other_id)["canonical_id"]==other_id
assert reader.entity(other_id,generation=merged["generation"])==merged
assert MdmIds(runtime)("invented.authority","invented-kind",{opaque_key})=={opaque_key:other_id}
linked=assertion(source_code="invented.authority",record_key="one",publication_key="three",
    revision=3,effective_at="2026-01-03T00:00:00Z",kind="invented-kind",
    identifiers={"invented_number":"171"},fields={"invented_amount":10**80+2,"name":"INVENTED UPDATED"},
    relationships=[{"type":"invented_link","target_subject":other_record["subject"],
        "valid_from":"2026-01-01T00:00:00Z","valid_to":None,"scope":"invented"}])
linked_result=save(assertions=[linked])
links=reader.snapshot_page("relationship")
assert len(links["items"])==1 and links["items"][0]["body"]["target_id"]==other_id
relation_args=Namespace(subject="relationship",key=pointer["entity_id"],search=None,
    as_of=None,as_at=None,detail="full",page=None,hops=1,relationship_type="")
related=Context(runtime).answer(relation_args)
assert related["related_count"]==1 and related["related"][0]["to"]["entity_id"]==other_id
assert related["related"][0]["sources"]==[{"source_code":"invented.authority","record_key":"one"}]
from datetime import UTC
recorded=api.batch_metadata(linked_result["generation"],limit=1)[0]["recorded_at"]
at=(datetime(1970,1,1,tzinfo=UTC)+timedelta(microseconds=recorded)).isoformat()
unlinked=assertion(source_code="invented.authority",record_key="one",publication_key="four",
    revision=4,effective_at="2026-01-04T00:00:00Z",kind="invented-kind",
    identifiers={"invented_number":"171"},fields={"invented_amount":10**80+2,"name":"INVENTED UPDATED"},relationships=[])
save(assertions=[unlinked])
assert Context(runtime).answer(relation_args)["related_count"]==0
assert Context(runtime).answer(Namespace(**{**vars(relation_args),"as_at":at}))["related_count"]==1
assert reader.snapshot_page("relationship",generation=linked_result["generation"])==links
assert reader.snapshot_page("relationship")["items"][0]["body"]["retired"] is True
assert reader.snapshot_page("entity",generation=1,limit=1)==page
import io
from contextlib import redirect_stdout
from edgar_warehouse.cli import main
os.environ["MDM_DATABASE_URL"]=os.environ["READ_RUNTIME_URL"]
os.environ["MDM_APPLICATION_ROLE"]=os.environ["READ_RUNTIME_ROLE"]
for arguments,expected in [(["mdm","counts"],{"entity":2,"relationship":1}),
    (["mdm","check-connectivity"],{"sql":True,"migrations":6})]:
    output=io.StringIO()
    with redirect_stdout(output):
        status=main(arguments)
    assert status==0 and json.loads(output.getvalue())==expected
output=io.StringIO()
with redirect_stdout(output):
    status=main(["context","relationship",pointer["entity_id"],"--as-at",at,"--detail","full"])
assert status==0 and json.loads(output.getvalue())["related_count"]==1
from unittest.mock import patch
from edgar_warehouse.mdm.clean import master_search
from edgar_warehouse.context import ContextError
missed=assertion(source_code="invented.authority",record_key="one",publication_key="five",
    revision=5,effective_at="2026-01-05T00:00:00Z",kind="invented-kind",
    identifiers={"invented_number":"171"},fields={"name":"INVENTED REBUILT"})
with patch.object(master_search,"normal_changes",return_value=[]):
    save(assertions=[missed])
try:
    searched("rebuilt")
except ContextError as error:
    assert "complete index" in str(error)
else:
    raise AssertionError("A missed index generation must refuse search")
before={key:value for key,value in counts().items() if key!="lookup"}
generation=api.generation()
os.environ["MDM_DATABASE_URL"]=os.environ["READ_OWNER_URL"]
for processed,ready in [(1,False),(1,True),(0,True)]:
    output=io.StringIO()
    with redirect_stdout(output):
        status=main(["mdm","rebuild-name-index","--limit","1"])
    assert status==0 and json.loads(output.getvalue())=={
        "generation":generation,"processed":processed,"ready":ready}
assert api.generation()==generation and {key:value for key,value in counts().items() if key!="lookup"}==before
assert searched("rebuilt")[0]["entity_id"]==pointer["entity_id"]
print(json.dumps({"independent_install":True,"preview_rolled_back":True,
                  "assessment_applied":True,"duplicate_unchanged":True,"identities":2,
                  "master_reads":True,"context":True,"silver_lookup":True,
                  "history_alias_reversal":True,"pinned_page":True,
                  "details":True,"relationships":True,"operator_cli":True,
                  "search":True,"owner_rebuild":True}))
'''.replace("invented-kind", kind).replace("invented.authority", source_code)
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
                         "assessment_applied": True, "duplicate_unchanged": True, "identities": 2,
                         "master_reads": True, "context": True, "silver_lookup": True,
                         "history_alias_reversal": True, "pinned_page": True,
                         "details": True, "relationships": True, "operator_cli": True,
                         "search": True, "owner_rebuild": True}
