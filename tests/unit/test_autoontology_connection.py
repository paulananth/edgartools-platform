from __future__ import annotations

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from tests.support.exposure import invented_manifest
from autoontology import (
    build_snowflake_connection,
    configure_connection,
    validate_query,
)


MANIFEST = invented_manifest(
    {"layer": "mdm", "table": "company", "description": "Mastered companies.", "columns": [("company_id", "BIGINT", "Key.")]},
    {"layer": "mdm", "table": "filing_detail", "description": "Filing details.", "columns": [("filing_id", "BIGINT", "Key.")]},
)


def test_connection_payload_scopes_snowflake_to_manifest_tables_without_logging_credentials():
    payload = build_snowflake_connection(
        MANIFEST,
        "snowflake://svc:secret@example-account?warehouse=READ_WH&database=INVENTED_MIRROR&role=INVENTED_MIRROR_READER",
    )

    assert payload["type"] == "snowflake"
    assert payload["database"] == "INVENTED_MIRROR"
    assert payload["schemas"] == ["MDM"]
    assert payload["table_allow_regex"] == r"^(?:COMPANY|FILING_DETAIL)$"
    assert payload["account"] == "example-account"
    assert payload["role"] == "INVENTED_MIRROR_READER"
    assert payload["password"] == "secret"


def test_connection_payload_rejects_database_mismatch():
    with pytest.raises(ValueError, match="connection database"):
        build_snowflake_connection(
            MANIFEST,
            "snowflake://svc:secret@account?warehouse=wh&database=OTHER&role=INVENTED_MIRROR_READER",
        )


def test_configure_connection_tests_before_creating_and_returns_readiness():
    calls = []

    def fake_request(method, url, *, headers, body=None):
        calls.append((method, url, headers, body))
        if url.endswith("/test"):
            return {"success": True, "schemas": ["MDM"]}
        if url.endswith("/semantic-compilation/status"):
            return {"calculated": True, "blockers": []}
        return {"data": {"database_name": "INVENTED_MIRROR"}}

    result = configure_connection(
        "http://auto-ontology:3000",
        "api-key",
        MANIFEST,
        "snowflake://svc:secret@account?warehouse=wh&database=INVENTED_MIRROR&role=INVENTED_MIRROR_READER",
        request=fake_request,
    )

    assert result["test"]["success"] is True
    assert result["created"]["data"]["database_name"] == "INVENTED_MIRROR"
    assert result["readiness"]["calculated"] is True
    assert [call[0] for call in calls] == ["POST", "POST", "GET"]


def test_validate_query_checks_generated_sql_and_rows():
    answer = validate_query(
        "http://auto-ontology:3000",
        "api-key",
        "How many companies?",
        "SELECT COUNT(*) AS n FROM MDM.COMPANY",
        [{"n": 1}],
        events=[
            'data: {"type":"result","answer":{"sql_code":"SELECT COUNT(*) AS n FROM MDM.COMPANY","sql_response_from_db":[{"n":1}]}}',
            "data: [DONE]",
        ],
    )
    assert answer["sql_response_from_db"] == [{"n": 1}]
