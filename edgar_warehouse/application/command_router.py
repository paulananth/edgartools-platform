"""Command routing facade for the warehouse CLI surface."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.commands import COMMAND_REGISTRY
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def run_command(command_name: str, args: Any) -> int:
    try:
        handler = COMMAND_REGISTRY[command_name]
    except KeyError as exc:
        raise WarehouseRuntimeError(f"Unsupported warehouse command: {command_name}") from exc
    return handler(args)


def run_seed_universe_command(args: Any) -> int:
    return COMMAND_REGISTRY["seed-universe"](args)


_build_warehouse_context = warehouse_orchestrator._build_warehouse_context
_error_payload = warehouse_orchestrator._error_payload
_namespace_to_payload = warehouse_orchestrator._namespace_to_payload

__all__ = [
    "StorageLocation",
    "WarehouseCommandContext",
    "WarehouseRuntimeError",
    "_build_warehouse_context",
    "_error_payload",
    "_namespace_to_payload",
    "run_command",
    "run_seed_universe_command",
]
