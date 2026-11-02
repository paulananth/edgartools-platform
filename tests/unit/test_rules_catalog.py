"""The Data Catalog is the rules, published one way (rules skill ticket 13)."""

from __future__ import annotations

from io import BytesIO
import json
import shutil
from argparse import Namespace
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
    assert {"cik", "entity_name", "business_address.postal_code", "name_census"} <= {c["name"] for c in sec["columns"]}
    company = tables["edgartools-rules.mdm.clean.company"]
    assert {"name", "address", "jurisdiction", "state_of_incorporation"} <= {c["name"] for c in company["columns"]}
    name = next(c for c in company["columns"] if c["name"] == "name")
    assert ("sec.company.v1, then gleif.level1.v1, then iapd.adv.filings.v1, then "
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
    assert "name_census" not in {c.rsplit(".", 1)[1].strip('"') for cols in by_field.values() for c in cols}
    feed = next(e for e in plan["lineage"] if e["to"].endswith('"sec.company.v1"'))
    assert feed["from"].endswith(".submissions") and feed["columns"] == []


def test_a_second_kind_from_another_sources_files_has_its_feed_lineage():
    # Person reads the submissions files the Company source's feed captures, and declares
    # no feed of its own (platform validation 05c, item 11).
    plan = catalog.plan()
    feed = [e for e in plan["lineage"] if e["to"].endswith('"sec.submissions.person.v1"')]
    assert [e["from"] for e in feed] == ['edgartools-rules.sources."sec.company".submissions']
    # A source whose family no feed captures gets no feed lineage; GLEIF's own feed leads to it.
    assert not [e for e in plan["lineage"] if e["to"].endswith('"iapd.adv.filings.v1"')]
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
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    path = root / "sources" / "sec.company" / "source.yaml"
    body = files.load_source(path)
    del mapdoc.mapped(body["mdm"]["sec.company.v1"]["contract"]["adapter"], "fields")["description"]
    files.write_source(body, path.parent)
    changed = catalog.plan(root)
    assert changed["service"]["description"] != catalog.plan()["service"]["description"]  # a new digest
    company = _tables(changed)["edgartools-rules.mdm.clean.company"]
    assert "description" not in {c["name"] for c in company["columns"]}


class _Server:
    """What `publish` asks of OpenMetadata, as the 2.0.2 server answered it
    (probed 2026-09-28): the catalog holds one table, one schema and one
    lineage link the rules no longer name."""

    def __init__(self, plan: dict):
        self.plan, self.calls, self.ids = plan, [], {}
        self.term_bodies, self.product_bodies, self.patches, self.draft = [], [], [], set()
        self.table_delete_params = []

    def __call__(self, method, path, body=None, params=None):
        self.calls.append((method, path))
        if method == "DELETE" and path.startswith("/tables/"):
            self.table_delete_params.append(params)
        if method == "PATCH":
            self.patches.append((path, body))
            if path.startswith("/glossaryTerms/"):
                self.draft.add(path.removeprefix("/glossaryTerms/"))
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
        if method == "PUT" and path == "/pipelines":
            return {**body, "fullyQualifiedName": catalog.fqn(body["service"], body["name"]), "id": "pipeline-" + body["name"]}
        if method == "PUT" and path == "/tables":
            name = f"{body['databaseSchema']}.{catalog.quote(body['name'])}"
            self.ids[name] = f"id-{len(self.ids)}"
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
        if method == "GET" and path.startswith("/lineage/table/name/edgartools-rules.mdm.clean.company"):
            company = self.ids["edgartools-rules.mdm.clean.company"]
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
    gleif = [edge for edge in plan["service_lineage"] if edge["pipeline"].endswith("source:gleif:mastering")]
    assert gleif and all("sources.gleif" in edge["table"] for edge in gleif)
    cases = {case["name"]: case for case in plan["quality_cases"]}
    assert "sec.company.v1.name_present" in cases
    assert cases["sec.company.v1.dc_state_is_empty"]["description"].startswith("Correction")
    assert cases["openfigi_listing.figi_valid"]["testDefinition"] == "edgartools-configured-column-check"
    assert all("testCaseResult" not in case for case in plan["quality_cases"])
    assert any(name.endswith("mdm.clean.security") for name in products["security_master"]["tables"])
    assert sum(1 for table in plan["tables"] if table["databaseSchema"].endswith(".relationships")) == 16
    certified = {item["table"]: item["tag"] for item in plan["certifications"]}
    assert certified["edgartools-rules.mdm.clean.company"] == "Certification.Gold"
    assert any(name.startswith("edgartools-rules.silver.") and tag == "Certification.Silver"
               for name, tag in certified.items())
    assert not any(name.startswith(("edgartools-rules.sources.", "edgartools-rules.rdm.")) for name in certified)
    assert catalog.glossary_relation_type_name("ISSUED_BY") == "issuedBy"
    assert catalog.glossary_relation_type_name("IS_FUND-MANAGED_BY") == "isFundManagedBy"
    assert "relatedTo" not in {edge["relationType"] for edge in plan["glossary_relations"]}


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


def test_a_term_is_written_as_draft_never_approved():
    plan = catalog.plan()
    server = _Server(plan)
    catalog.publish(plan, server)
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
    catalog.publish(plan, server)
    again = [path for path, _ in server.patches if path == "/glossaryTerms/Company Identity"]
    assert len(again) == 2
    assert server.draft >= {term["name"] for term in plan["glossary_terms"]}


def test_each_table_carries_its_data_class():
    plan = catalog.plan()
    marks = {item["table"]: item["tag"] for item in plan["data_class_marks"]}
    assert marks["edgartools-rules.mdm.clean.company"] == "data_class.master_data"
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
        "quality_definitions": [{}], "quality_cases": [{}, {}], "products": [{}], "pipelines": [{}, {}],
        "lineage": [{}, {}], "service_lineage": [{}], "domain_lineage": [{}], "glossary_relations": [{}, {}],
    }


