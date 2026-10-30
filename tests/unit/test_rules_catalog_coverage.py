"""Catalog coverage follows configuration rather than a fixed entity list."""
import shutil

import pytest

from edgar_warehouse.rules import catalog, files, mapdoc


def test_every_source_and_standalone_target_has_a_native_pipeline():
    plan = catalog.plan()
    expected = {}
    for folder, scope, filename in (("sources", "source", "source.yaml"), ("pipelines", "pipeline", "pipeline.yaml")):
        for path in sorted((files.ROOT / folder).glob("*/" + filename)):
            body = files.load_source(path) if scope == "source" else files.load(path)
            for target, definition in (body.get("bookkeeping", {}).get("targets") or {}).items():
                expected[f"{scope}:{path.parent.name}:{target}"] = definition
    actual = {p["name"]: p for p in plan["pipelines"]}
    assert set(actual) == set(expected)
    for name, definition in expected.items():
        tasks = {t["name"]: t for t in actual[name]["tasks"]}
        assert set(tasks) == {s["name"] for s in definition["steps"]}
        for step in definition["steps"]:
            assert tasks[step["name"]]["taskType"] == step["operation"]
            assert set(tasks[step["name"]]["downstreamTasks"]) == {
                s["name"] for s in definition["steps"] if step["name"] in s.get("requires", [])}
            assert all(check in tasks[step["name"]]["description"] for check in step.get("checks", []))
        assert "state" not in actual[name]  # definitions are not activation evidence


