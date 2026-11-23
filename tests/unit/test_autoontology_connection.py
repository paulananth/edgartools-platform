from __future__ import annotations

import json
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

import autoontology

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
            return {"calculated": True, "running": False, "last_success_at": "2026-11-19T12:00:00", "last_failure_at": None}
        if "/api/schemas/" in url:
            return {"schemas_count": 1, "schemas": [{"id": "s1", "schema_name": "MDM"}]}
        if "/api/tables/" in url:
            return {"data": [{"name": "COMPANY", "schema_name": "MDM"}, {"name": "FILING_DETAIL", "schema_name": "MDM"}], "count": 2}
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
    assert [call[0] for call in calls] == ["POST", "POST", "GET", "GET", "GET"]


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


def test_validate_query_streams_the_documented_chat_endpoint(monkeypatch):
    lines = [
        b'data: {"type":"step","node":"query","phase":"start"}\r\n',
        b'data: {"type":"result","answer":{"sql_code":"SELECT COUNT(*) AS n FROM MDM.COMPANY","sql_response_from_db":[{"n":1}]}}\r\n',
        b"data: [DONE]\r\n",
    ]
    consumed = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            for line in lines:
                consumed.append(line)
                yield line

    calls = []

    def fake_urlopen(request, *, timeout):
        calls.append((request, timeout))
        return Response()

    monkeypatch.setattr(autoontology, "urlopen", fake_urlopen)
    answer = validate_query(
        "http://auto-ontology:3000",
        "api-key",
        "How many companies?",
        "SELECT COUNT(*) AS n FROM MDM.COMPANY",
        [{"n": 1}],
    )

    request, timeout = calls[0]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert request.full_url == "http://auto-ontology:3000/api/chat/completions"
    assert request.get_method() == "POST"
    assert headers["x-api-key"] == "api-key"
    assert headers["content-type"] == "application/json"
    assert json.loads(request.data) == {"question": "How many companies?"}
    assert timeout == 900
    assert answer["sql_response_from_db"] == [{"n": 1}]
    assert consumed[-1] == b"data: [DONE]\r\n"



def test_validate_query_rejects_a_stream_that_ends_before_done(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            yield b'data: {"type":"result","answer":{"sql_code":"SELECT COUNT(*) AS n FROM MDM.COMPANY","sql_response_from_db":[{"n":1}]}}\r\n'

    monkeypatch.setattr(autoontology, "urlopen", lambda request, *, timeout: Response())
    with pytest.raises(RuntimeError, match=r"ended before \[DONE\]"):
        validate_query(
            "http://auto-ontology:3000",
            "api-key",
            "How many companies?",
            "SELECT COUNT(*) AS n FROM MDM.COMPANY",
            [{"n": 1}],
        )


CONNECTION = "snowflake://svc:secret@account?warehouse=wh&database=INVENTED_MIRROR&role=INVENTED_MIRROR_READER"


def _server(tables, status=None, schemas=("MDM",)):
    status = status or {"calculated": True, "running": False, "last_success_at": "t", "last_failure_at": None}

    def request(method, url, *, headers, body=None):
        if url.endswith("/test"):
            return {"success": True, "schemas": list(schemas)}
        if url.endswith("/semantic-compilation/status"):
            return status
        if "/api/schemas/" in url:
            return {"schemas_count": len(schemas), "schemas": [{"id": f"id-{s}", "schema_name": s} for s in schemas]}
        if "/api/tables/" in url:
            schema = url.rsplit("id-", 1)[1]
            return {"data": [{"name": n, "schema_name": s} for s, n in tables if s == schema], "count": 1}
        return {"data": {}}
    return request


def test_a_table_the_filter_let_in_by_name_alone_is_caught_by_reading_the_catalog_back():
    """The regex matches unqualified names, so a same-named table of another approved schema would be ingested."""
    manifest = invented_manifest(
        {"layer": "mdm", "table": "company", "description": "x.", "columns": [("id", "BIGINT", "Key.")]},
        {"layer": "silver", "table": "filing", "description": "x.", "columns": [("id", "BIGINT", "Key.")]})
    taken = [("MDM", "COMPANY"), ("SILVER", "FILING"), ("SILVER", "COMPANY")]  # the filter admitted SILVER.COMPANY by its name
    with pytest.raises(RuntimeError, match="1 extra, 0 missing"):
        configure_connection("http://ao", "k", manifest, CONNECTION, request=_server(taken, schemas=("MDM", "SILVER")))


def test_a_table_the_catalog_lacks_is_refused_too():
    with pytest.raises(RuntimeError, match="0 extra, 1 missing"):
        configure_connection("http://ao", "k", MANIFEST, CONNECTION, request=_server([("MDM", "COMPANY")]))


@pytest.mark.parametrize("status, reason", [
    ({"calculated": True, "running": True, "last_success_at": "t", "last_failure_at": None}, "running"),
    ({"calculated": True, "running": False, "last_success_at": "t", "last_failure_at": "t2"}, "failed"),
    ({"calculated": True, "running": False, "last_success_at": None, "last_failure_at": None}, "no semantic compilation"),
    ({"calculated": False, "running": False, "last_success_at": None, "last_failure_at": None}, "no semantic compilation"),
])
def test_calculated_alone_is_not_a_compilation_success(status, reason):
    taken = [("MDM", "COMPANY"), ("MDM", "FILING_DETAIL")]
    with pytest.raises(RuntimeError, match=reason):
        configure_connection("http://ao", "k", MANIFEST, CONNECTION, request=_server(taken, status=status))


def test_a_percent_encoded_credential_in_the_connection_string_is_decoded_once():
    payload = build_snowflake_connection(
        MANIFEST, "snowflake://svc%40corp:p%2Fss%3Aword@account?warehouse=wh&database=INVENTED_MIRROR&role=INVENTED_MIRROR_READER")
    assert payload["user"] == "svc@corp" and payload["password"] == "p/ss:word"
