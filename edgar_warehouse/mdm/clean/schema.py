"""Owner installation of configured vocabulary and generic per-kind views."""
from sqlalchemy import text

from . import catalog


VIEWS = {
    "stage": """SELECT assertion_id,source_code,record_key,publication_key,
        revision,mapping_version,effective_at,batch_id,body->>'subject' AS subject,
        body->>'schema_version' AS schema_version,body
        FROM mdm.source_reading WHERE body->>'kind'=:kind""",
    "stage_field": """SELECT a.assertion_id,a.source_code,a.record_key,a.publication_key,
        a.revision,a.mapping_version,a.effective_at,a.batch_id,a.body->>'subject' AS subject,
        f.key AS field_name,f.value->>'op' AS operation,f.value->>'value' AS field_value
        FROM mdm.source_reading a
        CROSS JOIN LATERAL jsonb_each(coalesce(a.body->'fields','{}'::jsonb)) f(key,value)
        WHERE a.body->>'kind'=:kind""",
    "master": """SELECT object_id AS entity_id,batch_id,body->>'status' AS status,
        body->>'canonical_id' AS canonical_id,body FROM mdm.current_record
        WHERE object_type='entity' AND body->>'kind'=:kind""",
    "master_field": """SELECT p.object_id AS entity_id,p.batch_id,p.body->>'status' AS status,
        f.key AS field_name,f.value->>'value' AS field_value,
        (f.value->>'cleared')::boolean AS cleared,
        f.value->'winner'->>'source_code' AS source_code,
        f.value->'winner'->>'record_key' AS record_key,
        (f.value->'winner'->>'effective_at')::timestamptz AS effective_at,
        f.value->>'policy_digest' AS policy_digest,f.value->>'kind_version' AS kind_version,
        jsonb_array_length(coalesce(f.value->'conflicts','[]'::jsonb)) AS conflict_count
        FROM mdm.current_record p
        CROSS JOIN LATERAL jsonb_each(coalesce(p.body->'fields','{}'::jsonb)) f(key,value)
        WHERE p.object_type='entity' AND p.body->>'kind'=:kind""",
}


def configure_kinds(conn):
    """Under the migration lock, install additions and disable removed kinds.

    The vocabulary stays small. Historical identities and existing views stay
    readable; a removed kind cannot acquire a new identity through save_batch.
    Runtime has no catalog writes or schema creation rights.
    """
    catalog.assert_current()
    conn.execute(text("SELECT pg_advisory_xact_lock(730234)"))
    known = set(conn.scalars(text("SELECT kind FROM mdm.master_kind")))
    configured = set(catalog.CATALOG["kinds"])
    quote = conn.dialect.identifier_preparer.quote_identifier
    maximum = conn.dialect.max_identifier_length
    for kind in sorted(configured - known):
        for shape, query in VIEWS.items():
            name = kind + "_" + shape
            if len(name.encode("utf-8")) > maximum:
                raise ValueError("Configured kind view exceeds the database identifier limit")
            target = "mdm." + quote(name)
            if conn.scalar(text("SELECT to_regclass(:name)"), {"name": target}) is not None:
                raise ValueError("Configured kind view collides with an existing relation")
            conn.execute(text("CREATE VIEW " + target + " AS " + query), {"kind": kind})
    conn.execute(text("UPDATE mdm.master_kind SET enabled=false WHERE enabled"))
    conn.execute(text("""INSERT INTO mdm.master_kind(kind,enabled) VALUES(:kind,true)
        ON CONFLICT(kind) DO UPDATE SET enabled=true"""), [{"kind": kind} for kind in sorted(configured)])
