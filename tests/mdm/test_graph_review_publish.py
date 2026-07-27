"""GH-251: persisting verify-graph's payload to the graph-review contract."""

from __future__ import annotations

import unittest

from edgar_warehouse.mdm.graph_review_publish import (
    GraphReviewPublishError,
    _native_check_detail,
    _parity_status,
    _render_publish_statements,
    publish_graph_review,
    resolve_active_generation_id,
)


class _RecordingCursor:
    def __init__(self, *, fetchone_rows=None, fail_on_substring=None):
        self.executed: list[str] = []
        self._fetchone_rows = list(fetchone_rows or [])
        self._fail_on = fail_on_substring
        self.closed = False

    def execute(self, sql: str):
        self.executed.append(sql)
        if self._fail_on and self._fail_on in sql:
            raise RuntimeError("simulated connector failure")
        return self

    def fetchone(self):
        if self._fetchone_rows:
            return self._fetchone_rows.pop(0)
        return None

    def close(self) -> None:
        self.closed = True


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _RecordingCursor:
        return self._cursor


def _sample_payload() -> dict:
    """Shape verified against SnowflakeGraphVerifier.verify()'s real output
    (edgar_warehouse/mdm/snowflake_graph.py) -- lowercase keys throughout,
    per _node_parity_payload/_relationship_parity_payload/_format_sample_rows."""
    return {
        "node_parity": {
            "status": "failed",
            "by_entity_type": [
                {
                    "entity_type": "COMPANY",
                    "mdm_active_count": 100,
                    "snowflake_graph_node_count": 98,
                    "mdm_minus_graph": 2,
                    "graph_minus_mdm": 0,
                },
                {
                    "entity_type": "PERSON",
                    "mdm_active_count": 50,
                    "snowflake_graph_node_count": 50,
                    "mdm_minus_graph": 0,
                    "graph_minus_mdm": 0,
                },
            ],
        },
        "relationship_parity": {
            "status": "ok",
            "by_relationship_type": [
                {
                    "relationship_type": "IS_INSIDER",
                    "mdm_active_count": 30,
                    "snowflake_graph_edge_count": 30,
                    "mdm_minus_graph": 0,
                    "graph_minus_mdm": 0,
                },
            ],
        },
        "diagnostics": {
            "missing_graph_nodes": [
                {"entity_type": "COMPANY", "nodeid": "company:320193"},
            ],
            "extra_graph_nodes": [],
            "missing_graph_edges": [],
            "extra_graph_edges": [],
            "missing_graph_edge_endpoints": [
                {
                    "relationship_type": "IS_INSIDER",
                    "edgeid": "edge:1",
                    "sourcenodeid": "person:1",
                    "targetnodeid": "company:320193",
                    "missing_source_node": False,
                    "missing_target_node": True,
                },
            ],
        },
        "native_app": {
            "status": "ok",
            "checks": [
                {"name": "app_installation", "status": "ok", "row_count": 1, "domain": "readiness"},
                {
                    "name": "compute_pool",
                    "status": "failed",
                    "remediation": "Provision the compute pool.",
                    "domain": "readiness",
                },
            ],
        },
    }


