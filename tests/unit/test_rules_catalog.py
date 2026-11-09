"""The Data Catalog is the rules, published one way (rules skill ticket 13)."""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import json
import shutil
from argparse import Namespace
from urllib.parse import unquote
from pathlib import Path
from urllib.error import HTTPError

import pytest

from edgar_warehouse.rules import catalog, files, mapdoc
from edgar_warehouse.rules import cli as rules_cli


def _tables(plan: dict) -> dict[str, dict]:
    return {f"{t['databaseSchema']}.{catalog.quote(t['name'])}": t for t in plan["tables"]}


def test_a_dotted_name_is_quoted_as_the_server_quotes_it():
    assert catalog.fqn("edgartools-rules", "sources", "sec.adv", "adv_bulk") == \
        'edgartools-rules.sources."sec.adv".adv_bulk'


def test_every_source_feed_dataset_and_mdm_field_is_in_the_catalog():
    plan = catalog.plan()
    sources = sorted(p.parent.name for p in (files.ROOT / "sources").glob("*/source.yaml"))
    assert [s["name"] for s in plan["schemas"] if s["database"].endswith(".sources")] == sources
    tables = _tables(plan)
    assert 'edgartools-rules.sources."sec.adv".adv_bulk' not in tables
    sec = tables['edgartools-rules.sources."sec.company"."sec.company.v1"']
    assert {"cik", "entity_name", "business_address.postal_code", "name_count"} <= {c["name"] for c in sec["columns"]}
    company = tables["edgartools-rules.mdm.master_records.company"]
    assert {"name", "address", "jurisdiction", "state_of_incorporation"} <= {c["name"] for c in company["columns"]}
    name = next(c for c in company["columns"] if c["name"] == "name")
    assert ("sec.company.v1, then gleif.level1.v1, then iapd.adv.filings.v2, then "
            "iapd.adv.custodians.v1, then sec.nport.registrant.v1: the first with a value wins") in name["description"]
    relationships = tables['edgartools-rules.sources.gleif."gleif.relationships.v1"']
    assert "It supplies no Company fields." in relationships["description"]
    assert "Read by the classification rule" in next(c for c in sec["columns"] if c["name"] == "sic")["description"]
    assert "held back and is not merged" in sec["description"]


def test_lineage_runs_column_by_column_and_leaves_matching_out():
    plan = catalog.plan()
    edge = next(e for e in plan["lineage"] if e["from"].endswith('"sec.company.v1"'))
    by_field = {c["toColumn"].rsplit(".", 1)[1]: c["fromColumns"] for c in edge["columns"]}
    assert len(by_field["address"]) == 6  # an address's parts fill one MDM field
    assert "name_count" not in {c.rsplit(".", 1)[1].strip('"') for cols in by_field.values() for c in cols}
    feed = next(e for e in plan["lineage"] if e["to"].endswith('"sec.company.v1"'))
    assert feed["from"].endswith(".submissions") and feed["columns"] == []


def test_a_second_kind_from_another_sources_files_has_its_feed_lineage():
    # Person reads the submissions files the Company source's feed captures, and declares
    # no feed of its own (platform validation 05c, item 11).
    plan = catalog.plan()
    feed = [e for e in plan["lineage"] if e["to"].endswith('"sec.submissions.person.v1"')]
    assert [e["from"] for e in feed] == ['edgartools-rules.sources."sec.company".submissions']
    # A source whose family no feed captures gets no feed lineage; GLEIF's own feed leads to it.
    assert not [e for e in plan["lineage"] if e["to"].endswith('"iapd.adv.filings.v2"')]
    assert [e["from"] for e in plan["lineage"] if e["to"].endswith('"gleif.level1.v1"')] == [
        "edgartools-rules.sources.gleif.golden_copy"]


def test_each_feed_that_captures_the_family_gives_lineage(tmp_path: Path):
    # Two feeds capturing one family both lead to the source that reads it; a feed that
    # names no family leads nowhere (an invented second feed on the OpenFIGI source).
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    path = root / "sources" / "openfigi" / "source.yaml"
    body = files.load_source(path)
    feeds = body["acquisition"]["feeds"]
    feeds["more_submissions"] = {**feeds["mapping"], "family": "submissions", "datasets": []}
    feeds["unnamed"] = {k: v for k, v in feeds["mapping"].items() if k != "family"} | {"datasets": []}
    files.write_source(body, path.parent)
    plan = catalog.plan(root)
    sources = sorted(e["from"] for e in plan["lineage"] if e["to"].endswith('"sec.submissions.person.v1"'))
    assert sources == ['edgartools-rules.sources."sec.company".submissions',
                       "edgartools-rules.sources.openfigi.more_submissions"]


def test_the_same_rules_give_the_same_catalog_and_a_change_shows(tmp_path: Path):
    assert catalog.plan() == catalog.plan()
    assert "Shared" not in {domain["name"] for domain in catalog.plan()["domains"]}
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    path = root / "sources" / "sec.company" / "source.yaml"
    body = files.load_source(path)
    del mapdoc.mapped(body["dataset_contracts"]["sec.company.v1"]["contract"]["adapter"], "fields")["description"]
    files.write_source(body, path.parent)
    changed = catalog.plan(root)
    assert changed["service"]["description"] != catalog.plan()["service"]["description"]  # a new digest
    company = _tables(changed)["edgartools-rules.mdm.master_records.company"]
    assert "description" not in {c["name"] for c in company["columns"]}


