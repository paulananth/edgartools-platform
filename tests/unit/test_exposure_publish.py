from urllib.parse import unquote

from edgar_warehouse.rules.exposure_manifest import build_manifest
from edgar_warehouse.rules.exposure_publish import exposure_plan, publish_exposure


def _manifest():
    return build_manifest({
        "tables": [{
            "database": "EDGARTOOLS_PROD",
            "schema": "EDGARTOOLS_GOLD",
            "table": "COMPANY",
            "description": "Mastered companies.",
            "authority": "mdm",
            "columns": [{"name": "company_id", "data_type": "BIGINT", "description": "Master key."}],
            "lineage": ["not-in-manifest"],
        }]
    })


class _Catalog:
    def __init__(self):
        self.entities = {}
        self.certification = {}
        self.tags = {}
        self.lineage = {}
        self.glossary_writes = []

    def __call__(self, method, path, body=None, params=None):
        if path == "/system/version":
            return {"version": "2.0.7"}
        if path == "/system/settings":
            return {"data": [{"config_type": "assetCertificationSettings", "config_value": {"validityPeriod": "P30D"}},
                             {"config_type": "entityRulesSettings", "config_value": {"entitySemantics": []}}]}
        if method == "PUT" and path == "/glossaryTerms":
            self.glossary_writes.append(body)
            return {}
        if method == "PUT":
            parent = (body or {}).get("databaseSchema") or (body or {}).get("database") or (body or {}).get("service")
            name = body["name"] if parent is None else parent + "." + body["name"]
            if path == "/services/databaseServices":
                name = body["name"]
            entity = {**body, "id": name, "fullyQualifiedName": name}
            self.entities[name] = entity
            return entity
        if method == "PATCH" and path.startswith("/tables/") and body and body[0]["path"] == "/certification":
            self.certification[path.removeprefix("/tables/")] = body[0]["value"]
            return {}
        if method == "PATCH" and "/tags/-" in str(body):
            self.tags.setdefault(path.removeprefix("/tables/"), []).append(body[0]["value"]["tagFQN"])
            return {}
        if method == "PUT" and path == "/lineage":
            edge = body["edge"]
            self.lineage[(edge["fromEntity"]["id"], edge["toEntity"]["id"])] = edge
            return {}
        if method == "GET" and path.startswith("/services/databaseServices/name/"):
            return self.entities.get(unquote(path.rsplit("/", 1)[-1]))
        if method == "GET" and "/name/" in path:
            name = unquote(path.split("/name/", 1)[1])
            entity = dict(self.entities.get(name) or {})
            if (params or {}).get("fields") == "certification":
                entity["certification"] = self.certification.get(entity.get("id"))
            if (params or {}).get("fields") == "tags":
                entity["tags"] = [{"tagFQN": tag} for tag in self.tags.get(entity.get("id"), [])]
            return entity
        if method == "GET" and path in ("/tables", "/databases", "/databaseSchemas"):
            wanted = {"/tables": 4, "/databases": 2, "/databaseSchemas": 3}[path]
            rows = [entity for entity in self.entities.values() if entity["fullyQualifiedName"].count(".") == wanted - 1]
            return {"data": rows, "paging": {}}
        if method == "GET" and path.startswith("/lineage/table/name/"):
            table = unquote(path.removeprefix("/lineage/table/name/"))
            edges = [{"fromEntity": source, "toEntity": target, "lineageDetails": edge["lineageDetails"]}
                     for (source, target), edge in self.lineage.items() if target == table]
            return {"upstreamEdges": edges}
        if method == "GET" and path.startswith("/services/pipelineServices/name/"):
            return None
        if method == "DELETE":
            return {}
        return {"data": [], "paging": {}}


def test_plan_uses_physical_identity_and_omits_unverified_lineage():
    plan = exposure_plan(_manifest())
    table = plan["tables"][0]
    assert table["name"] == "COMPANY"
    assert table["databaseSchema"] == "edgartools-snowflake.EDGARTOOLS_PROD.EDGARTOOLS_GOLD"
    assert table["columns"][0]["dataType"] == "BIGINT"
    assert plan["certifications"] == [{
        "table": "edgartools-snowflake.EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY",
        "tag": "Certification.Gold",
    }]
    assert plan["data_class_marks"][0]["tag"] == "data_class.master_data"
    assert plan["lineage"] == []


def test_publish_matches_catalog_readback_without_inventing_glossary_terms():
    server = _Catalog()
    result = publish_exposure(_manifest(), server)
    assert result["verified"]["differences"] == []
    assert server.glossary_writes == []
    assert server.certification["edgartools-snowflake.EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY"]["tagLabel"]["tagFQN"] == "Certification.Gold"
    assert "edgartools-snowflake" in server.entities
    assert "edgartools-snowflake.EDGARTOOLS_PROD.EDGARTOOLS_GOLD" in server.entities
