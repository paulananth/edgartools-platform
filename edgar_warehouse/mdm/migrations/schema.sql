-- MDM's own schema: the tables, views, indexes and guards of the `mdm` schema, with its kinds.
-- `mdm migrate` creates it in an empty database, then installs governed storage, the registration
-- function (registration_authority.sql) and the mastering tables. A later change is a numbered file
-- beside this one, named in MIGRATIONS (store.py).
SET LOCAL check_function_bodies = false;


CREATE SCHEMA mdm;

COMMENT ON SCHEMA mdm IS 'Master Data Management: the master record of each Company, Person and other kind, the source readings it is built from, and every decision that joined them. The application login reads it and writes only through its functions (save_batch and the others it is granted).';

CREATE FUNCTION mdm.immutable_row() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'MDM rows of this table are never changed (append-only)'; END;
$$;

COMMENT ON FUNCTION mdm.immutable_row() IS 'Trigger function: refuses any change or delete of a row in a table that is never changed.';

CREATE FUNCTION mdm.require_configured_kind() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
BEGIN
    PERFORM 1 FROM mdm.master_kind WHERE kind=NEW.kind AND enabled FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Master kind is not enabled in the installed configuration';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION mdm.require_configured_kind() IS 'Destination guard for new or changed identity kinds. Locks the configured vocabulary row and refuses a kind that is not enabled.';

CREATE TABLE mdm.attempt_event (
    attempt_id uuid NOT NULL,
    event text NOT NULL,
    run_id uuid NOT NULL,
    batch_id text NOT NULL,
    detail jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT attempt_event_detail_check CHECK ((jsonb_typeof(detail) = 'object'::text)),
    CONSTRAINT attempt_event_event_check CHECK ((event = ANY (ARRAY['started'::text, 'finished'::text, 'error'::text])))
);

COMMENT ON TABLE mdm.attempt_event IS 'Each try at saving a batch: started, finished or error, for recovery after a crash. Never changed. Written by record_attempt; read by the run coordinator.';

COMMENT ON COLUMN mdm.attempt_event.attempt_id IS 'The try''s id.';

COMMENT ON COLUMN mdm.attempt_event.event IS 'started, finished or error.';

COMMENT ON COLUMN mdm.attempt_event.run_id IS 'The Merge Stage run (run.run_id).';

COMMENT ON COLUMN mdm.attempt_event.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.attempt_event.detail IS 'What happened, e.g. the error.';

COMMENT ON COLUMN mdm.attempt_event.occurred_at IS 'When it happened.';

CREATE TABLE mdm.batch (
    batch_id text NOT NULL,
    request_hash text NOT NULL,
    run_id uuid NOT NULL,
    policy_digest text NOT NULL,
    generation bigint NOT NULL,
    consumer text NOT NULL,
    checkpoint bigint NOT NULL,
    effects jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

COMMENT ON TABLE mdm.batch IS 'Each saved batch of Merge Stage work: its request hash, run, policy and generation. A batch is saved whole or not at all, and saving the same batch again changes nothing. Never changed. Written by save_batch; read by duplicate checks, checkpoints and the outbox.';

COMMENT ON COLUMN mdm.batch.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.batch.request_hash IS 'The sha256 of the batch request; the same batch id with other content is refused.';

COMMENT ON COLUMN mdm.batch.run_id IS 'The Merge Stage run (run.run_id).';

COMMENT ON COLUMN mdm.batch.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.batch.generation IS 'The batch''s place in the order of all saved batches: 1, 2, 3, ...';

COMMENT ON COLUMN mdm.batch.consumer IS 'The reader the work is for, e.g. journal.';

COMMENT ON COLUMN mdm.batch.checkpoint IS 'The reader''s position this batch advanced to.';

COMMENT ON COLUMN mdm.batch.effects IS 'The whole batch request: readings, entities, decisions and current records.';

COMMENT ON COLUMN mdm.batch.created_at IS 'When the batch was saved.';

CREATE TABLE mdm.batch_change (
    batch_id text NOT NULL,
    "position" bigint NOT NULL,
    change text NOT NULL,
    CONSTRAINT batch_change_change_check CHECK ((change = ANY (ARRAY['insert'::text, 'update'::text, 'snapshot'::text]))),
    CONSTRAINT batch_change_position_check CHECK (("position" >= 1))
);

COMMENT ON TABLE mdm.batch_change IS 'Which projected records of a batch were inserted or changed (or, for a forced batch, sent as the snapshot); position is the record''s place in batch.effects->projections, from 1. Read by outbox_delivery for change data capture.';

COMMENT ON COLUMN mdm.batch_change.batch_id IS 'The batch (batch.batch_id).';

COMMENT ON COLUMN mdm.batch_change."position" IS 'Position of the record in the batch''s projections, from 1.';

COMMENT ON COLUMN mdm.batch_change.change IS 'insert (not current before), update (current before, now different) or snapshot (a forced page).';

CREATE TABLE mdm.current_record (
    object_type text NOT NULL,
    object_id text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL,
    CONSTRAINT current_record_object_type_check CHECK ((object_type = ANY (ARRAY['entity'::text, 'relationship'::text, 'review'::text])))
);

COMMENT ON TABLE mdm.current_record IS 'The current record of every master entity other than a Company, and of every relationship and review item, one row each, replaced as batches are saved. Written by save_batch; read by current_entity, stage_waiting and the per-kind _master views.';

COMMENT ON COLUMN mdm.current_record.object_type IS 'What the record is: entity, relationship or review.';

COMMENT ON COLUMN mdm.current_record.object_id IS 'The record''s id: an entity id, a relationship id or a review id.';

COMMENT ON COLUMN mdm.current_record.body IS 'The whole current record.';

COMMENT ON COLUMN mdm.current_record.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

CREATE VIEW mdm.branch_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'branch'::text));

COMMENT ON VIEW mdm.branch_master IS 'Each current master record of kind branch: a filter of current_record.';

COMMENT ON COLUMN mdm.branch_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.branch_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.branch_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.branch_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.branch_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.branch_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'branch'::text));

COMMENT ON VIEW mdm.branch_master_field IS 'Each current master record of kind branch, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.branch_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.branch_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.branch_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.branch_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.branch_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.branch_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.branch_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.branch_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.branch_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.branch_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.branch_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.branch_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE TABLE mdm.source_reading (
    assertion_id text NOT NULL,
    source_code text NOT NULL,
    record_key text NOT NULL,
    publication_key text NOT NULL,
    revision bigint NOT NULL,
    effective_at timestamp with time zone,
    body jsonb NOT NULL,
    batch_id text NOT NULL,
    mapping_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT source_reading_mapping_version_check CHECK ((mapping_version >= 1)),
    CONSTRAINT source_reading_revision_check CHECK ((revision >= 0))
);

COMMENT ON TABLE mdm.source_reading IS 'Every version of every source record as MDM read it: one row per reading, never changed. A new mapping version of the same record is a new reading. Written by save_batch; read by the Merge Stage, the Stage and the per-kind _stage views.';

COMMENT ON COLUMN mdm.source_reading.assertion_id IS 'The reading''s id, a hash of the reading.';

COMMENT ON COLUMN mdm.source_reading.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.source_reading.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.source_reading.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.source_reading.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.source_reading.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.source_reading.body IS 'The whole reading: kind, subject, identifiers, fields, relationships and provenance.';

COMMENT ON COLUMN mdm.source_reading.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.source_reading.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

CREATE VIEW mdm.branch_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'branch'::text);

COMMENT ON VIEW mdm.branch_stage IS 'Each source reading of kind branch, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.branch_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.branch_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.branch_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.branch_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.branch_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.branch_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.branch_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.branch_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.branch_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.branch_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.branch_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.branch_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'branch'::text);

COMMENT ON VIEW mdm.branch_stage_field IS 'Each source reading of kind branch, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.branch_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.branch_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.branch_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.branch_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.branch_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.branch_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.branch_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.branch_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.branch_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.branch_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.branch_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.branch_stage_field.field_value IS 'The field''s value, as text.';

CREATE TABLE mdm.checkpoint (
    consumer text NOT NULL,
    "position" bigint NOT NULL,
    batch_id text NOT NULL,
    source_family text DEFAULT ''::text NOT NULL,
    publication_family text DEFAULT ''::text NOT NULL,
    committed_publication text,
    continuity_proof jsonb,
    CONSTRAINT checkpoint_scope CHECK ((((source_family = ''::text) AND (publication_family = ''::text) AND (committed_publication IS NULL) AND (continuity_proof IS NULL)) OR ((btrim(source_family) <> ''::text) AND (btrim(publication_family) <> ''::text) AND (NULLIF(btrim(committed_publication), ''::text) IS NOT NULL) AND (continuity_proof IS NOT NULL) AND (jsonb_typeof(continuity_proof) = 'object'::text) AND (continuity_proof <> '{}'::jsonb))))
);

COMMENT ON TABLE mdm.checkpoint IS 'How far each reader (consumer) has read each source, so the next batch must continue from there. Written by save_batch; read by the next batch''s check.';

COMMENT ON COLUMN mdm.checkpoint.consumer IS 'The reader the work is for, e.g. journal.';

COMMENT ON COLUMN mdm.checkpoint."position" IS 'The last position saved.';