class _Server:
    """What `publish` asks of OpenMetadata, as the 2.0.2 server answered it
    (probed 2026-09-28): the catalog holds one table, one schema and one
    lineage link the rules no longer name."""

    def __init__(self, plan: dict):
        self.plan, self.calls, self.ids = plan, [], {}
        self.term_bodies, self.product_bodies, self.patches, self.draft = [], [], [], set()
        self.table_delete_params = []
        self.profiles, self.tags, self.certified, self.results = {}, {}, None, {}
        self.pipelines, self.pipeline_lineage, self.pipeline_inbound = {}, {}, {}
        self.pipeline_services = {}
        self.pipeline_service_delete_params = []

    def __call__(self, method, path, body=None, params=None):
        self.calls.append((method, path))
        if method == "DELETE" and path.startswith("/services/pipelineServices/"):
            service_id = path.rsplit("/", 1)[1]
            self.pipeline_service_delete_params.append(params)
            service = next((name for name, entity in self.pipeline_services.items()
                            if entity["id"] == service_id), None)
            if service:
                self.pipeline_services.pop(service)
                for name, entity in list(self.pipelines.items()):
                    if entity.get("service") == service:
                        self.pipelines.pop(name)
                        for edge in [key for key in self.pipeline_lineage if key[0] == name]:
                            self.pipeline_lineage.pop(edge, None)
            return {}
        if method == "DELETE" and path.startswith("/lineage/table/") and "/pipeline/" in path:
            _, _, _, table_id, _, pipeline_id = path.split("/")
            pipeline = next((name for name, entity in self.pipelines.items() if entity["id"] == pipeline_id), None)
            table = next((name for name, found_id in self.ids.items() if found_id == table_id), None)
            self.pipeline_inbound.pop((pipeline, table), None)
        if method == "PUT" and path == "/lineage" and body["edge"]["toEntity"]["type"] == "pipeline":
            by_id = {entity["id"]: name for name, entity in self.pipelines.items()}
            pipeline = by_id[body["edge"]["toEntity"]["id"]]
            if body["edge"]["fromEntity"]["type"] == "pipeline":
                before = by_id[body["edge"]["fromEntity"]["id"]]
                self.pipeline_lineage[(before, pipeline)] = body["edge"]["lineageDetails"]
                self.pipeline_inbound[(pipeline, before)] = body["edge"]["lineageDetails"]
                return {}
            table = next(name for name, found_id in self.ids.items() if found_id == body["edge"]["fromEntity"]["id"])
            self.pipeline_inbound[(pipeline, table)] = body["edge"]["lineageDetails"]
            return {}
        if method == "DELETE" and path.startswith("/lineage/pipeline/"):
            _, _, _, pipeline_id, kind, other_id = path.split("/")
            by_id = {entity["id"]: name for name, entity in self.pipelines.items()}
            pipeline = by_id.get(pipeline_id)
            if kind == "pipeline":
                after = by_id.get(other_id)
                self.pipeline_lineage.pop((pipeline, after), None)
                self.pipeline_inbound.pop((after, pipeline), None)
                return {}
            table = next((name for name, found_id in self.ids.items() if found_id == other_id), None)
            if pipeline and table:
                self.pipeline_lineage.pop((pipeline, table), None)
        if method == "DELETE" and path.startswith("/tables/"):
            self.table_delete_params.append(params)
        if method == "PATCH":
            self.patches.append((path, body))
            if path.startswith("/dataQuality/testCases/testCaseResults/") and not getattr(
                    self, "ignore_quality_patch", False):
                case_path, timestamp = path.removeprefix(
                    "/dataQuality/testCases/testCaseResults/").rsplit("/", 1)
                name = unquote(case_path)
                row = next(row for row in self.results[name] if row["timestamp"] == int(timestamp))
                for op in body:
                    row[op["path"].removeprefix("/")] = op["value"]
            for op in body if isinstance(body, list) else []:
                if path.startswith("/tables/") and op.get("path") == "/certification":
                    self.certified_by_id = getattr(self, "certified_by_id", {})
                    self.certified_by_id[path.removeprefix("/tables/")] = op["value"]
                if path.startswith("/tables/") and op.get("path") == "/tags/-":
                    self.tags.setdefault(path.removeprefix("/tables/"), []).append({"tagFQN": op["value"]["tagFQN"]})
            if path.startswith("/glossaryTerms/"):
                self.draft.add(path.removeprefix("/glossaryTerms/"))
        if method == "POST" and path.startswith("/dataQuality/testCases/testCaseResults/"):
            name = unquote(path.removeprefix("/dataQuality/testCases/testCaseResults/"))
            self.results.setdefault(name, []).append(body)
        if method == "GET" and path.startswith("/dataQuality/testCases/testCaseResults/"):
            name = unquote(path.removeprefix("/dataQuality/testCases/testCaseResults/"))
            timestamp = (params or {}).get("startTs")
            return {"data": [row for row in self.results.get(name, []) if row["timestamp"] == timestamp]}
        if method == "GET" and path == "/system/settings":
            return {"data": [{"config_type": "assetCertificationSettings", "config_value": {"validityPeriod": "P30D"}}]}
        if method == "GET" and path.startswith("/tables/name/") and (params or {}).get("fields") == "certification":
            if self.certified == {}:
                return {}
            return {"certification": getattr(self, "certified_by_id", {}).get(
                self.ids.get(unquote(path.removeprefix("/tables/name/"))))}
        if method == "GET" and path.startswith("/tables/name/") and (params or {}).get("fields") == "tags":
            return {"tags": self.tags.get(self.ids.get(unquote(path.removeprefix("/tables/name/"))), [])}
        if method == "GET" and path.endswith("/tableProfile/latest"):
            found = self.profiles.get(path.removeprefix("/tables/").removesuffix("/tableProfile/latest"))
            return {"profile": found} if found else {}
        if method == "GET" and path.startswith("/glossaryTerms/"):
            term_id = path.removeprefix("/glossaryTerms/")
            return {"id": term_id, "entityStatus": "Draft" if term_id in self.draft else "Approved"}
        if method == "PUT" and path == "/dataQuality/testCases":
            link = body.get("entityLink") or ""
            table = link.removeprefix("<#E::table::").split("::columns::")[0].removesuffix(">")
            column = link.split("::columns::", 1)[1].removesuffix(">") + "." if "::columns::" in link else ""
            return {**body, "id": body["name"], "fullyQualifiedName": f"{table}.{column}{catalog.quote(body['name'])}"}
        if method == "PUT" and path == "/dataProducts":
            self.product_bodies.append(body)
        if method == "PUT" and path == "/glossaryTerms":
            self.term_bodies.append(body)
            return {**body, "id": body["name"],
                    "fullyQualifiedName": body["glossary"] + "." + catalog.quote(body["name"])}
        if method == "PUT" and path == "/services/pipelineServices":
            name = body["name"]
            answer = {**body, "id": "pipeline-service-" + name, "fullyQualifiedName": name}
            self.pipeline_services[name] = answer
            return answer
        if method == "GET" and path.startswith("/services/pipelineServices/name/"):
            return self.pipeline_services.get(unquote(path.removeprefix("/services/pipelineServices/name/")))
        if method == "PUT" and path == "/pipelines":
            assert "pipelineStatus" not in body, "PipelineStatus must use the run-status API"
            name = catalog.fqn(body["service"], body["name"])
            answer = {**body, "fullyQualifiedName": name, "id": "pipeline-" + body["name"]}
            self.pipelines[name] = answer
            return answer
        if method == "GET" and path == "/pipelines":
            return {"data": [{"fullyQualifiedName": name, "id": entity["id"]}
                             for name, entity in self.pipelines.items()], "paging": {}}
        if method == "GET" and path.startswith("/pipelines/name/"):
            return self.pipelines.get(unquote(path.removeprefix("/pipelines/name/")), {})
        if method == "PUT" and path.startswith("/pipelines/") and path.endswith("/status"):
            name = unquote(path.removeprefix("/pipelines/").removesuffix("/status"))
            if name in self.pipelines and not getattr(self, "ignore_pipeline_status", False):
                self.pipelines[name]["pipelineStatus"] = body
                return self.pipelines[name]
            return {}
        if method == "PUT" and path.startswith("/lineage/pipeline/name/"):
            pipeline, _, table = path.removeprefix("/lineage/pipeline/name/").partition("/table/name/")
            self.pipeline_lineage[(unquote(pipeline), unquote(table))] = body
            return {}
        if method == "GET" and path.startswith("/lineage/pipeline/name/"):
            pipeline = unquote(path.removeprefix("/lineage/pipeline/name/"))
            entity = self.pipelines.get(pipeline)
            if entity is None:
                return {"entity": {}, "nodes": [], "upstreamEdges": [], "downstreamEdges": []}
            edges, nodes, inbound = [], [], []

            def node(name):
                found = self.ids.get(name) or (self.pipelines[name]["id"] if name in self.pipelines else None)
                return found, "pipeline" if name in self.pipelines else "table"

            for (name, other), details in self.pipeline_lineage.items():
                other_id, kind = node(other)
                if name == pipeline and other_id:
                    nodes.append({"id": other_id, "type": kind, "fullyQualifiedName": other})
                    edges.append({"fromEntity": entity["id"], "toEntity": other_id,
                                  "lineageDetails": {"description": details.get("description"),
                                                     "source": details.get("source")}})
            for (name, other), details in self.pipeline_inbound.items():
                other_id, kind = node(other)
                if name == pipeline and other_id:
                    nodes.append({"id": other_id, "type": kind, "fullyQualifiedName": other})
                    inbound.append({"fromEntity": other_id, "toEntity": entity["id"],
                                    "lineageDetails": {"description": details.get("description"),
                                                       "source": details.get("source")}})
            return {"entity": {"id": entity["id"], "type": "pipeline", "fullyQualifiedName": pipeline},
                    "nodes": nodes, "upstreamEdges": inbound, "downstreamEdges": edges}
        if method == "PUT" and path == "/tables":
            name = f"{body['databaseSchema']}.{catalog.quote(body['name'])}"
            self.ids.setdefault(name, f"id-{len(self.ids)}")
            return {**body, "fullyQualifiedName": name, "id": self.ids[name]}
        if method == "GET" and path == "/tables" and not params.get("after"):  # two pages
            stale = {"fullyQualifiedName": "edgartools-rules.sources.gone.old", "id": "id-old"}
            # a server that ignores `service` also lists another service's table
            other = {"fullyQualifiedName": "someone-else.db.schema.table", "id": "id-other"}
            return {"data": [stale, other], "paging": {"after": "page-2"}}
        if method == "GET" and path == "/tables":
            return {"data": [{"fullyQualifiedName": n, "id": i} for n, i in self.ids.items()], "paging": {}}
        if method == "GET" and path == "/databases":
            return {"data": [{"fullyQualifiedName": f"edgartools-rules.{d['name']}", "id": d["name"]}
                             for d in self.plan["databases"]]}
        if method == "GET" and path == "/databaseSchemas" and params["database"].endswith(".sources"):
            return {"data": [{"fullyQualifiedName": "edgartools-rules.sources.gone", "id": "id-gone"}]}
        if method == "GET" and path.startswith("/lineage/table/name/edgartools-rules.mdm.master_records.company"):
            company = self.ids["edgartools-rules.mdm.master_records.company"]
            ours = self.ids['edgartools-rules.sources.gleif."gleif.relationships.v1"']
            return {"upstreamEdges": [{"fromEntity": ours, "toEntity": company},
                                      {"fromEntity": "id-other", "toEntity": company}]}
        if method == "GET" and path == "/system/settings/glossaryTermRelationSettings":
            return {"config_type": "glossaryTermRelationSettings",
                    "config_value": {"relationTypes": [
                        {"name": "relatedTo", "displayName": "Related To", "isSystemDefined": True}]}}
        if method == "PUT" and "name" in body:
            parent = body.get("database") or body.get("service")
            return {**body, "id": body["name"], "fullyQualifiedName":
                    parent + "." + catalog.quote(body["name"]) if parent else body["name"]}
        return {"data": []} if method == "GET" else {}


