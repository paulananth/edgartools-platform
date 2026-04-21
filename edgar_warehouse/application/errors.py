"""Shared application exceptions."""

from __future__ import annotations


class WarehouseRuntimeError(RuntimeError):
    """Raised when a warehouse command cannot run in the current environment."""