def test_catalog_plan_counts_cover_configured_catalog_objects():
    assert catalog.plan_counts(_outcome_plan()) == {
        "domains": 1, "glossaries": 1, "glossary_terms": 2, "assets": 3,
        "quality_definitions": 1, "quality_cases": 2, "products": 1, "pipelines": 2,
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

    assert rules_cli._catalog(Namespace(action="publish", root="rules")) == 2

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
    monkeypatch.setattr(catalog, "publish", lambda selected, call: calls.append("publish") or {
        "service": "edgartools-rules", "tables": 3, "pipelines": 2, "lineage": 2,
        "removed": {"tables": 0, "schemas": 0, "databases": 0, "lineage": 0},
    })
    monkeypatch.setattr(catalog, "verify", lambda selected, call: calls.append("readback") or {
        "ok": True, "tables": 3, "pipelines": 2, "differences": [],
    })

    assert rules_cli._catalog(Namespace(action="publish", root="rules")) == 0

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

    def fail_publish(plan, call):
        raise catalog.CatalogError("PUT /tables: HTTP 401 body contains do-not-print")

    monkeypatch.setattr(catalog, "publish", fail_publish)
    monkeypatch.setattr(catalog, "verify", lambda *args: pytest.fail("failed publish cannot be confirmed"))

    assert rules_cli._catalog(Namespace(action="publish", root="rules")) == 1

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

    def fail_after_write(plan, call):
        call("PUT", "/tables", {})
        raise catalog.CatalogError("PUT /tables: HTTP 503")

    monkeypatch.setattr(catalog, "publish", fail_after_write)
    monkeypatch.setattr(catalog, "verify", lambda *args: pytest.fail("readback is deferred after failure"))

    assert rules_cli._catalog(Namespace(action="publish", root="rules")) == 1

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
    monkeypatch.setattr(catalog, "publish", lambda plan, call: {
        "service": "edgartools-rules", "removed": {"tables": 0},
    })
    monkeypatch.setattr(catalog, "verify", lambda plan, call: {
        "ok": False, "tables": 3, "pipelines": 2, "differences": ["tables: different membership"],
    })

    assert rules_cli._catalog(Namespace(action="publish", root="rules")) == 1

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
    monkeypatch.setattr(catalog, "verify", lambda plan, call: {
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
    company = server.ids["edgartools-rules.mdm.clean.company"]
    feed = server.ids['edgartools-rules.sources.gleif."gleif.relationships.v1"']
    assert deletes == ["/tables/id-old", "/databaseSchemas/id-gone", f"/lineage/table/{feed}/table/{company}"]
    # a renamed source's old table still holds test cases: the server refuses a delete that is not recursive
    assert server.table_delete_params == [{"hardDelete": "true", "recursive": "true"}]
    assert result["removed"] == {"tables": 1, "schemas": 1, "databases": 0, "lineage": 1}
    assert sum(1 for method, path in server.calls if (method, path) == ("PUT", "/lineage")) == len(plan["lineage"])
    posts = [path for method, path in server.calls if method == "POST" and path.endswith("/relations")]
    assert any(path.startswith("/glossaryTerms/Company Identity/") for path in posts)
    assert len(posts) == len(plan["glossary_relations"])
    assert ("PUT", "/system/settings") in server.calls


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
    assert {d["name"] for d in catalog.plan(root)["databases"]} == {"sources", "mdm"}


def test_an_approved_profile_in_the_repo_adds_silver_and_rdm():
    # OpenFIGI's approved findings (ticket 80) are the first profile committed.
    assert {d["name"] for d in catalog.plan()["databases"]} == {"sources", "mdm", "silver", "rdm"}


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