def test_the_plan_names_domains_glossaries_and_store_certification():
    plan = catalog.plan()
    names = {domain["name"] for domain in plan["domains"]}
    assert "company" in names and "market_venue" in names and "venue" not in names
    assert not [item for item in plan["memberships"] if item["table"].startswith("edgartools-rules.mdm.relationships.")]
    assert not [edge for edge in plan["lineage"] if edge["to"].startswith("edgartools-rules.mdm.relationships.")]
    issued = [edge for edge in plan["domain_lineage"] if edge["table"].endswith(".ISSUED_BY")]
    assert {edge["domain"] for edge in issued} >= {"security", "company"}
    assert all(edge["domain"] != edge["table"] for edge in plan["domain_lineage"])
    products = {product["name"]: product for product in plan["products"]}
    assert set(products) == {"company_master", "security_master", "company_fundamentals"}
    assert products["company_master"]["domains"] == ["company"]
    assert products["security_master"]["domains"] == ["security"]
    assert products["company_fundamentals"]["domains"] == ["company"]
    assert any(name.endswith("company_measure") for name in products["company_fundamentals"]["tables"])
    assert {name.rsplit(".", 1)[-1] for name in products["company_fundamentals"]["inputs"]} == {
        "company_fact", "company_line_item"}
    assert all(f".{catalog.SOURCES}." in name for name in products["company_master"]["inputs"])
    assert all(f".{catalog.SOURCES}." in name for name in products["security_master"]["inputs"])
    gleif = [edge for edge in plan["service_lineage"] if "source:gleif:mastering:" in edge["pipeline"]]
    assert any("sources.gleif" in edge.get("table", "") for edge in gleif)
    assert any("mdm." in edge.get("table", "") for edge in gleif)
    cases = {case["name"]: case for case in plan["quality_cases"]}
    assert "sec.company.v1.name_present" in cases
    assert cases["sec.company.v1.dc_state_is_empty"]["description"].startswith("Correction")
    assert cases["company_fact.one_form_per_filing"]["testDefinition"] == "edgartools-configured-column-check"
    assert all("testCaseResult" not in case for case in plan["quality_cases"])
    assert any(name.endswith("mdm.master_records.security") for name in products["security_master"]["tables"])
    assert sum(1 for table in plan["tables"] if table["databaseSchema"].endswith(".relationships")) == 17  # RELATED_PERSON (2026-11-08) is the 17th
    certified = {item["table"]: item["tag"] for item in plan["certifications"]}
    assert certified["edgartools-rules.mdm.master_records.company"] == "Certification.Gold"
    assert any(name.startswith("edgartools-rules.silver.") and tag == "Certification.Silver"
               for name, tag in certified.items())
    assert not any(name.startswith("edgartools-rules.sources.") for name in certified)  # a source dataset stays uncertified
    assert catalog.glossary_relation_type_name("ISSUED_BY") == "issuedBy"
    assert catalog.glossary_relation_type_name("IS_FUND-MANAGED_BY") == "isFundManagedBy"
    assert "relatedTo" not in {edge["relationType"] for edge in plan["glossary_relations"]}



def test_pipeline_services_are_split_by_source_and_standalone_owner():
    plan = catalog.plan()
    service_names = {service["name"] for service in plan["pipeline_services"]}
    owners = {}
    for pipeline in plan["pipelines"]:
        scope, owner, _ = pipeline["name"].split(":", 2)
        expected = f"{catalog.PIPELINES_SERVICE}-{scope}-{owner.replace('.', '-')}"
        assert pipeline["service"] == expected
        assert expected in service_names
        owners.setdefault((scope, owner), set()).add(pipeline["service"])
    assert all(len(services) == 1 for services in owners.values())
    assert service_names == {next(iter(services)) for services in owners.values()}
    assert plan["retired_pipeline_service"] == catalog.PIPELINES_SERVICE


def test_pipeline_display_names_are_distinct_and_omit_the_shared_prefix():
    plan = catalog.plan()
    labels = [item["displayName"] for item in plan["pipeline_services"] + plan["pipelines"]]
    assert len(labels) == len(set(labels))
    assert all(not label.startswith("edgartools-rules") for label in labels)
    named = next(pipeline for pipeline in plan["pipelines"]
                 if pipeline["name"] == "source:gleif:subfund-pairs")
    assert named["displayName"] == "GLEIF sub-fund pairs"
    company = next(pipeline for pipeline in plan["pipelines"]
                   if pipeline["name"] == "source:sec.company:capture")
    assert company["displayName"] == "SEC Company Capture"


def test_bookkeeping_steps_are_embedded_as_target_pipeline_tasks():
    plan = catalog.plan()
    for pipeline in plan["pipelines"]:
        scope, _, target = pipeline["name"].split(":", 2)
        path = files.ROOT / pipeline["pipelineLocation"]
        body = files.load_source(path) if scope == "source" else files.load(path)
        steps = (body.get("bookkeeping") or {}).get("targets", {}).get(target, {}).get("steps", [])
        assert [task["name"] for task in pipeline["tasks"]] == [step["name"] for step in steps]


def test_target_pipeline_lineage_includes_configured_silver_and_master_outputs():
    plan = catalog.plan()
    edges = defaultdict(set)
    steps_of = {catalog.fqn(p["service"], p["name"]): catalog.fqn(p["service"], p["name"].rsplit(":", 1)[0])
                for p in plan["pipelines"] if catalog._is_step(p)}
    for edge in plan["service_lineage"]:
        if "table" in edge:
            edges[steps_of[edge["pipeline"]]].add(edge["table"])
    tables = set(_tables(plan))
    master_prefix = catalog.fqn(catalog.SERVICE, catalog.MDM, catalog.MASTER_RECORDS) + "."
    source_pipelines = set()
    linked_silver = linked_master = False

    for pipeline in plan["pipelines"]:
        scope, folder, target_name = pipeline["name"].split(":", 2)
        if scope != "source" or catalog._is_step(pipeline):
            continue
        path = files.ROOT / pipeline["pipelineLocation"]
        body = files.load_source(path)
        source = body.get("source") or folder
        target = (body.get("bookkeeping") or {}).get("targets", {}).get(target_name, {})
        pipeline_fqn = catalog.fqn(pipeline["service"], pipeline["name"])
        if catalog._steward_steps(target):
            source_pipelines.add(pipeline_fqn)
        steps = target.get("steps") or []
        for step in steps:
            keys = (step.get("input") or {}).get("keys") or {}
            if step["operation"] in ("silver.land", "silver.derive") and keys.get("silver"):
                silver_table = catalog.fqn(catalog.SERVICE, catalog.SILVER, folder, keys["silver"])
                if silver_table in tables:
                    linked_silver = True
                    assert silver_table in edges[pipeline_fqn], (
                        "configured Silver output is missing from its target Pipeline lineage")
        if any(step["operation"] == "mastering.merge" for step in steps):
            datasets = {step["input"]["keys"]["dataset"] for step in steps
                        if step["operation"] == "mdm.prepare"
                        and (step.get("input") or {}).get("keys", {}).get("dataset")}
            inputs = {catalog.fqn(catalog.SERVICE, catalog.SOURCES, source, dataset) for dataset in datasets}
            outputs = {edge["to"] for edge in plan["lineage"]
                       if edge["from"] in inputs and edge["to"].startswith(master_prefix)}
            for output in outputs:
                linked_master = True
                assert output in edges[pipeline_fqn], (
                    "rule-derived master output is missing from its target Pipeline lineage")
    assert linked_silver and linked_master
    assert source_pipelines and source_pipelines <= set(edges)


def _target_graph(plan: dict, source: str, target: str) -> dict[str, set]:
    """What one target's steps read, publish and hand on, without the service prefix: sets of
    (step, table) for `reads` and `writes`, and (step, step) for `next`."""
    steps = {catalog.fqn(p["service"], p["name"]): p["name"].rsplit(":", 1)[-1]
             for p in plan["pipelines"] if p["name"].startswith(f"source:{source}:{target}:")}
    cut = len(catalog.SERVICE) + 1
    found = {"reads": set(), "writes": set(), "next": set()}
    for edge in plan["service_lineage"]:
        if edge["pipeline"] not in steps:
            continue
        if "next" in edge:
            found["next"].add((steps[edge["pipeline"]], steps[edge["next"]]))
        else:
            found["reads" if edge.get("inbound") else "writes"].add((steps[edge["pipeline"]], edge["table"][cut:]))
    return found


def test_company_mastering_graph_is_steps_with_their_feeds_reference_control_and_outputs():
    plan = catalog.plan()
    graph = _target_graph(plan, "sec.company", "mastering")
    submissions, ticker = 'sources."sec.company".submissions', 'sources."sec.company".company_tickers_exchange'
    dataset = 'sources."sec.company"."sec.company.v1"'
    assert graph["reads"] == {("combine", submissions), ("combine", ticker), ("name_count", submissions),
                              ("name_count", 'sources."sec.company".name_count'), ("merge", dataset)}
    assert graph["writes"] == {("records", dataset), ("merge", "mdm.master_records.company"),
                               ("merge", "journal.change_journal.processed_files")}
    assert graph["next"] == {("name_count", "combine"), ("combine", "records")}
    built = {edge["from"][len(catalog.SERVICE) + 1:] for edge in plan["lineage"]
             if edge["to"] == catalog.fqn(catalog.SERVICE, catalog.SOURCES, "sec.company", "name_count")}
    assert built == {'sources.gleif.golden_copy', 'sources."sec.company".submissions'}


