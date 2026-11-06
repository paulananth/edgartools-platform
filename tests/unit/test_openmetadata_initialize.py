"""Initialization excludes only the reviewed vendor samples, using native deletion."""
import importlib.util
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import os
import subprocess
from urllib.error import HTTPError

import pytest


spec = importlib.util.spec_from_file_location(
    "catalog_initialize", Path(__file__).parents[2] / "skills/openmetadata/scripts/initialize.py")
initialize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(initialize)


class NativeAPI:
    def __init__(self, deletes_work=True):
        self.entities = {"/services/" + collection + "/name/" + name:
                         {"id": "example-" + str(index), "name": name,
                          "fullyQualifiedName": name, "deleted": False}
                         for index, (collection, name) in enumerate(initialize.DEMO_SERVICES)}
        self.children = {"/" + collection + "/" + str(index):
                         {"id": "child-" + str(index), "name": "example-child-" + str(index),
                          "fullyQualifiedName": service + ".example-child-" + str(index),
                          "service": service, "deleted": False}
                         for index, (collection, service) in enumerate(initialize.DEMO_CHILD_COLLECTIONS)}
        self.deletes_work = deletes_work
        self.deleted = []

    def __call__(self, method, path, body=None, params=None):
        if method == "GET":
            if path in ("/llmModels", "/mcpServers"):
                service = (params or {}).get("service")
                return {"data": [deepcopy(child) for key, child in self.children.items()
                                  if key.startswith(path + "/") and child["service"] == service
                                  and not child.get("deleted", False)]}
            if any(path == "/" + collection + "/" + entity["id"]
                   for collection, service in initialize.DEMO_CHILD_COLLECTIONS
                   for entity in self.children.values() if entity["service"] == service):
                entity = next(e for e in self.children.values() if path.endswith("/" + e["id"]))
                return deepcopy(entity) if (params or {}).get("include") == "all" or not entity["deleted"] else None
            entity = self.entities[path]
            return deepcopy(entity) if (params or {}).get("include") == "all" or not entity["deleted"] else None
        assert method == "DELETE"
        if any(path.endswith("/" + e["id"]) for e in self.children.values()):
            entity = next(e for e in self.children.values() if path.endswith("/" + e["id"]))
            assert params == {"hardDelete": "false"}
            self.deleted.append(path)
            if self.deletes_work:
                entity["deleted"] = True
            return
        entity = next(e for e in self.entities.values() if path.endswith("/" + e["id"]))
        assert params == {"recursive": "true", "hardDelete": "false"}
        self.deleted.append(path)
        if self.deletes_work:
            entity["deleted"] = True


def test_init_removes_two_exact_services_and_repeat_preserves_deleted_markers():
    native = NativeAPI()
    first = initialize.exclude_demo_services(native)
    assert first == {"stage": "initialize", "status": "confirmed", "active_demo_services": 0,
                     "removed_services": 2, "already_excluded": 0,
                     "sample_children": 2, "removed_sample_children": 2}
    assert native.deleted == ["/llmModels/child-0", "/mcpServers/child-1",
                              "/services/llmServices/example-0", "/services/mcpServices/example-1"]
    second = initialize.exclude_demo_services(native)
    assert second["removed_services"] == 0 and second["already_excluded"] == 2
    assert second["sample_children"] == 0 and second["removed_sample_children"] == 0
    assert len(native.deleted) == 4
    assert all(e["deleted"] for e in native.entities.values())
    assert all(e["deleted"] for e in native.children.values())


def test_identity_mismatch_stops_before_any_delete():
    native = NativeAPI()
    list(native.entities.values())[1]["fullyQualifiedName"] = "invented-unrelated-service"
    with pytest.raises(initialize.InitError, match="identity differs"):
        initialize.exclude_demo_services(native)
    assert native.deleted == []


def test_child_inventory_with_another_page_fails_before_any_delete():
    native = NativeAPI()
    original_call = native.__call__

    def partial_inventory(method, path, body=None, params=None):
        if method == "GET" and path == "/llmModels":
            return {"data": [], "paging": {"after": "invented-next-page", "total": 1}}
        return original_call(method, path, body, params)

    with pytest.raises(initialize.InitError, match="incomplete demo asset inventory"):
        initialize.exclude_demo_services(partial_inventory)
    assert native.deleted == []