def test_new_pipeline_is_discovered_without_mdm_or_entity_code(tmp_path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    path = root / "pipelines" / "invented-flow" / "pipeline.yaml"
    path.parent.mkdir()
    path.write_text(files.dumps({"pipeline": "invented-flow", "bookkeeping": {"version": 1, "targets": {
        "archive": {"steps": [{"name": "copy", "operation": "artifact.copy", "requires": [], "checks": ["output.receipt"]}], "checks": ["work.accounting"]}}}}))
    plan = catalog.plan(root)
    assert next(p for p in plan["pipelines"] if p["name"] == "pipeline:invented-flow:archive")["tasks"][0]["taskType"] == "artifact.copy"
    document = mapdoc.documents(root)[path.with_name("MAPPING.xlsx")]
    assert "Pipeline steps" in document[1]
    assert any("artifact.copy" in row for row in document[1]["Pipeline steps"])


def test_pinned_relationship_types_and_endpoints_are_explicit_in_catalog_and_workbook():
    root = files.ROOT
    policy = files.policy(root)
    rows = files.pinned_reference(policy["relationships"]["pin"], root)
    definitions = [r for r in rows if r["parent_code"] is None]
    plan = catalog.plan(root)
    actual = {t["name"]: t for t in plan["tables"] if t["databaseSchema"] == catalog.fqn(catalog.SERVICE, "mdm", "relationships")}
    assert set(actual) == {r["code"] for r in definitions}
    for row in definitions:
        table = actual[row["code"]]
        assert {c["name"] for c in table["columns"]} == set(row["properties"])
        for value in row["properties"]["from"] + row["properties"]["to"]:
            assert value in table["description"]
    sheets = mapdoc.documents(root)[root / "merge" / "relationships.xlsx"][1]
    assert {row[0] for row in sheets["Relationship types"][1:]} == {r["code"] for r in definitions}


def test_relationship_metadata_refuses_a_changed_published_pin(tmp_path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    pin = files.reference_pin(files.policy(root)["relationships"]["pin"], root)
    path = root / "reference" / "published" / pin["code_set"] / str(pin["version"]) / "canonical.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(files.RulesFileError, match="pinned sha256"):
        catalog.plan(root)


def test_all_source_workbooks_include_declared_pipeline_steps():
    documents = mapdoc.documents()
    for path in sorted((files.ROOT / "sources").glob("*/source.yaml")):
        body = files.load_source(path)
        sheets = documents[path.with_name("MAPPING.xlsx")][1]
        targets = (body.get("bookkeeping") or {}).get("targets") or {}
        assert {r[0] for r in sheets["Pipeline targets"][1:]} == set(targets)
        assert len(sheets["Pipeline steps"]) - 1 == sum(len(t["steps"]) for t in targets.values())


def test_every_dataset_quality_rule_and_declared_link_is_described():
    tables = {catalog.fqn(catalog.SERVICE, "sources", p.parent.name, code): entry["contract"]
              for p in (files.ROOT / "sources").glob("*/source.yaml")
              for code, entry in (files.load_source(p).get("mdm") or {}).items()}
    actual = {t["databaseSchema"] + "." + catalog.quote(t["name"]): t for t in catalog.plan()["tables"]}
    for name, contract in tables.items():
        about = actual[name]["description"]
        for section in ("checks", "fixes"):
            for rule in (contract.get("quality") or {}).get(section) or []:
                assert rule["id"] in about
        for link in (contract.get("adapter") or {}).get("relationships") or []:
            for kind in ([link["type"]] if link.get("type") else (link.get("type_values") or {}).values()):
                assert kind in about


def test_publication_reconciles_only_its_own_pipeline_service():
    from tests.unit.test_rules_catalog import _Server

    class Server(_Server):
        def __call__(self, method, path, body=None, params=None):
            if method == "GET" and path == "/pipelines":
                return {"data": [{"fullyQualifiedName": catalog.PIPELINES_SERVICE + ".obsolete", "id": "obsolete"},
                                 {"fullyQualifiedName": "other-service.keep", "id": "foreign"}]}
            return super().__call__(method, path, body, params)

    server = Server(catalog.plan())
    result = catalog.publish(server.plan, server)
    assert ("DELETE", "/pipelines/obsolete") in server.calls
    assert ("DELETE", "/pipelines/foreign") not in server.calls
    assert result["removed"]["pipelines"] == 1


def test_catalog_check_reads_saved_metadata_and_detects_drift_without_writes():
    plan = {"service": {"name": catalog.SERVICE, "serviceType": "CustomDatabase", "description": "invented rules"},
            "databases": [], "schemas": [], "tables": [{"name": "invented", "databaseSchema": catalog.SERVICE + ".db.schema",
                "columns": [{"name": "key", "dataType": "STRING", "description": "invented key"}], "description": "invented table"}],
            "lineage": [], "pipeline_service": {"name": catalog.PIPELINES_SERVICE, "serviceType": "CustomPipeline"},
            "pipelines": [{"name": "invented-flow", "service": catalog.PIPELINES_SERVICE,
                           "tasks": [{"name": "copy", "taskType": "artifact.copy", "downstreamTasks": []}]}]}
    drift = False
    def call(method, path, body=None, params=None):
        assert method == "GET"
        if path == "/tables":
            return {"data": [{"fullyQualifiedName": catalog.SERVICE + ".db.schema.invented", "id": "table-id"}]}
        if path == "/pipelines":
            return {"data": [{"fullyQualifiedName": catalog.PIPELINES_SERVICE + ".invented-flow", "id": "pipeline-id"}]}
        if path.startswith("/tables/name/"):
            return {**plan["tables"][0], "description": "changed" if drift else "invented table"}
        if path.startswith("/pipelines/name/"):
            assert params == {"fields": "tasks"}
            return plan["pipelines"][0]
        if path.startswith("/services/databaseServices/name/"): return plan["service"]
        if path.startswith("/services/pipelineServices/name/"): return plan["pipeline_service"]
        return {"data": []}
    assert catalog.verify(plan, call)["ok"]
    drift = True
    result = catalog.verify(plan, call)
    assert not result["ok"]
    assert any("description" in difference for difference in result["differences"])


@pytest.mark.parametrize("ok, expected", [(True, 0), (False, 1)])
def test_catalog_check_cli_fails_on_remote_drift(monkeypatch, capsys, ok, expected):
    from argparse import Namespace
    from edgar_warehouse.rules import cli
    monkeypatch.setenv("OPENMETADATA_URL", "http://invented.invalid")
    monkeypatch.setenv("OPENMETADATA_TOKEN", "invented-not-a-credential")
    monkeypatch.setattr(catalog, "plan", lambda root: {})
    monkeypatch.setattr(catalog, "connect", lambda *args: None)
    monkeypatch.setattr(catalog, "verify", lambda *args: {"ok": ok, "differences": [] if ok else ["invented drift"]})
    assert cli._catalog(Namespace(action="check", root=str(files.ROOT))) == expected
    assert '"ok"' in capsys.readouterr().out


def test_owned_description_repair_handles_bot_put_preservation_and_keeps_other_metadata():
    body = {"name": "invented", "databaseSchema": catalog.SERVICE + ".db.schema",
            "description": "configured", "columns": [{"name": "key", "dataType": "STRING", "description": "configured key"}]}
    identity = catalog.SERVICE + ".db.schema.invented"
    saved = {**body, "fullyQualifiedName": identity, "id": "owned-id", "description": "old",
             "columns": [{**body["columns"][0], "description": "old key", "tags": ["keep"]}]}
    calls = []
    def call(method, endpoint, request, params=None):
        calls.append((method, endpoint, request))
        if method == "PUT": return saved
        assert endpoint == "/tables/owned-id" and method == "PATCH"
        assert request == [{"op": "add", "path": "/description", "value": "configured"},
                           {"op": "add", "path": "/columns/0/description", "value": "configured key"}]
        return {**saved, "description": "configured", "columns": [{**saved["columns"][0], "description": "configured key"}]}
    result = catalog._upsert(call, "/tables", body)
    assert result["columns"][0]["tags"] == ["keep"]
    assert len(calls) == 2


def test_wrong_entity_identity_is_refused_before_any_description_patch():
    body = {"name": "invented", "databaseSchema": catalog.SERVICE + ".db.schema", "description": "configured"}
    def call(method, endpoint, request, params=None):
        assert method == "PUT"
        return {"id": "foreign-id", "fullyQualifiedName": "other-service.db.schema.invented", "description": "old"}
    with pytest.raises(catalog.CatalogError, match="server named table"):
        catalog._upsert(call, "/tables", body)
