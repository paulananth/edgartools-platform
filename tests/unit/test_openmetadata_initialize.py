"""Initialization clears active AI Governance resources through native APIs."""

import importlib.util
import os
import subprocess
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location(
    "catalog_initialize",
    Path(__file__).parents[2] / "skills/openmetadata/scripts/initialize.py",
)
initialize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(initialize)


def _entity(path, index, *, ai=True):
    entity = {
        "id": f"entity-{index}",
        "name": f"example-{index}",
        "fullyQualifiedName": f"example-{index}",
        "deleted": False,
    }
    if path.endswith("workflowDefinitions"):
        entity["trigger"] = {
            "config": {"entityTypes": ["aiGovernancePolicy" if ai else "table"]}
        }
    if path.endswith("intakeForms"):
        entity["entityType"] = "aiApplication" if ai else "table"
    return entity


class NativeAPI:
    def __init__(self, deletes_work=True):
        self.entities = {}
        self.collections = {}
        for index, (_, path, *_rest) in enumerate(initialize.AI_GOVERNANCE_COLLECTIONS):
            entity = _entity(path, index)
            self.entities[(path, entity["id"])] = entity
            self.collections.setdefault(path, []).append(entity)
        for path, offset, ai in (
            ("/governance/workflowDefinitions", 20, True),
            ("/governance/workflowDefinitions", 21, False),
            ("/governance/intakeForms", 30, True),
            ("/governance/intakeForms", 31, False),
        ):
            entity = _entity(path, offset, ai=ai)
            self.entities[(path, entity["id"])] = entity
            self.collections.setdefault(path, []).append(entity)
        self.deletes_work = deletes_work
        self.deleted = []
        self.incomplete_path = None

    def __call__(self, method, path, body=None, params=None):
        if method == "GET":
            for collection, entities in self.collections.items():
                if path == collection:
                    active = [
                        deepcopy(e) for e in entities if not e.get("deleted", False)
                    ]
                    paging = {"total": len(active)}
                    if self.incomplete_path == path:
                        paging.update(
                            {"after": "invented-next-page", "total": len(active) + 1}
                        )
                    return {"data": active, "paging": paging}
            for (collection, entity_id), entity in self.entities.items():
                if path == f"{collection}/{entity_id}":
                    return (
                        deepcopy(entity)
                        if (params or {}).get("include") == "all"
                        or not entity["deleted"]
                        else None
                    )
            raise AssertionError(f"unexpected GET path: {path}")

        assert method == "DELETE"
        collection, entity_id = path.rsplit("/", 1)
        entity = self.entities[(collection, entity_id)]
        recursive_collections = {
            path
            for _, path, _, recursive, _ in initialize.AI_GOVERNANCE_COLLECTIONS
            if recursive
        }
        if collection == "/governance/workflowDefinitions":
            recursive_collections.add(collection)
        assert params == (
            {"hardDelete": "false", "recursive": "true"}
            if collection in recursive_collections
            else {"hardDelete": "false"}
        )
        self.deleted.append(path)
        if self.deletes_work:
            entity["deleted"] = True


def test_init_clears_every_ai_collection_and_preserves_non_ai_workflows_and_forms():
    native = NativeAPI()
    result = initialize.clear_ai_governance(native)
    assert result["status"] == "confirmed"
    assert result["active_ai_governance_entities"] == 0
    assert (
        result["removed_ai_governance_entities"]
        == len(initialize.AI_GOVERNANCE_COLLECTIONS) + 2
    )
    assert len(native.deleted) == result["removed_ai_governance_entities"]
    assert (
        native.entities[("/governance/workflowDefinitions", "entity-21")]["deleted"]
        is False
    )
    assert native.entities[("/governance/intakeForms", "entity-31")]["deleted"] is False


def test_inventory_must_be_complete_before_any_delete():
    native = NativeAPI()
    native.incomplete_path = "/aiApplications"
    with pytest.raises(
        initialize.InitError, match="incomplete AI Governance inventory"
    ):
        initialize.clear_ai_governance(native)
    assert native.deleted == []