COMMENT ON COLUMN mdm.checkpoint.batch_id IS 'The batch that saved this position.';

COMMENT ON COLUMN mdm.checkpoint.source_family IS 'The source family read, e.g. gleif; empty for a reader of no family.';

COMMENT ON COLUMN mdm.checkpoint.publication_family IS 'The publication family within it, e.g. golden_copy; empty for a reader of no family.';

COMMENT ON COLUMN mdm.checkpoint.committed_publication IS 'The last source publication fully read, for a reader of a publication family.';

COMMENT ON COLUMN mdm.checkpoint.continuity_proof IS 'Evidence that the publications read so far follow one another with no gap.';

CREATE TABLE mdm.company (
    entity_id uuid NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL,
    status text NOT NULL,
    quarantined boolean DEFAULT false NOT NULL,
    cik text,
    lei text,
    identifiers jsonb NOT NULL,
    name text,
    sic text,
    state_of_incorporation text,
    fiscal_year_end text,
    description text,
    jurisdiction text,
    address jsonb,
    gleif_legal_form text,
    gleif_entity_status text,
    gleif_registration_status text,
    gleif_initial_registration text,
    gleif_managing_lou text,
    gleif_validation_source text,
    gleif_registration_authority text,
    gleif_registration_authority_entity_id text,
    gleif_entity_creation_date text,
    body jsonb NOT NULL,
    CONSTRAINT company_generation_period CHECK (((to_generation IS NULL) OR (from_generation < to_generation))),
    CONSTRAINT company_open_version_has_no_end CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT company_status_check CHECK ((status = ANY (ARRAY['accepted'::text, 'review'::text]))),
    CONSTRAINT company_valid_period CHECK (((valid_to IS NULL) OR (valid_from < valid_to)))
);

COMMENT ON TABLE mdm.company IS 'Each Company, versioned: one row per version, the current one with valid_to empty. The only place a Company is kept. Written by record_company_version inside save_batch; read by current_entity and the company_* views.';

COMMENT ON COLUMN mdm.company.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.company.from_generation IS 'The batch generation that made this version current.';

COMMENT ON COLUMN mdm.company.to_generation IS 'The batch generation that replaced this version; empty while it is current.';

COMMENT ON COLUMN mdm.company.valid_from IS 'When MDM recorded this version (not when the source says it took effect).';

COMMENT ON COLUMN mdm.company.valid_to IS 'When MDM replaced this version; empty while it is current.';

COMMENT ON COLUMN mdm.company.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.company.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.company.quarantined IS 'True when the Company is held back from readers until a person reviews it.';

COMMENT ON COLUMN mdm.company.cik IS 'SEC Central Index Key, when the Company has one.';

COMMENT ON COLUMN mdm.company.lei IS 'Legal Entity Identifier from GLEIF, when the Company has one.';

COMMENT ON COLUMN mdm.company.identifiers IS 'Every identifier the Company holds (cik, lei, ein and others), as an object.';

COMMENT ON COLUMN mdm.company.name IS 'The Company''s legal name, as the Mastering Policy chose it.';

COMMENT ON COLUMN mdm.company.sic IS 'SEC Standard Industrial Classification code.';

COMMENT ON COLUMN mdm.company.state_of_incorporation IS 'Where the Company is incorporated, as SEC reports it.';

COMMENT ON COLUMN mdm.company.fiscal_year_end IS 'The Company''s fiscal year end, MMDD, as SEC reports it.';

COMMENT ON COLUMN mdm.company.description IS 'The Company''s business description.';

COMMENT ON COLUMN mdm.company.jurisdiction IS 'The legal jurisdiction, as GLEIF reports it.';

COMMENT ON COLUMN mdm.company.address IS 'The Company''s address, as an object (lines, city, region, postcode, country).';

COMMENT ON COLUMN mdm.company.gleif_legal_form IS 'GLEIF legal form code (ISO 20275).';

COMMENT ON COLUMN mdm.company.gleif_entity_status IS 'GLEIF entity status, e.g. ACTIVE or INACTIVE.';

COMMENT ON COLUMN mdm.company.gleif_registration_status IS 'GLEIF registration status of the LEI, e.g. ISSUED or LAPSED.';

COMMENT ON COLUMN mdm.company.gleif_initial_registration IS 'When the LEI was first registered.';

COMMENT ON COLUMN mdm.company.gleif_managing_lou IS 'The LEI of the Local Operating Unit that manages this LEI.';

COMMENT ON COLUMN mdm.company.gleif_validation_source IS 'How GLEIF validated the record, e.g. FULLY_CORROBORATED.';

COMMENT ON COLUMN mdm.company.gleif_registration_authority IS 'The registration authority (business register) GLEIF names.';

COMMENT ON COLUMN mdm.company.gleif_registration_authority_entity_id IS 'The Company''s id in that registration authority.';

COMMENT ON COLUMN mdm.company.gleif_entity_creation_date IS 'When the legal entity was created, as GLEIF reports it.';

COMMENT ON COLUMN mdm.company.body IS 'The whole master record as the Merge Stage built it.';

CREATE TABLE mdm.company_alias (
    alias_id uuid NOT NULL,
    canonical_id uuid NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL,
    CONSTRAINT company_alias_generation_period CHECK (((to_generation IS NULL) OR (from_generation < to_generation))),
    CONSTRAINT company_alias_not_itself CHECK ((alias_id <> canonical_id)),
    CONSTRAINT company_alias_open_version_has_no_end CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT company_alias_valid_period CHECK (((valid_to IS NULL) OR (valid_from < valid_to)))
);

COMMENT ON TABLE mdm.company_alias IS 'Company ids that now point to another Company after a merge, versioned like company. Lets a reader follow an old id to its survivor. Written by record_company_version; read by current_entity.';

COMMENT ON COLUMN mdm.company_alias.alias_id IS 'The merged-away Company id.';

COMMENT ON COLUMN mdm.company_alias.canonical_id IS 'The surviving Company it now points to.';

COMMENT ON COLUMN mdm.company_alias.from_generation IS 'The batch generation that made this alias current.';

COMMENT ON COLUMN mdm.company_alias.to_generation IS 'The batch generation that ended this alias; empty while it is current.';

COMMENT ON COLUMN mdm.company_alias.valid_from IS 'When MDM recorded this alias.';

COMMENT ON COLUMN mdm.company_alias.valid_to IS 'When MDM ended this alias; empty while it is current.';

COMMENT ON COLUMN mdm.company_alias.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

CREATE VIEW mdm.company_master_field AS
 SELECT c.entity_id,
    c.batch_id,
    c.status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.company c
     CROSS JOIN LATERAL jsonb_each((c.body -> 'fields'::text)) f(key, value))
  WHERE (c.valid_to IS NULL);

COMMENT ON VIEW mdm.company_master_field IS 'Each current Company, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.company_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.company_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.company_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.company_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.company_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.company_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.company_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.company_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.company_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.company_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.company_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.company_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.company_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'company'::text);

COMMENT ON VIEW mdm.company_stage IS 'Each source reading of kind company, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.company_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.company_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.company_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.company_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.company_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.company_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.company_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.company_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.company_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.company_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.company_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.company_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'company'::text);

COMMENT ON VIEW mdm.company_stage_field IS 'Each source reading of kind company, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.company_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.company_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.company_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.company_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.company_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.company_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.company_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.company_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.company_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.company_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.company_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.company_stage_field.field_value IS 'The field''s value, as text.';

CREATE VIEW mdm.current_entity AS
 SELECT p.object_id,
    (p.body ->> 'kind'::text) AS kind,
    (p.body ->> 'status'::text) AS status,
    (p.body ->> 'canonical_id'::text) AS canonical_id,
    p.body
   FROM mdm.current_record p
  WHERE (p.object_type = 'entity'::text)
UNION ALL
 SELECT (c.entity_id)::text AS object_id,
    'company'::text AS kind,
    c.status,
    (c.body ->> 'canonical_id'::text) AS canonical_id,
    c.body
   FROM mdm.company c
  WHERE (c.valid_to IS NULL)
UNION ALL
 SELECT (a.alias_id)::text AS object_id,
    'company'::text AS kind,
    'alias'::text AS status,
    (a.canonical_id)::text AS canonical_id,
    jsonb_build_object('entity_id', (a.alias_id)::text, 'kind', 'company', 'canonical_id', (a.canonical_id)::text, 'status', 'alias') AS body
   FROM mdm.company_alias a
  WHERE (a.valid_to IS NULL);

COMMENT ON VIEW mdm.current_entity IS 'The one read of every current master entity of every kind: Companies from company (and their aliases), the rest from current_record.';

COMMENT ON COLUMN mdm.current_entity.object_id IS 'The entity''s id.';

COMMENT ON COLUMN mdm.current_entity.kind IS 'The kind of master entity: company, person, security, fund_structure, branch, government, international_organization or venue.';

COMMENT ON COLUMN mdm.current_entity.status IS 'accepted, review when a person must look at it, or alias for a merged-away Company id.';

COMMENT ON COLUMN mdm.current_entity.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.current_entity.body IS 'The whole current master record.';