def test_child_outside_reviewed_service_fqn_stops_before_any_delete():
    native = NativeAPI()
    native.children["/llmModels/0"]["fullyQualifiedName"] = "unrelated.example-child"
    with pytest.raises(initialize.InitError, match="inventory differs"):
        initialize.exclude_demo_services(native)
    assert native.deleted == []


def test_active_children_are_removed_even_when_parent_service_is_already_deleted():
    native = NativeAPI()
    native.entities["/services/llmServices/name/ai_governance_llm"]["deleted"] = True
    result = initialize.exclude_demo_services(native)
    assert result["removed_services"] == 1
    assert result["removed_sample_children"] == 2
    assert all(child["deleted"] for child in native.children.values())
    assert all(service["deleted"] for service in native.entities.values())


def test_active_list_children_without_deleted_field_are_removed():
    native = NativeAPI()
    for child in native.children.values():
        child.pop("deleted")
    result = initialize.exclude_demo_services(native)
    assert result["removed_sample_children"] == 2
    assert all(child["deleted"] for child in native.children.values())


def test_http_success_without_absent_readback_is_an_init_failure():
    with pytest.raises(initialize.InitError, match="sample AI asset was not retained"):
        initialize.exclude_demo_services(NativeAPI(deletes_work=False))


def test_native_errors_omit_credentials_endpoint_and_response_body(monkeypatch):
    secret = "invented-private-token"

    def refused(request, timeout):
        raise HTTPError(request.full_url, 403, "forbidden", {}, BytesIO(secret.encode()))

    monkeypatch.setattr(initialize, "urlopen", refused)
    call = initialize.connect({"OPENMETADATA_URL": "http://private.example.invalid", "OPENMETADATA_TOKEN": secret})
    with pytest.raises(initialize.InitError, match="HTTP 403") as error:
        call("GET", "/services/llmServices/name/example")
    assert secret not in str(error.value)
    assert "private.example.invalid" not in str(error.value)


def test_credentials_in_endpoint_are_rejected_without_echoing_them():
    with pytest.raises(initialize.InitError) as error:
        initialize.connect({"OPENMETADATA_URL": "http://invented:private-password@example.invalid"})
    assert "private-password" not in str(error.value)


def test_failed_initialization_exits_nonzero_with_a_stage(monkeypatch, capsys):
    def failed(environment):
        raise initialize.InitError("Native readback failed")

    monkeypatch.setattr(initialize, "connect", failed)
    assert initialize.main() == 1
    assert '"stage": "initialize"' in capsys.readouterr().err


def test_unqualified_server_release_stops_before_any_exclusion(monkeypatch, capsys):
    def native(method, path):
        assert (method, path) == ('GET', '/system/version')
        return {'version': 'invented-unqualified-release'}

    monkeypatch.setattr(initialize, 'connect', lambda environment: native)
    assert initialize.main() == 1
    assert 'Qualify the running OpenMetadata release' in capsys.readouterr().err


@pytest.mark.parametrize('server_exit,exclusion_exit,expected,stages', [
    (17, 0, 17, ['server']),
    (0, 42, 42, ['server', 'exclusion']),
])
def test_init_command_requires_both_server_and_exclusion_to_succeed(tmp_path, server_exit, exclusion_exit, expected, stages):
    log = tmp_path / 'stages'
    for name, stage, exit_code in [('docker', 'server', server_exit), ('uv', 'exclusion', exclusion_exit)]:
        command = tmp_path / name
        command.write_text('#!/bin/sh\nprintf "%s\\n" ' + stage + ' >> "$INIT_STAGE_LOG"\nexit ' + str(exit_code) + '\n')
        command.chmod(0o755)
    result = subprocess.run(['bash', str(Path(__file__).parents[2] / 'infra/openmetadata/init.sh')],
                            env={**os.environ, 'PATH':str(tmp_path) + ':' + os.environ['PATH'], 'INIT_STAGE_LOG':str(log)},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == expected
    assert log.read_text().splitlines() == stages
