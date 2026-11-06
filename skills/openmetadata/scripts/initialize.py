"""Exclude the vendor's demo services through the native API; no project install needed."""
from __future__ import annotations

import base64
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


DEMO_SERVICES = (("llmServices", "ai_governance_llm"), ("mcpServices", "ai_governance_mcp"))
DEMO_CHILD_COLLECTIONS = (("llmModels", "ai_governance_llm"), ("mcpServers", "ai_governance_mcp"))


class InitError(RuntimeError):
    """A safe operator-facing initialization failure."""


def connect(environment):
    endpoint = environment.get("OPENMETADATA_URL", "http://127.0.0.1:8585").rstrip("/").removesuffix("/api/v1")
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        raise InitError("Set a valid OPENMETADATA_URL without credentials or query parameters") from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InitError("Set a valid OPENMETADATA_URL without credentials or query parameters")
    token = environment.get("OPENMETADATA_TOKEN", "")

    def call(method, path, body=None, params=None):
        query = "?" + urlencode(params) if params else ""
        request = Request(endpoint + "/api/v1" + path + query, method=method,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read()
        except HTTPError as error:
            if method == "GET" and error.code == 404:
                return None
            raise InitError(f"OpenMetadata {method} failed (HTTP {error.code}); check private credentials and service permissions") from None
        except (URLError, TimeoutError, OSError):
            raise InitError("OpenMetadata did not answer; check server health and private endpoint configuration") from None
        try:
            return json.loads(content) if content else None
        except (ValueError, UnicodeDecodeError):
            raise InitError("OpenMetadata returned invalid JSON") from None

    email = environment.get("OPENMETADATA_LOGIN_EMAIL")
    password = environment.get("OPENMETADATA_LOGIN_PASSWORD") or environment.get("OPENMETADATA_PASSWORD")
    if email and password:
        answer = call("POST", "/users/login", {"email": email, "password": base64.b64encode(password.encode()).decode()})
        if not isinstance(answer, dict):
            raise InitError("OpenMetadata login returned an invalid response")
        token = answer.get("accessToken", "")
        if not isinstance(token, str):
            raise InitError("OpenMetadata login returned an invalid response")
    if not token:
        raise InitError("Load OPENMETADATA_TOKEN or private OpenMetadata login environment variables")
    return call


def exclude_demo_services(call):
    planned = []
    for collection, name in DEMO_SERVICES:
        path = "/services/" + collection
        entity = call("GET", path + "/name/" + name, params={"include": "all"})
        if entity is not None and (not isinstance(entity, dict) or entity.get("name") != name or entity.get("fullyQualifiedName") != name or not entity.get("id")):
            raise InitError("Demo service identity differs from the reviewed initialization scope")
        planned.append((path, name, entity))
    children = []
    for collection, service_name in DEMO_CHILD_COLLECTIONS:
        result = call("GET", "/" + collection, params={"service": service_name, "limit": "1000"})
        entities = (result or {}).get("data") if isinstance(result, dict) else None
        if not isinstance(entities, list):
            raise InitError("OpenMetadata returned an invalid demo asset inventory")
        paging = result.get("paging", {})
        if isinstance(paging, dict) and paging.get("after"):
            raise InitError("OpenMetadata returned an incomplete demo asset inventory")
        total = paging.get("total") if isinstance(paging, dict) else None
        if isinstance(total, int) and total != len(entities):
            raise InitError("OpenMetadata returned an incomplete demo asset inventory")
        for entity in entities:
            fqn = entity.get("fullyQualifiedName") if isinstance(entity, dict) else None
            service_ref = entity.get("service") if isinstance(entity, dict) else None
            service_matches = (service_ref is None or service_ref == service_name or
                               isinstance(service_ref, dict) and service_ref.get("name") == service_name)
            if (not fqn or not fqn.startswith(service_name + ".") or not entity.get("id")
                    or not service_matches or entity.get("deleted") not in (None, False)):
                raise InitError("Demo asset inventory differs from the reviewed service scope")
            children.append((collection, service_name, entity))
    removed = 0
    children_removed = 0
    for collection, service_name, entity in children:
        if entity.get("deleted") is not True:
            call("DELETE", "/" + collection + "/" + entity["id"], params={"hardDelete": "false"})
            children_removed += 1
    for collection, service_name, entity in children:
        retained = call("GET", "/" + collection + "/" + entity["id"], params={"include": "all"})
        if not isinstance(retained, dict) or retained.get("fullyQualifiedName") != entity["fullyQualifiedName"] or not retained.get("deleted"):
            raise InitError("A sample AI asset was not retained as deleted after initialization")
        if call("GET", "/" + collection + "/" + entity["id"]) is not None:
            raise InitError("A sample AI asset remains active after initialization")
    for path, name, entity in planned:
        if entity is not None and not entity.get("deleted"):
            call("DELETE", path + "/" + entity["id"], params={"recursive": "true", "hardDelete": "false"})
            removed += 1
        if call("GET", path + "/name/" + name) is not None:
            raise InitError("A default AI demo service remains active after initialization")
        retained = call("GET", path + "/name/" + name, params={"include": "all"})
        if entity is not None and (not isinstance(retained, dict) or retained.get("id") != entity["id"]
                                   or retained.get("fullyQualifiedName") != name or not retained.get("deleted")):
            raise InitError("The demo exclusion marker was not retained")
    for collection, service_name in DEMO_CHILD_COLLECTIONS:
        active = call("GET", "/" + collection, params={"service": service_name, "limit": "1000"})
        entities = (active or {}).get("data") if isinstance(active, dict) else None
        paging = active.get("paging", {}) if isinstance(active, dict) else {}
        total = paging.get("total") if isinstance(paging, dict) else None
        if (not isinstance(entities, list) or entities or (isinstance(paging, dict) and paging.get("after"))
                or isinstance(total, int) and total != len(entities)):
            raise InitError("A sample AI asset remains active after initialization")
    return {"stage": "initialize", "status": "confirmed", "active_demo_services": 0,
            "removed_services": removed, "already_excluded": len(DEMO_SERVICES) - removed,
            "sample_children": len(children), "removed_sample_children": children_removed}


def main():
    try:
        call = connect(os.environ)
        version = call("GET", "/system/version")
        if not isinstance(version, dict) or version.get("version") != "2.0.2":
            raise InitError("Qualify the running OpenMetadata release before changing initialization exclusions")
        result = exclude_demo_services(call)
    except InitError as error:
        print(json.dumps({"stage": "initialize", "status": "failed", "cause": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