CREATE TABLE mdm.stage_record (
    source_code text NOT NULL,
    record_key text NOT NULL,
    subject text NOT NULL,
    kind text NOT NULL,
    revision bigint NOT NULL,
    mapping_version bigint NOT NULL,
    publication_key text NOT NULL,
    assertion_id text NOT NULL,
    effective_at timestamp with time zone,
    snapshot jsonb NOT NULL,
    bronze jsonb,
    batch_id text NOT NULL,
    reading jsonb NOT NULL,
    entity_id uuid,
    CONSTRAINT stage_record_bronze_check CHECK (((bronze IS NULL) OR ((jsonb_typeof(bronze) = 'object'::text) AND (bronze ?& ARRAY['object'::text, 'sha256'::text, 'locator'::text])))),
    CONSTRAINT stage_record_mapping_version_check CHECK ((mapping_version >= 1)),
    CONSTRAINT stage_record_reading_is_winner CHECK (((reading ->> 'assertion_id'::text) = assertion_id)),
    CONSTRAINT stage_record_revision_check CHECK ((revision >= 0)),
    CONSTRAINT stage_record_snapshot_check CHECK ((jsonb_typeof(snapshot) = 'object'::text))
);

COMMENT ON TABLE mdm.stage_record IS 'The Stage: one row per source record (source and its own record key) with its latest winning reading, what it resolves to, and the entity it is joined to. Written by record_stage, record_binding and release_binding inside save_batch; read by the Merge Stage for binding and matching.';

COMMENT ON COLUMN mdm.stage_record.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.stage_record.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.stage_record.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.stage_record.kind IS 'The kind of master entity: company, person, security, fund_structure, branch, government, international_organization or venue.';

COMMENT ON COLUMN mdm.stage_record.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.stage_record.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.stage_record.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.stage_record.assertion_id IS 'The winning source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.stage_record.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.stage_record.snapshot IS 'What the readings this record has accepted resolve to, field by field.';

COMMENT ON COLUMN mdm.stage_record.bronze IS 'The bronze object the winning reading was delivered in: object, sha256 and locator.';

COMMENT ON COLUMN mdm.stage_record.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.stage_record.reading IS 'The winning reading, whole.';

COMMENT ON COLUMN mdm.stage_record.entity_id IS 'The master entity this record is joined to; empty until a bind decision joins it. A join never moves; a correction revokes it.';

CREATE VIEW mdm.cross_reference AS
 SELECT x.key AS namespace,
    x.value,
    s.source_code,
    s.record_key,
    s.kind,
    (s.entity_id)::text AS bound_entity_id,
    COALESCE(e.canonical_id, (s.entity_id)::text) AS entity_id,
    s.assertion_id,
    s.batch_id
   FROM ((mdm.stage_record s
     CROSS JOIN LATERAL jsonb_each_text((s.reading -> 'cross_references'::text)) x(key, value))
     LEFT JOIN mdm.current_entity e ON (((e.object_id = (s.entity_id)::text) AND (e.canonical_id IS NOT NULL))));

COMMENT ON VIEW mdm.cross_reference IS 'Every cross-reference id a source record carries: an id kept so any document can be looked up by it, never used to join records. One row per id of each record, read from the record''s current reading. To look one id up, use mdm.cross_reference_lookup, which uses an index.';

COMMENT ON COLUMN mdm.cross_reference.namespace IS 'What kind of id it is, as the Dataset Contract names it (for example a tax number).';

COMMENT ON COLUMN mdm.cross_reference.value IS 'The id, formatted as the contract says.';

COMMENT ON COLUMN mdm.cross_reference.source_code IS 'The Dataset Contract of the record that carries the id.';

COMMENT ON COLUMN mdm.cross_reference.record_key IS 'The record''s key in that source.';

COMMENT ON COLUMN mdm.cross_reference.kind IS 'The kind of master entity the record describes.';

COMMENT ON COLUMN mdm.cross_reference.bound_entity_id IS 'The master entity the record is bound to; empty while the record waits for binding.';

COMMENT ON COLUMN mdm.cross_reference.entity_id IS 'The master entity to read now: the bound entity, or the entity it was merged into.';

COMMENT ON COLUMN mdm.cross_reference.assertion_id IS 'The reading the id comes from.';

COMMENT ON COLUMN mdm.cross_reference.batch_id IS 'The batch that wrote that reading.';

CREATE TABLE mdm.dataset (
    source_code text NOT NULL,
    registry_version uuid NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT dataset_body_check CHECK ((body ?& ARRAY['provider'::text, 'family'::text, 'schema_version'::text, 'record_key'::text, 'publication_key'::text, 'effective_time'::text, 'semantics'::text, 'registry_evidence'::text]))
);

COMMENT ON TABLE mdm.dataset IS 'Each source (a Dataset Contract) MDM accepts readings from, with the registry version that authorises it. Never changed. Written by register_dataset when rules activate runs; read by save_batch.';

COMMENT ON COLUMN mdm.dataset.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.dataset.registry_version IS 'The approved rules version that authorises this source.';

COMMENT ON COLUMN mdm.dataset.body IS 'The whole Dataset Contract: provider, family, keys, effective time and which set-aside reasons do not block.';

CREATE TABLE mdm.dataset_mapping (
    source_code text NOT NULL,
    mapping_version bigint NOT NULL,
    body jsonb NOT NULL,
    registry_version uuid NOT NULL,
    registered_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dataset_mapping_body_check CHECK ((jsonb_typeof(body) = 'object'::text)),
    CONSTRAINT dataset_mapping_mapping_version_check CHECK ((mapping_version >= 1))
);

COMMENT ON TABLE mdm.dataset_mapping IS 'Each version of how a source is read (its mapping). A correction is a new version, so earlier readings keep the version that read them. Never changed. Written by register_dataset; read by save_batch and the Stage.';

COMMENT ON COLUMN mdm.dataset_mapping.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.dataset_mapping.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.dataset_mapping.body IS 'The whole mapping: schema version and how each source field becomes an MDM field.';

COMMENT ON COLUMN mdm.dataset_mapping.registry_version IS 'The approved rules version this mapping came from.';

COMMENT ON COLUMN mdm.dataset_mapping.registered_at IS 'When rules activate registered it.';

CREATE TABLE mdm.decision (
    decision_id text NOT NULL,
    operation text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL,
    CONSTRAINT decision_operation_check CHECK ((operation = ANY (ARRAY['bind'::text, 'merge'::text, 'reverse'::text, 'override'::text, 'revoke'::text, 'exclude'::text, 'retire_source'::text, 'quarantine'::text])))
);

COMMENT ON TABLE mdm.decision IS 'Every decision that changes master data: bind (join a source record to an entity), merge, reverse, override, revoke, exclude, retire a source, quarantine and the others, with who or which rule made it and why. Never changed. Written by save_batch; read by the Merge Stage and corrections.';

COMMENT ON COLUMN mdm.decision.decision_id IS 'The decision''s id.';

COMMENT ON COLUMN mdm.decision.operation IS 'What the decision does, e.g. bind, merge, revoke or exclude.';

COMMENT ON COLUMN mdm.decision.body IS 'The whole decision: its targets, actor, reason and the rule or person behind it.';

COMMENT ON COLUMN mdm.decision.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

CREATE TABLE mdm.detail_version (
    entity_id text NOT NULL,
    detail text NOT NULL,
    key text NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT detail_version_generation_period CHECK (((to_generation IS NULL) OR (from_generation < to_generation))),
    CONSTRAINT detail_version_open_has_no_end CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT detail_version_valid_period CHECK (((valid_to IS NULL) OR (valid_from < valid_to)))
);

COMMENT ON TABLE mdm.detail_version IS 'Every recorded state of every detail row of every master (a Security''s listings), one row per master, list and key per change. The row whose from_generation <= g < to_generation (to_generation empty: still current) is what MDM had recorded at generation g. mdm.current_record''s entity body holds the current rows under details.';

COMMENT ON COLUMN mdm.detail_version.entity_id IS 'The master, as in mdm.current_record.object_id.';

COMMENT ON COLUMN mdm.detail_version.detail IS 'The list, as the Dataset Contract names it (listings).';

COMMENT ON COLUMN mdm.detail_version.key IS 'The row''s key within its list (a listing''s FIGI).';

COMMENT ON COLUMN mdm.detail_version.from_generation IS 'The generation of the batch that recorded this state.';

COMMENT ON COLUMN mdm.detail_version.to_generation IS 'The generation of the batch that changed or ended it; empty while current.';

COMMENT ON COLUMN mdm.detail_version.valid_from IS 'Recording time this state started: its batch''s created_at.';

COMMENT ON COLUMN mdm.detail_version.valid_to IS 'Recording time it was changed or ended; empty while current.';

COMMENT ON COLUMN mdm.detail_version.batch_id IS 'The batch that recorded this state (mdm.batch).';

COMMENT ON COLUMN mdm.detail_version.body IS 'The row as recorded: its fields and the sources that gave its key.';

CREATE VIEW mdm.fund_structure_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'fund_structure'::text));

COMMENT ON VIEW mdm.fund_structure_master IS 'Each current master record of kind fund_structure: a filter of current_record.';

COMMENT ON COLUMN mdm.fund_structure_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.fund_structure_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.fund_structure_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.fund_structure_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.fund_structure_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.fund_structure_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'fund_structure'::text));

