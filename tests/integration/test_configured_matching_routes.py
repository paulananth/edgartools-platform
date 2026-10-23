"""Configured candidate paths reach current readings and normal merge proposals."""
import copy
import os
import subprocess
import sys

import pytest
from sqlalchemy import event, text

from edgar_warehouse.mdm.clean import matching, store
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm.test_configured_pair_comparison import PROGRAM, configured_root


@pytest.mark.parametrize("route", ["census", "cascade"])
@pytest.mark.parametrize("arrival", ["holder_first", "candidate_first", "together"])
def test_invented_route_reaches_normal_merge(database, configured_root, route, arrival):
    body = files.load(configured_root / "mastering/engine-v1.yaml")
    body["legacy_pair_comparison"] = "existing-name-binding"
    body["accepted_bars"]["invented-kind"] = copy.deepcopy(body["accepted_bars"]["company"])
    (configured_root / "mastering/engine-v1.yaml").write_text(files.dumps(body))
    program = PROGRAM + '''
import os
from sqlalchemy import create_engine, text
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm.test_clean_activation import COMPANY_BAR, proof
from tests.integration.test_clean_name_matching import LEI_CONTRACT
from edgar_warehouse.mdm.clean.store import migrate, register_policy
from edgar_warehouse.mdm.clean.matching import candidate_paths, _stored
owner = create_engine(os.environ["ROUTE_OWNER_URL"], hide_parameters=True)
runtime = create_engine(os.environ["ROUTE_RUNTIME_URL"], hide_parameters=True)
try:
    migrate(owner, application_role="clean_application")
    primitive = "cascade_pass@1" if os.environ["ROUTE"] == "cascade" else "name_census_match@1"
    args = names if primitive == "name_census_match@1" else {**names, "pass":"P1",
        "compare":["street","city","postcode"], "refused_flags":[], "over_shared":10}
    tests = [{"primitive":primitive,"args":args},
        {"primitive":"gleif_entity_eligible@1","args":eligibility},
        {"primitive":"holds_no_other_lei@1","args":{}}]
    if primitive == "name_census_match@1":
        tests.append({"primitive":"postal_agrees@1","args":{
            "sec_code":"matching.invented_postal", "sec_country":"matching.invented_country",
            "gleif_code":"matching.invented_postal", "gleif_country":"matching.invented_country"}})
    rule = {"rule_id":"invented-route","version":"1","family":"name_binding",
        "pair_comparison":"invented-comparison","applies_to_verdict":"invented-kind",
        "emits":["bind"],"on_no_match":"wait","source":"fixture.secondary",
        "holder_source":"fixture.primary","when":tests}
    policy = {"version":"invented-routes","required_consumers":["export","graph"],
        "kinds":{"invented-kind":{"version":"1","defaults":{
            "sources":["fixture.primary","fixture.secondary"],"allow_unknown_effective":True},
            "rules":[rule],"identifiers":{"invented_reference":{
                **LEI_CONTRACT,"normalizer":"normalize_text@legal-form-kept-v1"}},
            "bars":{"name_binding":COMPANY_BAR}}},
        "automatic_rules":[{"kind":"invented-kind","family":"name_binding", "rule_id":"invented-route",
            "rule_version":"1","verdict":"bind","activation":"measured","proof":proof(n=300,correct=300)}]}
    with owner.begin() as conn:
        pin = register_policy(conn, policy)
    db = core.Database(owner,runtime,pin,"")
    for raw in (left,right):
        raw["provenance"]["matching"].update(invented_postal="11111",invented_country="ZZ")
    holder = core.source("origin-1",kind="invented-kind",fields={"invented_name":"INVENTED LAB INC"},
        provenance=left["provenance"])
    candidate = core.source("target-1",source_code="fixture.secondary",kind="invented-kind",
        identifiers=right["identifiers"],effective_at=right["effective_at"],
        fields={k:v["value"] for k,v in right["fields"].items()},provenance=right["provenance"])
    identity,binding = core.identity_and_binding(holder)
    arrival = os.environ["ARRIVAL"]
    if arrival == "together":
        command = dict(assertions=[holder,candidate],identities=[identity],decisions=[binding])
        first = core.apply(db,1,**command)
        again = core.apply(db,1,**command)
    else:
        if arrival == "holder_first":
            core.apply(db,1,assertions=[holder],identities=[identity],decisions=[binding])
            command = dict(assertions=[candidate])
        else:
            core.apply(db,1,assertions=[candidate])
            assert core.documents(db,"entity") == {}
            command = dict(assertions=[holder],identities=[identity],decisions=[binding])
        first = core.apply(db,2,**command)
        again = core.apply(db,2,**command)
    assert again == {**first,"duplicate":True}
    found = core.documents(db,"entity")
    assert len(found) == 1
    assert found[identity["entity_id"]]["identifiers"] == {"invented_reference":["target-1"]}
    # The held-value veto must use this profile's namespace too. A fresh
    # candidate matching the corrected census cannot replace the held value.
    entry = copy.deepcopy(left["provenance"])
    census = entry["matching"]["invented_census"]
    census["invented_matches"][0][0] = "other-target"
    census["invented_assignment"]["invented_target"] = "other-target"
    changed = core.source("origin-1",revision=2,kind="invented-kind",
        fields={"invented_name":"INVENTED LAB INC"},provenance=entry)
    other = core.source("other-target",source_code="fixture.secondary",kind="invented-kind",
        identifiers={"invented_reference":"other-target"},effective_at=right["effective_at"],
        fields={k:v["value"] for k,v in right["fields"].items()},provenance=right["provenance"])
    core.apply(db,2 if arrival == "together" else 3,assertions=[changed,other])
    assert core.documents(db,"entity")[identity["entity_id"]]["identifiers"] == {"invented_reference":["target-1"]}
    with runtime.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL")) == 2
        for name in ("identifier",os.environ["ROUTE"]):
            source = "fixture.secondary" if name == "identifier" else "fixture.primary"
            key = "target-1" if name == "identifier" else "other-target"
            assert len(_stored(conn,source,candidate_paths(rule)[name],[key])) == 1
finally:
    owner.dispose(); runtime.dispose()
'''
    result = subprocess.run([sys.executable, "-c", program], env={**os.environ,
        "EDGAR_RULES_ROOT": str(configured_root), "ROUTE": route, "ARRIVAL": arrival,
        "ROUTE_OWNER_URL": database.admin.url.render_as_string(hide_password=False),
        "ROUTE_RUNTIME_URL": database.application.url.render_as_string(hide_password=False)},
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_populated_candidate_index_upgrade_preserves_history_and_pins(database, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(store, "MIGRATIONS", store.MIGRATIONS[:-1])
        db = core.initialize_database(database.admin, database.application)
        item = core.source("invented-existing", provenance={"matching":{
            "name_census":{"leis":[["invented-target",1]]}}})
        identity,binding = core.identity_and_binding(item)
        core.apply(db,1,assertions=[item],identities=[identity],decisions=[binding])
    tables = ("source_reading","stage_record","master_entity","policy","batch","outbox","checkpoint")
    def snapshot():
        with database.admin.connect() as conn:
            return {name: conn.scalar(text("SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM mdm."+name+" t")) for name in tables}
    before = snapshot()
    store.migrate(database.admin, application_role="clean_application")
    store.migrate(database.admin, application_role="clean_application")
    assert snapshot() == before
    with database.application.connect() as conn:
        assert matching._stored(conn,"fixture.primary",matching.candidate_paths({})["census"],["invented-target"]) == [item]
        assert conn.scalar(text("SELECT reloptions FROM pg_class WHERE oid='mdm.stage_record_matching'::regclass")) == ["fastupdate=off"]


def test_candidate_containment_checks_exact_array_position_and_duplicates(database):
    items = [core.source("invented-"+str(n), provenance={"matching":{
        "name_census":{"leis":entries}}}) for n,entries in enumerate([
            [["first",1],["second",2]], [["second",1]], [["missing",1],["first",2]],
            ["first"], {"0":["first"]}, [[False,1]], [["",1]],
        ])]
    core.apply(database,1,assertions=items)
    with database.application.connect() as conn:
        actual = matching._stored(conn,"fixture.primary",matching.candidate_paths({})["census"],["first","second","first"])
        assert {item["record_key"] for item in actual} == {"invented-0","invented-1"}
        assert len(actual) == 2


@pytest.mark.parametrize("route,index", [("identifier","stage_record_identifiers"),
    ("census","stage_record_matching"),("cascade","stage_record_matching")])
def test_each_candidate_value_probes_its_real_index(database, route, index):
    # A large unrelated cohort catches whole-index reads disguised as index use.
    items = [core.source("invented-"+str(n), identifiers={"lei":"target-"+str(n)},
        provenance={"matching":{"name_census":{"leis":[["target-"+str(n),1]],
            "cascade":{"lei":"target-"+str(n)}}}}) for n in range(1,5002)]
    for start in range(0,len(items),500):
        core.apply(database,start//500+1,assertions=items[start:start+500])
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE mdm.stage_record"))
    statements = []
    def capture(conn, cursor, statement, params, context, many):
        if "CROSS JOIN LATERAL" in statement:
            statements.append((statement,params))
    with database.application.connect() as conn:
        event.listen(conn,"before_cursor_execute",capture)
        assert len(matching._stored(conn,"fixture.primary",matching.candidate_paths({})[route],["target-3","target-77"])) == 2
        event.remove(conn,"before_cursor_execute",capture)
        statement,params = statements.pop()
        plan = conn.exec_driver_sql("EXPLAIN (ANALYZE,FORMAT JSON) "+statement,params).scalar()
    def nodes(node):
        yield node
        for child in node.get("Plans",[]): yield from nodes(child)
    found = list(nodes(plan[0]["Plan"]))
    probes = [node for node in found if node.get("Index Name") == index]
    assert len(probes) == 1 and probes[0]["Actual Loops"] == 2
    assert probes[0]["Actual Rows"] == 1
    assert "Index Cond" in probes[0]
    assert not any(node["Node Type"] == "Seq Scan" and node.get("Relation Name") == "stage_record" for node in found)
