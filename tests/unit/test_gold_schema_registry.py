from __future__ import annotations

from pathlib import Path

import pyarrow as pa


def test_gold_schema_registry_loads_packaged_yaml() -> None:
    from edgar_warehouse.serving.gold_schema_registry import (
        SCHEMA_VERSION,
        load_gold_schemas,
    )

    schemas = load_gold_schemas()

    assert SCHEMA_VERSION == 1
    assert schemas["_DIM_COMPANY_SCHEMA"].field("company_key").type == pa.int64()
    assert schemas["_DIM_DATE_SCHEMA"].field("full_date").type == pa.date32()
    assert schemas["_SEC_FINANCIAL_FACT_SCHEMA"].field("cik").nullable is False
    assert schemas["_SEC_FINANCIAL_FACT_SCHEMA"].field("ingested_at").type == pa.timestamp(
        "us", tz="UTC"
    )


def test_gold_schema_registry_validates_schema_version() -> None:
    import pytest

    from edgar_warehouse.serving.gold_schema_registry import (
        GoldSchemaConfigError,
        load_gold_schemas_from_config,
    )

    with pytest.raises(GoldSchemaConfigError, match="SCHEMA_VERSION"):
        load_gold_schemas_from_config({"SCHEMA_VERSION": 999, "schemas": {}})


def test_gold_models_schema_constants_are_loaded_from_yaml() -> None:
    source = Path("edgar_warehouse/serving/gold_models.py").read_text()

    assert "pa.schema(" not in source
