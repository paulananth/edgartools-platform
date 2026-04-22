"""Artifact metadata models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawArtifactRecord:
    """Warehouse raw artifact metadata."""

    source_name: str
    source_url: str
    relative_path: str
    sha256: str
    size_bytes: int