COMMENT ON VIEW mdm.fund_structure_master_field IS 'Each current master record of kind fund_structure, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.fund_structure_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.fund_structure_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.fund_structure_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.fund_structure_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.fund_structure_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.fund_structure_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.fund_structure_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.fund_structure_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.fund_structure_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.fund_structure_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.fund_structure_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.fund_structure_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.fund_structure_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'fund_structure'::text);

COMMENT ON VIEW mdm.fund_structure_stage IS 'Each source reading of kind fund_structure, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.fund_structure_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.fund_structure_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.fund_structure_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.fund_structure_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.fund_structure_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.fund_structure_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.fund_structure_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.fund_structure_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.fund_structure_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.fund_structure_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.fund_structure_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.fund_structure_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'fund_structure'::text);

COMMENT ON VIEW mdm.fund_structure_stage_field IS 'Each source reading of kind fund_structure, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.fund_structure_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.fund_structure_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.fund_structure_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.fund_structure_stage_field.field_value IS 'The field''s value, as text.';

CREATE VIEW mdm.government_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'government'::text));

COMMENT ON VIEW mdm.government_master IS 'Each current master record of kind government: a filter of current_record.';

COMMENT ON COLUMN mdm.government_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.government_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.government_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.government_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.government_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.government_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'government'::text));

COMMENT ON VIEW mdm.government_master_field IS 'Each current master record of kind government, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.government_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.government_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.government_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.government_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.government_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.government_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.government_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.government_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.government_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.government_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.government_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.government_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.government_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'government'::text);

COMMENT ON VIEW mdm.government_stage IS 'Each source reading of kind government, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.government_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.government_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.government_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.government_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.government_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.government_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.government_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.government_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.government_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.government_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.government_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.government_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'government'::text);

COMMENT ON VIEW mdm.government_stage_field IS 'Each source reading of kind government, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.government_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.government_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.government_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.government_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.government_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.government_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.government_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.government_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.government_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.government_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.government_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.government_stage_field.field_value IS 'The field''s value, as text.';

CREATE VIEW mdm.international_organization_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'international_organization'::text));

COMMENT ON VIEW mdm.international_organization_master IS 'Each current master record of kind international_organization: a filter of current_record.';

COMMENT ON COLUMN mdm.international_organization_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.international_organization_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.international_organization_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.international_organization_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.international_organization_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.international_organization_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'international_organization'::text));

COMMENT ON VIEW mdm.international_organization_master_field IS 'Each current master record of kind international_organization, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.international_organization_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.international_organization_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.international_organization_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.international_organization_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.international_organization_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.international_organization_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.international_organization_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.international_organization_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.international_organization_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.international_organization_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.international_organization_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.international_organization_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.international_organization_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'international_organization'::text);

COMMENT ON VIEW mdm.international_organization_stage IS 'Each source reading of kind international_organization, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.international_organization_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.international_organization_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.international_organization_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.international_organization_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.international_organization_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.international_organization_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.international_organization_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.international_organization_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.international_organization_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.international_organization_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.international_organization_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.international_organization_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'international_organization'::text);

COMMENT ON VIEW mdm.international_organization_stage_field IS 'Each source reading of kind international_organization, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.international_organization_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.international_organization_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.international_organization_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.international_organization_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.international_organization_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.international_organization_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.international_organization_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.international_organization_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.international_organization_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.international_organization_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.international_organization_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.international_organization_stage_field.field_value IS 'The field''s value, as text.';

CREATE TABLE mdm.master_entity (
    entity_id uuid NOT NULL,
    kind text NOT NULL,
    published_at timestamp with time zone NOT NULL,
    batch_id text NOT NULL
);

COMMENT ON TABLE mdm.master_entity IS 'One row per master entity (a Company, a Person, ...): its id and kind, and when it was published. Never changed. Written by save_batch; read by save_batch and match_proposal_snapshot, and referenced by company, company_alias and stage_record.';

COMMENT ON COLUMN mdm.master_entity.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.master_entity.kind IS 'The kind of master entity: company, person, security, fund_structure, branch, government, international_organization or venue.';

COMMENT ON COLUMN mdm.master_entity.published_at IS 'When MDM first published the entity. Of two merged entities, the earlier-published one survives.';

COMMENT ON COLUMN mdm.master_entity.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

CREATE TABLE mdm.master_kind (
    kind text NOT NULL,
    enabled boolean NOT NULL
);

COMMENT ON TABLE mdm.master_kind IS 'Owner-installed configured master kinds; disabled historical kinds retain their identities and read views.';

COMMENT ON COLUMN mdm.master_kind.kind IS 'Configured master kind. The owner installs vocabulary; runtime may read it but cannot change it.';

COMMENT ON COLUMN mdm.master_kind.enabled IS 'Whether the installed configuration permits new identities of this kind. Disabling retains existing identities and read views.';

CREATE TABLE mdm.match_proposal (
    assessment_id text NOT NULL,
    body jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_xid xid8 DEFAULT pg_current_xact_id() NOT NULL
);

COMMENT ON TABLE mdm.match_proposal IS 'Proposed joins and merges (match proposals), checked before they may be saved: the command, the rule''s automatic proposals, and a snapshot of what they were checked against. Never changed. Written by record_match_proposal; read by save_batch.';

COMMENT ON COLUMN mdm.match_proposal.assessment_id IS 'The proposal''s id, a hash of the proposal.';

COMMENT ON COLUMN mdm.match_proposal.body IS 'The whole proposal: the command, its outcome (ready or rejected), its effects, scope and snapshot hash.';

COMMENT ON COLUMN mdm.match_proposal.created_at IS 'When it was recorded.';

COMMENT ON COLUMN mdm.match_proposal.created_xid IS 'The transaction that recorded it. A proposal cannot be saved in the transaction that recorded it.';

CREATE TABLE mdm.match_proposal_event (
    event_id bigint NOT NULL,
    assessment_id text NOT NULL,
    run_id uuid NOT NULL,
    event text NOT NULL,
    batch_id text,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT match_proposal_event_event_check CHECK ((event = ANY (ARRAY['ready'::text, 'rejected'::text, 'observed'::text, 'superseded'::text, 'applied'::text])))
);

COMMENT ON TABLE mdm.match_proposal_event IS 'What became of each match proposal: ready, rejected, observed, superseded or applied. Never changed. Written by record_match_proposal, save_batch and supersede_match_proposal.';

COMMENT ON COLUMN mdm.match_proposal_event.event_id IS 'The event''s number, in order.';

COMMENT ON COLUMN mdm.match_proposal_event.assessment_id IS 'The match proposal (match_proposal.assessment_id).';

COMMENT ON COLUMN mdm.match_proposal_event.run_id IS 'The Merge Stage run (run.run_id).';

COMMENT ON COLUMN mdm.match_proposal_event.event IS 'ready, rejected, observed, superseded or applied.';

COMMENT ON COLUMN mdm.match_proposal_event.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.match_proposal_event.occurred_at IS 'When it happened.';

ALTER TABLE mdm.match_proposal_event ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME mdm.match_proposal_event_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE mdm.migration (
    name text NOT NULL,
    checksum text NOT NULL,
    installed_at timestamp with time zone DEFAULT now() NOT NULL
);

COMMENT ON TABLE mdm.migration IS 'Which migration files are applied, with their checksums. A changed file is refused. Never changed. Written and read by mdm migrate.';

COMMENT ON COLUMN mdm.migration.name IS 'The migration file''s name.';

COMMENT ON COLUMN mdm.migration.checksum IS 'The sha256 of the file as applied.';

COMMENT ON COLUMN mdm.migration.installed_at IS 'When it was applied.';

CREATE TABLE mdm.outbox (
    batch_id text NOT NULL,
    consumer text NOT NULL,
    payload jsonb,
    payload_hash text NOT NULL,
    fence bigint DEFAULT 0 NOT NULL,
    lease_until timestamp with time zone,
    worker text,
    verified_at timestamp with time zone,
    contract_version integer DEFAULT 2 NOT NULL,
    CONSTRAINT outbox_contract_version_check CHECK ((contract_version = ANY (ARRAY[2, 3])))
);

COMMENT ON TABLE mdm.outbox IS 'What must be sent on from each saved batch (to the Change Journal, exports), one row per batch and consumer, with its delivery lease and when it was verified. Written by save_batch, claim_outbox and finish_outbox; read by publishers and change-journal recover mdm.';

COMMENT ON COLUMN mdm.outbox.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.outbox.consumer IS 'Who it is for, e.g. journal.';

COMMENT ON COLUMN mdm.outbox.payload IS 'What to send, for a row saved before migration 014; NULL for a later row, whose payload is built from its batch (outbox_delivery).';

COMMENT ON COLUMN mdm.outbox.payload_hash IS 'The sha256 of the payload; delivery is verified against it.';

COMMENT ON COLUMN mdm.outbox.fence IS 'Raised on each claim; a delivery by an older claim is refused.';

COMMENT ON COLUMN mdm.outbox.lease_until IS 'Until when the current claim holds.';

COMMENT ON COLUMN mdm.outbox.worker IS 'Who holds the claim.';

COMMENT ON COLUMN mdm.outbox.verified_at IS 'When delivery was verified; empty until then.';

COMMENT ON COLUMN mdm.outbox.contract_version IS 'Payload contract: 2 sends the whole batch (rows before migration 018, and the journal); 3 sends only the changed records (change data capture) or a forced snapshot page.';

