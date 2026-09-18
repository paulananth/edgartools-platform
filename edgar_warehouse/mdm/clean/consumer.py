"""Version-2 read contract, including aliases and selected-field provenance."""

from __future__ import annotations

from sqlalchemy import text

from .store import Conflict, digest


class ContractReader:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _generation(conn, generation):
        latest = conn.scalar(
            text("SELECT coalesce(max(generation),0) FROM mdm_v2.batch")
        )
        if generation is None:
            return latest
        if type(generation) is not int or generation < 1 or generation > latest:
            raise KeyError("Unknown generation")
        return generation

    @staticmethod
    def _provenance(conn, fields):
        result = {}
        for name, field in fields.items():
            source = conn.execute(
                text("""SELECT a.body,b.run_id::text FROM mdm_v2.assertion a
                JOIN mdm_v2.batch b USING(batch_id) WHERE a.assertion_id=:id
                UNION ALL SELECT d.body,b.run_id::text FROM mdm_v2.decision d
                JOIN mdm_v2.batch b USING(batch_id) WHERE d.decision_id=:id"""),
                {"id": field["winner"]["assertion_id"]},
            ).first()
            if source is None:
                raise Conflict("Selected field has missing provenance")
            result[name] = {
                "evidence": source[0],
                "origin_run_id": source[1],
                "policy_digest": field["policy_digest"],
            }
        return result

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
            generation = self._generation(conn, generation)
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
            projection = dict(
                conn.execute(
                    text("""SELECT b.generation,b.run_id::text AS origin_run_id,
                b.policy_digest,b.effects->>'as_of' AS as_of FROM mdm_v2.batch b,
                jsonb_array_elements(b.effects->'projections') item
                WHERE b.generation<=:g AND item->>'object_type'='entity' AND item->>'object_id'=:id
                ORDER BY b.generation DESC LIMIT 1"""),
                    {"g": generation, "id": key},
                )
                .mappings()
                .one()
            )
            return {
                "contract_version": 2,
                "generation": generation,
                "requested_id": requested_id,
                "canonical_id": key,
                "identity": body,
                "projection": projection,
                "business_hash": digest(body),
                "field_provenance": self._provenance(conn, body.get("fields", {})),
                "profile_field_provenance": {
                    p["profile_id"]: self._provenance(conn, p.get("fields", {}))
                    for p in body.get("profiles", [])
                },
            }

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
        with self.engine.connect() as conn:
            generation = self._generation(conn, generation)
            items = [
                dict(row)
                for row in conn.execute(
                    text("""WITH versions AS (
                SELECT DISTINCT ON (item->>'object_id') item->>'object_id' AS object_id,
                  item->'body' AS body,b.generation AS projection_generation,
                  b.effects->>'as_of' AS projection_as_of,b.policy_digest,
                  b.run_id::text AS origin_run_id FROM mdm_v2.batch b,
                  jsonb_array_elements(b.effects->'projections') item
                WHERE b.generation<=:g AND item->>'object_type'=:t AND item->>'object_id'>:after
                ORDER BY item->>'object_id',b.generation DESC
                ) SELECT * FROM versions ORDER BY object_id LIMIT :lim"""),
                    {
                        "g": generation,
                        "t": object_type,
                        "after": after,
                        "lim": limit + 1,
                    },
                ).mappings()
            ]
            more = len(items) > limit
            items = items[:limit]
            return {
                "contract_version": 2,
                "generation": generation,
                "object_type": object_type,
                "items": items,
                "next_after": items[-1]["object_id"] if more else None,
                "business_hash": digest(
                    [{k: row[k] for k in ("object_id", "body")} for row in items]
                ),
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
