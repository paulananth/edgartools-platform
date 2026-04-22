"""Manifest-related typed payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LayerManifest:
    """Warehouse layer manifest payload."""

    command: str
    layer: str
    relative_path: str
    run_id: str
    runtime_mode: str
    created_at: str
    arguments: dict[str, Any]
    scope: dict[str, Any]
