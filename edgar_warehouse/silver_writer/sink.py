"""Where silver rows land: one small interface, so a warehouse sink can follow the
PostgreSQL one (plan decision 36) without the writer changing."""

from __future__ import annotations

from typing import Iterable, Protocol


class Sink(Protocol):
    def spec(self, table: str) -> dict:
        """The registered spec of a table; a table with no registered spec is refused."""

    def write(self, spec: dict, rows: Iterable[dict]) -> dict:
        """Write one delivery of rows (the spec's columns and each link's MDM id) as the
        spec's load mode says, all or nothing, and count what changed."""

    def link_keys(self, spec: dict, link: dict) -> set[str]:
        """Every source key value a link's column holds in the table, as text."""

    def set_ids(self, spec: dict, link: dict, found: dict[str, str | None]) -> int:
        """Set a link's MDM id on every row from `found` (source key to id, or empty); count rows changed."""


# Compatibility import for existing callers. All selected destinations use the
# same implementation; the name is retained until callers have migrated.
from .relational import DatabaseSink
PostgresSink = DatabaseSink
