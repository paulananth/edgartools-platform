"""Shared run-manifest writing for Ticket 13-registered acquisition commands.

``capture-filing-artifact`` (Ticket 15) and ``drive-filing-discovery-for-date``
(Ticket 16) both write the same declared-layer-manifests-plus-consolidated-
run-manifest shape from their own registration's ``resolve_scope``/
``planned_writes``. Factored here, once, so the two workflows cannot
silently drift on the next change -- the exact "a fix landed in one sibling
path but not the other" shape CLAUDE.md's incident log warns about
repeatedly (``ShardedSilverReader._TABLES``, the silver OPERATE+SELECT
grant gap, the shard-publish/monolith divergence).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from edgar_warehouse.application.acquisition_command_registry import (
    acquisition_command_registration,
)
from edgar_warehouse.infrastructure.run_manifest_builder import (
    layer_manifest,
    run_manifest,
    run_manifest_relative_path,
)


def write_declared_layer_manifests(
    *,
    command_name: str,
    context: Any,
    run_id: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    """Write the run-manifest layers this command's own registration declares.

    Mirrors ``warehouse_orchestrator._execute_warehouse_infrastructure_validation``'s
    write loop, scoped to what the command actually declares (bronze/staging/
    artifacts -- no silver/gold for these acquisition commands).
    """

    registration = acquisition_command_registration(command_name)
    assert registration is not None, f"{command_name} is not registered"
    planned = registration.planned_writes(
        command_path=command_name, run_id=run_id, scope=scope
    )
    writes: list[dict[str, Any]] = []
    for layer, relative_path in planned.items():
        target = context.bronze_root if layer == "bronze" else context.storage_root
        manifest = layer_manifest(
            command_name,
            run_id,
            layer,
            relative_path,
            arguments,
            scope,
            now,
            context.runtime_mode,
        )
        writes.append(
            {
                "layer": layer,
                "path": target.write_json(relative_path, manifest),
                "relative_path": relative_path,
            }
        )
    return writes


def write_consolidated_run_manifest(
    *,
    command_name: str,
    context: Any,
    run_id: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
    manifest_writes: list[dict[str, Any]],
    row_counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relative_path = run_manifest_relative_path(command_name, run_id)
    payload = run_manifest(
        command_name=command_name,
        run_id=run_id,
        command_path=command_name,
        arguments=arguments,
        scope=scope,
        now=now,
        runtime_mode=context.runtime_mode,
        environment_name=context.environment_name,
        manifest_writes=manifest_writes,
        row_counts=row_counts or {},
    )
    return {
        "layer": "run_manifest",
        "path": context.bronze_root.write_json(relative_path, payload),
        "relative_path": relative_path,
    }