CREATE VIEW mdm.outbox_delivery AS
 SELECT o.batch_id,
    o.consumer,
    COALESCE(o.payload,
        CASE
            WHEN (o.contract_version = 3) THEN jsonb_build_object('contract_version', 3, 'generation', b.generation, 'run_id', b.run_id, 'policy_digest', (b.effects ->> 'policy_digest'::text), 'forced', COALESCE(((b.effects ->> 'forced'::text))::boolean, false), 'objects', COALESCE(( SELECT jsonb_agg((p.value || jsonb_build_object('change', c.change)) ORDER BY c."position") AS jsonb_agg
               FROM (jsonb_array_elements((b.effects -> 'projections'::text)) WITH ORDINALITY p(value, "position")
                 JOIN mdm.batch_change c ON (((c.batch_id = b.batch_id) AND (c."position" = p."position"))))), '[]'::jsonb))
            ELSE (jsonb_build_object('contract_version', 2, 'generation', b.generation, 'run_id', b.run_id, 'policy_digest', (b.effects ->> 'policy_digest'::text), 'objects', (b.effects -> 'projections'::text)) ||
            CASE
                WHEN (o.consumer = 'journal'::text) THEN jsonb_build_object('effects', b.effects)
                ELSE '{}'::jsonb
            END)
        END) AS payload
   FROM (mdm.outbox o
     JOIN mdm.batch b USING (batch_id));

COMMENT ON VIEW mdm.outbox_delivery IS 'What each outbox row sends: its stored payload (a row saved before migration 014); else, for contract 3, only the batch''s changed records, each with its change (insert, update or snapshot), and whether it is forced; else built from its batch: generation, run, policy digest and current records, and for journal the whole batch. Read by claim_outbox, outbox_input and the publishers; write_batch keeps its hash.';

COMMENT ON COLUMN mdm.outbox_delivery.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.outbox_delivery.consumer IS 'The reader the work is for, e.g. journal.';

COMMENT ON COLUMN mdm.outbox_delivery.payload IS 'What to send.';

CREATE TABLE mdm.outbox_event (
    event_id bigint NOT NULL,
    batch_id text NOT NULL,
    consumer text NOT NULL,
    fence bigint NOT NULL,
    event text NOT NULL,
    detail jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT outbox_event_event_check CHECK ((event = ANY (ARRAY['claimed'::text, 'verified'::text, 'failed'::text])))
);

COMMENT ON TABLE mdm.outbox_event IS 'Each claim, verified delivery and failure of an outbox row. Never changed. Written by claim_outbox and finish_outbox.';

COMMENT ON COLUMN mdm.outbox_event.event_id IS 'The event''s number, in order.';

COMMENT ON COLUMN mdm.outbox_event.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.outbox_event.consumer IS 'The reader the work is for, e.g. journal.';

COMMENT ON COLUMN mdm.outbox_event.fence IS 'The claim''s fence.';

COMMENT ON COLUMN mdm.outbox_event.event IS 'claimed, verified or failed.';

COMMENT ON COLUMN mdm.outbox_event.detail IS 'The worker, the verified hash or the error.';

COMMENT ON COLUMN mdm.outbox_event.occurred_at IS 'When it happened.';

ALTER TABLE mdm.outbox_event ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME mdm.outbox_event_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE VIEW mdm.outbox_input AS
 SELECT o.batch_id,
    o.consumer,
    o.payload_hash,
    b.created_at,
        CASE
            WHEN (o.payload IS NOT NULL) THEN (o.payload)::text
            WHEN (o.contract_version = 3) THEN ( SELECT (d.payload)::text AS payload
               FROM mdm.outbox_delivery d
              WHERE ((d.batch_id = o.batch_id) AND (d.consumer = o.consumer)))
            ELSE NULL::text
        END AS payload_text,
    b.generation,
    (b.run_id)::text AS run_id,
        CASE
            WHEN ((o.payload IS NULL) AND (o.contract_version = 2)) THEN (b.effects ->> 'policy_digest'::text)
            ELSE NULL::text
        END AS policy_digest,
        CASE
            WHEN ((o.payload IS NULL) AND (o.contract_version = 2)) THEN ((b.effects -> 'projections'::text))::text
            ELSE NULL::text
        END AS projections_text,
        CASE
            WHEN ((o.payload IS NULL) AND (o.contract_version = 2) AND (o.consumer = 'journal'::text)) THEN (b.effects)::text
            ELSE NULL::text
        END AS effects_text
   FROM (mdm.outbox o
     JOIN mdm.batch b USING (batch_id));

COMMENT ON VIEW mdm.outbox_input IS 'Indexed immutable publication inputs. Programs shape/hash them against the committed payload_hash before sending. Raw JSON text preserves numeric precision/scale. Previously stored payloads are sent as stored.';

COMMENT ON COLUMN mdm.outbox_input.batch_id IS 'Saved batch that owns this immutable publication intent (batch.batch_id).';

COMMENT ON COLUMN mdm.outbox_input.consumer IS 'Destination reader, such as journal; together with batch_id identifies the outbox row.';

COMMENT ON COLUMN mdm.outbox_input.payload_hash IS 'Expected SHA-256 of publication JSONB text, independently derived by the database at commit; programs must match it before sending.';

COMMENT ON COLUMN mdm.outbox_input.created_at IS 'Original batch commit time; journal publication uses this durable event time.';

COMMENT ON COLUMN mdm.outbox_input.payload_text IS 'Publication JSONB text sent as is: a stored pre-014 payload, or a contract 3 payload (outbox_delivery); NULL for contract 2 intent prepared from the fields below.';

COMMENT ON COLUMN mdm.outbox_input.generation IS 'Committed batch generation; claims deliver a consumer in this order.';

COMMENT ON COLUMN mdm.outbox_input.run_id IS 'Run that committed the batch, exposed as text for envelope preparation.';

COMMENT ON COLUMN mdm.outbox_input.policy_digest IS 'Approved policy digest from the immutable batch request; NULL when a legacy stored payload is used.';

COMMENT ON COLUMN mdm.outbox_input.projections_text IS 'Committed golden records as raw JSONB text, preserving numeric precision and scale; NULL when a legacy stored payload is used.';

COMMENT ON COLUMN mdm.outbox_input.effects_text IS 'Whole committed batch request as raw JSONB text for the journal envelope; NULL for other consumers or legacy stored payloads.';

CREATE VIEW mdm.person_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'person'::text));

COMMENT ON VIEW mdm.person_master IS 'Each current master record of kind person: a filter of current_record.';

COMMENT ON COLUMN mdm.person_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.person_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.person_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.person_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.person_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.person_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'person'::text));

COMMENT ON VIEW mdm.person_master_field IS 'Each current master record of kind person, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.person_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.person_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.person_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.person_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.person_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.person_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.person_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.person_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.person_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.person_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.person_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.person_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.person_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'person'::text);

COMMENT ON VIEW mdm.person_stage IS 'Each source reading of kind person, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.person_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.person_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.person_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.person_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.person_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.person_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.person_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.person_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.person_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.person_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.person_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.person_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'person'::text);

COMMENT ON VIEW mdm.person_stage_field IS 'Each source reading of kind person, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.person_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.person_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.person_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.person_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.person_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.person_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.person_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.person_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.person_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.person_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.person_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.person_stage_field.field_value IS 'The field''s value, as text.';

CREATE TABLE mdm.policy (
    digest text NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT policy_body_check CHECK ((jsonb_typeof(body) = 'object'::text))
);

COMMENT ON TABLE mdm.policy IS 'Each Mastering Policy (the merge rules), stored by its fingerprint as approved. Never changed. Written by register_policy when rules activate runs; read by save_batch and the Merge Stage.';

COMMENT ON COLUMN mdm.policy.digest IS 'The policy''s fingerprint: the sha256 of its body.';

COMMENT ON COLUMN mdm.policy.body IS 'The whole policy: kinds, matching rules, field winners, required consumers and approvals.';

CREATE TABLE mdm.relationship_version (
    relationship_id text NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL,
    source_id text,
    target_id text,
    type text,
    body jsonb NOT NULL,
    CONSTRAINT relationship_version_generation_period CHECK (((to_generation IS NULL) OR (from_generation < to_generation))),
    CONSTRAINT relationship_version_open_has_no_end CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT relationship_version_valid_period CHECK (((valid_to IS NULL) OR (valid_from < valid_to)))
);

COMMENT ON TABLE mdm.relationship_version IS 'Every recorded state of every relationship, one row per relationship per change. The row whose from_generation <= g < to_generation (to_generation empty: still current) is what MDM had recorded at generation g; a batch''s generation and created_at say when. mdm.current_record holds the latest; this table answers "what did MDM have by then" (--as-at). Business time is in the body''s periods.';

COMMENT ON COLUMN mdm.relationship_version.relationship_id IS 'The relationship''s id, as in mdm.current_record.object_id.';

COMMENT ON COLUMN mdm.relationship_version.from_generation IS 'The generation of the batch that recorded this state.';

COMMENT ON COLUMN mdm.relationship_version.to_generation IS 'The generation of the batch that replaced it; empty while it is the current state.';

COMMENT ON COLUMN mdm.relationship_version.valid_from IS 'Recording time this state started: its batch''s created_at.';