def test_plumbing_steps_and_the_target_pipeline_itself_carry_no_lineage():
    plan = catalog.plan()
    targets = {catalog.fqn(p["service"], p["name"]) for p in plan["pipelines"] if not catalog._is_step(p)}
    on_graph = {edge["pipeline"] for edge in plan["service_lineage"]}
    assert on_graph and not on_graph & targets
    steps = {p["name"].rsplit(":", 1)[-1] for p in plan["pipelines"] if catalog._is_step(p)}
    assert not {"keys", "main", "catalog", "processed"} & steps
    assert {"capture", "name_count", "combine", "records", "merge"} <= steps


def test_a_target_that_only_merges_publishes_its_master_and_reads_nothing():
    graph = _target_graph(catalog.plan(), "sec.company", "merge-batch")
    assert graph == {"reads": set(), "writes": {("merge", "mdm.master_records.company")}, "next": set()}


def test_a_capture_target_reads_its_feed_and_publishes_nothing():
    graph = _target_graph(catalog.plan(), "sec.company", "capture")
    assert graph == {"reads": {("capture", 'sources."sec.company".submissions')}, "writes": set(), "next": set()}


def test_a_feed_is_read_by_the_first_step_that_can_fail_after_the_read():
    graph = _target_graph(catalog.plan(), "gleif", "mastering")
    assert ("prepare", "sources.gleif.golden_copy") in graph["reads"]


def test_a_target_whose_steps_are_all_plumbing_has_no_graph():
    assert _target_graph(catalog.plan(), "gleif", "subfund-pairs") == {"reads": set(), "writes": set(), "next": set()}


def test_publish_writes_inbound_and_step_edges_and_removes_a_stale_one():
    plan = catalog.plan()
    server = _Server(plan)
    name = next(edge["pipeline"] for edge in plan["service_lineage"] if edge.get("inbound"))
    unread = catalog.fqn(catalog.SERVICE, catalog.MDM, catalog.MASTER_RECORDS, "company")
    catalog.publish(plan, server)
    expected = {(edge["pipeline"], edge["table"]) for edge in plan["service_lineage"] if edge.get("inbound")}
    assert {key for key in server.pipeline_inbound if key[1] in _tables(plan)} == expected
    chained = {(edge["pipeline"], edge["next"]) for edge in plan["service_lineage"] if "next" in edge}
    assert chained and chained <= set(server.pipeline_lineage)
    server.pipeline_inbound[(name, unread)] = {"description": "old", "source": "PipelineLineage"}
    report = catalog.publish(plan, server)
    assert {key for key in server.pipeline_inbound if key[1] in _tables(plan)} == expected
    assert report["removed"]["pipeline_lineage"] == 1


def test_catalog_check_reports_missing_pipeline_table_lineage():
    plan = catalog.plan()
    report = catalog.verify(plan, _Server(plan))
    assert any("pipeline lineage" in difference for difference in report["differences"])


def _terms(plan):
    return {f"{term['glossary']}.{term['name']}": term for term in plan["glossary_terms"]}


def test_a_relationship_type_is_a_term_of_the_domain_its_from_list_names_first():
    plan = catalog.plan()
    fqns = set(_terms(plan))
    assert "shared" not in {glossary["name"] for glossary in plan["glossaries"]}
    assert not [name for name in fqns if name.startswith("shared.")]
    assert {"company.CUSTODIAN", "company.IS_SUBFUND_OF", "company.SUCCESSOR_ENTITY", "person.EMPLOYED_BY",
            "security.ISSUED_BY", "company.BENEFICIAL_OWNER_OF"} <= fqns
    term = _terms(plan)["person.EMPLOYED_BY"]
    assert term["table"].endswith("relationships.EMPLOYED_BY")
    company_graph = {edge["to"]: edge["relationType"] for edge in plan["glossary_relations"]
                     if edge["from"] == "company.Company Identity"}
    assert company_graph["company.CUSTODIAN"] == "custodian"
    assert "company.ISSUED_BY" not in company_graph
    security_graph = {edge["to"]: edge["relationType"] for edge in plan["glossary_relations"]
                      if edge["from"] == "security.Security Identity"}
    assert security_graph == {"security.ISSUED_BY": "issuedBy"}


def test_a_type_no_rule_reads_stays_an_asset_marked_planned():
    plan = catalog.plan()
    names = {term["name"] for term in plan["glossary_terms"]}
    marker = "(planned: no rule reads this type yet and no link is loaded)"
    tables = _tables(plan)
    for code in ("AUDITED_BY", "HAS_MARKET_OPERATOR", "IS_SUBSIDIARY_OF"):
        assert code not in names
        assert marker in tables[f"edgartools-rules.mdm.relationships.{code}"]["description"]
    assert marker not in tables["edgartools-rules.mdm.relationships.CUSTODIAN"]["description"]


def test_only_entity_terms_are_published_as_draft_terms():
    plan = catalog.plan()
    names = {term["name"] for term in plan["glossary_terms"]}
    assert {"Company Identity", "Adviser", "Audit Firm", "Fund", "Fund Series", "Market/Venue"} <= names
    for platform in ("Merge Stage", "Source Extract", "Relationship Capacity", "Master Data", "Holdings", "Discretion"):
        assert platform not in names
    assert not [name for name in names if name.endswith("Profile")]
    placed = {f"{term['glossary']}.{term['name']}" for term in plan["glossary_terms"]}
    assert {"company.Adviser", "fund_structure.Fund", "fund_structure.Fund Series", "market_venue.Market/Venue"} <= placed
    assert "company.Fund" not in placed  # a fund is a collection of securities, not a company
    domains = {domain["name"] for domain in plan["domains"]}
    assert {glossary["name"] for glossary in plan["glossaries"]} == domains


def test_a_publish_leaves_the_term_status_to_the_server_unless_asked():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
    assert not [path for path, _ in server.patches if path.startswith("/glossaryTerms/")]


def test_a_term_is_written_as_draft_never_approved_when_asked():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server, draft_terms=True)
    assert server.term_bodies and not any("entityStatus" in body for body in server.term_bodies)  # the create body has no such field
    patched = [body for path, body in server.patches if path.startswith("/glossaryTerms/")]
    assert len(patched) == len(server.term_bodies)
    assert all(ops == [{"op": "add", "path": "/entityStatus", "value": "Draft"}] for ops in patched)


def test_a_patch_that_puts_a_related_term_back_to_approved_is_patched_again():
    plan = catalog.plan()

    last = plan["glossary_terms"][-1]["name"]

    class Resetting(_Server):
        """The 2.0.2 server resets a related term when another term is patched (seen 2026-11-01)."""
        resets = 0

        def __call__(self, method, path, body=None, params=None):
            answer = super().__call__(method, path, body, params)
            if method == "PATCH" and path == "/glossaryTerms/" + last and not self.resets:
                self.resets += 1
                self.draft.discard("Company Identity")  # the fake's term id is its name
            return answer

    server = Resetting(plan)
    catalog.publish(plan, server, draft_terms=True)
    again = [path for path, _ in server.patches if path == "/glossaryTerms/Company Identity"]
    assert len(again) == 2
    assert server.draft >= {term["name"] for term in plan["glossary_terms"]}


def test_each_table_carries_its_data_class():
    plan = catalog.plan()
    marks = {item["table"]: item["tag"] for item in plan["data_class_marks"]}
    assert marks["edgartools-rules.mdm.master_records.company"] == "data_class.master_data"
    assert marks["edgartools-rules.mdm.relationships.CUSTODIAN"] == "data_class.relationship"
    assert any(name.startswith("edgartools-rules.rdm.code_sets.") and tag == "data_class.reference_data"
               for name, tag in marks.items())
    assert any(name.startswith("edgartools-rules.silver.") and tag == "data_class.transaction_data"
               for name, tag in marks.items())
    assert not any(".sources." in name for name in marks)
    classes = {tag["name"] for tag in plan["classifications"][0]["tags"]}
    assert plan["classifications"][0]["name"] == "data_class"
    assert classes == {"master_data", "reference_data", "relationship", "transaction_data"}
    tables = _tables(plan)
    assert "Reference Hierarchy" in next(
        table["description"] for name, table in tables.items() if name.startswith("edgartools-rules.rdm.code_sets."))
    assert "interval" in tables["edgartools-rules.mdm.relationships.CUSTODIAN"]["description"].lower()
    assert "capacity" in tables["edgartools-rules.mdm.relationships.CUSTODIAN"]["description"].lower()


