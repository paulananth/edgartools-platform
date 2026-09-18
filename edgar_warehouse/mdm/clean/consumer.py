"""Version-2 read contract, including aliases and selected-field provenance."""

from __future__ import annotations

from sqlalchemy import text

from .store import Conflict


class ContractReader:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _object(conn, kind, key, generation):
        if generation is None:
            return conn.scalar(
                text(
                    "SELECT body FROM mdm_v2.projection WHERE object_type=:t AND object_id=:id"
                ),
                {"t": kind, "id": key},
            )
        return conn.scalar(
            text("""SELECT item->'body' FROM mdm_v2.batch b,
          jsonb_array_elements(b.effects->'projections') item
          WHERE b.generation<=:g AND item->>'object_type'=:t AND item->>'object_id'=:id
          ORDER BY b.generation DESC LIMIT 1"""),
            {"g": generation, "t": kind, "id": key},
        )

    def entity(self, requested_id: str, *, generation: int | None = None) -> dict:
        with self.engine.connect() as conn:
            if generation is None:
                generation = conn.scalar(
                    text("SELECT coalesce(max(generation),0) FROM mdm_v2.batch")
                )
            if generation < 1:
                raise KeyError(requested_id)
            key = requested_id
            seen = set()
            while True:
                if key in seen:
                    raise Conflict("Alias cycle")
                seen.add(key)
                body = self._object(conn, "entity", key, generation)
                if body is None:
                    raise KeyError(key)
                if body["canonical_id"] == key:
                    break
                key = body["canonical_id"]
            provenance = {}
            for name, field in body.get("fields", {}).items():
                assertion_id = field["winner"]["assertion_id"]
                source = conn.execute(
                    text("""SELECT a.body,b.run_id::text FROM mdm_v2.assertion a
                  JOIN mdm_v2.batch b USING(batch_id) WHERE a.assertion_id=:id
                  UNION ALL SELECT d.body,b.run_id::text FROM mdm_v2.decision d
                  JOIN mdm_v2.batch b USING(batch_id) WHERE d.decision_id=:id"""),
                    {"id": assertion_id},
                ).first()
                if source is None:
                    raise Conflict("Selected field has missing provenance")
                provenance[name] = {
                    "evidence": source[0],
                    "origin_run_id": source[1],
                    "policy_digest": field["policy_digest"],
                }
            return {
                "contract_version": 2,
                "generation": generation,
                "requested_id": requested_id,
                "canonical_id": key,
                "identity": body,
                "field_provenance": provenance,
            }

    def page(
        self, object_type: str, *, after: str = "", limit: int = 100
    ) -> list[dict]:
        if (
            object_type not in {"entity", "relationship", "review"}
            or not 1 <= limit <= 1000
        ):
            raise ValueError("Invalid bounded consumer page")
        with self.engine.connect() as conn:
            return list(
                conn.scalars(
                    text("""SELECT body FROM mdm_v2.projection
              WHERE object_type=:t AND object_id>:after ORDER BY object_id LIMIT :lim"""),
                    {"t": object_type, "after": after, "lim": limit},
                )
            )
