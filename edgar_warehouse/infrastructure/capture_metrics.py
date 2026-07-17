"""Aggregate network vs silver-skip counters for capture runs (ticket 02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaptureNetworkMetrics:
    """Comparable counts for real SEC/edgartools network work vs silver skips."""

    network_fetches: int = 0
    silver_skips: int = 0
    accessions_with_network: int = 0
    accessions_silver_skip: int = 0

    def record_artifact_result(self, artifact_result: dict[str, Any] | None) -> None:
        """Accumulate one accession's artifact fetch result."""
        if not artifact_result:
            return
        fetches = int(artifact_result.get("network_fetches", 0) or 0)
        self.network_fetches += max(0, fetches)
        if fetches > 0:
            self.accessions_with_network += 1
        else:
            # Cache hit / already-captured path: no SEC round-trip
            self.silver_skips += 1
            self.accessions_silver_skip += 1

    def as_dict(self) -> dict[str, int]:
        return {
            "network_fetches": self.network_fetches,
            "silver_skips": self.silver_skips,
            "accessions_with_network": self.accessions_with_network,
            "accessions_silver_skip": self.accessions_silver_skip,
        }

    def merge_into(self, metrics: dict[str, Any]) -> None:
        """Fold into an orchestrator metrics dict (additive)."""
        for key, value in self.as_dict().items():
            metrics[key] = int(metrics.get(key, 0) or 0) + value
