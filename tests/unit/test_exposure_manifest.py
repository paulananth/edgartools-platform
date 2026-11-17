from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgar_warehouse.rules.exposure_manifest import (
    MANIFEST_VERSION,
    build_manifest,
    validate_manifest,
    write_manifest,
)


def test_manifest_is_deterministic_and_keeps_physical_and_business_identity_separate():
    rules = {
        "tables": [
            {
                "database": "EDGARTOOLS_PROD",
                "schema": "EDGARTOOLS_GOLD",
                "table": "COMPANY",
                "description": "Mastered company identities.",
                "authority": "mdm",
                "columns": [
                    {"name": "company_id", "data_type": "BIGINT", "description": "Master identity key."}
                ],
                "lineage": [{"from": "EDGARTOOLS_SILVER.SEC_COMPANY", "to": "COMPANY"}],
            }
        ]
    }

    first = build_manifest(rules)
    second = build_manifest({"tables": list(reversed(rules["tables"]))})

    assert first == second
    assert first["manifest_version"] == MANIFEST_VERSION
    assert first["tables"][0]["physical"] == {
        "database": "EDGARTOOLS_PROD",
        "schema": "EDGARTOOLS_GOLD",
        "table": "COMPANY",
    }
    assert first["tables"][0]["business"]["authority"] == "mdm"
    assert first["tables"][0]["business"]["description"] == "Mastered company identities."
    assert first["tables"][0]["columns"] == [
        {"name": "company_id", "data_type": "BIGINT", "description": "Master identity key."}
    ]
    validate_manifest(first)
    with pytest.raises(ValueError, match="unsupported manifest version"):
        validate_manifest({**first, "manifest_version": MANIFEST_VERSION + 1})
    with pytest.raises(ValueError, match="digest"):
        validate_manifest({**first, "digest": "bad"})
    assert first["digest"] == build_manifest(rules)["digest"]


def test_writer_emits_canonical_json(tmp_path: Path):
    destination = tmp_path / "manifest.json"
    written = write_manifest(destination, {"tables": []})

    assert json.loads(destination.read_text()) == written
    assert destination.read_text().endswith("\n")


def test_manifest_rejects_internal_or_unapproved_tables():
    with pytest.raises(ValueError, match="approved table scope"):
        build_manifest(
            {
                "tables": [
                    {
                        "database": "EDGARTOOLS_PROD",
                        "schema": "EDGARTOOLS_MDM_CONTROL",
                        "table": "RUNS",
                        "description": "Internal control state.",
                        "authority": "bookkeeping",
                    }
                ]
            }
        )


def test_manifest_rejects_missing_business_metadata():
    with pytest.raises(ValueError, match="description"):
        build_manifest(
            {
                "tables": [
                    {
                        "database": "EDGARTOOLS_PROD",
                        "schema": "EDGARTOOLS_GOLD",
                        "table": "COMPANY",
                        "authority": "mdm",
                    }
                ]
            }
        )
