"""Version-2 read contract, including aliases and selected-field provenance."""

from __future__ import annotations

from contextlib import nullcontext


class ContractReader:
    def __init__(self, engine):
        self.engine = engine

    def entity(
        self, requested_id: str, *, generation: int | None = None, connection=None
    ) -> dict:
        with (
            self.engine.connect().execution_options(isolation_level="REPEATABLE READ")
            if connection is None
            else nullcontext(connection)
        ) as conn:
            from .prepared_registry import require_installed as installed

            adapter = installed(conn)
            from .master_reads import entity

            return entity(adapter, conn, requested_id, generation)

    def snapshot_page(
        self,
        object_type: str,
        *,
        generation: int | None = None,
        after: str = "",
        limit: int = 100,
    ) -> dict:
        """Pin pagination to a committed generation, including retirement markers."""
        if (
            object_type not in {"entity", "relationship", "review"}
            or not 1 <= limit <= 1000
        ):
            raise ValueError("Invalid bounded consumer page")
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            from .prepared_registry import require_installed as installed

            adapter = installed(conn)
            from .master_reads import snapshot_page

            return snapshot_page(adapter, conn, object_type, generation, after, limit)

    def page(
        self, object_type: str, *, after: str = "", limit: int = 100
    ) -> list[dict]:
        if (
            object_type not in {"entity", "relationship", "review"}
            or not 1 <= limit <= 1000
        ):
            raise ValueError("Invalid bounded consumer page")
        return [
            item["body"]
            for item in self.snapshot_page(object_type, after=after, limit=limit)["items"]
        ]