def test_delete_without_tombstone_readback_fails():
    with pytest.raises(initialize.InitError, match="not retained as deleted"):
        initialize.clear_ai_governance(NativeAPI(deletes_work=False))


def test_workflow_and_intake_cleanup_is_scoped_to_ai_entity_types():
    assert initialize.is_ai_governance_workflow(
        {"trigger": {"config": {"entityTypes": ["AI_Governance_Policy", "table"]}}}
    )
    assert not initialize.is_ai_governance_workflow(
        {"trigger": {"config": {"entityTypes": ["table"]}}}
    )
    assert initialize.is_ai_governance_intake_form({"entityType": "aiApplication"})
    assert not initialize.is_ai_governance_intake_form({"entityType": "table"})


def test_native_errors_omit_credentials_endpoint_and_response_body(monkeypatch):
    secret = "invented-private-token"

    def refused(request, timeout):
        raise HTTPError(
            request.full_url, 403, "forbidden", {}, BytesIO(secret.encode())
        )

    monkeypatch.setattr(initialize, "urlopen", refused)
    call = initialize.connect(
        {
            "OPENMETADATA_URL": "http://private.example.invalid",
            "OPENMETADATA_TOKEN": secret,
        }
    )
    with pytest.raises(initialize.InitError, match="HTTP 403") as error:
        call("GET", "/system/version")
    assert secret not in str(error.value)
    assert "private.example.invalid" not in str(error.value)


def test_credentials_in_endpoint_are_rejected_without_echoing_them():
    with pytest.raises(initialize.InitError) as error:
        initialize.connect(
            {"OPENMETADATA_URL": "http://invented:private-password@example.invalid"}
        )
    assert "private-password" not in str(error.value)


def test_failed_initialization_exits_nonzero_with_a_stage(monkeypatch, capsys):
    def failed(environment):
        raise initialize.InitError("Native readback failed")

    monkeypatch.setattr(initialize, "connect", failed)
    assert initialize.main() == 1
    assert '"stage": "initialize"' in capsys.readouterr().err


def test_qualified_server_release_allows_clearout(monkeypatch, capsys):
    native = NativeAPI()

    def qualified(method, path, body=None, params=None):
        if path == "/system/version":
            assert method == "GET"
            return {"version": "2.0.7"}
        return native(method, path, body, params)

    monkeypatch.setattr(initialize, "connect", lambda environment: qualified)
    assert initialize.main() == 0
    assert '"status": "confirmed"' in capsys.readouterr().out
    assert len(native.deleted) == len(initialize.AI_GOVERNANCE_COLLECTIONS) + 2


def test_unqualified_server_release_stops_before_any_clearout(monkeypatch, capsys):
    def native(method, path):
        assert (method, path) == ("GET", "/system/version")
        return {"version": "invented-unqualified-release"}

    monkeypatch.setattr(initialize, "connect", lambda environment: native)
    assert initialize.main() == 1
    assert "Qualify the running OpenMetadata release" in capsys.readouterr().err


@pytest.mark.parametrize(
    "server_exit,clearout_exit,expected,stages",
    [
        (17, 0, 17, ["server"]),
        (0, 42, 42, ["server", "clearout"]),
    ],
)
def test_init_command_requires_server_and_clearout_success(
    tmp_path, server_exit, clearout_exit, expected, stages
):
    log = tmp_path / "stages"
    for name, stage, exit_code in [
        ("docker", "server", server_exit),
        ("uv", "clearout", clearout_exit),
    ]:
        command = tmp_path / name
        command.write_text(
            '#!/bin/sh\nprintf "%s\\n" '
            + stage
            + ' >> "$INIT_STAGE_LOG"\nexit '
            + str(exit_code)
            + "\n"
        )
        command.chmod(0o755)
    result = subprocess.run(
        ["bash", str(Path(__file__).parents[2] / "infra/openmetadata/init.sh")],
        env={
            **os.environ,
            "PATH": str(tmp_path) + ":" + os.environ["PATH"],
            "INIT_STAGE_LOG": str(log),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == expected
    assert log.read_text().splitlines() == stages
