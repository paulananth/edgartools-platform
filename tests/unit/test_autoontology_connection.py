from __future__ import annotations

import json

import pytest

from edgar_warehouse.rules.exposure_manifest import build_manifest
from edgar_warehouse.integrations.autoontology import (
    build_snowflake_connection,
    configure_connection,
    validate_query,
)


MANIFEST = build_manifest(
    {
        "tables": [
            {
                "database": "EDGARTOOLS_PROD",
                "schema": "EDGARTOOLS_GOLD",
                "table": "COMPANY",
                "description": "Mastered companies.",
                "authority": "mdm",
            },
            {
                "database": "EDGARTOOLS_PROD",
                "schema": "EDGARTOOLS_GOLD",
                "table": "FILING_DETAIL",
                "description": "Filing details.",
                "authority": "source",
            },
        ]
    }
)


def test_connection_payload_scopes_snowflake_to_manifest_tables_without_logging_credentials():
    payload = build_snowflake_connection(
        MANIFEST,
        "snowflake://svc:secret@example-account?warehouse=READ_WH&database=EDGARTOOLS_PROD&role=EDGARTOOLS_PROD_READER",
    )

    assert payload["type"] == "snowflake"
    assert payload["database"] == "EDGARTOOLS_PROD"
    assert payload["schemas"] == ["EDGARTOOLS_GOLD"]
    assert payload["table_allow_regex"] == r"^(?:COMPANY|FILING_DETAIL)$"
    assert payload["account"] == "example-account"
    assert payload["role"] == "EDGARTOOLS_PROD_READER"
    assert payload["password"] == "secret"


def test_connection_payload_rejects_database_mismatch():
    with pytest.raises(ValueError, match="connection database"):
        build_snowflake_connection(
            MANIFEST,
            "snowflake://svc:secret@account?warehouse=wh&database=OTHER&role=EDGARTOOLS_PROD_READER",
        )


def test_configure_connection_tests_before_creating_and_returns_readiness():
    calls = []

    def fake_request(method, url, *, headers, body=None):
        calls.append((method, url, headers, body))
        if url.endswith("/test"):
            return {"success": True, "schemas": ["EDGARTOOLS_GOLD"]}
        if url.endswith("/semantic-compilation/status"):
            return {"calculated": True, "blockers": []}
        return {"data": {"database_name": "EDGARTOOLS_PROD"}}

    result = configure_connection(
        "http://auto-ontology:3000",
        "api-key",
        MANIFEST,
        "snowflake://svc:secret@account?warehouse=wh&database=EDGARTOOLS_PROD&role=EDGARTOOLS_PROD_READER",
        request=fake_request,
    )

    assert result["test"]["success"] is True
    assert result["created"]["data"]["database_name"] == "EDGARTOOLS_PROD"
    assert result["readiness"]["calculated"] is True
    assert [call[0] for call in calls] == ["POST", "POST", "GET"]


def test_validate_query_checks_generated_sql_and_rows():
    answer = validate_query(
        "http://auto-ontology:3000",
        "api-key",
        "How many companies?",
        "SELECT COUNT(*) AS n FROM EDGARTOOLS_GOLD.COMPANY",
        [{"n": 1}],
        events=[
            'data: {"type":"result","answer":{"sql_code":"SELECT COUNT(*) AS n FROM EDGARTOOLS_GOLD.COMPANY","sql_response_from_db":[{"n":1}]}}',
            "data: [DONE]",
        ],
    )
    assert answer["sql_response_from_db"] == [{"n": 1}]