COMMENT ON COLUMN mdm.relationship_version.valid_to IS 'Recording time it was replaced; empty while current.';

COMMENT ON COLUMN mdm.relationship_version.batch_id IS 'The batch that recorded this state (mdm.batch).';

COMMENT ON COLUMN mdm.relationship_version.source_id IS 'The entity the link starts from (body source_id), indexed for a walk at a past generation.';

COMMENT ON COLUMN mdm.relationship_version.target_id IS 'The entity the link points to (body target_id), indexed likewise.';

COMMENT ON COLUMN mdm.relationship_version.type IS 'The relationship type (body type).';

COMMENT ON COLUMN mdm.relationship_version.body IS 'The relationship as recorded: periods, evidence, retired flag and the rest.';

CREATE TABLE mdm.run (
    run_id uuid NOT NULL,
    scope jsonb NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'running'::text NOT NULL,
    report jsonb,
    completed_at timestamp with time zone,
    CONSTRAINT run_report_check CHECK (((report IS NULL) OR (jsonb_typeof(report) = 'object'::text))),
    CONSTRAINT run_scope_check CHECK ((jsonb_typeof(scope) = 'object'::text)),
    CONSTRAINT run_status_check CHECK ((status = ANY (ARRAY['running'::text, 'succeeded'::text])))
);

COMMENT ON TABLE mdm.run IS 'Each Merge Stage run: its frozen scope and its reconciled outcome. Written only by start_run and finish_run; read by the run coordinator.';

COMMENT ON COLUMN mdm.run.run_id IS 'The Merge Stage run (run.run_id).';

COMMENT ON COLUMN mdm.run.scope IS 'The run''s frozen scope: the captures and readings it was started on. A changed scope is refused.';

COMMENT ON COLUMN mdm.run.started_at IS 'When the run was registered.';

COMMENT ON COLUMN mdm.run.status IS 'running, or succeeded once reconciled complete. A succeeded run stays succeeded.';

COMMENT ON COLUMN mdm.run.report IS 'The reconciled outcome: counts per batch and what is left.';

COMMENT ON COLUMN mdm.run.completed_at IS 'When the run succeeded.';

CREATE TABLE mdm.run_batch (
    run_id uuid NOT NULL,
    batch_id text NOT NULL
);

COMMENT ON TABLE mdm.run_batch IS 'Which run saw which batch, including a run that met a batch already saved. Never changed. Written by save_batch; read when a run is reconciled.';

COMMENT ON COLUMN mdm.run_batch.run_id IS 'The Merge Stage run (run.run_id).';

COMMENT ON COLUMN mdm.run_batch.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

CREATE VIEW mdm.security_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'security'::text));

COMMENT ON VIEW mdm.security_master IS 'Each current master record of kind security: a filter of current_record.';

COMMENT ON COLUMN mdm.security_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.security_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.security_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.security_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.security_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.security_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'security'::text));

COMMENT ON VIEW mdm.security_master_field IS 'Each current master record of kind security, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.security_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.security_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.security_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.security_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.security_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.security_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.security_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.security_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.security_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.security_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.security_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.security_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.security_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'security'::text);

COMMENT ON VIEW mdm.security_stage IS 'Each source reading of kind security, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.security_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.security_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.security_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.security_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.security_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.security_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.security_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.security_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.security_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.security_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.security_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.security_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'security'::text);

COMMENT ON VIEW mdm.security_stage_field IS 'Each source reading of kind security, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.security_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.security_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.security_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.security_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.security_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.security_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.security_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.security_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.security_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.security_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.security_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.security_stage_field.field_value IS 'The field''s value, as text.';

CREATE TABLE mdm.set_aside_record (
    deferred_id text NOT NULL,
    source_code text NOT NULL,
    publication_key text NOT NULL,
    record_locator text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL
);

COMMENT ON TABLE mdm.set_aside_record IS 'Source records MDM read but did not accept, and why: not this kind, an invalid field, or waiting for review. Never changed. Written by save_batch; read by stage_waiting.';

COMMENT ON COLUMN mdm.set_aside_record.deferred_id IS 'The set-aside record''s id.';

COMMENT ON COLUMN mdm.set_aside_record.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.set_aside_record.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.set_aside_record.record_locator IS 'Where in the publication the record sits, e.g. a file member and line.';

COMMENT ON COLUMN mdm.set_aside_record.body IS 'The whole set-aside record: its reason, probable kind, the classification step that set it aside, and the raw record.';

COMMENT ON COLUMN mdm.set_aside_record.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

CREATE VIEW mdm.stage_waiting AS
 SELECT d.deferred_id,
    d.source_code,
    d.publication_key,
    d.record_locator,
    d.batch_id,
    (d.body ->> 'probable_kind'::text) AS probable_kind,
    (d.body ->> 'reason'::text) AS reason,
    (((d.body -> 'provenance'::text) -> 'classification'::text) ->> 'rule_id'::text) AS rule_id,
    (((d.body -> 'provenance'::text) -> 'classification'::text) ->> 'version'::text) AS rule_version,
    (((d.body -> 'provenance'::text) -> 'classification'::text) ->> 'step'::text) AS rule_step,
    ((r.body ->> 'blocking'::text))::boolean AS blocking,
    (d.body -> 'raw_record'::text) AS raw_record
   FROM (mdm.set_aside_record d
     JOIN mdm.current_record r ON (((r.object_type = 'review'::text) AND (r.object_id = d.deferred_id))))
  WHERE (((r.body -> 'open'::text) = 'true'::jsonb) AND (COALESCE((r.body -> 'retired'::text), 'false'::jsonb) = 'false'::jsonb));

COMMENT ON VIEW mdm.stage_waiting IS 'Source records still waiting for review, with the kind each probably is and the classification step that set it aside.';

COMMENT ON COLUMN mdm.stage_waiting.deferred_id IS 'The set-aside record (set_aside_record.deferred_id).';

COMMENT ON COLUMN mdm.stage_waiting.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.stage_waiting.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.stage_waiting.record_locator IS 'Where in the publication the record sits, e.g. a file member and line.';

COMMENT ON COLUMN mdm.stage_waiting.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.stage_waiting.probable_kind IS 'The kind the record probably is.';

COMMENT ON COLUMN mdm.stage_waiting.reason IS 'Why it was set aside.';

COMMENT ON COLUMN mdm.stage_waiting.rule_id IS 'The classification rule that set it aside.';

COMMENT ON COLUMN mdm.stage_waiting.rule_version IS 'That rule''s version.';

COMMENT ON COLUMN mdm.stage_waiting.rule_step IS 'The step of that rule that set it aside.';

COMMENT ON COLUMN mdm.stage_waiting.blocking IS 'True when the record blocks its source from counting as complete.';

COMMENT ON COLUMN mdm.stage_waiting.raw_record IS 'The record as the source delivered it.';

CREATE VIEW mdm.venue_master AS
 SELECT object_id AS entity_id,
    batch_id,
    (body ->> 'status'::text) AS status,
    (body ->> 'canonical_id'::text) AS canonical_id,
    body
   FROM mdm.current_record p
  WHERE ((object_type = 'entity'::text) AND ((body ->> 'kind'::text) = 'venue'::text));

COMMENT ON VIEW mdm.venue_master IS 'Each current master record of kind venue: a filter of current_record.';

COMMENT ON COLUMN mdm.venue_master.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.venue_master.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.venue_master.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.venue_master.canonical_id IS 'The entity this one points to after a merge; itself when it survived.';

