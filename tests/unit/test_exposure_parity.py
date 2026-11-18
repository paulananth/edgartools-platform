import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from exposure_manifest import build_manifest
from exposure_parity import check_parity


def manifest():
    return build_manifest({"tables": [{
        "database": "EDGARTOOLS_PROD", "schema": "EDGARTOOLS_GOLD", "table": "COMPANY",
        "description": "Mastered companies.", "authority": "mdm",
        "columns": [{"name": "company_id", "data_type": "BIGINT", "description": "Key."}],
        "lineage": [],
    }]})


def snapshot(description="Mastered companies.", authority="mdm", column_type="BIGINT"):
    return {"tables": [{
        "database": "EDGARTOOLS_PROD", "schema": "EDGARTOOLS_GOLD", "table": "COMPANY",
        "description": description, "authority": authority,
        "columns": [{"name": "company_id", "data_type": column_type}],
    }], "lineage": []}


def test_parity_passes_for_matching_snapshots():
    result = check_parity(manifest(), snowflake=snapshot(), openmetadata=snapshot(), autoontology=snapshot())
    assert result["ok"] is True
    assert result["mismatches"] == []


def test_parity_separates_physical_and_business_drift_with_remediation():
    result = check_parity(
        manifest(),
        snowflake=snapshot(column_type="VARCHAR"),
        openmetadata=snapshot(description="Wrong.", authority="source"),
        autoontology={"tables": [], "lineage": []},
    )
    by_kind = {m["kind"] for m in result["mismatches"]}
    assert {"type_drift", "description_drift", "authority_drift", "missing_asset"} <= by_kind
    assert all(m["owner"] and m["remediation"] for m in result["mismatches"])


def test_parity_reports_extra_assets_and_lineage_separately():
    extra = snapshot()
    extra["tables"].append({"database": "EDGARTOOLS_PROD", "schema": "EDGARTOOLS_GOLD", "table": "EXTRA", "columns": []})
    extra["lineage"] = [{"from": "x", "to": "y"}]
    result = check_parity(manifest(), snowflake=extra, openmetadata=snapshot(), autoontology=snapshot())
    assert any(m["kind"] == "extra_asset" for m in result["mismatches"])
    assert any(m["kind"] == "extra_lineage" for m in result["mismatches"])
