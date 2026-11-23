"""Where silver rows land: one small interface, so a warehouse sink can follow the
PostgreSQL one (plan decision 36) without the writer changing."""

from __future__ import annotations

from typing import Iterable, Protocol


class Sink(Protocol):
    def spec(self, table: str) -> dict:
        """The registered spec of a table; a table with no registered spec is refused."""

    def write(self, spec: dict, rows: Iterable[dict]) -> dict:
        """Write one delivery of rows (the spec's columns) as the
        spec's load mode says, all or nothing, and count what changed."""


# Compatibility import for existing callers. All selected destinations use the
# same implementation; the name is retained until callers have migrated.
from .relational import DatabaseSink
PostgresSink = DatabaseSink
