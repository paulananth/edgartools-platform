"""Facade that preserves the public runtime contract while delegating to command modules."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.commands import COMMAND_REGISTRY
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application import runtime_legacy
from edgar_warehouse.domain.models.run_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.storage import StorageLocation


def run_command(command_name: str, args: Any) -> int:
    try:
        handler = COMMAND_REGISTRY[command_name]
    except KeyError as exc:
        raise WarehouseRuntimeError(f"Unsupported warehouse command: {command_name}") from exc
    return handler(args)


def run_seed_universe_command(args: Any) -> int:
    return COMMAND_REGISTRY["seed-universe"](args)


WarehouseRuntimeError = WarehouseRuntimeError
StorageLocation = StorageLocation
WarehouseCommandContext = WarehouseCommandContext

# Backward-compatible re-exports for callers that relied on runtime helpers.
_build_warehouse_context = runtime_legacy._build_warehouse_context
_error_payload = runtime_legacy._error_payload
_namespace_to_payload = runtime_legacy._namespace_to_payload
