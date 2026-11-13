"""Clear active AI Governance resources through the native OpenMetadata API."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

# These are the native AI entity collections in the pinned OpenMetadata
# release. Governance forms and workflows are scoped by entity type below.
# Keep entity collections in dependency order: executions and application
# assets first, then policies/frameworks, then their services.
AI_GOVERNANCE_COLLECTIONS = (
    ("MCP executions", "/mcpExecutions", False, False, False),
    ("AI applications", "/aiApplications", True, True, True),
    ("prompt templates", "/promptTemplates", True, False, True),
    ("LLM models", "/llmModels", True, False, True),
    ("MCP servers", "/mcpServers", True, True, True),
    ("AI Governance policies", "/aiGovernancePolicies", True, False, True),
    ("AI Governance frameworks", "/aiGovernanceFrameworks", True, True, True),
    ("LLM services", "/services/llmServices", True, True, True),
    ("MCP services", "/services/mcpServices", True, True, True),
)
AI_GOVERNANCE_ENTITY_TYPES = frozenset(
    {
        "aiapplication",
        "aigovernanceframework",
        "aigovernancepolicy",
        "llmservice",
        "llmmodel",
        "mcpservice",
        "mcpserver",
        "mcpexecution",
        "prompttemplate",
    }
)
QUALIFIED_OPENMETADATA_VERSIONS = frozenset({"2.0.7"})


class InitError(RuntimeError):
    """A safe operator-facing initialization failure."""


def connect(environment):
    endpoint = (
        environment.get("OPENMETADATA_URL", "http://127.0.0.1:8587")
        .rstrip("/")
        .removesuffix("/api/v1")
    )
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        raise InitError(
            "Set a valid OPENMETADATA_URL without credentials or query parameters"
        ) from None
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise InitError(
            "Set a valid OPENMETADATA_URL without credentials or query parameters"
        )
    token = environment.get("OPENMETADATA_TOKEN", "")

    def call(method, path, body=None, params=None):
        query = "?" + urlencode(params) if params else ""
        request = Request(
            endpoint + "/api/v1" + path + query,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": "Bearer " + token} if token else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read()
        except HTTPError as error:
            if method == "GET" and error.code == 404:
                return None
            raise InitError(
                f"OpenMetadata {method} failed (HTTP {error.code}); check private credentials and service permissions"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise InitError(
                "OpenMetadata did not answer; check server health and private endpoint configuration"
            ) from None
        try:
            return json.loads(content) if content else None
        except (ValueError, UnicodeDecodeError):
            raise InitError("OpenMetadata returned invalid JSON") from None

    email = environment.get("OPENMETADATA_LOGIN_EMAIL")
    password = environment.get("OPENMETADATA_LOGIN_PASSWORD") or environment.get(
        "OPENMETADATA_PASSWORD"
    )
    if email and password:
        answer = call(
            "POST",
            "/users/login",
            {"email": email, "password": base64.b64encode(password.encode()).decode()},
        )
        if not isinstance(answer, dict):
            raise InitError("OpenMetadata login returned an invalid response")
        token = answer.get("accessToken", "")
        if not isinstance(token, str):
            raise InitError("OpenMetadata login returned an invalid response")
    if not token:
        raise InitError(
            "Load OPENMETADATA_TOKEN or private OpenMetadata login environment variables"
        )
    return call


def list_active(call, path, supports_include):
    entities = []
    cursor = None
    seen_cursors = set()
    expected_total = None
    while True:
        page_limit = "1000" if supports_include else "1000000"
        params = {"limit": page_limit}
        if supports_include:
            params["include"] = "non-deleted"
        if cursor:
            params["after"] = cursor
        result = call("GET", path, params=params)
        page = result.get("data") if isinstance(result, dict) else None
        paging = result.get("paging", {}) if isinstance(result, dict) else None
        if not isinstance(page, list) or not isinstance(paging, dict):
            raise InitError("OpenMetadata returned an invalid AI Governance inventory")
        total = paging.get("total")
        if isinstance(total, int):
            if expected_total is not None and expected_total != total:
                raise InitError(
                    "OpenMetadata AI Governance inventory changed during initialization"
                )
            expected_total = total
        for entity in page:
            if (
                not isinstance(entity, dict)
                or not isinstance(entity.get("id"), str)
                or not entity["id"]
                or entity.get("deleted") not in (None, False)
            ):
                raise InitError(
                    "OpenMetadata AI Governance inventory differs from the active scope"
                )
            entities.append(entity)
        next_cursor = paging.get("after")
        if not next_cursor:
            if (
                not supports_include
                and len(entities) >= int(page_limit)
                and expected_total is None
            ):
                raise InitError(
                    "OpenMetadata may have truncated the AI Governance execution inventory"
                )
            break
        if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
            raise InitError(
                "OpenMetadata returned an incomplete AI Governance inventory"
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    if expected_total is not None and expected_total != len(entities):
        raise InitError("OpenMetadata returned an incomplete AI Governance inventory")
    if len({entity["id"] for entity in entities}) != len(entities):
        raise InitError("OpenMetadata returned duplicate AI Governance entities")
    return entities


def is_ai_governance_workflow(entity):
    trigger = entity.get("trigger") if isinstance(entity, dict) else None
    config = trigger.get("config") if isinstance(trigger, dict) else None
    entity_types = config.get("entityTypes") if isinstance(config, dict) else None
    if not isinstance(entity_types, list):
        return False
    return any(
        is_ai_entity_type(value) for value in entity_types if isinstance(value, str)
    )


def is_ai_entity_type(value):
    return re.sub(r"[^a-z0-9]", "", value.lower()) in AI_GOVERNANCE_ENTITY_TYPES


def is_ai_governance_intake_form(entity):
    entity_type = entity.get("entityType") if isinstance(entity, dict) else None
    return isinstance(entity_type, str) and is_ai_entity_type(entity_type)


def clear_ai_governance(call):
    inventories = []
    for (
        label,
        path,
        supports_include,
        recursive,
        supports_tombstones,
    ) in AI_GOVERNANCE_COLLECTIONS:
        entities = list_active(call, path, supports_include)
        inventories.append((label, path, recursive, supports_tombstones, entities))
    workflow_path = "/governance/workflowDefinitions"
    workflows = [
        entity
        for entity in list_active(call, workflow_path, True)
        if is_ai_governance_workflow(entity)
    ]
    inventories.append(
        ("AI Governance workflow definitions", workflow_path, True, True, workflows)
    )
    intake_path = "/governance/intakeForms"
    intake_forms = [
        entity
        for entity in list_active(call, intake_path, True)
        if is_ai_governance_intake_form(entity)
    ]
    inventories.append(
        ("AI Governance intake forms", intake_path, False, True, intake_forms)
    )

    removed = 0
    counts = {}
    for label, path, recursive, supports_tombstones, entities in inventories:
        counts[label] = len(entities)
        for entity in entities:
            params = {"hardDelete": "false"}
            if recursive:
                params["recursive"] = "true"
            call("DELETE", path + "/" + entity["id"], params=params)
            removed += 1
            if supports_tombstones:
                retained = call(
                    "GET", path + "/" + entity["id"], params={"include": "all"}
                )
                if (
                    not isinstance(retained, dict)
                    or retained.get("id") != entity["id"]
                    or not retained.get("deleted")
                ):
                    raise InitError(
                        "An AI Governance entity was not retained as deleted after initialization"
                    )

    for label, path, supports_include, _, _ in AI_GOVERNANCE_COLLECTIONS:
        if list_active(call, path, supports_include):
            raise InitError("Active AI Governance entities remain after initialization")
    active_workflows = list_active(call, workflow_path, True)
    if any(is_ai_governance_workflow(entity) for entity in active_workflows):
        raise InitError(
            "An AI Governance workflow definition remains active after initialization"
        )
    active_intake_forms = list_active(call, intake_path, True)
    if any(is_ai_governance_intake_form(entity) for entity in active_intake_forms):
        raise InitError(
            "An AI Governance intake form remains active after initialization"
        )
    return {
        "stage": "initialize",
        "status": "confirmed",
        "active_ai_governance_entities": 0,
        "removed_ai_governance_entities": removed,
        "inventory_counts": counts,
    }


def main():
    try:
        call = connect(os.environ)
        version = call("GET", "/system/version")
        if (
            not isinstance(version, dict)
            or not isinstance(version.get("version"), str)
            or version["version"] not in QUALIFIED_OPENMETADATA_VERSIONS
        ):
            raise InitError(
                "Qualify the running OpenMetadata release before clearing AI Governance resources"
            )
        result = clear_ai_governance(call)
    except InitError as error:
        print(
            json.dumps(
                {"stage": "initialize", "status": "failed", "cause": str(error)}
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
