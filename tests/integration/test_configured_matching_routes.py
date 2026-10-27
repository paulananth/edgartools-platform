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
from edgar_warehouse.mdm.clean.record_reads import for_connection
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
    assert len([value for value in core.bindings(db).values() if value is not None]) == 2
    with runtime.connect() as connection:
        conn = for_connection(connection)
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


def test_populated_candidate_index_upgrade_preserves_history_and_pins(database):
    from sqlalchemy import select
    from edgar_warehouse.mdm.clean.record_reads import for_connection
    db = database
    item = core.source("invented-existing", provenance={"matching":{
        "name_census":{"leis":[["invented-target",1]]}}})
    identity, binding = core.identity_and_binding(item)
    core.apply(db, 1, assertions=[item], identities=[identity], decisions=[binding])
    def snapshot():
        with database.admin.connect() as conn:
            api = for_connection(conn).adapter
            return {name: list(conn.execute(select(api.tables[name]).order_by(*api.tables[name].primary_key)))
                    for name in ("evidence", "lookup", "current", "pin", "batch", "outbox", "checkpoint")}
    before = snapshot()
    store.migrate(database.admin, application_role="clean_application")
    store.migrate(database.admin, application_role="clean_application")
    assert snapshot() == before
    with database.application.connect() as conn:
        assert matching._stored(for_connection(conn), "fixture.primary", matching.candidate_paths({})["census"], ["invented-target"]) == [item]


def test_candidate_containment_checks_exact_array_position_and_duplicates(database):
    items = [core.source("invented-"+str(n), provenance={"matching":{
        "name_census":{"leis":entries}}}) for n,entries in enumerate([
            [["first",1],["second",2]], [["second",1]], [["missing",1],["first",2]],
            ["first"], {"0":["first"]}, [[False,1]], [["",1]],
        ])]
    core.apply(database,1,assertions=items)
    from edgar_warehouse.mdm.clean.record_reads import for_connection
    with database.application.connect() as connection:
        actual = matching._stored(for_connection(connection),"fixture.primary",matching.candidate_paths({})["census"],["first","second","first"])
        assert {item["record_key"] for item in actual} == {"invented-0","invented-1"}
        assert len(actual) == 2


@pytest.mark.parametrize("route", ["identifier", "census", "cascade"])
def test_each_candidate_value_probes_its_real_index(database, route):
    from edgar_warehouse.mdm.clean.record_reads import for_connection
    # Unrelated entries ensure the two probes return only their exact groups.
    items = [core.source("invented-"+str(n), identifiers={"lei":"target-"+str(n)},
        provenance={"matching":{"name_census":{"leis":[["target-"+str(n),1]],
            "cascade":{"lei":"target-"+str(n)}}}}) for n in range(80)]
    core.apply(database, 1, assertions=items)
    statements = []
    def capture(conn, clause, multiparams, params, options):
        if "mdm_store_lookup" in str(clause):
            statements.append(clause)
    with database.application.connect() as conn:
        reader = for_connection(conn)
        event.listen(conn, "before_execute", capture)
        try:
            found = matching._stored(reader, "fixture.primary", matching.candidate_paths({})[route], ["target-3", "target-77"])
        finally:
            event.remove(conn, "before_execute", capture)
        assert {row["record_key"] for row in found} == {"invented-3", "invented-77"}
        assert statements
        for query in statements:
            sql = str(query.compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True}))
            conn.execute(text("SET LOCAL enable_seqscan=off"))
            plan = conn.execute(text("EXPLAIN (ANALYZE, FORMAT JSON) " + sql)).scalar()[0]["Plan"]
            def nodes(node):
                yield node
                for child in node.get("Plans", []):
                    yield from nodes(child)
            accesses = list(nodes(plan))
            probes = [node for node in accesses if node.get("Index Name") == "mdm_store_lookup_pkey"]
            assert probes and all("Index Cond" in node for node in probes)
            assert sum(node["Actual Rows"] * node["Actual Loops"] for node in probes) <= 2
            assert not any(node["Node Type"] == "Seq Scan" for node in accesses)
