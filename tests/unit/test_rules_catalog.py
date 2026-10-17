"""The Data Catalog is the rules, published one way (rules skill ticket 13)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from edgar_warehouse.rules import catalog, files, mapdoc


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
    sec = tables['edgartools-rules.sources."sec.submissions.company"."sec.submissions.company.v1"']
    assert {"cik", "entity_name", "business_address.postal_code", "name_census"} <= {c["name"] for c in sec["columns"]}
    company = tables["edgartools-rules.mdm.clean.company"]
    assert {"name", "address", "jurisdiction", "state_of_incorporation"} <= {c["name"] for c in company["columns"]}
    name = next(c for c in company["columns"] if c["name"] == "name")
    assert ("`sec.submissions.company.v1`, then `gleif.level1.v1`, then `iapd.adv.filings.v1`, then "
            "`iapd.adv.custodians.v1`, then `sec.nport.registrant.v1`: the first with a value wins") in name["description"]
    relationships = tables['edgartools-rules.sources.gleif."gleif.relationships.v1"']
    assert "it fills no company field" in relationships["description"]
    assert "Read by the classification rule" in next(c for c in sec["columns"] if c["name"] == "sic")["description"]
    assert "Critical data elements" in sec["description"]


def test_lineage_runs_column_by_column_and_leaves_matching_out():
    plan = catalog.plan()
    edge = next(e for e in plan["lineage"] if e["from"].endswith('"sec.submissions.company.v1"'))
    by_field = {c["toColumn"].rsplit(".", 1)[1]: c["fromColumns"] for c in edge["columns"]}
    assert len(by_field["address"]) == 6  # an address's parts fill one MDM field
    assert "name_census" not in {c.rsplit(".", 1)[1].strip('"') for cols in by_field.values() for c in cols}
    feed = next(e for e in plan["lineage"] if e["to"].endswith('"sec.submissions.company.v1"'))
    assert feed["from"].endswith(".submissions") and feed["columns"] == []


def test_the_same_rules_give_the_same_catalog_and_a_change_shows(tmp_path: Path):
    assert catalog.plan() == catalog.plan()
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    path = root / "sources" / "sec.submissions.company" / "source.yaml"
    body = files.load_source(path)
    del mapdoc.mapped(body["mdm"]["sec.submissions.company.v1"]["contract"]["adapter"], "fields")["description"]
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

    def __call__(self, method, path, body=None, params=None):
        self.calls.append((method, path))
        if method == "PUT" and path == "/tables":
            name = f"{body['databaseSchema']}.{catalog.quote(body['name'])}"
            self.ids[name] = f"id-{len(self.ids)}"
            return {"fullyQualifiedName": name, "id": self.ids[name]}
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
        return {"data": []} if method == "GET" else {}


def test_publish_deletes_only_what_the_rules_no_longer_name():
    plan = catalog.plan()
    server = _Server(plan)
    result = catalog.publish(plan, server)
    deletes = [path for method, path in server.calls if method == "DELETE"]
    company = server.ids["edgartools-rules.mdm.clean.company"]
    feed = server.ids['edgartools-rules.sources.gleif."gleif.relationships.v1"']
    assert deletes == ["/tables/id-old", "/databaseSchemas/id-gone", f"/lineage/table/{feed}/table/{company}"]
    assert result["removed"] == {"tables": 1, "schemas": 1, "databases": 0, "lineage": 1}
    assert sum(1 for method, path in server.calls if (method, path) == ("PUT", "/lineage")) == len(plan["lineage"])


def test_publish_stops_when_the_server_names_a_table_otherwise():
    plan = catalog.plan()

    def call(method, path, body=None, params=None):
        return {"fullyQualifiedName": "elsewhere", "id": "x"} if path == "/tables" else {}

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


def test_without_a_profile_the_catalog_has_no_silver_or_rdm_database(tmp_path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root, ignore=shutil.ignore_patterns("profile.yaml"))
    assert {d["name"] for d in catalog.plan(root)["databases"]} == {"sources", "mdm"}


def test_an_approved_profile_in_the_repo_adds_silver_and_rdm():
    # OpenFIGI's approved findings (ticket 80) are the first profile committed.
    assert {d["name"] for d in catalog.plan()["databases"]} == {"sources", "mdm", "silver", "rdm"}