def test_each_data_product_carries_its_identity_term_in_the_suggested_state():
    plan = catalog.plan()
    products = {product["name"]: product for product in plan["products"]}
    assert products["company_master"]["tags"] == ["company.Company Identity"]
    assert products["company_fundamentals"]["tags"] == ["company.Company Identity"]
    assert products["security_master"]["tags"] == ["security.Security Identity"]
    server = _Server(plan)
    catalog.publish(plan, server)
    sent = {body["name"]: body for body in server.product_bodies}
    assert sent["company_master"]["tags"] == [{
        "tagFQN": "company.Company Identity", "source": "Glossary", "labelType": "Manual", "state": "Suggested"}]


def _outcome_plan():
    return {
        "domains": [{}], "glossaries": [{}], "glossary_terms": [{}, {}], "tables": [{}, {}, {}],
        "quality_definitions": [{}], "quality_cases": [{}, {}], "products": [{}],
        "pipelines": [{}, {}], "pipeline_services": [{}],
        "lineage": [{}, {}], "service_lineage": [{}], "domain_lineage": [{}], "glossary_relations": [{}, {}],
    }


def test_catalog_plan_counts_cover_configured_catalog_objects():
    assert catalog.plan_counts(_outcome_plan()) == {
        "domains": 1, "glossaries": 1, "glossary_terms": 2, "assets": 3,
        "quality_definitions": 1, "quality_cases": 2, "products": 1, "pipelines": 2, "pipeline_services": 1,
        "lineage": {"table": 2, "pipeline": 1, "domain": 1, "glossary": 2},
    }


def test_catalog_endpoint_identity_omits_credentials_path_and_query():
    assert catalog.endpoint_identity("https://user:private@catalog.example:8585/private/path?token=secret") == \
        "https://catalog.example:8585"


def test_catalog_http_error_does_not_expose_response_body(monkeypatch):
    def fail_request(*args, **kwargs):
        raise HTTPError("https://catalog.example/api/v1", 401, "unauthorized", {},
                        BytesIO(b"response echoed bearer-secret"))

    monkeypatch.setattr(catalog, "urlopen", fail_request)
    with pytest.raises(catalog.CatalogError) as error:
        catalog.connect("https://catalog.example", "bearer-secret")("GET", "/services")

    assert "HTTP 401" in str(error.value)
    assert "bearer-secret" not in str(error.value)
    assert "response echoed" not in str(error.value)


def test_catalog_plan_is_read_only_and_reports_pending(capsys, monkeypatch):
    plan = _outcome_plan()
    monkeypatch.setattr(catalog, "plan", lambda root: plan)
    monkeypatch.setattr(catalog, "connect", lambda *args: pytest.fail("plan must not connect"))
    monkeypatch.delenv("OPENMETADATA_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_TOKEN", raising=False)

    assert rules_cli._catalog(Namespace(action="plan", root="rules")) == 0

    output = capsys.readouterr()
    assert json.loads(output.out) == plan
    assert "PENDING" in output.err and "Nothing was sent" in output.err


def test_catalog_publish_missing_configuration_preserves_usage_exit_code(capsys, monkeypatch):
    monkeypatch.setattr(catalog, "plan", lambda root: _outcome_plan())
    monkeypatch.delenv("OPENMETADATA_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_TOKEN", raising=False)
    monkeypatch.setattr(catalog, "connect", lambda *args: pytest.fail("missing config must stop before connect"))

    assert rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False)) == 2

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "failed" and report["failed_stage"] == "configuration"
    assert "OPENMETADATA_TOKEN" in output.err


def test_catalog_publish_requires_matching_readback_and_returns_structured_result(capsys, monkeypatch):
    plan = _outcome_plan()
    calls = []
    monkeypatch.setenv("OPENMETADATA_URL", "https://user:private@catalog.example:8585/private?token=url-secret")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "header-secret")
    monkeypatch.setattr(catalog, "plan", lambda root: plan)
    monkeypatch.setattr(catalog, "connect", lambda url, token: calls.append((url, token)) or (lambda *args, **kwargs: {}))
    monkeypatch.setattr(catalog, "publish", lambda selected, call, **kw: calls.append("publish") or {
        "service": "edgartools-rules", "tables": 3, "pipelines": 2, "lineage": 2,
        "removed": {"tables": 0, "schemas": 0, "databases": 0, "lineage": 0, "pipeline_lineage": 0},
    })
    monkeypatch.setattr(catalog, "verify", lambda selected, call, **kw: calls.append("readback") or {
        "ok": True, "tables": 3, "pipelines": 2, "differences": [],
    })

    assert rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False)) == 0

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "confirmed"
    assert report["endpoint"] == "https://catalog.example:8585"
    assert report["plan"]["counts"] == catalog.plan_counts(plan)
    assert report["publish"]["created"] is None and report["publish"]["updated"] is None
    assert report["publish"]["removed"]["tables"] == 0
    assert report["readback"]["status"] == "matched"
    assert calls[-2:] == ["publish", "readback"]
    assert "CONFIRMED" in output.err
    assert all(secret not in output.out + output.err for secret in ("private", "url-secret", "header-secret"))


def test_catalog_publish_failure_names_stage_and_redacts_error_details(capsys, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_URL", "https://catalog.example")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "do-not-print")
    monkeypatch.setattr(catalog, "plan", lambda root: _outcome_plan())
    monkeypatch.setattr(catalog, "connect", lambda url, token: lambda *args, **kwargs: {})

    def fail_publish(plan, call, **kw):
        raise catalog.CatalogError("PUT /tables: HTTP 401 body contains do-not-print")

    monkeypatch.setattr(catalog, "publish", fail_publish)
    monkeypatch.setattr(catalog, "verify", lambda *args: pytest.fail("failed publish cannot be confirmed"))

    assert rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False)) == 1

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "failed" and report["failed_stage"] == "publish"
    assert report["cause"] == "OpenMetadata returned HTTP 401"
    assert report["next_action"].startswith("Correct the rejected request")
    assert "do-not-print" not in output.out + output.err


def test_catalog_partial_publish_failure_requires_readback_before_retry(capsys, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_URL", "http://localhost:8585")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "local-token")
    monkeypatch.setattr(catalog, "plan", lambda root: _outcome_plan())
    monkeypatch.setattr(catalog, "connect", lambda url, token: lambda *args, **kwargs: {"ok": True})

    def fail_after_write(plan, call, **kw):
        call("PUT", "/tables", {})
        raise catalog.CatalogError("PUT /tables: HTTP 503")

    monkeypatch.setattr(catalog, "publish", fail_after_write)
    monkeypatch.setattr(catalog, "verify", lambda *args: pytest.fail("readback is deferred after failure"))

    assert rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False)) == 1

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "partial" and report["failed_stage"] == "publish"
    assert report["publish"]["completed_write_requests"] == 1
    assert report["next_action"].startswith("Run the read-only")


def test_catalog_publish_with_remote_drift_is_partial(capsys, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_URL", "http://localhost:8585")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "local-token")
    monkeypatch.setattr(catalog, "plan", lambda root: _outcome_plan())
    monkeypatch.setattr(catalog, "connect", lambda url, token: lambda *args, **kwargs: {})
    monkeypatch.setattr(catalog, "publish", lambda plan, call, **kw: {
        "service": "edgartools-rules", "removed": {"tables": 0},
    })
    monkeypatch.setattr(catalog, "verify", lambda plan, call, **kw: {
        "ok": False, "tables": 3, "pipelines": 2, "differences": ["tables: different membership"],
    })

    assert rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False)) == 1

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "partial" and report["failed_stage"] == "readback"
    assert report["publish"]["status"] == "sent"
    assert report["readback"]["status"] == "drift"
    assert report["readback"]["differences"] == ["tables: different membership"]


def test_catalog_check_is_read_only_and_reports_confirmed_readback(capsys, monkeypatch):
    monkeypatch.setenv("OPENMETADATA_URL", "http://localhost:8585")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "local-token")
    monkeypatch.setattr(catalog, "plan", lambda root: _outcome_plan())
    monkeypatch.setattr(catalog, "connect", lambda url, token: lambda *args, **kwargs: {})
    monkeypatch.setattr(catalog, "publish", lambda *args: pytest.fail("check must not publish"))
    monkeypatch.setattr(catalog, "verify", lambda plan, call, **kw: {
        "ok": True, "tables": 3, "pipelines": 2, "differences": [],
    })

    assert rules_cli._catalog(Namespace(action="check", root="rules")) == 0

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "confirmed"
    assert report["publish"]["status"] == "not_run"
    assert report["readback"]["status"] == "matched"


