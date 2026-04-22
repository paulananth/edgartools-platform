"""Compatibility shim for the warehouse runtime public surface."""

from __future__ import annotations

from edgar_warehouse.application.command_router import (
    StorageLocation,
    WarehouseCommandContext,
    WarehouseRuntimeError,
    _build_warehouse_context,
    _error_payload,
    _namespace_to_payload,
    run_command,
    run_seed_universe_command,
)

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
