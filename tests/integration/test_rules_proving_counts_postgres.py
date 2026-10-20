"""`proving.counts` hashes every current record row by row (ticket 120): the same md5 as one
string of them all, which the store's memory limit killed at 383,612 Securities."""
from sqlalchemy import text

from edgar_warehouse.rules import proving

ONE_STRING = text(
    "SELECT md5(coalesce((SELECT string_agg(object_type || ':' || object_id || ':' || body::text, "
    "',' ORDER BY object_type, object_id) FROM mdm.current_record), '') || '|' || "
    "coalesce((SELECT string_agg(c::text, ',' ORDER BY c.entity_id) FROM mdm.company c "
    "WHERE c.to_generation IS NULL), ''))")


def test_the_streamed_hash_is_the_one_string_hash(database):
    with database.admin.connect() as conn:
        empty = conn.scalar(ONE_STRING)
    assert proving.counts(database.admin)["current_records_md5"] == empty

    with database.admin.begin() as conn:
        # Rows only to hash: no batch behind them, so the foreign keys are not checked.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        for object_type, object_id, body in [("review", "r-1", '{"open": true}'),
                                             ("entity", "e-2", '{"name": "Société B"}'),
                                             ("entity", "e-1", '{"name": "A", "identifiers": {"cusip": ["X"]}}')]:
            conn.execute(text("INSERT INTO mdm.current_record (object_type, object_id, body, batch_id) "
                              "VALUES (:t, :i, CAST(:b AS jsonb), 'batch-1')"), {"t": object_type, "i": object_id, "b": body})
    with database.admin.connect() as conn:
        expected = conn.scalar(ONE_STRING)

    assert expected != empty
    assert proving.counts(database.admin)["current_records_md5"] == expected