class PublishGraphReviewTests(unittest.TestCase):
    def test_requires_generation_id(self) -> None:
        cursor = _RecordingCursor()
        connection = _RecordingConnection(cursor)

        with self.assertRaises(GraphReviewPublishError):
            publish_graph_review(
                connection,
                database="EDGARTOOLS_DEV",
                payload=_sample_payload(),
                generation_id="",
            )
        self.assertEqual(cursor.executed, [])

    def test_deletes_then_inserts_scoped_to_one_generation(self) -> None:
        cursor = _RecordingCursor()
        connection = _RecordingConnection(cursor)

        publish_graph_review(
            connection,
            database="EDGARTOOLS_DEV",
            payload=_sample_payload(),
            generation_id="gen-2026-07-27-001",
        )

        executed = cursor.executed
        self.assertTrue(cursor.closed)

        # Every statement scopes to the one generation_id, single-quote
        # escaped the same way snowflake_graph.py's other DML does.
        for statement in executed:
            self.assertIn("'gen-2026-07-27-001'", statement)

        deletes = [s for s in executed if s.startswith("DELETE FROM")]
        self.assertEqual(len(deletes), 4)
        for table in (
            "GRAPH_REVIEW_ENTITY_PARITY",
            "GRAPH_REVIEW_RELATIONSHIP_PARITY",
            "GRAPH_REVIEW_MISMATCH_SAMPLE",
            "GRAPH_REVIEW_NATIVE_APP_CHECK",
        ):
            self.assertTrue(
                any(table in s for s in deletes), f"missing DELETE for {table}"
            )

        entity_inserts = [
            s for s in executed if "INSERT INTO" in s and "GRAPH_REVIEW_ENTITY_PARITY" in s
        ]
        self.assertEqual(len(entity_inserts), 2)  # COMPANY + PERSON
        self.assertTrue(any("'COMPANY'" in s and "'Mismatch'" in s for s in entity_inserts))
        self.assertTrue(any("'PERSON'" in s and "'OK'" in s for s in entity_inserts))

        relationship_inserts = [
            s
            for s in executed
            if "INSERT INTO" in s and "GRAPH_REVIEW_RELATIONSHIP_PARITY" in s
        ]
        self.assertEqual(len(relationship_inserts), 1)
        self.assertIn("'IS_INSIDER'", relationship_inserts[0])
        self.assertIn("'OK'", relationship_inserts[0])

        sample_inserts = [
            s for s in executed if "INSERT INTO" in s and "GRAPH_REVIEW_MISMATCH_SAMPLE" in s
        ]
        # 1 missing_graph_nodes row + 1 missing_graph_edge_endpoints row
        self.assertEqual(len(sample_inserts), 2)
        self.assertTrue(any("'missing_graph_nodes'" in s and "'company:320193'" in s for s in sample_inserts))
        self.assertTrue(
            any(
                "'missing_graph_edge_endpoints'" in s
                and "'person:1'" in s
                and "'company:320193'" in s
                for s in sample_inserts
            )
        )

        native_inserts = [
            s for s in executed if "INSERT INTO" in s and "GRAPH_REVIEW_NATIVE_APP_CHECK" in s
        ]
        self.assertEqual(len(native_inserts), 2)
        self.assertTrue(any("'app_installation'" in s and "'ok'" in s for s in native_inserts))
        self.assertTrue(
            any(
                "'compute_pool'" in s and "'failed'" in s and "Provision the compute pool." in s
                for s in native_inserts
            )
        )

    def test_empty_payload_still_deletes_but_inserts_nothing(self) -> None:
        cursor = _RecordingCursor()
        connection = _RecordingConnection(cursor)

        publish_graph_review(
            connection,
            database="EDGARTOOLS_DEV",
            payload={},
            generation_id="gen-empty",
        )

        deletes = [s for s in cursor.executed if s.startswith("DELETE FROM")]
        inserts = [s for s in cursor.executed if "INSERT INTO" in s]
        self.assertEqual(len(deletes), 4)
        self.assertEqual(inserts, [])

    def test_cursor_execute_failure_raises_graph_review_publish_error(self) -> None:
        cursor = _RecordingCursor(fail_on_substring="GRAPH_REVIEW_RELATIONSHIP_PARITY")
        connection = _RecordingConnection(cursor)

        with self.assertRaises(GraphReviewPublishError) as ctx:
            publish_graph_review(
                connection,
                database="EDGARTOOLS_DEV",
                payload=_sample_payload(),
                generation_id="gen-1",
            )
        self.assertIn("gen-1", str(ctx.exception))
        self.assertTrue(cursor.closed)

    def test_custom_review_schema_is_honored(self) -> None:
        cursor = _RecordingCursor()
        connection = _RecordingConnection(cursor)

        publish_graph_review(
            connection,
            database="EDGARTOOLS_PROD",
            payload=_sample_payload(),
            generation_id="gen-1",
            review_schema="CUSTOM_REVIEW_SCHEMA",
        )

        self.assertTrue(
            all(
                "EDGARTOOLS_PROD.CUSTOM_REVIEW_SCHEMA." in s
                for s in cursor.executed
            )
        )


