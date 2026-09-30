"""The Data Catalog is the rules, published one way (rules skill ticket 13)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from edgar_warehouse.rules import catalog, files


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
    assert "`sec.submissions.company.v1`, then `gleif.level1.v1`: the first with a value wins" in name["description"]
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
    del body["mdm"]["sec.submissions.company.v1"]["contract"]["adapter"]["fields"]["description"]
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