def test_publish_deletes_only_what_the_rules_no_longer_name():
    plan = catalog.plan()
    server = _Server(plan)
    result = catalog.publish(plan, server)
    deletes = [path for method, path in server.calls if method == "DELETE"]
    company = server.ids["edgartools-rules.mdm.master_records.company"]
    feed = server.ids['edgartools-rules.sources.gleif."gleif.relationships.v1"']
    assert deletes == ["/tables/id-old", "/databaseSchemas/id-gone", f"/lineage/table/{feed}/table/{company}"]
    # a renamed source's old table still holds test cases: the server refuses a delete that is not recursive
    assert server.table_delete_params == [{"hardDelete": "true", "recursive": "true"}]
    assert result["removed"] == {"tables": 1, "schemas": 1, "databases": 0, "lineage": 1,
                                 "pipeline_lineage": 0, "pipelines": 0, "pipeline_services": 0}
    inbound = sum(1 for edge in plan["service_lineage"] if edge.get("inbound") or "next" in edge)
    assert sum(1 for method, path in server.calls if (method, path) == ("PUT", "/lineage")) == len(plan["lineage"]) + inbound
    posts = [path for method, path in server.calls if method == "POST" and path.endswith("/relations")]
    assert any(path.startswith("/glossaryTerms/Company Identity/") for path in posts)
    assert len(posts) == len(plan["glossary_relations"])
    assert ("PUT", "/system/settings") in server.calls


def test_publish_removes_stale_owned_pipeline_to_table_edges():
    plan = catalog.plan()
    expected = {(edge["pipeline"], edge["table"]) for edge in plan["service_lineage"] if "table" in edge}
    pipeline = sorted({edge["pipeline"] for edge in plan["service_lineage"] if "table" in edge})[0]
    table = next(name for name in _tables(plan) if (pipeline, name) not in expected)
    server = _Server(plan)
    server.pipeline_lineage[(pipeline, table)] = {"description": "Stale link", "source": "PipelineLineage"}

    result = catalog.publish(plan, server)

    assert (pipeline, table) not in server.pipeline_lineage
    assert result["removed"]["pipeline_lineage"] == 1

    report = catalog.verify(plan, server)
    assert not [difference for difference in report["differences"] if "pipeline lineage" in difference]


def test_publish_stops_when_the_server_names_a_table_otherwise():
    plan = catalog.plan()

    server = _Server(plan)
    def call(method, path, body=None, params=None):
        if path == "/tables":
            return {"fullyQualifiedName": "elsewhere", "id": "x"}
        return server(method, path, body, params)

    with pytest.raises(catalog.CatalogError, match="The server named table"):
        catalog.publish(plan, call)


def test_an_approved_profile_puts_silver_fields_quality_rules_and_code_sets_in_the_catalog(tmp_path: Path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    folder = root / "sources" / "example.profiled"
    folder.mkdir()
    profile = {"version": 1, "dataset": "example", "profiled_at": "2026-10-15T06:00:00-04:00",
               "approved_at": "2026-10-15T06:10:00-04:00",
               "parts": [{"part": "visit", "class": "transaction", "kind": None, "rows": 3000,
                          "record_key": ["visit_id"],
                          "silver": {"table": "visit", "load_mode": "append", "key": ["visit_id"],
                                     "fields": [{"name": "visit_id", "type": "BIGINT", "nullable": False,
                                                 "sensitivity": "none"},
                                                {"name": "kind_code", "type": "VARCHAR", "nullable": True,
                                                 "sensitivity": "none", "code_set": "visit_kind"}],
                                     "links": [{"source_key": "member_id", "to_part": "member",
                                                "mdm_id_column": "member_id_mdm_id"}]},
                          "quality": [{"check": "missing", "column": "visit_id", "failed_rows": 0,
                                       "proposal": "exception", "why": "a record key column is empty"},
                                      {"check": "code_list", "column": "kind_code", "failed_rows": 4,
                                       "proposal": "flag", "why": "a new code is flagged"}]}],
               "code_sets": [{"code_set": "visit_kind", "existing": False, "codes": 5,
                              "columns": ["visit.kind_code"]}]}
    (folder / "profile.yaml").write_text(files.dumps(profile), encoding="utf-8")
    plan = catalog.plan(root)
    assert {"silver", "rdm"} <= {d["name"] for d in plan["databases"]}
    tables = _tables(plan)
    visit = tables['edgartools-rules.silver."example.profiled".visit']
    assert [c["name"] for c in visit["columns"]] == ["visit_id", "kind_code"]
    assert visit["columns"][0]["dataType"] == "BIGINT" and "Always filled" in visit["columns"][0]["description"]
    assert "missing (exception)" in visit["columns"][0]["description"]
    assert "4 rows failed it when profiled" in visit["columns"][1]["description"]
    assert "`member_id_mdm_id` holds the MDM id of `member`" in visit["description"]
    code_set = tables["edgartools-rules.rdm.code_sets.visit_kind"]
    assert "proposed" in code_set["description"] and "5 codes" in code_set["description"]
    edge = next(e for e in plan["lineage"] if e["from"].endswith("code_sets.visit_kind"))
    assert edge["to"] == 'edgartools-rules.silver."example.profiled".visit'
    assert catalog.plan(root) == plan  # the same rules, the same catalog


def test_without_a_profile_or_a_silver_spec_the_catalog_has_no_silver_or_rdm_database(tmp_path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root, ignore=shutil.ignore_patterns("profile.yaml", "silver-*.yaml"))
    assert {d["name"] for d in catalog.plan(root)["databases"]} == {"sources", "mdm", "journal"}


def test_an_approved_profile_in_the_repo_adds_silver_and_rdm():
    # OpenFIGI's approved findings (ticket 80) are the first profile committed.
    assert {d["name"] for d in catalog.plan()["databases"]} == {"sources", "mdm", "silver", "rdm", "journal"}


def test_a_registered_silver_table_shows_as_it_lands(tmp_path):
    """Ticket 79: the catalog shows the table `silver register` makes from the
    source's spec, replacing its profile's proposal of the same name; a source
    with a spec and no profile gets its silver schema."""
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root, ignore=shutil.ignore_patterns("profile.yaml"))
    folder = root / "sources" / "example.profiled"
    folder.mkdir()
    (folder / "silver-visit.yaml").write_text(files.dumps({
        "table": "visit", "definition": "One visit.", "grain": "one row per visit", "key": ["visit_id"],
        "load_mode": "append", "partition": [], "why": "A visit is an event.",
        "time": {"as_of": "seen", "as_at": "loaded_at", "event_time": None},
        "columns": [{"name": "visit_id", "type": "VARCHAR", "nullable": False, "definition": "The visit's id.",
                     "source": "ID", "sensitivity": "none"},
                    {"name": "seen", "type": "DATE", "nullable": True, "definition": "When it happened.",
                     "source": "SEEN", "sensitivity": "none"}],
        "links": [{"columns": ["visit_id"], "kind": "company", "source_code": "example.v1", "to_part": "company",
                   "source_key": "visit_id", "mdm_id_column": "company_mdm_id"}],
        "checks": [{"id": "visit_known", "check": "in_set", "column": "visit_id", "values": ["V1", "V2"],
                    "on_fail": "flag", "why": "A visit is one the desk issued."}]}), encoding="utf-8")
    plan = catalog.plan(root)
    assert '"example.profiled"' in {catalog.quote(s["name"]) for s in plan["schemas"]
                                    if s["database"] == "edgartools-rules.silver"}
    tables = {f"{t['databaseSchema']}.{t['name']}": t for t in plan["tables"]}
    visit = tables['edgartools-rules.silver."example.profiled".visit']
    columns = {c["name"]: c for c in visit["columns"]}
    assert list(columns) == ["visit_id", "seen", "company_mdm_id", "quality", "loaded_at"]
    assert columns["seen"]["dataType"] == "DATE" and "visit_known (flag)" in columns["visit_id"]["description"]
    assert "Key: visit_id; load mode append." in visit["description"]
    # A profile proposing a table of the same name is replaced by the registered one.
    (folder / "profile.yaml").write_text(files.dumps({
        "version": 1, "dataset": "example", "parts": [{"part": "visits", "class": "transaction", "rows": 3,
        "silver": {"table": "visit", "key": [], "load_mode": "replace", "fields": [
            {"name": "other", "type": "VARCHAR", "nullable": True, "sensitivity": "none"}]}}]}), encoding="utf-8")
    again = [t for t in catalog.plan(root)["tables"] if t["name"] == "visit"]
    assert [[c["name"] for c in t["columns"]] for t in again] == [["visit_id", "seen", "company_mdm_id", "quality", "loaded_at"]]


def _invented_profile(tmp_path: Path):
    """A copy of the rules whose openfigi profile is an invented one: 2 parts, 40 rows, 3 fields."""
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    path = root / "sources" / "openfigi" / "profile.yaml"
    profile = files.load(path)
    profile.update(dataset="Invented set", profiled_at="2026-01-02T03:04:05+00:00", approved_at="2026-01-03T00:00:00+00:00")
    profile["parts"] = profile["parts"][:2]
    profile["parts"][0]["rows"] = 40
    profile["parts"][0]["silver"]["fields"] = profile["parts"][0]["silver"]["fields"][:3]
    path.write_text(files.dumps(profile), encoding="utf-8")
    return root, profile