class ResolveActiveGenerationIdTests(unittest.TestCase):
    def test_returns_string_value_not_coerced_to_int(self) -> None:
        """Regression: must NOT reuse snowflake_graph._fetch_scalar, which
        calls int() on its result -- correct for row/edge counts, fatal for
        a non-numeric GENERATION_ID string."""
        cursor = _RecordingCursor(fetchone_rows=[("gen-2026-07-27-001",)])
        connection = _RecordingConnection(cursor)

        result = resolve_active_generation_id(connection, database="EDGARTOOLS_DEV")

        self.assertEqual(result, "gen-2026-07-27-001")
        self.assertTrue(cursor.closed)
        self.assertIn("POINTER_ID = 'active'", cursor.executed[0])
        self.assertIn("EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER", cursor.executed[0])

    def test_returns_none_when_no_generation_has_ever_been_activated(self) -> None:
        cursor = _RecordingCursor(fetchone_rows=[])
        connection = _RecordingConnection(cursor)

        result = resolve_active_generation_id(connection, database="EDGARTOOLS_DEV")

        self.assertIsNone(result)

    def test_returns_none_when_pointer_row_has_null_generation(self) -> None:
        cursor = _RecordingCursor(fetchone_rows=[(None,)])
        connection = _RecordingConnection(cursor)

        result = resolve_active_generation_id(connection, database="EDGARTOOLS_DEV")

        self.assertIsNone(result)

    def test_honors_custom_graph_schema(self) -> None:
        cursor = _RecordingCursor(fetchone_rows=[("gen-1",)])
        connection = _RecordingConnection(cursor)

        resolve_active_generation_id(
            connection, database="EDGARTOOLS_DEV", graph_schema="CUSTOM_GRAPH_SCHEMA"
        )

        self.assertIn("EDGARTOOLS_DEV.CUSTOM_GRAPH_SCHEMA.GRAPH_ACTIVE_POINTER", cursor.executed[0])


class HelperFunctionTests(unittest.TestCase):
    def test_parity_status(self) -> None:
        self.assertEqual(_parity_status({"mdm_minus_graph": 0, "graph_minus_mdm": 0}), "OK")
        self.assertEqual(_parity_status({"mdm_minus_graph": 1, "graph_minus_mdm": 0}), "Mismatch")
        self.assertEqual(_parity_status({"mdm_minus_graph": 0, "graph_minus_mdm": 1}), "Mismatch")

    def test_native_check_detail_uses_row_count_when_present(self) -> None:
        self.assertEqual(_native_check_detail({"row_count": 3}), "3 row(s) returned.")

    def test_native_check_detail_falls_back_without_row_count(self) -> None:
        self.assertEqual(_native_check_detail({}), "Check ran before returning rows.")

    def test_render_publish_statements_handles_missing_sample_fields_as_null(self) -> None:
        payload = {
            "diagnostics": {
                "missing_graph_nodes": [{"entity_type": "COMPANY", "nodeid": "company:1"}],
                "extra_graph_nodes": [],
                "missing_graph_edges": [],
                "extra_graph_edges": [],
                "missing_graph_edge_endpoints": [],
            }
        }
        statements = _render_publish_statements(
            database="EDGARTOOLS_DEV",
            review_schema="MDM_GRAPH_REVIEW",
            payload=payload,
            generation_id="gen-1",
        )
        sample_insert = next(s for s in statements if "GRAPH_REVIEW_MISMATCH_SAMPLE" in s and "INSERT" in s)
        # entity_type/node_id present; relationship_type/edge_id/source/target absent -> NULL
        self.assertIn("'COMPANY'", sample_insert)
        self.assertIn("'company:1'", sample_insert)
        self.assertIn("NULL", sample_insert)


if __name__ == "__main__":
    unittest.main()