COMMENT ON COLUMN mdm.venue_master.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.venue_master_field AS
 SELECT p.object_id AS entity_id,
    p.batch_id,
    (p.body ->> 'status'::text) AS status,
    f.key AS field_name,
    (f.value ->> 'value'::text) AS field_value,
    ((f.value ->> 'cleared'::text))::boolean AS cleared,
    ((f.value -> 'winner'::text) ->> 'source_code'::text) AS source_code,
    ((f.value -> 'winner'::text) ->> 'record_key'::text) AS record_key,
    (((f.value -> 'winner'::text) ->> 'effective_at'::text))::timestamp with time zone AS effective_at,
    (f.value ->> 'policy_digest'::text) AS policy_digest,
    (f.value ->> 'kind_version'::text) AS kind_version,
    jsonb_array_length(COALESCE((f.value -> 'conflicts'::text), '[]'::jsonb)) AS conflict_count
   FROM (mdm.current_record p
     CROSS JOIN LATERAL jsonb_each(COALESCE((p.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((p.object_type = 'entity'::text) AND ((p.body ->> 'kind'::text) = 'venue'::text));

COMMENT ON VIEW mdm.venue_master_field IS 'Each current master record of kind venue, one row per field: its value and the source reading that won it.';

COMMENT ON COLUMN mdm.venue_master_field.entity_id IS 'The master entity (master_entity.entity_id).';

COMMENT ON COLUMN mdm.venue_master_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.venue_master_field.status IS 'accepted, or review when a person must look at it.';

COMMENT ON COLUMN mdm.venue_master_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.venue_master_field.field_value IS 'The field''s value, as text.';

COMMENT ON COLUMN mdm.venue_master_field.cleared IS 'True when the winning reading cleared the field.';

COMMENT ON COLUMN mdm.venue_master_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.venue_master_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.venue_master_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.venue_master_field.policy_digest IS 'The Mastering Policy (policy.digest) in force.';

COMMENT ON COLUMN mdm.venue_master_field.kind_version IS 'The version of the kind''s merge rules that chose the winner.';

COMMENT ON COLUMN mdm.venue_master_field.conflict_count IS 'How many other readings disagreed with the winner.';

CREATE VIEW mdm.venue_stage AS
 SELECT assertion_id,
    source_code,
    record_key,
    publication_key,
    revision,
    mapping_version,
    effective_at,
    batch_id,
    (body ->> 'subject'::text) AS subject,
    (body ->> 'schema_version'::text) AS schema_version,
    body
   FROM mdm.source_reading a
  WHERE ((body ->> 'kind'::text) = 'venue'::text);

COMMENT ON VIEW mdm.venue_stage IS 'Each source reading of kind venue, as read and never changed: a filter of source_reading.';

COMMENT ON COLUMN mdm.venue_stage.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.venue_stage.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.venue_stage.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.venue_stage.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.venue_stage.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.venue_stage.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.venue_stage.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.venue_stage.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.venue_stage.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.venue_stage.schema_version IS 'The source''s schema version the record was read under.';

COMMENT ON COLUMN mdm.venue_stage.body IS 'The whole record, as JSON.';

CREATE VIEW mdm.venue_stage_field AS
 SELECT a.assertion_id,
    a.source_code,
    a.record_key,
    a.publication_key,
    a.revision,
    a.mapping_version,
    a.effective_at,
    a.batch_id,
    (a.body ->> 'subject'::text) AS subject,
    f.key AS field_name,
    (f.value ->> 'op'::text) AS operation,
    (f.value ->> 'value'::text) AS field_value
   FROM (mdm.source_reading a
     CROSS JOIN LATERAL jsonb_each(COALESCE((a.body -> 'fields'::text), '{}'::jsonb)) f(key, value))
  WHERE ((a.body ->> 'kind'::text) = 'venue'::text);

COMMENT ON VIEW mdm.venue_stage_field IS 'Each source reading of kind venue, one row per field it states, sets or clears.';

COMMENT ON COLUMN mdm.venue_stage_field.assertion_id IS 'The source reading (source_reading.assertion_id).';

COMMENT ON COLUMN mdm.venue_stage_field.source_code IS 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).';

COMMENT ON COLUMN mdm.venue_stage_field.record_key IS 'The source''s own key for the record, e.g. a CIK or an LEI.';

COMMENT ON COLUMN mdm.venue_stage_field.publication_key IS 'The source publication (delivered file or release) the record came in.';

COMMENT ON COLUMN mdm.venue_stage_field.revision IS 'The source''s revision of the record; a higher revision supersedes a lower one.';

COMMENT ON COLUMN mdm.venue_stage_field.mapping_version IS 'The version of the source''s mapping (dataset_mapping) that read it.';

COMMENT ON COLUMN mdm.venue_stage_field.effective_at IS 'When the source says the reading took effect.';

COMMENT ON COLUMN mdm.venue_stage_field.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';

COMMENT ON COLUMN mdm.venue_stage_field.subject IS 'The source record''s subject: a digest of its source and record key, the name the Merge Stage joins to an entity.';

COMMENT ON COLUMN mdm.venue_stage_field.field_name IS 'The MDM field, e.g. name or address.';

COMMENT ON COLUMN mdm.venue_stage_field.operation IS 'What the reading does to the field: states a value, clears it, or leaves it unknown.';

COMMENT ON COLUMN mdm.venue_stage_field.field_value IS 'The field''s value, as text.';

ALTER TABLE ONLY mdm.attempt_event
    ADD CONSTRAINT attempt_event_pkey PRIMARY KEY (attempt_id, event);

ALTER TABLE ONLY mdm.batch_change
    ADD CONSTRAINT batch_change_pkey PRIMARY KEY (batch_id, "position");

ALTER TABLE ONLY mdm.batch
    ADD CONSTRAINT batch_generation_key UNIQUE (generation);

ALTER TABLE ONLY mdm.batch
    ADD CONSTRAINT batch_pkey PRIMARY KEY (batch_id);

ALTER TABLE ONLY mdm.checkpoint
    ADD CONSTRAINT checkpoint_pkey PRIMARY KEY (consumer, source_family, publication_family);

ALTER TABLE ONLY mdm.company_alias
    ADD CONSTRAINT company_alias_pkey PRIMARY KEY (alias_id, from_generation);

ALTER TABLE ONLY mdm.company
    ADD CONSTRAINT company_pkey PRIMARY KEY (entity_id, from_generation);

ALTER TABLE ONLY mdm.current_record
    ADD CONSTRAINT current_record_pkey PRIMARY KEY (object_type, object_id);

ALTER TABLE ONLY mdm.dataset_mapping
    ADD CONSTRAINT dataset_mapping_pkey PRIMARY KEY (source_code, mapping_version);

ALTER TABLE ONLY mdm.dataset
    ADD CONSTRAINT dataset_pkey PRIMARY KEY (source_code);

ALTER TABLE ONLY mdm.decision
    ADD CONSTRAINT decision_pkey PRIMARY KEY (decision_id);

ALTER TABLE ONLY mdm.detail_version
    ADD CONSTRAINT detail_version_pkey PRIMARY KEY (entity_id, detail, key, from_generation);

ALTER TABLE ONLY mdm.master_entity
    ADD CONSTRAINT master_entity_pkey PRIMARY KEY (entity_id);

ALTER TABLE ONLY mdm.master_kind
    ADD CONSTRAINT master_kind_pkey PRIMARY KEY (kind);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_assessment_id_run_id_event_key UNIQUE (assessment_id, run_id, event);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY mdm.match_proposal
    ADD CONSTRAINT match_proposal_pkey PRIMARY KEY (assessment_id);

ALTER TABLE ONLY mdm.migration
    ADD CONSTRAINT migration_pkey PRIMARY KEY (name);

ALTER TABLE ONLY mdm.outbox_event
    ADD CONSTRAINT outbox_event_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY mdm.outbox
    ADD CONSTRAINT outbox_pkey PRIMARY KEY (batch_id, consumer);

ALTER TABLE ONLY mdm.policy
    ADD CONSTRAINT policy_pkey PRIMARY KEY (digest);

ALTER TABLE ONLY mdm.relationship_version
    ADD CONSTRAINT relationship_version_pkey PRIMARY KEY (relationship_id, from_generation);

ALTER TABLE ONLY mdm.run_batch
    ADD CONSTRAINT run_batch_pkey PRIMARY KEY (run_id, batch_id);

ALTER TABLE ONLY mdm.run
    ADD CONSTRAINT run_pkey PRIMARY KEY (run_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_pkey PRIMARY KEY (deferred_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_source_code_publication_key_record_locator_key UNIQUE (source_code, publication_key, record_locator);

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_one_per_publication_and_mapping UNIQUE (source_code, record_key, publication_key, mapping_version);

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_pkey PRIMARY KEY (assertion_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_pkey PRIMARY KEY (source_code, record_key);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_subject_key UNIQUE (subject);

CREATE INDEX attempt_run ON mdm.attempt_event USING btree (run_id, batch_id);

CREATE UNIQUE INDEX company_alias_current ON mdm.company_alias USING btree (alias_id) WHERE (valid_to IS NULL);

CREATE INDEX company_alias_current_text ON mdm.company_alias USING btree (((alias_id)::text)) WHERE (valid_to IS NULL);

CREATE INDEX company_current_cik ON mdm.company USING btree (cik) WHERE ((valid_to IS NULL) AND (status = 'accepted'::text) AND (cik IS NOT NULL));

CREATE UNIQUE INDEX company_current_entity ON mdm.company USING btree (entity_id) WHERE (valid_to IS NULL);

CREATE INDEX company_current_entity_text ON mdm.company USING btree (((entity_id)::text)) WHERE (valid_to IS NULL);

CREATE INDEX company_current_lei ON mdm.company USING btree (lei) WHERE ((valid_to IS NULL) AND (status = 'accepted'::text) AND (lei IS NOT NULL));

CREATE INDEX company_generation_page ON mdm.company USING btree (from_generation, to_generation, entity_id);

CREATE INDEX current_record_entity_kind ON mdm.current_record USING btree (((body ->> 'kind'::text))) WHERE (object_type = 'entity'::text);

CREATE INDEX current_record_link_end ON mdm.current_record USING btree (((body ->> 'target_id'::text))) WHERE (object_type = 'relationship'::text);

COMMENT ON INDEX mdm.current_record_link_end IS 'Finds the current links that end at an entity.';

CREATE INDEX current_record_link_start ON mdm.current_record USING btree (((body ->> 'source_id'::text))) WHERE (object_type = 'relationship'::text);

COMMENT ON INDEX mdm.current_record_link_start IS 'Finds the current links that start at an entity.';

CREATE INDEX current_record_review_affected_subjects ON mdm.current_record USING gin (((body -> 'affected_subjects'::text))) WITH (fastupdate=off) WHERE (object_type = 'review'::text);

COMMENT ON INDEX mdm.current_record_review_affected_subjects IS 'Finds the current reviews that name a record among the records they are about (05b part 1: only their own).';

CREATE INDEX current_record_review_entity ON mdm.current_record USING btree (((body ->> 'entity_id'::text))) WHERE (object_type = 'review'::text);

COMMENT ON INDEX mdm.current_record_review_entity IS 'Finds the current reviews about an entity.';

CREATE INDEX current_record_review_subject ON mdm.current_record USING btree (((body ->> 'subject'::text))) WHERE (object_type = 'review'::text);

COMMENT ON INDEX mdm.current_record_review_subject IS 'Finds the current reviews about a record.';

CREATE INDEX decision_entity ON mdm.decision USING btree (((body ->> 'entity_id'::text)));

CREATE INDEX decision_left ON mdm.decision USING btree (((body ->> 'left'::text)));

CREATE INDEX decision_retired_source ON mdm.decision USING btree (((body ->> 'source_code'::text))) WHERE (operation = 'retire_source'::text);

COMMENT ON INDEX mdm.decision_retired_source IS 'Finds the decisions that retire a source, so every part of the snapshot''s decision lookup has an index.';

CREATE INDEX decision_right ON mdm.decision USING btree (((body ->> 'right'::text)));

CREATE INDEX decision_subject ON mdm.decision USING btree (((body ->> 'subject'::text)));

CREATE INDEX decision_target ON mdm.decision USING btree (((body ->> 'target'::text)));

CREATE INDEX detail_version_key ON mdm.detail_version USING btree (detail, key) WHERE (to_generation IS NULL);

CREATE UNIQUE INDEX detail_version_open ON mdm.detail_version USING btree (entity_id, detail, key) WHERE (to_generation IS NULL);

CREATE INDEX master_entity_id_text ON mdm.master_entity USING btree (((entity_id)::text));

COMMENT ON INDEX mdm.master_entity_id_text IS 'Finds an entity by its id written as text, as the snapshot and the closure compare it with their keys.';

CREATE INDEX master_entity_kind_published_at ON mdm.master_entity USING btree (kind, published_at);

CREATE INDEX match_proposal_batch ON mdm.match_proposal USING btree ((((body -> 'command'::text) ->> 'batch_id'::text)));

CREATE INDEX match_proposal_created_at_assessment_id_idx ON mdm.match_proposal USING btree (created_at DESC, assessment_id);

CREATE INDEX match_proposal_event_assessment_id_event_id_idx ON mdm.match_proposal_event USING btree (assessment_id, event_id DESC);

CREATE UNIQUE INDEX relationship_version_open ON mdm.relationship_version USING btree (relationship_id) WHERE (to_generation IS NULL);

CREATE INDEX relationship_version_source ON mdm.relationship_version USING btree (source_id, from_generation);

CREATE INDEX relationship_version_target ON mdm.relationship_version USING btree (target_id, from_generation);

CREATE INDEX set_aside_record_probable_kind ON mdm.set_aside_record USING btree (((body ->> 'probable_kind'::text)));

CREATE INDEX source_reading_identifier_cik ON mdm.source_reading USING btree ((((body -> 'identifiers'::text) ->> 'cik'::text)));

CREATE INDEX source_reading_identifier_lei ON mdm.source_reading USING btree ((((body -> 'identifiers'::text) ->> 'lei'::text)));

CREATE INDEX source_reading_kind ON mdm.source_reading USING btree (((body ->> 'kind'::text)));

CREATE INDEX source_reading_source_code_mapping_version_idx ON mdm.source_reading USING btree (source_code, mapping_version);

CREATE INDEX source_reading_source_code_record_key_revision_idx ON mdm.source_reading USING btree (source_code, record_key, revision);

CREATE INDEX source_reading_subject ON mdm.source_reading USING btree (((body ->> 'subject'::text)));

CREATE INDEX stage_record_cik ON mdm.stage_record USING btree ((((reading -> 'identifiers'::text) ->> 'cik'::text)));

CREATE INDEX stage_record_cross_references ON mdm.stage_record USING gin (((reading -> 'cross_references'::text)) jsonb_path_ops) WITH (fastupdate=off);

COMMENT ON INDEX mdm.stage_record_cross_references IS 'Finds the source records that carry one cross-reference id, for mdm.cross_reference_lookup.';

CREATE INDEX stage_record_entity ON mdm.stage_record USING btree (entity_id) WHERE (entity_id IS NOT NULL);

CREATE INDEX stage_record_identifiers ON mdm.stage_record USING gin (((reading -> 'identifiers'::text)) jsonb_path_ops) WITH (fastupdate=off);

COMMENT ON INDEX mdm.stage_record_identifiers IS 'Finds the source records that carry one identifier of any namespace: binding probes it one value at a time, and edgar-warehouse context <kind> <namespace>:<value> reads it. No pending list (fastupdate off), so a probe costs the same however many saves came before.';

CREATE INDEX stage_record_kind ON mdm.stage_record USING btree (kind, source_code);

CREATE INDEX stage_record_lei ON mdm.stage_record USING btree ((((reading -> 'identifiers'::text) ->> 'lei'::text)));

CREATE INDEX stage_record_matching ON mdm.stage_record USING gin ((((reading -> 'provenance'::text) -> 'matching'::text)) jsonb_path_ops) WITH (fastupdate=off);

COMMENT ON INDEX mdm.stage_record_matching IS 'Finds current candidate readings through configured matching metadata paths, one key per indexed probe, with no pending list. The caller checks exact scalar/array positions after containment.';

CREATE INDEX stage_record_name_count_lei ON mdm.stage_record USING btree ((((((((reading -> 'provenance'::text) -> 'matching'::text) -> 'name_count'::text) -> 'leis'::text) -> 0) ->> 0)));

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.attempt_event FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.batch FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.dataset FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.dataset_mapping FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.decision FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.master_entity FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.match_proposal FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.match_proposal_event FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.migration FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.outbox_event FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.policy FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.run_batch FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.set_aside_record FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.source_reading FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER master_entity_configured_kind BEFORE INSERT OR UPDATE OF kind ON mdm.master_entity FOR EACH ROW EXECUTE FUNCTION mdm.require_configured_kind();

ALTER TABLE ONLY mdm.batch_change
    ADD CONSTRAINT batch_change_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.batch
    ADD CONSTRAINT batch_policy_digest_fkey FOREIGN KEY (policy_digest) REFERENCES mdm.policy(digest);

ALTER TABLE ONLY mdm.checkpoint
    ADD CONSTRAINT checkpoint_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.company_alias
    ADD CONSTRAINT company_alias_alias_id_fkey FOREIGN KEY (alias_id) REFERENCES mdm.master_entity(entity_id);

ALTER TABLE ONLY mdm.company_alias
    ADD CONSTRAINT company_alias_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.company_alias
    ADD CONSTRAINT company_alias_canonical_id_fkey FOREIGN KEY (canonical_id) REFERENCES mdm.master_entity(entity_id);

ALTER TABLE ONLY mdm.company_alias
    ADD CONSTRAINT company_alias_from_generation_fkey FOREIGN KEY (from_generation) REFERENCES mdm.batch(generation);

ALTER TABLE ONLY mdm.company_alias
    ADD CONSTRAINT company_alias_to_generation_fkey FOREIGN KEY (to_generation) REFERENCES mdm.batch(generation);

ALTER TABLE ONLY mdm.company
    ADD CONSTRAINT company_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.company
    ADD CONSTRAINT company_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES mdm.master_entity(entity_id);

ALTER TABLE ONLY mdm.company
    ADD CONSTRAINT company_from_generation_fkey FOREIGN KEY (from_generation) REFERENCES mdm.batch(generation);

ALTER TABLE ONLY mdm.company
    ADD CONSTRAINT company_to_generation_fkey FOREIGN KEY (to_generation) REFERENCES mdm.batch(generation);

ALTER TABLE ONLY mdm.current_record
    ADD CONSTRAINT current_record_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.dataset_mapping
    ADD CONSTRAINT dataset_mapping_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

ALTER TABLE ONLY mdm.decision
    ADD CONSTRAINT decision_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.detail_version
    ADD CONSTRAINT detail_version_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.master_entity
    ADD CONSTRAINT master_entity_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.master_entity
    ADD CONSTRAINT master_entity_kind_fkey FOREIGN KEY (kind) REFERENCES mdm.master_kind(kind);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES mdm.match_proposal(assessment_id);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.outbox
    ADD CONSTRAINT outbox_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.outbox_event
    ADD CONSTRAINT outbox_event_batch_id_consumer_fkey FOREIGN KEY (batch_id, consumer) REFERENCES mdm.outbox(batch_id, consumer);

ALTER TABLE ONLY mdm.relationship_version
    ADD CONSTRAINT relationship_version_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.run_batch
    ADD CONSTRAINT run_batch_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_assertion_id_fkey FOREIGN KEY (assertion_id) REFERENCES mdm.source_reading(assertion_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES mdm.master_entity(entity_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

INSERT INTO mdm.master_kind VALUES ('company', true);
INSERT INTO mdm.master_kind VALUES ('person', true);
INSERT INTO mdm.master_kind VALUES ('security', true);
INSERT INTO mdm.master_kind VALUES ('fund_structure', true);
INSERT INTO mdm.master_kind VALUES ('branch', true);
INSERT INTO mdm.master_kind VALUES ('government', true);
INSERT INTO mdm.master_kind VALUES ('international_organization', true);
INSERT INTO mdm.master_kind VALUES ('venue', true);