def test_a_profiled_source_says_so_and_an_unprofiled_one_says_not_yet(tmp_path: Path):
    root, _ = _invented_profile(tmp_path)
    plan = catalog.plan(root)
    schemas = {schema["name"]: schema["description"] for schema in plan["schemas"] if schema["database"].endswith(".sources")}
    assert schemas["openfigi"].endswith("Profile: Invented set; 2 parts, profiled 2026-01-02, approved 2026-01-03.")
    assert schemas["sec.company"].endswith("Not profiled yet.")


def test_a_kind_table_says_which_profile_feeds_it_or_not_yet(tmp_path: Path):
    root, profile = _invented_profile(tmp_path)
    profile["parts"][1]["kind"] = "security"
    (root / "sources" / "openfigi" / "profile.yaml").write_text(files.dumps(profile), encoding="utf-8")
    tables = _tables(catalog.plan(root))
    assert tables["edgartools-rules.mdm.master_records.security"]["description"].endswith("Profiled from openfigi: 1 part.")
    assert tables["edgartools-rules.mdm.master_records.company"]["description"].endswith("Not profiled yet.")


def test_a_profiled_silver_table_carries_its_row_and_column_count(tmp_path: Path):
    root, profile = _invented_profile(tmp_path)
    plan = catalog.plan(root)
    table = profile["parts"][0]["silver"]["table"]
    assert [item for item in plan["profiles"] if item["table"].endswith("." + table)] == [{
        "table": f"edgartools-rules.silver.openfigi.{table}", "timestamp": 1767323045000, "rowCount": 40, "columnCount": 3}]
    assert len(plan["profiles"]) == 2


def test_a_profile_date_without_a_zone_is_utc(tmp_path: Path):
    root, profile = _invented_profile(tmp_path)
    profile["profiled_at"] = "2026-01-02T03:04:05"
    (root / "sources" / "openfigi" / "profile.yaml").write_text(files.dumps(profile), encoding="utf-8")
    assert {item["timestamp"] for item in catalog.plan(root)["profiles"]} == {1767323045000}


def test_publish_writes_the_profile_and_check_says_when_it_is_stale():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
    assert [path for method, path in server.calls if method == "PUT" and path.endswith("/tableProfile")]
    mark = plan["profiles"][0]
    server.profiles = {mark["table"]: {**mark, "rowCount": mark["rowCount"] + 1}}
    report = catalog.verify(plan, server)
    assert f"{mark['table']}: profile changed, publish again" in report["differences"]
    server.profiles = {item["table"]: item for item in plan["profiles"]}
    assert not [d for d in catalog.verify(plan, server)["differences"] if "profile changed" in d]


def test_each_identifier_limit_of_a_kind_is_a_check_on_its_master_table():
    plan = catalog.plan(files.ROOT)
    cases = {case["name"]: case for case in plan["quality_cases"]}
    forward, reverse = cases["company.cik-per-master"], cases["company.cik-masters-per-value"]
    assert forward["entityLink"].endswith("mdm.master_records.company>")
    assert forward["testDefinition"] == "edgartools-configured-table-check"
    assert "at most 1 `cik` value" in forward["description"] and "merge/kinds/company.yaml" in reverse["description"]
    assert "security.cusip-per-master" in cases and not any(n.startswith("security.") and n.endswith("masters-per-value")
                                                            for n in cases)


def test_master_and_reference_tables_are_gold_and_silver_tables_are_silver():
    plan = catalog.plan()
    certified = {item["table"]: item["tag"] for item in plan["certifications"]}
    assert certified[f"{catalog.SERVICE}.mdm.master_records.company"] == "Certification.Gold"
    assert any(name.startswith(f"{catalog.SERVICE}.rdm.code_sets.") and tag == "Certification.Gold"
               for name, tag in certified.items())
    assert {tag for name, tag in certified.items() if ".silver." in name} == {"Certification.Silver"}
    assert not any(".sources." in name for name in certified)
    assert "processing_layer" not in {c["name"] for c in plan["classifications"]}


def test_check_says_when_a_table_is_not_certified_as_planned():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
    assert not [d for d in catalog.verify(plan, server)["differences"] if "not certified" in d]
    server.certified = {}
    assert any("not certified Certification.Gold" in d for d in catalog.verify(plan, server)["differences"])


def test_a_code_list_edge_maps_the_code_to_the_column_that_holds_it():
    plan = catalog.plan(files.ROOT)
    edges = [e for e in plan["lineage"] if ".rdm." in e["from"]]
    assert edges and all(e["columns"] for e in edges)
    edge = next(e for e in edges if e["from"].endswith('"requests.idType"'))
    assert edge["columns"][0]["fromColumns"][0].endswith('"requests.idType".code')
    assert edge["columns"][0]["toColumn"].startswith(edge["to"] + ".")
    assert not any(e["columns"] for e in plan["lineage"] if ".sources." in e["from"] and ".sources." in e["to"])


def _results_file():
    return {"company_fact.one_form_per_filing": {"table": "company_fact", "check": "one_form_per_filing", "on_fail": "flag",
                                           "at": "2026-11-02T12:00:00+00:00", "rows_checked": 40, "rows_failed": 3}}


def test_publish_sends_each_recorded_result_to_its_case_and_check_reads_it_back():
    plan = catalog.plan()
    server = _Server(plan)
    results = _results_file()
    catalog.publish(plan, server, results=results)
    (fqn_, sent_rows), = server.results.items()
    sent, = sent_rows
    assert fqn_.endswith('.company_fact.form."company_fact.one_form_per_filing"')
    assert sent["testCaseStatus"] == "Failed" and sent["failedRows"] == 3 and sent["passedRows"] == 37
    assert sent["timestamp"] == 1793620800000
    assert not [d for d in catalog.verify(plan, server, results=results)["differences"] if "result" in d]
    server.results[fqn_][0] = {**sent, "testCaseStatus": "Success"}
    assert any("result changed, publish again" in d for d in catalog.verify(plan, server, results=results)["differences"])


def test_a_publish_without_results_sends_none():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
    assert server.results == {}


def test_a_result_that_fails_more_rows_than_it_checked_is_refused():
    plan = catalog.plan()
    bad = {"company_fact.one_form_per_filing": {**_results_file()["company_fact.one_form_per_filing"], "rows_failed": 41}}
    with pytest.raises(catalog.CatalogError, match="fails 41 of 40 rows"):
        catalog.publish(plan, _Server(plan), results=bad)


def test_check_says_when_the_row_counts_of_a_result_differ():
    plan = catalog.plan()
    server = _Server(plan)
    results = _results_file()
    catalog.publish(plan, server, results=results)
    key, sent_rows = next(iter(server.results.items()))
    server.results[key][0] = {**sent_rows[0], "failedRows": 0, "passedRows": 40}
    assert any("result changed" in d for d in catalog.verify(plan, server, results=results)["differences"])


def test_publish_preserves_and_verifies_every_run_result_and_is_idempotent():
    plan = catalog.plan()
    server = _Server(plan)
    one = _results_file()["company_fact.one_form_per_filing"]
    two = {**one, "at": "2026-11-02T12:00:00.001+00:00",
           "correlation": "Bookkeeping run run-a, step silver, unit abc123, attempt 1"}
    results = {"company_fact.one_form_per_filing": [one, two]}

    sent = catalog.publish(plan, server, results=results)
    first_count = sum(len(rows) for rows in server.results.values())
    replay = catalog.publish(plan, server, results=results)

    assert sent["quality_results_sent"] == 2
    assert replay["quality_results_sent"] == 0
    assert sum(len(rows) for rows in server.results.values()) == first_count == 2
    rows = next(iter(server.results.values()))
    assert "unit abc123" in rows[1]["result"]
    differences = catalog.verify(plan, server, results=results)["differences"]
    assert not [difference for difference in differences if "result" in difference]


def test_publish_corrects_conflicting_result_once_and_reads_it_back():
    plan = catalog.plan()
    server = _Server(plan)
    results = _results_file()
    catalog.publish(plan, server, results=results)
    changed = {**results["company_fact.one_form_per_filing"], "rows_failed": 4}
    corrected = catalog.publish(plan, server, results={"company_fact.one_form_per_filing": changed})
    assert corrected["quality_results_sent"] == 1
    assert len([path for path, _ in server.patches if path.startswith(
        "/dataQuality/testCases/testCaseResults/")]) == 1
    key, rows = next(iter(server.results.items()))
    assert rows[0]["failedRows"] == 4 and rows[0]["passedRows"] == 36
    assert not [difference for difference in catalog.verify(
        plan, server, results={"company_fact.one_form_per_filing": changed})["differences"]
                if "result" in difference]


def test_publish_stops_after_one_quality_result_correction():
    plan = catalog.plan()
    server = _Server(plan)
    results = _results_file()
    catalog.publish(plan, server, results=results)
    key, rows = next(iter(server.results.items()))
    rows[0] = {**rows[0], "failedRows": 0, "passedRows": rows[0]["passedRows"] + rows[0]["failedRows"]}
    server.ignore_quality_patch = True
    changed = {"company_fact.one_form_per_filing": results["company_fact.one_form_per_filing"]}
    with pytest.raises(catalog.CatalogError, match="after one permitted correction"):
        catalog.publish(plan, server, results=changed)
    assert len([path for path, _ in server.patches if path.startswith(
        "/dataQuality/testCases/testCaseResults/")]) == 1


