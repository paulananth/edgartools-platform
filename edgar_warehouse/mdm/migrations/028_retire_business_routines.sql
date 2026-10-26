-- Owner-only retirement after governed storage and the shared caller qualify.
-- Tables, retained bytes, uniqueness, immutable triggers, and kind guards remain.
-- Explicit dependencies only: an unknown dependency aborts the whole migration.
-- No cascading drops and no data rewrite. Historical checksums stay unchanged.
DROP VIEW IF EXISTS mdm.is_insider;
DROP VIEW IF EXISTS mdm.relationship_context;
DROP VIEW IF EXISTS mdm.entity_context;
DROP INDEX IF EXISTS mdm.source_reading_link_subjects;
DROP INDEX IF EXISTS mdm.current_record_entity_name_search;
DROP INDEX IF EXISTS mdm.company_name_search;
DROP TRIGGER IF EXISTS keep_relationship_version ON mdm.current_record;
DROP TRIGGER IF EXISTS keep_detail_versions_insert ON mdm.current_record;
DROP TRIGGER IF EXISTS keep_detail_versions_update ON mdm.current_record;

DROP FUNCTION IF EXISTS
    mdm.claim_outbox(text,text,integer),
    mdm.claim_outbox_input(text,text,integer,text),
    mdm.cross_reference_lookup(text,text),
    mdm.decisions_naming(text[]),
    mdm.detail_rows(jsonb),
    mdm.entity_name(jsonb),
    mdm.entity_search(text,text,integer),
    mdm.finish_outbox(text,text,bigint,text,text),
    mdm.finish_run(uuid,jsonb,boolean),
    mdm.force_publish(text,uuid,bigint,text,text,integer),
    mdm.keep_detail_versions(),
    mdm.keep_relationship_version(),
    mdm.keep_stage(jsonb),
    mdm.preview_batch(text,uuid),
    mdm.queue_outbox(text,jsonb),
    mdm.reading_link_subjects(jsonb),
    mdm.readings_naming(text[]),
    mdm.record_attempt(uuid,uuid,text,text,jsonb),
    mdm.record_binding(jsonb),
    mdm.record_company_version(jsonb,text,timestamp with time zone),
    mdm.record_detail_versions(text,jsonb,text),
    mdm.record_match_proposal(text,uuid),
    mdm.record_relationship_version(text,jsonb,text),
    mdm.record_stage(jsonb,text,jsonb),
    mdm.relationship_chain(text,text,integer,timestamp with time zone),
    mdm.relationship_holds(jsonb,timestamp with time zone),
    mdm.release_binding(jsonb),
    mdm.save_batch(text,uuid),
    mdm.stage_claim(jsonb,jsonb),
    mdm.stage_fold(jsonb,jsonb),
    mdm.stage_profile_key(jsonb),
    mdm.start_run(uuid,jsonb),
    mdm.supersede_match_proposal(text,uuid),
    mdm.write_batch(text,uuid);
