"""Credential-safe AutoOntology connection setup for the approved manifest."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling exposure scripts

import json
import os
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import Request, urlopen

from exposure_manifest import validate_manifest


_REQUEST_TIMEOUT_S = 30


def _request_json(method: str, url: str, *, headers: dict[str, str], body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method=method)
    try:
        with urlopen(request, timeout=_REQUEST_TIMEOUT_S) as response:
            return json.loads(response.read())
    except (HTTPError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"AutoOntology request failed: {method} {urlsplit(url).path}") from error


def _table_regex(names: list[str]) -> str:
    escaped = sorted(re.escape(name) for name in names)
    return rf"^(?:{'|'.join(escaped)})$"


def build_snowflake_connection(manifest: dict[str, Any], connection_string: str) -> dict[str, Any]:
    """Build the UI-managed AutoOntology payload from a validated manifest.

    The connection string remains in memory only. Callers must provide it from
    a secret-backed environment and must not print the returned payload.
    """
    validate_manifest(manifest)
    parsed = urlsplit(connection_string)
    if parsed.scheme.lower() != "snowflake":
        raise ValueError("AutoOntology source must use a Snowflake connection string")
    if not parsed.hostname:
        raise ValueError("Snowflake connection string must include an account")

    parsed_query = parse_qs(parsed.query)
    account = parsed.hostname
    user = unquote(parsed.username) if parsed.username else None  # a credential in a URL is percent-encoded
    warehouse = parsed_query.get("warehouse", [None])[0]
    connection_database = parsed_query.get("database", [None])[0]
    role = parsed_query.get("role", [None])[0]
    if not user or not warehouse or not connection_database or not role:
        raise ValueError("Snowflake connection requires user, warehouse, database, and role")
    if not role.upper().endswith("_READER"):
        raise ValueError("Snowflake connection role must be a read-only *_READER role")
    password = unquote(parsed.password) if parsed.password else None
    private_key = parsed_query.get("private_key", [None])[0]
    if not password and not private_key:
        raise ValueError("Snowflake connection requires a password or private key")

    identities = [table["physical"] for table in manifest["tables"]]
    databases = {item["database"] for item in identities}
    if len(databases) != 1:
        raise ValueError("manifest must target one Snowflake database")
    database = next(iter(databases))
    if connection_database.upper() != database:
        raise ValueError("connection database does not match manifest database")
    schemas = sorted({item["schema"] for item in identities})
    names = [item["table"] for item in identities]
    if not names:
        raise ValueError("manifest must contain at least one table")
    connection: dict[str, Any] = {
        "type": "snowflake",
        "account": account,
        "user": user,
        "warehouse": warehouse,
        "database": database,
        "role": role,
        "schemas": schemas,
        "table_allow_regex": _table_regex(names),
    }
    if password:
        connection["password"] = password
    else:
        connection["private_key"] = private_key
    return connection


def approved_identities(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    """The (schema, table) pairs the manifest approves, in the case Snowflake stores them."""
    return {(item["schema"].upper(), item["table"].upper()) for item in (t["physical"] for t in manifest["tables"])}


def read_back_identities(base: str, headers: dict[str, str], database: str, request: Callable[..., dict[str, Any]]) -> set[tuple[str, str]]:
    """What AutoOntology actually ingested, by exact schema and table, read from its catalog."""
    found: set[tuple[str, str]] = set()
    listed = request("GET", f"{base}/api/schemas/{quote(database, safe='')}", headers=headers) or {}
    for schema in listed.get("schemas", []):
        tables = request("GET", f"{base}/api/tables/{quote(schema['id'], safe='')}", headers=headers)
        for table in tables.get("data", []):
            found.add(((table.get("schema_name") or schema.get("schema_name") or "").upper(), (table.get("name") or "").upper()))
    return found


def compilation_outcome(status: dict[str, Any]) -> str | None:
    """None when the last semantic compilation succeeded and nothing newer failed; otherwise why not, in a sentence. `calculated`
    only says some Term exists, which a failed or running pass can also leave behind."""
    if status.get("running"):
        return "a semantic compilation is running"
    if status.get("last_failure_at"):
        return "the last semantic compilation failed"
    if not status.get("calculated") or not status.get("last_success_at"):
        return "no semantic compilation has succeeded"
    return None


def configure_connection(
    api_url: str,
    api_key: str,
    manifest: dict[str, Any],
    connection_string: str,
    *,
    request: Callable[..., dict[str, Any]] = _request_json,
) -> dict[str, Any]:
    """Test, create, and verify one bounded AutoOntology source connection."""
    expected = build_snowflake_connection(manifest, connection_string)
    payload = {"connection": expected}
    base = api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    tested = request("POST", f"{base}/api/connections/test", headers=headers, body=payload)
    if not tested.get("success"):
        raise RuntimeError("AutoOntology rejected the Snowflake connection")
    if set(tested.get("schemas", [])) != set(expected["schemas"]):
        raise RuntimeError("AutoOntology returned schemas outside the approved manifest")
    created = request("POST", f"{base}/api/connections", headers=headers, body=payload)
    ingested = read_back_identities(base, headers, expected["database"], request)
    approved = approved_identities(manifest)
    if ingested != approved:  # the regex filters unqualified names, so only the catalog itself shows what was taken
        raise RuntimeError(f"AutoOntology ingested tables that differ from the approved manifest: "
                           f"{len(ingested - approved)} extra, {len(approved - ingested)} missing")
    readiness = request("GET", f"{base}/api/semantic-compilation/status", headers=headers)
    problem = compilation_outcome(readiness)
    if problem:
        raise RuntimeError(f"AutoOntology semantic compilation is not ready: {problem}")
    return {"test": tested, "created": created, "readiness": readiness}


def configure_from_environment(manifest: dict[str, Any]) -> dict[str, Any]:
    """Configure AutoOntology using secrets supplied only through the environment."""
    api_url = os.environ.get("AUTO_ONTOLOGY_API_URL")
    api_key = os.environ.get("AUTO_ONTOLOGY_API_KEY")
    connection_string = os.environ.get("AUTO_ONTOLOGY_SNOWFLAKE_CONNECTION")
    if not api_url or not api_key or not connection_string:
        raise RuntimeError(
            "Set AUTO_ONTOLOGY_API_URL, AUTO_ONTOLOGY_API_KEY, and "
            "AUTO_ONTOLOGY_SNOWFLAKE_CONNECTION in the private environment"
        )
    return configure_connection(api_url, api_key, manifest, connection_string)


def _answer_from_events(lines: list[str]) -> dict[str, Any]:
    for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if payload == "[DONE]":
            break
        event = json.loads(payload)
        if event.get("type") == "error":
            raise RuntimeError(event.get("message") or "AutoOntology query failed")
        if event.get("type") == "result":
            return event["answer"]
    raise RuntimeError("AutoOntology query returned no result")


def validate_query(
    api_url: str,
    api_key: str,
    question: str,
    expected_sql: str,
    expected_rows: list[dict[str, Any]],
    *,
    events: list[str] | None = None,
) -> dict[str, Any]:
    """Validate one generated query against expected SQL and rows.

    Tests pass ``events`` so the seam does not need a live AutoOntology server.
    """
    if events is None:
        raise RuntimeError("live AutoOntology query validation requires a streaming client")
    answer = _answer_from_events(events)
    if answer.get("sql_code") != expected_sql:
        raise RuntimeError("generated SQL did not match the approved query")
    if answer.get("sql_response_from_db") != expected_rows:
        raise RuntimeError("query rows did not match the approved result")
    return answer
