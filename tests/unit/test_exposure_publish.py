from edgar_warehouse.rules.exposure_manifest import build_manifest
from edgar_warehouse.rules.exposure_publish import plan_exposure, publish_exposure


def _manifest():
    return build_manifest(
        {
            "tables": [
                {
                    "database": "EDGARTOOLS_PROD",
                    "schema": "EDGARTOOLS_GOLD",
                    "table": "COMPANY",
                    "description": "Mastered companies.",
                    "authority": "mdm",
                    "columns": [{"name": "company_id", "data_type": "BIGINT", "description": "Master key."}],
                    "lineage": ["EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY", "unverified"],
                }
            ]
        }
    )


def test_plan_keeps_physical_identity_and_skips_unverified_lineage():
    plan = plan_exposure(_manifest())
    table = plan["tables"][0]
    assert table["database"] == "EDGARTOOLS_PROD"
    assert table["name"] == "COMPANY"
    assert table["columns"] == [{"name": "company_id", "dataType": "BIGINT", "description": "Master key."}]
    assert table["certification"] == "Certification.Gold"
    assert table["glossaryTerm"] == "mdm"
    assert plan["lineage"] == []


def test_publish_is_idempotent_and_readback_matches_scope():
    calls = []

    def call(method, path, body=None):
        calls.append((method, path))
        if path == "/system/version":
            return {"version": "2.0.7"}
        if path.endswith("/tables") and method == "GET":
            return {"data": [{"fullyQualifiedName": "edgartools-snowflake.EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY"}]}
        return {}

    first = publish_exposure(_manifest(), call)
    second = publish_exposure(_manifest(), call)
    assert first["plan"] == second["plan"]
    assert first["readback"] == ["edgartools-snowflake.EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY"]
    assert calls.count(("PUT", "/tables")) == 2