def test_the_catalog_command_reads_the_results_file_it_is_given(tmp_path):
    from edgar_warehouse.silver_writer import results as silver_results

    path = tmp_path / "results.json"
    silver_results.record(path, "company_fact", {"checks": {"one_form_per_filing": {"on_fail": "flag", "rows_failed": 3}},
                                                     "rows_checked": 40})
    assert rules_cli._results(Namespace(results=path))["company_fact.one_form_per_filing"]["rows_failed"] == 3
    assert rules_cli._results(Namespace(results=None)) == {}


def test_catalog_results_can_come_directly_from_admitted_bookkeeping_evidence(monkeypatch):
    from edgar_warehouse.bookkeeping.clean import cli as bookkeeping_cli
    from edgar_warehouse.bookkeeping.clean import quality

    class Bookkeeping:
        closed = False

        def close(self):
            self.closed = True

    book = Bookkeeping()
    monkeypatch.setattr(bookkeeping_cli, "configured_bookkeeping", lambda: book)
    monkeypatch.setattr(quality, "aggregate", lambda _book, run_id: {
        "status": "passed", "units_unknown": 0, "results": [{
            "run_id": run_id, "step": "silver", "work_unit_ref": "unit-ref",
            "attempt": "attempt-ref", "table": "company_fact", "check": "one_form_per_filing",
            "kind": "unique", "failure_action": "flag", "observed_at": "2026-11-06T12:00:00Z",
            "rows_checked": 40, "rows_failed": 0, "status": "passed"}]})

    rows = rules_cli._results(Namespace(results=None, bookkeeping_run="run-a"))

    assert book.closed
    assert rows["company_fact.one_form_per_filing"][0]["correlation"] == (
        "Bookkeeping run run-a, step silver, unit unit-ref, attempt attempt-ref; "
        "observed at 2026-11-06T12:00:00Z")


def test_catalog_results_arguments_are_mutually_exclusive():
    with pytest.raises(ValueError, match="either --results or --bookkeeping-run"):
        rules_cli._results(Namespace(results=Path("results.json"), bookkeeping_run="run-a"))


def test_catalog_cause_preserves_safe_quality_readback_stage():
    error = catalog.CatalogError("quality result readback mismatch after one permitted correction")

    assert rules_cli._catalog_cause(error, catalog) == (
        "OpenMetadata quality result readback mismatch after bounded correction")


def test_incomplete_bookkeeping_run_is_reported_pending_without_catalog_writes(capsys, monkeypatch):
    monkeypatch.setattr(rules_cli, "_bookkeeping_quality", lambda _run_id: {
        "status": "unknown", "run_id": "run-a", "run_complete": False,
        "units_expected": 2, "units_verified": 1, "units_unknown": 1,
        "unknown_units": [{"step": "silver", "work_unit_ref": "opaque-unknown"}],
        "results": [{"run_id": "run-a", "step": "silver", "work_unit_ref": "opaque-known",
                     "status": "passed"}]})
    monkeypatch.setattr(catalog, "connect", lambda *_args: pytest.fail("unknown evidence cannot contact OpenMetadata"))

    code = rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False,
                                        results=None, bookkeeping_run="run-a"))

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pending"
    assert report["failed_stage"] == "quality_evidence"
    assert report["quality"]["units_verified"] == 1
    assert report["quality"]["unknown_units"] == [{"step": "silver", "work_unit_ref": "opaque-unknown"}]


def test_incomplete_run_summary_says_not_complete_when_no_units_are_unknown(capsys, monkeypatch):
    monkeypatch.setattr(rules_cli, "_bookkeeping_quality", lambda _run_id: {
        "status": "unknown", "run_id": "run-a", "run_complete": False,
        "units_expected": 2, "units_verified": 2, "units_unknown": 0,
        "unknown_units": [], "results": []})
    monkeypatch.setattr(catalog, "connect", lambda *_args: pytest.fail("incomplete evidence cannot contact OpenMetadata"))

    code = rules_cli._catalog(Namespace(action="publish", root="rules", draft_terms=False,
                                        results=None, bookkeeping_run="run-a"))

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pending"
    assert "is not complete" in report["summary"]
    assert "2/2 units verified and 0 unknown" in report["summary"]


def test_catalog_status_reports_retryable_bookkeeping_failure_on_target_pipeline(capsys, monkeypatch):
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
    pipeline = plan["pipelines"][0]
    location = files.ROOT / pipeline["pipelineLocation"]
    scope, folder, target = pipeline["name"].split(":", 2)
    config = files.load_source(location) if scope == "source" else files.load(location)
    run_name = config.get("source") or folder if scope == "source" else config["pipeline"]
    run_id = "00000000-0000-0000-0000-000000000001"
    step = pipeline["tasks"][0]["name"]
    snapshot = {"run": {"run_id": run_id, "state": "waiting",
                        "submission": {"kind": scope, "name": run_name, "target": target}},
                "items": [{"step": step, "state": "waiting", "attempt": "00000000-0000-0000-0000-000000000002",
                           "error": "private failure details"}],
                "counts": {"waiting": 1}, "failed_steps": [step]}
    monkeypatch.setenv("OPENMETADATA_URL", "https://catalog.example")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "not-a-credential")
    monkeypatch.setattr(rules_cli, "_bookkeeping_status", lambda _run_id: snapshot)
    monkeypatch.setattr(rules_cli, "_bookkeeping_quality", lambda _run_id: {"status": "unknown"})
    monkeypatch.setattr(catalog, "connect", lambda *_args: server)

    code = rules_cli._catalog(Namespace(action="status", root=str(files.ROOT), draft_terms=False,
                                        results=None, bookkeeping_run=run_id))

    report = json.loads(capsys.readouterr().out)
    held = server.pipelines[catalog.fqn(pipeline["service"], pipeline["name"])]["pipelineStatus"]
    assert code == 0
    assert report["status"] == "confirmed"
    assert report["pipeline_status"] == {"execution_status": "Pending", "failed_tasks": 1}
    assert held["executionStatus"] == "Pending"
    assert held["taskStatus"] == [{"name": step, "executionStatus": "Failed"}]
    assert held["error"]["errorMessage"] == (
        "A Bookkeeping attempt failed; inspect Bookkeeping for run details.")
    assert "private failure details" not in json.dumps(report)
    assert "private failure details" not in json.dumps(held)


@pytest.mark.parametrize("kind", ["source", "pipeline"])
@pytest.mark.parametrize("state", ["running", "waiting", "blocked", "complete"])
def test_bookkeeping_run_states_map_to_target_pipeline(kind, state):
    plan = catalog.plan()
    folder = "sources" if kind == "source" else "pipelines"
    pipeline = next(item for item in plan["pipelines"]
                    if Path(item["pipelineLocation"]).parts[0] == folder)
    path = files.ROOT / pipeline["pipelineLocation"]
    body = files.load_source(path) if kind == "source" else files.load(path)
    owner = body.get("source") or path.parent.name if kind == "source" else body["pipeline"]
    target = pipeline["name"].rsplit(":", 1)[-1]
    step = pipeline["tasks"][0]["name"]
    run_id = "00000000-0000-0000-0000-000000000007"
    failed_steps = [step] if state == "waiting" else []
    snapshot = {"run": {"run_id": run_id, "state": state,
                        "submission": {"kind": kind, "name": owner, "target": target}},
                "items": ([{"step": step, "state": "waiting", "attempt":
                            "00000000-0000-0000-0000-000000000008",
                            "error": "private failure detail"}] if failed_steps else []),
                "failed_steps": failed_steps}

    update = catalog.pipeline_status_from_bookkeeping(plan, files.ROOT, snapshot)
    expected_status = "Successful" if state == "complete" else "Pending"

    assert update["pipeline"] == catalog.fqn(pipeline["service"], pipeline["name"])
    assert update["status"]["executionStatus"] == expected_status
    if failed_steps:
        assert update["status"]["taskStatus"] == [{"name": step, "executionStatus": "Failed"}]
        assert update["status"]["error"]["errorMessage"] == (
            "A Bookkeeping attempt failed; inspect Bookkeeping for run details.")
    else:
        assert "taskStatus" not in update["status"]

def test_pipeline_status_publication_requires_matching_readback():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
    pipeline = plan["pipelines"][0]
    server.ignore_pipeline_status = True
    update = {"pipeline": catalog.fqn(pipeline["service"], pipeline["name"]),
              "status": {"timestamp": 1, "executionStatus": "Pending", "executionId":
                         "00000000-0000-0000-0000-000000000005"}}

    with pytest.raises(catalog.CatalogError, match="status readback did not match"):
        catalog.publish_pipeline_status(plan, server, update)
