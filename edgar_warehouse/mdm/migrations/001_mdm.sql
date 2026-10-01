-- MDM schema baseline.
--
-- The schema MDM keeps its master data in, created in one file. It replaces
-- the Clean MDM migrations 023-043 (schema mdm_v2), which built the same
-- tables step by step; this file is their end state, re-baselined under the
-- business names the operator chose on 2026-09-30 (platform validation
-- slice 3). Later changes are new numbered files, applied once each by
-- `mdm migrate` (edgar_warehouse/mdm/clean/store.py).
--
-- Contents, in order: tables and their keys, functions, views (including the
-- per-kind views, generated), indexes, triggers, then a comment on every
-- object. Run as the migration owner; the application login gets only
-- SELECT and EXECUTE on the functions store.migrate grants.


-- Schema --------------------------------------------------------------------

CREATE SCHEMA mdm;

-- Tables --------------------------------------------------------------------

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

CREATE TABLE mdm.match_proposal (
    assessment_id text NOT NULL,
    body jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_xid xid8 DEFAULT pg_current_xact_id() NOT NULL
);

CREATE TABLE mdm.match_proposal_event (
    event_id bigint NOT NULL,
    assessment_id text NOT NULL,
    run_id uuid NOT NULL,
    event text NOT NULL,
    batch_id text,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT match_proposal_event_event_check CHECK ((event = ANY (ARRAY['ready'::text, 'rejected'::text, 'observed'::text, 'superseded'::text, 'applied'::text])))
);

ALTER TABLE mdm.match_proposal_event ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME mdm.match_proposal_event_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

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

CREATE TABLE mdm.current_record (
    object_type text NOT NULL,
    object_id text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL,
    CONSTRAINT current_record_object_type_check CHECK ((object_type = ANY (ARRAY['entity'::text, 'relationship'::text, 'review'::text])))
);

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
    sic_description text,
    state_of_incorporation text,
    fiscal_year_end text,
    description text,
    jurisdiction text,
    address jsonb,
    gleif_legal_form text,
    gleif_entity_status text,
    gleif_registration_status text,
    gleif_initial_registration text,
    gleif_last_update text,
    gleif_next_renewal text,
    gleif_managing_lou text,
    gleif_validation_source text,
    gleif_registration_authority text,
    gleif_registration_authority_entity_id text,
    gleif_entity_creation_date text,
    fields jsonb NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT company_check CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT company_check1 CHECK (((valid_to IS NULL) OR (valid_from < valid_to))),
    CONSTRAINT company_check2 CHECK (((to_generation IS NULL) OR (from_generation < to_generation))),
    CONSTRAINT company_status_check CHECK ((status = ANY (ARRAY['accepted'::text, 'review'::text])))
);

CREATE TABLE mdm.company_alias (
    alias_id uuid NOT NULL,
    canonical_id uuid NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL,
    CONSTRAINT company_alias_check CHECK ((alias_id <> canonical_id)),
    CONSTRAINT company_alias_check1 CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT company_alias_check2 CHECK (((valid_to IS NULL) OR (valid_from < valid_to))),
    CONSTRAINT company_alias_check3 CHECK (((to_generation IS NULL) OR (from_generation < to_generation)))
);

CREATE TABLE mdm.dataset (
    source_code text NOT NULL,
    registry_version uuid NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT dataset_body_check CHECK ((body ?& ARRAY['provider'::text, 'family'::text, 'schema_version'::text, 'record_key'::text, 'publication_key'::text, 'effective_time'::text, 'semantics'::text, 'registry_evidence'::text]))
);

CREATE TABLE mdm.dataset_mapping (
    source_code text NOT NULL,
    mapping_version bigint NOT NULL,
    body jsonb NOT NULL,
    registry_version uuid NOT NULL,
    registered_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dataset_mapping_body_check CHECK ((jsonb_typeof(body) = 'object'::text)),
    CONSTRAINT dataset_mapping_mapping_version_check CHECK ((mapping_version >= 1))
);

CREATE TABLE mdm.decision (
    decision_id text NOT NULL,
    operation text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL,
    CONSTRAINT decision_operation_check CHECK ((operation = ANY (ARRAY['bind'::text, 'merge'::text, 'reverse'::text, 'override'::text, 'revoke'::text, 'exclude'::text, 'retire_source'::text, 'quarantine'::text])))
);

CREATE TABLE mdm.set_aside_record (
    deferred_id text NOT NULL,
    source_code text NOT NULL,
    publication_key text NOT NULL,
    record_locator text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL
);

CREATE TABLE mdm.master_entity (
    entity_id uuid NOT NULL,
    kind text NOT NULL,
    published_at timestamp with time zone NOT NULL,
    batch_id text NOT NULL,
    CONSTRAINT master_entity_kind_check CHECK ((kind = ANY (ARRAY['company'::text, 'person'::text, 'security'::text, 'fund_structure'::text, 'branch'::text, 'government'::text, 'international_organization'::text, 'venue'::text])))
);

CREATE TABLE mdm.migration (
    name text NOT NULL,
    checksum text NOT NULL,
    installed_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE mdm.run_batch (
    run_id uuid NOT NULL,
    batch_id text NOT NULL
);

CREATE TABLE mdm.policy (
    digest text NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT policy_body_check CHECK ((jsonb_typeof(body) = 'object'::text))
);

CREATE TABLE mdm.outbox (
    batch_id text NOT NULL,
    consumer text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fence bigint DEFAULT 0 NOT NULL,
    lease_until timestamp with time zone,
    worker text,
    verified_at timestamp with time zone
);

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

ALTER TABLE mdm.outbox_event ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME mdm.outbox_event_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

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

-- Keys and checks -----------------------------------------------------------

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_pkey PRIMARY KEY (assertion_id);

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_one_per_publication_and_mapping UNIQUE (source_code, record_key, publication_key, mapping_version);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_assessment_id_run_id_event_key UNIQUE (assessment_id, run_id, event);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY mdm.match_proposal
    ADD CONSTRAINT match_proposal_pkey PRIMARY KEY (assessment_id);

ALTER TABLE ONLY mdm.attempt_event
    ADD CONSTRAINT attempt_event_pkey PRIMARY KEY (attempt_id, event);

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

ALTER TABLE ONLY mdm.dataset_mapping
    ADD CONSTRAINT dataset_mapping_pkey PRIMARY KEY (source_code, mapping_version);

ALTER TABLE ONLY mdm.dataset
    ADD CONSTRAINT dataset_pkey PRIMARY KEY (source_code);

ALTER TABLE ONLY mdm.decision
    ADD CONSTRAINT decision_pkey PRIMARY KEY (decision_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_pkey PRIMARY KEY (deferred_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_source_code_publication_key_record_locator_key UNIQUE (source_code, publication_key, record_locator);

ALTER TABLE ONLY mdm.master_entity
    ADD CONSTRAINT master_entity_pkey PRIMARY KEY (entity_id);

ALTER TABLE ONLY mdm.migration
    ADD CONSTRAINT migration_pkey PRIMARY KEY (name);

ALTER TABLE ONLY mdm.run_batch
    ADD CONSTRAINT run_batch_pkey PRIMARY KEY (run_id, batch_id);

ALTER TABLE ONLY mdm.policy
    ADD CONSTRAINT policy_pkey PRIMARY KEY (digest);

ALTER TABLE ONLY mdm.current_record
    ADD CONSTRAINT current_record_pkey PRIMARY KEY (object_type, object_id);

ALTER TABLE ONLY mdm.outbox_event
    ADD CONSTRAINT outbox_event_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY mdm.outbox
    ADD CONSTRAINT outbox_pkey PRIMARY KEY (batch_id, consumer);

ALTER TABLE ONLY mdm.run
    ADD CONSTRAINT run_pkey PRIMARY KEY (run_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_pkey PRIMARY KEY (source_code, record_key);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_subject_key UNIQUE (subject);

-- References between tables -------------------------------------------------

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.source_reading
    ADD CONSTRAINT source_reading_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES mdm.match_proposal(assessment_id);

ALTER TABLE ONLY mdm.match_proposal_event
    ADD CONSTRAINT match_proposal_event_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

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

ALTER TABLE ONLY mdm.dataset_mapping
    ADD CONSTRAINT dataset_mapping_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

ALTER TABLE ONLY mdm.decision
    ADD CONSTRAINT decision_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.set_aside_record
    ADD CONSTRAINT set_aside_record_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);

ALTER TABLE ONLY mdm.master_entity
    ADD CONSTRAINT master_entity_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.run_batch
    ADD CONSTRAINT run_batch_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.current_record
    ADD CONSTRAINT current_record_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.outbox
    ADD CONSTRAINT outbox_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.outbox_event
    ADD CONSTRAINT outbox_event_batch_id_consumer_fkey FOREIGN KEY (batch_id, consumer) REFERENCES mdm.outbox(batch_id, consumer);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_assertion_id_fkey FOREIGN KEY (assertion_id) REFERENCES mdm.source_reading(assertion_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES mdm.batch(batch_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES mdm.master_entity(entity_id);

ALTER TABLE ONLY mdm.stage_record
    ADD CONSTRAINT stage_record_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);


--
-- PostgreSQL database dump complete
--

-- Functions -----------------------------------------------------------------

CREATE FUNCTION mdm.match_proposal_snapshot(scope jsonb) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'mdm'
    SET "TimeZone" TO 'UTC'
    AS $$
DECLARE keys text[]; sources text[]; snapshot jsonb; n integer;
BEGIN
    IF jsonb_typeof(scope->'keys') IS DISTINCT FROM 'array'
       OR jsonb_typeof(scope->'sources') IS DISTINCT FROM 'array'
       OR jsonb_array_length(scope->'keys')>50000 OR jsonb_array_length(scope->'sources')>10000 THEN
        RAISE EXCEPTION 'Invalid assessment scope';
    END IF;
    SELECT array_agg(value) INTO keys FROM jsonb_array_elements_text(scope->'keys');
    SELECT array_agg(value) INTO sources FROM jsonb_array_elements_text(scope->'sources');
    WITH evidence AS (
        SELECT assertion_id AS id,body FROM mdm.source_reading
        WHERE body->>'subject'=ANY(keys) OR EXISTS(
            SELECT 1 FROM jsonb_array_elements(body->'relationships') r WHERE r->>'target_subject'=ANY(keys))
        LIMIT 10001
    ), decisions AS (
        SELECT decision_id AS id,body FROM mdm.decision
        WHERE decision_id=ANY(keys) OR body->>'subject'=ANY(keys) OR body->>'entity_id'=ANY(keys)
           OR body->>'left'=ANY(keys) OR body->>'right'=ANY(keys) OR body->>'target'=ANY(keys)
           OR (operation='retire_source' AND body->>'source_code'=ANY(sources))
        LIMIT 10001
    ), identities AS (
        SELECT entity_id::text AS id,to_jsonb(i) AS body FROM mdm.master_entity i
        WHERE entity_id::text=ANY(keys) LIMIT 10001
    ), projections AS (
        -- Entities are read from current_entity, which holds the
        -- Companies; relationships and reviews stay in current_record.
        SELECT id,body FROM (
            SELECT 'entity/'||object_id AS id,body FROM mdm.current_entity
            WHERE object_id=ANY(keys)
            UNION ALL
            SELECT object_type||'/'||object_id,body FROM mdm.current_record
            WHERE (object_type='relationship' AND (body->>'source_id'=ANY(keys) OR body->>'target_id'=ANY(keys)))
               OR (object_type='review' AND (body->>'entity_id'=ANY(keys) OR body->>'subject'=ANY(keys)
                   OR body->'affected_subjects' ?| keys))
        ) scoped LIMIT 10001
    ), all_rows AS (
        SELECT 'source_reading' AS kind,id,body FROM evidence UNION ALL
        SELECT 'decision',id,body FROM decisions UNION ALL
        SELECT 'master_entity',id,body FROM identities UNION ALL
        SELECT 'current_record',id,body FROM projections
    ) SELECT count(*),coalesce(jsonb_agg(to_jsonb(a) ORDER BY kind,id),'[]') INTO n,snapshot FROM all_rows a;
    IF n>30000 THEN RAISE EXCEPTION 'Assessment snapshot exceeds bounded budget'; END IF;
    -- Individual branches may not be silently truncated, even below total cap.
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot) r GROUP BY r->>'kind' HAVING count(*)>10000) THEN
        RAISE EXCEPTION 'Assessment snapshot exceeds bounded budget';
    END IF;
    snapshot := jsonb_build_object('rows',snapshot,'checkpoint',coalesce(
        (SELECT position FROM mdm.checkpoint WHERE consumer=scope->>'consumer'
            AND source_family=coalesce(scope->>'source_family','')
            AND publication_family=coalesce(scope->>'publication_family','')),0));
    RETURN encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
END;
$$;

CREATE FUNCTION mdm.claim_outbox(destination text, owner_name text, lease_seconds integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE p mdm.outbox%ROWTYPE;
BEGIN
    IF lease_seconds NOT BETWEEN 1 AND 3600 OR nullif(owner_name,'') IS NULL THEN RAISE EXCEPTION 'Invalid lease'; END IF;
    -- Preserve generation order per consumer; an unexpired earlier claim blocks later delivery.
    SELECT q.* INTO p FROM mdm.outbox q JOIN mdm.batch b USING(batch_id)
      WHERE q.consumer=destination AND q.verified_at IS NULL ORDER BY b.generation LIMIT 1 FOR UPDATE OF q;
    IF NOT FOUND OR p.lease_until > clock_timestamp() THEN RETURN NULL; END IF;
    UPDATE mdm.outbox SET fence=fence+1,worker=owner_name,
      lease_until=clock_timestamp()+make_interval(secs=>lease_seconds)
      WHERE batch_id=p.batch_id AND consumer=p.consumer RETURNING * INTO p;
    INSERT INTO mdm.outbox_event(batch_id,consumer,fence,event,detail)
      VALUES(p.batch_id,p.consumer,p.fence,'claimed',jsonb_build_object('worker',owner_name));
    RETURN to_jsonb(p);
END;
$$;

CREATE FUNCTION mdm.save_batch(request_text text, root_run uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE r jsonb := request_text::jsonb; b jsonb; result jsonb; key text := r->>'assessment_id';
BEGIN
    PERFORM pg_advisory_xact_lock(730234);
    -- A batch already saved stays replayable.
    IF EXISTS(SELECT 1 FROM mdm.batch WHERE batch_id=r->>'batch_id') THEN
        RETURN mdm.write_batch(request_text,root_run);
    END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(r->'decisions') d WHERE d->>'operation' IN ('bind','merge')) THEN
        SELECT body INTO b FROM mdm.match_proposal WHERE assessment_id=key;
        IF b IS NULL OR b->>'outcome' IS DISTINCT FROM 'ready'
           OR EXISTS(SELECT 1 FROM mdm.match_proposal WHERE assessment_id=key AND created_xid=pg_current_xact_id())
           OR EXISTS(SELECT 1 FROM mdm.match_proposal_event WHERE assessment_id=key AND event IN ('applied','superseded')) THEN
            RAISE EXCEPTION 'Identity decision requires a ready assessment';
        END IF;
        IF (r - 'assessment_id' - 'expected_generation') IS DISTINCT FROM b->'effects' THEN
            RAISE EXCEPTION 'Command differs from assessed effects';
        END IF;
        IF b->>'snapshot' IS DISTINCT FROM mdm.match_proposal_snapshot(b->'scope') THEN
            RAISE EXCEPTION USING ERRCODE='P0A01', MESSAGE='Stale identity assessment';
        END IF;
        -- A rule's new Company is published after every stored master
        -- entity of its kind.
        IF EXISTS(
            SELECT 1 FROM jsonb_array_elements(coalesce(b->'automatic'->'identities','[]')) i
            WHERE (i->>'published_at')::timestamptz
                  <= (SELECT max(published_at) FROM mdm.master_entity WHERE kind=i->>'kind')) THEN
            RAISE EXCEPTION 'A new Company would be published at or before an identity of its kind already stored';
        END IF;
    ELSIF key IS NOT NULL THEN
        RAISE EXCEPTION 'Assessment supplied without an identity proposal';
    END IF;
    result := mdm.write_batch(request_text,root_run);
    IF key IS NOT NULL THEN
        INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event,batch_id)
            VALUES(key,root_run,'applied',r->>'batch_id');
    END IF;
    -- The batch is saved, so no other match proposal of it can
    -- apply; close every one still open.
    INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event,batch_id)
    SELECT a.assessment_id, root_run, 'superseded', r->>'batch_id'
    FROM mdm.match_proposal a
    WHERE a.body->'command'->>'batch_id' = r->>'batch_id'
      AND a.assessment_id IS DISTINCT FROM key
      AND a.body->>'outcome' = 'ready'
      AND NOT EXISTS(SELECT 1 FROM mdm.match_proposal_event e
                     WHERE e.assessment_id = a.assessment_id
                       AND e.event IN ('applied','superseded'))
    ON CONFLICT DO NOTHING;
    RETURN result;
END;
$$;

CREATE FUNCTION mdm.write_batch(request_text text, root_run uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE r jsonb := request_text::jsonb; item jsonb; src mdm.dataset%ROWTYPE;
    result jsonb; old mdm.set_aside_record%ROWTYPE;
    h text := encode(sha256(convert_to(request_text,'UTF8')),'hex');
    prior mdm.batch%ROWTYPE;
    current_generation bigint;
    next_generation bigint;
    pos bigint;
    outputs jsonb;
    required jsonb;
    delivered jsonb;
BEGIN
    IF coalesce(jsonb_array_length(r->'deferred'),0)>1000 OR
       coalesce(jsonb_array_length(r->'deferred'),0)+coalesce(jsonb_array_length(r->'assertions'),0)>1000 THEN
        RAISE EXCEPTION 'Unbounded source records';
    END IF;
    IF (r ? 'source_accounting' OR coalesce(jsonb_array_length(r->'deferred'),0)>0)
       AND r->'source_accounting' IS DISTINCT FROM jsonb_build_object(
           'normalized',coalesce(jsonb_array_length(r->'assertions'),0),
           'deferred',coalesce(jsonb_array_length(r->'deferred'),0),
           'total',coalesce(jsonb_array_length(r->'assertions'),0)+coalesce(jsonb_array_length(r->'deferred'),0)) THEN
        RAISE EXCEPTION 'Invalid source accounting';
    END IF;
    -- Save the batch itself: bounds, the batch row, source readings, master
    -- entities, decisions, current records, the checkpoint and the outbox.
    -- A batch saved before (same key, same content) is not written again.
    <<core>>
    BEGIN
        IF root_run IS NULL OR octet_length(request_text) > 16777216
           OR coalesce(jsonb_array_length(r->'assertions'),0) > 1000
           OR coalesce(jsonb_array_length(r->'decisions'),0) > 1000
           OR coalesce(jsonb_array_length(r->'projections'),0) > 10000 THEN
            RAISE EXCEPTION 'Invalid or unbounded batch';
        END IF;
        IF coalesce(r->>'source_family','')<>'' AND NOT EXISTS(
            SELECT 1 FROM mdm.dataset WHERE body->>'family'=r->>'source_family'
              AND body->'publication_families' ? (r->>'publication_family')) THEN
            RAISE EXCEPTION 'Unknown publication family contract';
        END IF;
        PERFORM pg_advisory_xact_lock(730234);
        SELECT * INTO prior FROM mdm.batch WHERE batch_id = r->>'batch_id';
        IF FOUND THEN
            IF prior.request_hash <> h THEN RAISE EXCEPTION 'Batch key reused with different content'; END IF;
            INSERT INTO mdm.run_batch VALUES(root_run,prior.batch_id) ON CONFLICT DO NOTHING;
            result := jsonb_build_object('batch_id',prior.batch_id,'generation',prior.generation,'duplicate',true);
            EXIT core;
        END IF;
        SELECT coalesce(max(generation),0) INTO current_generation FROM mdm.batch;
        IF (r->>'expected_generation')::bigint IS DISTINCT FROM current_generation THEN
            RAISE EXCEPTION 'Stale generation';
        END IF;
        SELECT coalesce((SELECT position FROM mdm.checkpoint WHERE consumer=r->>'consumer'
            AND source_family=coalesce(r->>'source_family','')
            AND publication_family=coalesce(r->>'publication_family','')),0) INTO pos;
        IF (r->>'expected_checkpoint')::bigint IS DISTINCT FROM pos
           OR (r->>'checkpoint')::bigint IS NULL OR (r->>'checkpoint')::bigint <= pos THEN
            RAISE EXCEPTION 'Stale or nonadvancing checkpoint';
        END IF;
        SELECT body->'required_consumers' INTO required FROM mdm.policy WHERE digest=r->>'policy_digest';
        IF required IS NULL OR jsonb_array_length(required)=0 THEN RAISE EXCEPTION 'Missing frozen consumer contract'; END IF;
        next_generation := current_generation+1;
        INSERT INTO mdm.batch VALUES(r->>'batch_id',h,root_run,r->>'policy_digest',next_generation,
            r->>'consumer',(r->>'checkpoint')::bigint,r,now());
        INSERT INTO mdm.run_batch VALUES(root_run,r->>'batch_id');
        FOR item IN SELECT value FROM jsonb_array_elements(r->'assertions') LOOP
            SELECT * INTO src FROM mdm.dataset WHERE source_code=item->>'source_code';
            IF NOT FOUND OR src.body->'registry_evidence'->>'status' IS DISTINCT FROM 'active'
               OR src.body->'registry_evidence'->>'version_id' IS DISTINCT FROM src.registry_version::text
               OR src.body->'registry_evidence'->>'source_family' IS DISTINCT FROM src.body->>'family' THEN
                RAISE EXCEPTION 'Dataset has no pinned registry authority';
            END IF;
            IF NOT EXISTS(SELECT 1 FROM mdm.dataset_mapping m
                WHERE m.source_code=item->>'source_code'
                  AND m.mapping_version=coalesce((item->>'mapping_version')::bigint,1)
                  AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
                RAISE EXCEPTION 'Unsupported source schema';
            END IF;
            IF EXISTS(SELECT 1 FROM mdm.source_reading a WHERE a.assertion_id=item->>'assertion_id' AND a.body<>item) THEN
                RAISE EXCEPTION 'Assertion identity collision';
            END IF;
            INSERT INTO mdm.source_reading(assertion_id,source_code,record_key,publication_key,
              revision,effective_at,body,batch_id,mapping_version)
              VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
              item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id',
              coalesce((item->>'mapping_version')::bigint,1))
              ON CONFLICT(assertion_id) DO NOTHING;
        END LOOP;
        FOR item IN SELECT value FROM jsonb_array_elements(r->'identities') LOOP
            INSERT INTO mdm.master_entity VALUES((item->>'entity_id')::uuid,item->>'kind',
              (item->>'published_at')::timestamptz,r->>'batch_id');
        END LOOP;
        FOR item IN SELECT value FROM jsonb_array_elements(r->'decisions') LOOP
            IF nullif(item->>'actor','') IS NULL OR nullif(item->>'reason','') IS NULL THEN
                RAISE EXCEPTION 'Decision requires actor and reason';
            END IF;
            INSERT INTO mdm.decision VALUES(item->>'decision_id',item->>'operation',item,r->>'batch_id');
        END LOOP;
        FOR item IN SELECT value FROM jsonb_array_elements(r->'projections') LOOP
            -- A Company is kept in the Company table only. The batch row
            -- above holds this commit's generation; now() is its created_at.
            IF item->>'object_type'='entity' AND item->'body'->>'kind'='company' THEN
                PERFORM mdm.record_company_version(item->'body',r->>'batch_id',now());
            ELSE
                INSERT INTO mdm.current_record VALUES(item->>'object_type',item->>'object_id',item->'body',r->>'batch_id')
                ON CONFLICT(object_type,object_id) DO UPDATE SET body=excluded.body,batch_id=excluded.batch_id;
            END IF;
        END LOOP;
        INSERT INTO mdm.checkpoint(consumer,position,batch_id,source_family,publication_family,committed_publication,continuity_proof)
        VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id',coalesce(r->>'source_family',''),
            coalesce(r->>'publication_family',''),r->>'committed_publication',r->'continuity_proof')
        ON CONFLICT(consumer,source_family,publication_family) DO UPDATE SET position=excluded.position,
            batch_id=excluded.batch_id,committed_publication=excluded.committed_publication,continuity_proof=excluded.continuity_proof;
        outputs := jsonb_build_object('contract_version',2,'generation',next_generation,'run_id',root_run,
           'policy_digest',r->>'policy_digest','objects',r->'projections');
        FOR item IN SELECT value FROM jsonb_array_elements(required) LOOP
            delivered := CASE WHEN item#>>'{}'='journal' THEN outputs || jsonb_build_object('effects',r) ELSE outputs END;
            INSERT INTO mdm.outbox(batch_id,consumer,payload,payload_hash)
            VALUES(r->>'batch_id',item#>>'{}',delivered,encode(sha256(convert_to(delivered::text,'UTF8')),'hex'));
        END LOOP;
        result := jsonb_build_object('batch_id',r->>'batch_id','generation',next_generation,'duplicate',false);
    END core;
    FOR item IN SELECT value FROM jsonb_array_elements(coalesce(r->'deferred','[]')) LOOP
        IF NOT (item ?& ARRAY['deferred_id','source_code','publication_key','record_locator','schema_version','reason','raw_record','provenance'])
           OR item->>'deferred_id' IS NULL OR item->>'record_locator' IS NULL
           OR item->>'publication_key' IS NULL OR item->>'reason' IS NULL THEN
            RAISE EXCEPTION 'Invalid deferred source evidence';
        END IF;
        SELECT * INTO src FROM mdm.dataset WHERE source_code=item->>'source_code';
        IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM mdm.dataset_mapping m
            WHERE m.source_code=item->>'source_code'
              AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
            RAISE EXCEPTION 'Unknown deferred dataset contract';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(r->'projections','[]')) p
            WHERE p->>'object_type'='review' AND p->>'object_id'=item->>'deferred_id'
              AND p->'body'->>'deferred_id'=item->>'deferred_id'
              AND p->'body'->'open'='true'::jsonb
              AND p->'body'->'blocking'=to_jsonb(NOT (coalesce(src.body->'nonblocking_deferred_reasons','[]'::jsonb) ? (item->>'reason')))
              AND coalesce(p->'body'->'retired','false'::jsonb)='false'::jsonb
        ) THEN
            RAISE EXCEPTION 'Deferred evidence requires an open review with its registered blocking disposition';
        END IF;
        INSERT INTO mdm.set_aside_record VALUES(item->>'deferred_id',item->>'source_code',
            item->>'publication_key',item->>'record_locator',item,r->>'batch_id') ON CONFLICT DO NOTHING;
        SELECT * INTO old FROM mdm.set_aside_record WHERE source_code=item->>'source_code'
            AND publication_key=item->>'publication_key' AND record_locator=item->>'record_locator';
        IF NOT FOUND OR old.body IS DISTINCT FROM item THEN
            RAISE EXCEPTION 'Deferred source publication collision';
        END IF;
    END LOOP;
    -- Inspect only touched reviews. Untouched durable reviews were validated
    -- when committed; rescanning all retained source evidence is unbounded.
    -- No caller may close or reclassify a prior set-aside review.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(coalesce(r->'projections','[]')) changed
        JOIN mdm.set_aside_record d ON changed->>'object_type'='review'
          AND changed->>'object_id'=d.deferred_id
        JOIN mdm.dataset ds ON ds.source_code=d.source_code
        LEFT JOIN mdm.current_record p ON p.object_type='review' AND p.object_id=d.deferred_id
        WHERE p.body->>'deferred_id' IS DISTINCT FROM d.deferred_id
           OR p.body->'open' IS DISTINCT FROM 'true'::jsonb
           OR p.body->'blocking' IS DISTINCT FROM to_jsonb(NOT (coalesce(ds.body->'nonblocking_deferred_reasons','[]'::jsonb) ? (d.body->>'reason')))
           OR coalesce(p.body->'retired','false'::jsonb) IS DISTINCT FROM 'false'::jsonb
    ) THEN
        RAISE EXCEPTION 'Deferred evidence requires its registered open review disposition';
    END IF;
    IF coalesce((result->>'duplicate')::boolean, false) IS FALSE THEN
        PERFORM mdm.keep_stage(r);
    END IF;
    RETURN result;
END;
$$;

CREATE FUNCTION mdm.finish_outbox(batch_key text, destination text, token bigint, verified_hash text, failure text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE p mdm.outbox%ROWTYPE;
BEGIN
    SELECT * INTO p FROM mdm.outbox WHERE batch_id=batch_key AND consumer=destination FOR UPDATE;
    IF NOT FOUND OR p.verified_at IS NOT NULL OR p.fence<>token OR p.lease_until<=clock_timestamp() OR p.lease_until IS NULL THEN
        RAISE EXCEPTION 'Stale publication fence';
    END IF;
    IF failure IS NULL AND verified_hash IS DISTINCT FROM p.payload_hash THEN RAISE EXCEPTION 'Unverified publication'; END IF;
    INSERT INTO mdm.outbox_event(batch_id,consumer,fence,event,detail)
      VALUES(batch_key,destination,token,CASE WHEN failure IS NULL THEN 'verified' ELSE 'failed' END,
        jsonb_build_object('hash',verified_hash,'error',failure));
    UPDATE mdm.outbox SET verified_at=CASE WHEN failure IS NULL THEN clock_timestamp() ELSE NULL END,
      lease_until=NULL,worker=NULL WHERE batch_id=batch_key AND consumer=destination;
END;
$$;

CREATE FUNCTION mdm.finish_run(root_run uuid, body jsonb, complete boolean) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE current_status text;
BEGIN
    IF root_run IS NULL OR body IS NULL OR jsonb_typeof(body)<>'object' OR complete IS NULL THEN
        RAISE EXCEPTION 'Invalid run report';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(root_run::text,43));
    SELECT status INTO current_status FROM mdm.run WHERE run_id=root_run;
    IF NOT FOUND THEN RAISE EXCEPTION 'Root run was not registered'; END IF;
    IF current_status='succeeded' THEN RETURN; END IF;
    UPDATE mdm.run SET report=body,
        status=CASE WHEN complete THEN 'succeeded' ELSE 'running' END,
        completed_at=CASE WHEN complete THEN now() ELSE NULL END
    WHERE run_id=root_run;
END;
$$;

CREATE FUNCTION mdm.immutable_row() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'Clean MDM evidence and decisions are append-only'; END;
$$;

CREATE FUNCTION mdm.keep_stage(r jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $_$
DECLARE
    item jsonb;
BEGIN
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o
        WHERE jsonb_typeof(o) IS DISTINCT FROM 'object'
           OR (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(o) k)
              IS DISTINCT FROM ARRAY['assertion_id','locator','object','sha256']
           OR EXISTS (SELECT 1 FROM unnest(ARRAY['assertion_id','locator','object','sha256']) k
                      WHERE jsonb_typeof(o->k) IS DISTINCT FROM 'string')
           OR nullif(o->>'object','') IS NULL OR nullif(o->>'locator','') IS NULL
           OR coalesce(o->>'sha256','') !~ '^[0-9a-f]{64}$')
       OR EXISTS (
        SELECT o->>'assertion_id' FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o
        EXCEPT
        SELECT x->>'assertion_id' FROM jsonb_array_elements(coalesce(r->'assertions','[]')) x)
       OR (SELECT count(*) FROM jsonb_array_elements(coalesce(r->'occurrences','[]')))
          IS DISTINCT FROM (SELECT count(DISTINCT o->>'assertion_id')
                            FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o) THEN
        RAISE EXCEPTION 'Invalid bronze occurrence';
    END IF;
    -- item is [the stored reading, its occurrence or null]. Readings are
    -- found by id from the batch, never by scanning the source_reading table.
    FOR item IN
        WITH named AS (
            SELECT coalesce(jsonb_object_agg(o->>'assertion_id', o), '{}'::jsonb) AS by_id
            FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o)
        SELECT jsonb_build_array(s.body, named.by_id->s.assertion_id)
        FROM jsonb_array_elements(coalesce(r->'assertions','[]')) x
        JOIN mdm.source_reading s
          ON s.assertion_id = x->>'assertion_id' AND s.batch_id = r->>'batch_id'
        CROSS JOIN named
        ORDER BY s.source_code, s.record_key, s.revision, s.mapping_version,
                 s.publication_key, s.assertion_id
    LOOP
        PERFORM mdm.record_stage(item->0, r->>'batch_id',
            CASE WHEN jsonb_typeof(item->1) = 'object' THEN item->1 END);
    END LOOP;
    -- Revocations first (ticket 13): a record whose bind is revoked is
    -- unbound before this batch binds it again, to the same Company or
    -- another. A bind this same batch revokes is never kept.
    FOR item IN
        SELECT value FROM jsonb_array_elements(coalesce(r->'decisions','[]'))
        WHERE value->>'operation' = 'revoke'
    LOOP
        PERFORM mdm.release_binding(item);
    END LOOP;
    FOR item IN
        SELECT b.value FROM jsonb_array_elements(coalesce(r->'decisions','[]')) b
        WHERE b.value->>'operation' = 'bind'
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(r->'decisions','[]')) v
            WHERE v.value->>'operation' = 'revoke' AND v.value->>'target' = b.value->>'decision_id')
    LOOP
        PERFORM mdm.record_binding(item);
    END LOOP;
END;
$_$;

CREATE FUNCTION mdm.preview_batch(request_text text, root_run uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE result jsonb;
BEGIN
    BEGIN
        result := mdm.write_batch(request_text,root_run);
        RAISE EXCEPTION USING ERRCODE='P0P01', MESSAGE='preview rollback';
    EXCEPTION WHEN SQLSTATE 'P0P01' THEN
        RETURN result;
    END;
END;
$$;

CREATE FUNCTION mdm.record_match_proposal(body_text text, root_run uuid) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE b jsonb := body_text::jsonb; key text := encode(sha256(convert_to(body_text,'UTF8')),'hex');
    caller jsonb := coalesce(b->'command'->'decisions','[]'::jsonb);
    automatic jsonb := coalesce(b->'automatic'->'decisions','[]'::jsonb);
BEGIN
    IF root_run IS NULL OR octet_length(body_text)>16777216
       OR NOT (b ?& ARRAY['version','command','outcome','rule_version'])
       OR b->>'version' IS DISTINCT FROM '1'
       OR b->>'outcome' NOT IN ('ready','rejected') OR b->>'outcome' IS NULL
       OR jsonb_typeof(caller) IS DISTINCT FROM 'array'
       OR jsonb_typeof(automatic) IS DISTINCT FROM 'array'
       OR jsonb_array_length(caller) > 1000
       OR jsonb_array_length(automatic) > 1000
       OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(caller || automatic) d WHERE d->>'operation' IN ('bind','merge')) THEN
        RAISE EXCEPTION 'Invalid or unbounded identity assessment';
    END IF;
    IF b->>'outcome'='ready' AND (
        jsonb_typeof(b->'effects') IS DISTINCT FROM 'object' OR NOT (b ?& ARRAY['scope','snapshot'])
        OR b->'effects'->>'policy_digest' IS DISTINCT FROM b->'command'->>'policy_digest'
        OR b->'effects'->>'batch_id' IS DISTINCT FROM b->'command'->>'batch_id') THEN
        RAISE EXCEPTION 'Ready assessment requires proposed effects and dependency snapshot';
    END IF;
    INSERT INTO mdm.match_proposal(assessment_id,body) VALUES(key,b) ON CONFLICT DO NOTHING;
    IF NOT EXISTS(SELECT 1 FROM mdm.match_proposal WHERE assessment_id=key AND body=b) THEN
        RAISE EXCEPTION 'Assessment digest collision';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM mdm.match_proposal_event WHERE assessment_id=key) THEN
        INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event)
            VALUES(key,root_run,b->>'outcome') ON CONFLICT DO NOTHING;
    END IF;
    INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event)
        VALUES(key,root_run,'observed') ON CONFLICT DO NOTHING;
    RETURN key;
END;
$$;

CREATE FUNCTION mdm.record_attempt(attempt uuid, root_run uuid, batch text, phase text, body jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE old mdm.attempt_event%ROWTYPE;
BEGIN
    IF attempt IS NULL OR root_run IS NULL OR batch IS NULL OR length(batch)=0
       OR phase IS NULL OR phase NOT IN ('started','finished','error')
       OR body IS NULL OR jsonb_typeof(body)<>'object' OR octet_length(body::text)>16384 THEN
        RAISE EXCEPTION 'Invalid attempt event';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(attempt::text,26));
    IF phase<>'started' THEN
        SELECT * INTO old FROM mdm.attempt_event WHERE attempt_id=attempt AND event='started';
        IF NOT FOUND OR old.run_id<>root_run OR old.batch_id<>batch THEN
            RAISE EXCEPTION 'Attempt has no matching start';
        END IF;
        IF EXISTS(SELECT 1 FROM mdm.attempt_event WHERE attempt_id=attempt AND event NOT IN ('started',phase)) THEN
            RAISE EXCEPTION 'Attempt already has another terminal event';
        END IF;
    END IF;
    INSERT INTO mdm.attempt_event(attempt_id,event,run_id,batch_id,detail)
        VALUES(attempt,phase,root_run,batch,body) ON CONFLICT DO NOTHING;
    SELECT * INTO old FROM mdm.attempt_event WHERE attempt_id=attempt AND event=phase;
    IF old.run_id<>root_run OR old.batch_id<>batch OR old.detail<>body THEN
        RAISE EXCEPTION 'Attempt event identity reused with different content';
    END IF;
END;
$$;

CREATE FUNCTION mdm.record_binding(d jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    bound uuid;
BEGIN
    SELECT entity_id INTO bound FROM mdm.stage_record
      WHERE subject = d->>'subject' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A binding names no Stage record';
    END IF;
    IF bound = (d->>'entity_id')::uuid THEN
        RETURN;
    END IF;
    IF bound IS NOT NULL THEN
        RAISE EXCEPTION 'Moving an established source binding requires a correction contract';
    END IF;
    UPDATE mdm.stage_record SET entity_id = (d->>'entity_id')::uuid
      WHERE subject = d->>'subject';
END;
$$;

CREATE FUNCTION mdm.record_company_version(projected jsonb, source_batch text, recorded_at timestamp with time zone) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    previous mdm.company%ROWTYPE;
    old_alias mdm.company_alias%ROWTYPE;
    generation_number bigint;
    starts_at timestamptz;
    refs jsonb;
    selected jsonb;
BEGIN
    IF projected->>'kind' IS DISTINCT FROM 'company' THEN RETURN; END IF;
    SELECT generation INTO generation_number FROM mdm.batch WHERE batch_id=source_batch;
    IF generation_number IS NULL THEN RAISE EXCEPTION 'Company projection has no committed batch'; END IF;
    SELECT * INTO previous FROM mdm.company
      WHERE entity_id=(projected->>'entity_id')::uuid AND valid_to IS NULL FOR UPDATE;
    SELECT * INTO old_alias FROM mdm.company_alias
      WHERE alias_id=(projected->>'entity_id')::uuid AND valid_to IS NULL FOR UPDATE;
    IF projected->>'status'='alias' AND old_alias.alias_id IS NOT NULL
       AND old_alias.canonical_id::text=projected->>'canonical_id' THEN RETURN; END IF;
    IF projected->>'status'<>'alias' AND previous.entity_id IS NOT NULL
       AND previous.body=projected THEN RETURN; END IF;
    starts_at := greatest(
        recorded_at,
        coalesce(previous.valid_from + interval '1 microsecond',recorded_at),
        coalesce(old_alias.valid_from + interval '1 microsecond',recorded_at)
    );
    IF previous.entity_id IS NOT NULL THEN
        UPDATE mdm.company SET valid_to=starts_at,to_generation=generation_number
          WHERE entity_id=previous.entity_id AND valid_to IS NULL;
    END IF;
    IF old_alias.alias_id IS NOT NULL THEN
        UPDATE mdm.company_alias SET valid_to=starts_at,to_generation=generation_number
          WHERE alias_id=old_alias.alias_id AND valid_to IS NULL;
    END IF;
    -- A merged-away ID is only routing metadata, not another Company row.
    IF projected->>'status' = 'alias' THEN
        INSERT INTO mdm.company_alias(
            alias_id,canonical_id,from_generation,valid_from,batch_id
        ) VALUES (
            (projected->>'entity_id')::uuid,(projected->>'canonical_id')::uuid,
            generation_number,starts_at,source_batch
        );
        RETURN;
    END IF;
    IF projected->>'status' NOT IN ('accepted','review') OR projected->>'canonical_id' IS DISTINCT FROM projected->>'entity_id' THEN
        RAISE EXCEPTION 'Invalid Company projection';
    END IF;
    refs := coalesce(projected->'identifiers','{}'::jsonb);
    selected := coalesce(projected->'fields','{}'::jsonb);
    INSERT INTO mdm.company (
        entity_id,from_generation,valid_from,batch_id,status,quarantined,
        cik,lei,identifiers,name,sic,sic_description,state_of_incorporation,
        fiscal_year_end,description,jurisdiction,address,gleif_legal_form,
        gleif_entity_status,gleif_registration_status,gleif_initial_registration,
        gleif_last_update,gleif_next_renewal,gleif_managing_lou,
        gleif_validation_source,gleif_registration_authority,
        gleif_registration_authority_entity_id,gleif_entity_creation_date,fields,body
    ) VALUES (
        (projected->>'entity_id')::uuid,generation_number,starts_at,source_batch,
        projected->>'status',coalesce((projected->>'quarantined')::boolean,false),
        CASE WHEN jsonb_array_length(coalesce(refs->'cik','[]'::jsonb))=1 THEN refs->'cik'->>0 END,
        CASE WHEN jsonb_array_length(coalesce(refs->'lei','[]'::jsonb))=1 THEN refs->'lei'->>0 END,
        refs,selected->'name'->>'value',selected->'sic'->>'value',
        selected->'sic_description'->>'value',selected->'state_of_incorporation'->>'value',
        selected->'fiscal_year_end'->>'value',selected->'description'->>'value',
        selected->'jurisdiction'->>'value',
        CASE WHEN selected->'address'->'value'='null'::jsonb THEN NULL
             ELSE selected->'address'->'value' END,
        selected->'gleif_legal_form'->>'value',selected->'gleif_entity_status'->>'value',
        selected->'gleif_registration_status'->>'value',
        selected->'gleif_initial_registration'->>'value',
        selected->'gleif_last_update'->>'value',selected->'gleif_next_renewal'->>'value',
        selected->'gleif_managing_lou'->>'value',selected->'gleif_validation_source'->>'value',
        selected->'gleif_registration_authority'->>'value',
        selected->'gleif_registration_authority_entity_id'->>'value',
        selected->'gleif_entity_creation_date'->>'value',selected,projected
    );
END;
$$;

CREATE FUNCTION mdm.record_stage(a jsonb, source_batch text, occurrence jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    current_row mdm.stage_record%ROWTYPE;
    ordering bigint[] := ARRAY[(a->>'revision')::bigint,
                               coalesce((a->>'mapping_version')::bigint, 1)];
    bronze_of jsonb := CASE WHEN occurrence IS NULL THEN NULL ELSE jsonb_build_object(
        'object', occurrence->>'object', 'sha256', occurrence->>'sha256',
        'locator', occurrence->>'locator') END;
BEGIN
    SELECT * INTO current_row FROM mdm.stage_record
      WHERE source_code = a->>'source_code' AND record_key = a->>'record_key'
      FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO mdm.stage_record (
            source_code, record_key, subject, kind, revision, mapping_version,
            publication_key, assertion_id, effective_at, snapshot, bronze,
            batch_id, reading
        ) VALUES (
            a->>'source_code', a->>'record_key', a->>'subject', a->>'kind',
            ordering[1], ordering[2], a->>'publication_key', a->>'assertion_id',
            (a->>'effective_at')::timestamptz, mdm.stage_fold(NULL, a), bronze_of,
            source_batch, a);
        RETURN;
    END IF;
    IF ordering = ARRAY[current_row.revision, current_row.mapping_version] THEN
        IF current_row.assertion_id IS DISTINCT FROM a->>'assertion_id' THEN
            RAISE EXCEPTION 'Source native revision has contradictory publications';
        END IF;
        RETURN;
    END IF;
    IF ordering < ARRAY[current_row.revision, current_row.mapping_version] THEN
        RETURN;  -- an older reading delivered later keeps the current row
    END IF;
    UPDATE mdm.stage_record SET
        subject = a->>'subject', kind = a->>'kind',
        revision = ordering[1], mapping_version = ordering[2],
        publication_key = a->>'publication_key', assertion_id = a->>'assertion_id',
        effective_at = (a->>'effective_at')::timestamptz,
        snapshot = mdm.stage_fold(current_row.snapshot, a),
        bronze = bronze_of, batch_id = source_batch, reading = a
      WHERE source_code = current_row.source_code AND record_key = current_row.record_key;
END;
$$;

CREATE FUNCTION mdm.release_binding(d jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    target jsonb;
    bound uuid;
BEGIN
    SELECT body INTO target FROM mdm.decision WHERE decision_id = d->>'target';
    IF target IS NULL OR target->>'operation' IS DISTINCT FROM 'bind' THEN
        RETURN;
    END IF;
    -- Once only: a second revocation would unbind whatever the record was
    -- bound to since.
    IF EXISTS (SELECT 1 FROM mdm.decision WHERE operation = 'revoke'
               AND body->>'target' = d->>'target' AND decision_id <> d->>'decision_id') THEN
        RAISE EXCEPTION 'This bind is already revoked';
    END IF;
    SELECT entity_id INTO bound FROM mdm.stage_record
      WHERE subject = target->>'subject' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A revocation names no Stage record';
    END IF;
    IF bound IS NULL THEN
        RETURN;
    END IF;
    IF bound IS DISTINCT FROM (target->>'entity_id')::uuid THEN
        RAISE EXCEPTION 'A revocation names a bind its record no longer holds';
    END IF;
    UPDATE mdm.stage_record SET entity_id = NULL WHERE subject = target->>'subject';
END;
$$;

CREATE FUNCTION mdm.stage_claim(item jsonb, a jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
    SELECT item || jsonb_build_object(
        'assertion_id', a->'assertion_id', 'source_code', a->'source_code',
        'record_key', a->'record_key', 'effective_at', a->'effective_at')
$$;

CREATE FUNCTION mdm.stage_fold(previous jsonb, a jsonb) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    claims jsonb := coalesce(previous->'fields', '{}'::jsonb);
    before jsonb := coalesce(previous->'profile_fields', '{}'::jsonb);
    continuing jsonb := '{}'::jsonb;
    values_of jsonb;
    field record;
    profile jsonb;
    profile_id text;
    item jsonb;
BEGIN
    FOR field IN SELECT f.key AS name, f.value AS item
                 FROM jsonb_each(coalesce(a->'fields', '{}'::jsonb)) f LOOP
        IF field.item->>'op' = 'unknown' THEN
            CONTINUE;
        ELSIF field.item->>'op' = 'retract' THEN
            claims := claims - field.name;
        ELSE
            claims := claims || jsonb_build_object(field.name, mdm.stage_claim(field.item, a));
        END IF;
    END LOOP;
    FOR profile IN SELECT value FROM jsonb_array_elements(coalesce(a->'profiles', '[]'::jsonb)) LOOP
        profile_id := mdm.stage_profile_key(profile);
        values_of := coalesce(before->profile_id, '{}'::jsonb);
        FOR field IN SELECT f.key AS name, f.value AS item
                     FROM jsonb_each(coalesce(profile->'fields', '{}'::jsonb)) f LOOP
            item := CASE
                WHEN jsonb_typeof(field.item) = 'object' AND field.item ? 'op' THEN field.item
                WHEN jsonb_typeof(field.item) = 'null' THEN '{"op":"unknown"}'::jsonb
                ELSE jsonb_build_object('op', 'value', 'value', field.item) END;
            IF item->>'op' = 'unknown' THEN
                CONTINUE;
            ELSIF item->>'op' = 'retract' THEN
                values_of := values_of - field.name;
            ELSIF item->>'op' IN ('value', 'clear') THEN
                IF item->>'op' = 'value' AND (item->'value' IS NULL OR jsonb_typeof(item->'value') = 'null') THEN
                    RAISE EXCEPTION 'Use unknown for null profile evidence';
                END IF;
                values_of := values_of || jsonb_build_object(field.name, mdm.stage_claim(item, a));
            ELSE
                RAISE EXCEPTION 'Unknown profile field operation';
            END IF;
        END LOOP;
        continuing := continuing || jsonb_build_object(profile_id, values_of);
    END LOOP;
    RETURN jsonb_build_object(
        'kind', a->'kind',
        'fields', claims,
        'identifiers', a->'identifiers',
        'profiles', a->'profiles',
        'profile_fields', continuing,
        'relationships', a->'relationships',
        'assertion_id', a->'assertion_id',
        'source_meta', jsonb_build_object(
            'source_code', a->'source_code', 'record_key', a->'record_key',
            'effective_at', a->'effective_at'));
END;
$$;

CREATE FUNCTION mdm.stage_profile_key(profile jsonb) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['role','authority','registration','jurisdiction','valid_from']) part
               WHERE coalesce(jsonb_typeof(profile->part), 'null') NOT IN ('string', 'null')) THEN
        RAISE EXCEPTION 'Profile identifying values must be text';
    END IF;
    RETURN (SELECT encode(sha256(convert_to('[' || string_agg(
        coalesce((profile->part)::text, 'null'), ',' ORDER BY n) || ']', 'UTF8')), 'hex')
        FROM unnest(ARRAY['role','authority','registration','jurisdiction','valid_from'])
            WITH ORDINALITY AS parts(part, n));
END;
$$;

CREATE FUNCTION mdm.start_run(root_run uuid, body jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE old jsonb;
BEGIN
    IF root_run IS NULL OR body IS NULL OR jsonb_typeof(body)<>'object'
       OR octet_length(body::text)>1048576 THEN
        RAISE EXCEPTION 'Invalid run scope';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(root_run::text,43));
    SELECT scope INTO old FROM mdm.run WHERE run_id=root_run;
    IF FOUND THEN
        IF old<>body THEN RAISE EXCEPTION 'Root run scope changed'; END IF;
        RETURN;
    END IF;
    INSERT INTO mdm.run(run_id,scope) VALUES(root_run,body);
END;
$$;

CREATE FUNCTION mdm.supersede_match_proposal(key text, root_run uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE b jsonb;
BEGIN
    PERFORM pg_advisory_xact_lock(730234);
    SELECT body INTO b FROM mdm.match_proposal WHERE assessment_id=key;
    IF root_run IS NULL OR b IS NULL THEN RAISE EXCEPTION 'Unknown assessment or run'; END IF;
    IF b->>'outcome'='ready'
       AND NOT EXISTS(SELECT 1 FROM mdm.match_proposal_event WHERE assessment_id=key AND event IN ('applied','superseded'))
       AND b->>'snapshot' IS DISTINCT FROM mdm.match_proposal_snapshot(b->'scope') THEN
        INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event) VALUES(key,root_run,'superseded');
    END IF;
END;
$$;

-- Views ---------------------------------------------------------------------

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
     CROSS JOIN LATERAL jsonb_each(c.fields) f(key, value))
  WHERE (c.valid_to IS NULL);

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

-- Per-kind read views, generated for every kind master_entity permits.
--
-- Source readings and current records stay in one table each, with the kind
-- as a value inside them. These views present each table as if it were split
-- per kind, so a reader asks for Person readings without repeating the
-- filter, and a new kind needs only its value added to master_entity's check.
--
--   <kind>_stage         each source reading of that kind
--   <kind>_stage_field   the same readings, one row per field
--   <kind>_master        each current master record of that kind
--   <kind>_master_field  the same records, one row per field and its winner
--
-- Company has no <kind>_master view: its master records are the versioned
-- company table, and company_master_field (above) reads that table.
DO $kinds$
DECLARE
    k text;
    made int := 0;
BEGIN
    FOR k IN
        SELECT m[1]
        FROM pg_constraint c,
        LATERAL regexp_matches(
            substring(pg_get_constraintdef(c.oid)
                      from 'kind[^=]*= ANY \(ARRAY\[(.*?)\]\)'),
            '''([a-z_]+)''', 'g') m
        WHERE c.conrelid = 'mdm.master_entity'::regclass
          AND c.conname = 'master_entity_kind_check'
    LOOP
        EXECUTE format($v$
            CREATE VIEW mdm.%I AS
            SELECT assertion_id, source_code, record_key, publication_key,
                   revision, mapping_version, effective_at, batch_id,
                   body->>'subject' AS subject,
                   body->>'schema_version' AS schema_version,
                   body
            FROM mdm.source_reading a
            WHERE body->>'kind' = %L$v$, k || '_stage', k);
        EXECUTE format($v$
            COMMENT ON VIEW mdm.%I IS %L$v$, k || '_stage',
            'Each source reading of kind ' || k || ', as read and never changed: a filter of source_reading.');
        EXECUTE format($v$
            CREATE VIEW mdm.%I AS
            SELECT a.assertion_id, a.source_code, a.record_key, a.publication_key,
                   a.revision, a.mapping_version, a.effective_at, a.batch_id,
                   a.body->>'subject' AS subject,
                   f.key AS field_name,
                   f.value->>'op' AS operation,
                   f.value->>'value' AS field_value
            FROM mdm.source_reading a
            CROSS JOIN LATERAL jsonb_each(coalesce(a.body->'fields', '{}'::jsonb)) f(key, value)
            WHERE a.body->>'kind' = %L$v$, k || '_stage_field', k);
        EXECUTE format($v$
            COMMENT ON VIEW mdm.%I IS %L$v$, k || '_stage_field',
            'Each source reading of kind ' || k || ', one row per field it states, sets or clears.');
        IF k <> 'company' THEN
            EXECUTE format($v$
                CREATE VIEW mdm.%I AS
                SELECT object_id AS entity_id, batch_id,
                       body->>'status' AS status,
                       body->>'canonical_id' AS canonical_id,
                       body
                FROM mdm.current_record p
                WHERE object_type = 'entity' AND body->>'kind' = %L$v$, k || '_master', k);
            EXECUTE format($v$
                COMMENT ON VIEW mdm.%I IS %L$v$, k || '_master',
                'Each current master record of kind ' || k || ': a filter of current_record.');
            EXECUTE format($v$
                CREATE VIEW mdm.%I AS
                SELECT p.object_id AS entity_id, p.batch_id,
                       p.body->>'status' AS status,
                       f.key AS field_name,
                       f.value->>'value' AS field_value,
                       (f.value->>'cleared')::boolean AS cleared,
                       f.value->'winner'->>'source_code' AS source_code,
                       f.value->'winner'->>'record_key' AS record_key,
                       (f.value->'winner'->>'effective_at')::timestamptz AS effective_at,
                       f.value->>'policy_digest' AS policy_digest,
                       f.value->>'kind_version' AS kind_version,
                       jsonb_array_length(coalesce(f.value->'conflicts', '[]'::jsonb)) AS conflict_count
                FROM mdm.current_record p
                CROSS JOIN LATERAL jsonb_each(coalesce(p.body->'fields', '{}'::jsonb)) f(key, value)
                WHERE p.object_type = 'entity' AND p.body->>'kind' = %L$v$, k || '_master_field', k);
            EXECUTE format($v$
                COMMENT ON VIEW mdm.%I IS %L$v$, k || '_master_field',
                'Each current master record of kind ' || k || ', one row per field: its value and the source reading that won it.');
        END IF;
        made := made + 1;
    END LOOP;
    IF made = 0 THEN
        RAISE EXCEPTION 'Cannot read the permitted kinds out of master_entity_kind_check';
    END IF;
END;
$kinds$;

-- Indexes -------------------------------------------------------------------

CREATE INDEX source_reading_source_code_mapping_version_idx ON mdm.source_reading USING btree (source_code, mapping_version);

CREATE INDEX source_reading_source_code_record_key_revision_idx ON mdm.source_reading USING btree (source_code, record_key, revision);

CREATE INDEX match_proposal_created_at_assessment_id_idx ON mdm.match_proposal USING btree (created_at DESC, assessment_id);

CREATE INDEX match_proposal_event_assessment_id_event_id_idx ON mdm.match_proposal_event USING btree (assessment_id, event_id DESC);

CREATE INDEX match_proposal_expr_idx ON mdm.match_proposal USING btree ((((body -> 'command'::text) ->> 'batch_id'::text)));

CREATE INDEX source_reading_identifier_cik ON mdm.source_reading USING btree ((((body -> 'identifiers'::text) ->> 'cik'::text)));

CREATE INDEX source_reading_identifier_lei ON mdm.source_reading USING btree ((((body -> 'identifiers'::text) ->> 'lei'::text)));

CREATE INDEX source_reading_kind ON mdm.source_reading USING btree (((body ->> 'kind'::text)));

CREATE INDEX source_reading_subject ON mdm.source_reading USING btree (((body ->> 'subject'::text)));

CREATE INDEX attempt_run ON mdm.attempt_event USING btree (run_id, batch_id);

CREATE INDEX decision_entity ON mdm.decision USING btree (((body ->> 'entity_id'::text)));

CREATE INDEX decision_left ON mdm.decision USING btree (((body ->> 'left'::text)));

CREATE INDEX decision_right ON mdm.decision USING btree (((body ->> 'right'::text)));

CREATE INDEX decision_subject ON mdm.decision USING btree (((body ->> 'subject'::text)));

CREATE INDEX decision_target ON mdm.decision USING btree (((body ->> 'target'::text)));

CREATE INDEX deferred_probable_kind ON mdm.set_aside_record USING btree (((body ->> 'probable_kind'::text)));

CREATE INDEX master_entity_kind_published_at ON mdm.master_entity USING btree (kind, published_at);

CREATE INDEX current_record_entity_kind ON mdm.current_record USING btree (((body ->> 'kind'::text))) WHERE (object_type = 'entity'::text);

CREATE UNIQUE INDEX company_alias_current ON mdm.company_alias USING btree (alias_id) WHERE (valid_to IS NULL);

CREATE INDEX company_alias_current_text ON mdm.company_alias USING btree (((alias_id)::text)) WHERE (valid_to IS NULL);

CREATE INDEX company_current_cik ON mdm.company USING btree (cik) WHERE ((valid_to IS NULL) AND (status = 'accepted'::text) AND (cik IS NOT NULL));

CREATE UNIQUE INDEX company_current_entity ON mdm.company USING btree (entity_id) WHERE (valid_to IS NULL);

CREATE INDEX company_current_entity_text ON mdm.company USING btree (((entity_id)::text)) WHERE (valid_to IS NULL);

CREATE INDEX company_current_lei ON mdm.company USING btree (lei) WHERE ((valid_to IS NULL) AND (status = 'accepted'::text) AND (lei IS NOT NULL));

CREATE INDEX company_generation_page ON mdm.company USING btree (from_generation, to_generation, entity_id);

CREATE INDEX stage_record_census_lei ON mdm.stage_record USING btree ((((((((reading -> 'provenance'::text) -> 'matching'::text) -> 'name_census'::text) -> 'leis'::text) -> 0) ->> 0)));

CREATE INDEX stage_record_cik ON mdm.stage_record USING btree ((((reading -> 'identifiers'::text) ->> 'cik'::text)));

CREATE INDEX stage_record_entity ON mdm.stage_record USING btree (entity_id) WHERE (entity_id IS NOT NULL);

CREATE INDEX stage_record_kind ON mdm.stage_record USING btree (kind, source_code);

CREATE INDEX stage_record_lei ON mdm.stage_record USING btree ((((reading -> 'identifiers'::text) ->> 'lei'::text)));

-- Triggers: rows that are never changed -------------------------------------

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.source_reading FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.match_proposal FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.match_proposal_event FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.attempt_event FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.batch FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.dataset FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.dataset_mapping FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.decision FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.set_aside_record FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.master_entity FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.migration FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.run_batch FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.policy FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.outbox_event FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

-- Every table, column, view and function says what it holds or does, who
-- writes it and who reads it, so \d+ and the Data Catalog explain the schema.
-- tests/integration/test_mdm_schema_comments.py fails on any object without one.

COMMENT ON SCHEMA mdm IS
    'Master Data Management: the master record of each Company, Person and other kind, the source readings it is built from, and every decision that joined them. The application login reads it and writes only through its functions (save_batch and the others it is granted).';

-- Master data -------------------------------------------------------------

COMMENT ON TABLE mdm.master_entity IS
    'One row per master entity (a Company, a Person, ...): its id and kind, and when it was published. Never changed. Written by save_batch; read by the Merge Stage and the per-kind views.';
COMMENT ON COLUMN mdm.master_entity.published_at IS
    'When MDM first published the entity. Of two merged entities, the earlier-published one survives.';

COMMENT ON TABLE mdm.company IS
    'Each Company, versioned: one row per version, the current one with valid_to empty. The only place a Company is kept. Written by record_company_version inside save_batch; read by current_entity and the company_* views.';
COMMENT ON COLUMN mdm.company.from_generation IS 'The batch generation that made this version current.';
COMMENT ON COLUMN mdm.company.to_generation IS 'The batch generation that replaced this version; empty while it is current.';
COMMENT ON COLUMN mdm.company.valid_from IS 'When MDM recorded this version (not when the source says it took effect).';
COMMENT ON COLUMN mdm.company.valid_to IS 'When MDM replaced this version; empty while it is current.';
COMMENT ON COLUMN mdm.company.quarantined IS 'True when the Company is held back from readers until a person reviews it.';
COMMENT ON COLUMN mdm.company.cik IS 'SEC Central Index Key, when the Company has one.';
COMMENT ON COLUMN mdm.company.lei IS 'Legal Entity Identifier from GLEIF, when the Company has one.';
COMMENT ON COLUMN mdm.company.identifiers IS 'Every identifier the Company holds (cik, lei, ein and others), as an object.';
COMMENT ON COLUMN mdm.company.name IS 'The Company''s legal name, as the Mastering Policy chose it.';
COMMENT ON COLUMN mdm.company.sic IS 'SEC Standard Industrial Classification code.';
COMMENT ON COLUMN mdm.company.sic_description IS 'The SIC code''s description.';
COMMENT ON COLUMN mdm.company.state_of_incorporation IS 'Where the Company is incorporated, as SEC reports it.';
COMMENT ON COLUMN mdm.company.fiscal_year_end IS 'The Company''s fiscal year end, MMDD, as SEC reports it.';
COMMENT ON COLUMN mdm.company.description IS 'The Company''s business description.';
COMMENT ON COLUMN mdm.company.jurisdiction IS 'The legal jurisdiction, as GLEIF reports it.';
COMMENT ON COLUMN mdm.company.address IS 'The Company''s address, as an object (lines, city, region, postcode, country).';
COMMENT ON COLUMN mdm.company.gleif_legal_form IS 'GLEIF legal form code (ISO 20275).';
COMMENT ON COLUMN mdm.company.gleif_entity_status IS 'GLEIF entity status, e.g. ACTIVE or INACTIVE.';
COMMENT ON COLUMN mdm.company.gleif_registration_status IS 'GLEIF registration status of the LEI, e.g. ISSUED or LAPSED.';
COMMENT ON COLUMN mdm.company.gleif_initial_registration IS 'When the LEI was first registered.';
COMMENT ON COLUMN mdm.company.gleif_last_update IS 'When GLEIF last updated the LEI record.';
COMMENT ON COLUMN mdm.company.gleif_next_renewal IS 'When the LEI is next due for renewal.';
COMMENT ON COLUMN mdm.company.gleif_managing_lou IS 'The LEI of the Local Operating Unit that manages this LEI.';
COMMENT ON COLUMN mdm.company.gleif_validation_source IS 'How GLEIF validated the record, e.g. FULLY_CORROBORATED.';
COMMENT ON COLUMN mdm.company.gleif_registration_authority IS 'The registration authority (business register) GLEIF names.';
COMMENT ON COLUMN mdm.company.gleif_registration_authority_entity_id IS 'The Company''s id in that registration authority.';
COMMENT ON COLUMN mdm.company.gleif_entity_creation_date IS 'When the legal entity was created, as GLEIF reports it.';
COMMENT ON COLUMN mdm.company.fields IS 'Every chosen field, including ones without a column, each with its value, the source reading that won it and the readings that disagreed.';
COMMENT ON COLUMN mdm.company.body IS 'The whole master record as the Merge Stage built it.';

COMMENT ON TABLE mdm.company_alias IS
    'Company ids that now point to another Company after a merge, versioned like company. Lets a reader follow an old id to its survivor. Written by record_company_version; read by current_entity.';
COMMENT ON COLUMN mdm.company_alias.alias_id IS 'The merged-away Company id.';
COMMENT ON COLUMN mdm.company_alias.canonical_id IS 'The surviving Company it now points to.';
COMMENT ON COLUMN mdm.company_alias.from_generation IS 'The batch generation that made this alias current.';
COMMENT ON COLUMN mdm.company_alias.to_generation IS 'The batch generation that ended this alias; empty while it is current.';
COMMENT ON COLUMN mdm.company_alias.valid_from IS 'When MDM recorded this alias.';
COMMENT ON COLUMN mdm.company_alias.valid_to IS 'When MDM ended this alias; empty while it is current.';

COMMENT ON TABLE mdm.current_record IS
    'The current record of every master entity other than a Company, and of every relationship and review item, one row each, replaced as batches are saved. Written by save_batch; read by current_entity, stage_waiting and the per-kind _master views.';
COMMENT ON COLUMN mdm.current_record.object_type IS 'What the record is: entity, relationship or review.';
COMMENT ON COLUMN mdm.current_record.object_id IS 'The record''s id: an entity id, a relationship id or a review id.';
COMMENT ON COLUMN mdm.current_record.body IS 'The whole current record.';

COMMENT ON TABLE mdm.stage_record IS
    'The Stage: one row per source record (source and its own record key) with its latest winning reading, what it resolves to, and the entity it is joined to. Written by record_stage, record_binding and release_binding inside save_batch; read by the Merge Stage for binding and matching.';
COMMENT ON COLUMN mdm.stage_record.assertion_id IS 'The winning source reading (source_reading.assertion_id).';
COMMENT ON COLUMN mdm.stage_record.snapshot IS 'What the readings this record has accepted resolve to, field by field.';
COMMENT ON COLUMN mdm.stage_record.bronze IS 'The bronze object the winning reading was delivered in: object, sha256 and locator.';
COMMENT ON COLUMN mdm.stage_record.reading IS 'The winning reading, whole.';
COMMENT ON COLUMN mdm.stage_record.entity_id IS 'The master entity this record is joined to; empty until a bind decision joins it. A join never moves; a correction revokes it.';

COMMENT ON TABLE mdm.decision IS
    'Every decision that changes master data: bind (join a source record to an entity), merge, reverse, override, revoke, exclude, retire a source, quarantine and the others, with who or which rule made it and why. Never changed. Written by save_batch; read by the Merge Stage and corrections.';
COMMENT ON COLUMN mdm.decision.decision_id IS 'The decision''s id.';
COMMENT ON COLUMN mdm.decision.operation IS 'What the decision does, e.g. bind, merge, revoke or exclude.';
COMMENT ON COLUMN mdm.decision.body IS 'The whole decision: its targets, actor, reason and the rule or person behind it.';

-- Source evidence -----------------------------------------------------------

COMMENT ON TABLE mdm.source_reading IS
    'Every version of every source record as MDM read it: one row per reading, never changed. A new mapping version of the same record is a new reading. Written by save_batch; read by the Merge Stage, the Stage and the per-kind _stage views.';
COMMENT ON COLUMN mdm.source_reading.assertion_id IS 'The reading''s id, a hash of the reading.';
COMMENT ON COLUMN mdm.source_reading.body IS 'The whole reading: kind, subject, identifiers, fields, relationships and provenance.';

COMMENT ON TABLE mdm.set_aside_record IS
    'Source records MDM read but did not accept, and why: not this kind, an invalid field, or waiting for review. Never changed. Written by save_batch; read by stage_waiting.';
COMMENT ON COLUMN mdm.set_aside_record.deferred_id IS 'The set-aside record''s id.';
COMMENT ON COLUMN mdm.set_aside_record.body IS 'The whole set-aside record: its reason, probable kind, the classification step that set it aside, and the raw record.';

-- Rules ---------------------------------------------------------------------

COMMENT ON TABLE mdm.policy IS
    'Each Mastering Policy (the merge rules), stored by its fingerprint as approved. Never changed. Written by register_policy when rules activate runs; read by save_batch and the Merge Stage.';
COMMENT ON COLUMN mdm.policy.digest IS 'The policy''s fingerprint: the sha256 of its body.';
COMMENT ON COLUMN mdm.policy.body IS 'The whole policy: kinds, matching rules, field winners, required consumers and approvals.';

COMMENT ON TABLE mdm.dataset IS
    'Each source (a Dataset Contract) MDM accepts readings from, with the registry version that authorises it. Never changed. Written by register_dataset when rules activate runs; read by save_batch.';
COMMENT ON COLUMN mdm.dataset.registry_version IS 'The approved rules version that authorises this source.';
COMMENT ON COLUMN mdm.dataset.body IS 'The whole Dataset Contract: provider, family, keys, effective time and which set-aside reasons do not block.';

COMMENT ON TABLE mdm.dataset_mapping IS
    'Each version of how a source is read (its mapping). A correction is a new version, so earlier readings keep the version that read them. Never changed. Written by register_dataset; read by save_batch and the Stage.';
COMMENT ON COLUMN mdm.dataset_mapping.body IS 'The whole mapping: schema version and how each source field becomes an MDM field.';
COMMENT ON COLUMN mdm.dataset_mapping.registry_version IS 'The approved rules version this mapping came from.';
COMMENT ON COLUMN mdm.dataset_mapping.registered_at IS 'When rules activate registered it.';

-- Support -------------------------------------------------------------------

COMMENT ON TABLE mdm.batch IS
    'Each saved batch of Merge Stage work: its request hash, run, policy and generation. A batch is saved whole or not at all, and saving the same batch again changes nothing. Never changed. Written by save_batch; read by duplicate checks, checkpoints and the outbox.';
COMMENT ON COLUMN mdm.batch.request_hash IS 'The sha256 of the batch request; the same batch id with other content is refused.';
COMMENT ON COLUMN mdm.batch.generation IS 'The batch''s place in the order of all saved batches: 1, 2, 3, ...';
COMMENT ON COLUMN mdm.batch.checkpoint IS 'The reader''s position this batch advanced to.';
COMMENT ON COLUMN mdm.batch.effects IS 'The whole batch request: readings, entities, decisions and current records.';
COMMENT ON COLUMN mdm.batch.created_at IS 'When the batch was saved.';

COMMENT ON TABLE mdm.run_batch IS
    'Which run saw which batch, including a run that met a batch already saved. Never changed. Written by save_batch; read when a run is reconciled.';

COMMENT ON TABLE mdm.run IS
    'Each Merge Stage run: its frozen scope and its reconciled outcome. Written only by start_run and finish_run; read by the run coordinator.';
COMMENT ON COLUMN mdm.run.scope IS 'The run''s frozen scope: the captures and readings it was started on. A changed scope is refused.';
COMMENT ON COLUMN mdm.run.started_at IS 'When the run was registered.';
COMMENT ON COLUMN mdm.run.status IS 'running, or succeeded once reconciled complete. A succeeded run stays succeeded.';
COMMENT ON COLUMN mdm.run.report IS 'The reconciled outcome: counts per batch and what is left.';
COMMENT ON COLUMN mdm.run.completed_at IS 'When the run succeeded.';

COMMENT ON TABLE mdm.checkpoint IS
    'How far each reader (consumer) has read each source, so the next batch must continue from there. Written by save_batch; read by the next batch''s check.';
COMMENT ON COLUMN mdm.checkpoint.position IS 'The last position saved.';
COMMENT ON COLUMN mdm.checkpoint.batch_id IS 'The batch that saved this position.';
COMMENT ON COLUMN mdm.checkpoint.committed_publication IS 'The last source publication fully read, for a reader of a publication family.';
COMMENT ON COLUMN mdm.checkpoint.continuity_proof IS 'Evidence that the publications read so far follow one another with no gap.';

COMMENT ON TABLE mdm.attempt_event IS
    'Each try at saving a batch: started, finished or error, for recovery after a crash. Never changed. Written by record_attempt; read by the run coordinator.';
COMMENT ON COLUMN mdm.attempt_event.attempt_id IS 'The try''s id.';
COMMENT ON COLUMN mdm.attempt_event.event IS 'started, finished or error.';
COMMENT ON COLUMN mdm.attempt_event.detail IS 'What happened, e.g. the error.';

COMMENT ON TABLE mdm.match_proposal IS
    'Proposed joins and merges (match proposals), checked before they may be saved: the command, the rule''s automatic proposals, and a snapshot of what they were checked against. Never changed. Written by record_match_proposal; read by save_batch.';
COMMENT ON COLUMN mdm.match_proposal.assessment_id IS 'The proposal''s id, a hash of the proposal.';
COMMENT ON COLUMN mdm.match_proposal.body IS 'The whole proposal: the command, its outcome (ready or rejected), its effects, scope and snapshot hash.';
COMMENT ON COLUMN mdm.match_proposal.created_xid IS 'The transaction that recorded it. A proposal cannot be saved in the transaction that recorded it.';

COMMENT ON TABLE mdm.match_proposal_event IS
    'What became of each match proposal: ready, rejected, observed, superseded or applied. Never changed. Written by record_match_proposal, save_batch and supersede_match_proposal.';
COMMENT ON COLUMN mdm.match_proposal_event.assessment_id IS 'The match proposal (match_proposal.assessment_id).';
COMMENT ON COLUMN mdm.match_proposal_event.event IS 'ready, rejected, observed, superseded or applied.';

COMMENT ON TABLE mdm.outbox IS
    'What must be sent on from each saved batch (to the Change Journal, exports), one row per batch and consumer, with its delivery lease and when it was verified. Written by save_batch, claim_outbox and finish_outbox; read by publishers and change-journal recover mdm.';
COMMENT ON COLUMN mdm.outbox.consumer IS 'Who it is for, e.g. journal.';
COMMENT ON COLUMN mdm.outbox.payload IS 'What to send.';
COMMENT ON COLUMN mdm.outbox.payload_hash IS 'The sha256 of the payload; delivery is verified against it.';
COMMENT ON COLUMN mdm.outbox.fence IS 'Raised on each claim; a delivery by an older claim is refused.';
COMMENT ON COLUMN mdm.outbox.lease_until IS 'Until when the current claim holds.';
COMMENT ON COLUMN mdm.outbox.worker IS 'Who holds the claim.';
COMMENT ON COLUMN mdm.outbox.verified_at IS 'When delivery was verified; empty until then.';

COMMENT ON TABLE mdm.outbox_event IS
    'Each claim, verified delivery and failure of an outbox row. Never changed. Written by claim_outbox and finish_outbox.';
COMMENT ON COLUMN mdm.outbox_event.fence IS 'The claim''s fence.';
COMMENT ON COLUMN mdm.outbox_event.event IS 'claimed, verified or failed.';
COMMENT ON COLUMN mdm.outbox_event.detail IS 'The worker, the verified hash or the error.';

COMMENT ON TABLE mdm.migration IS
    'Which migration files are applied, with their checksums. A changed file is refused. Never changed. Written and read by mdm migrate.';
COMMENT ON COLUMN mdm.migration.name IS 'The migration file''s name.';
COMMENT ON COLUMN mdm.migration.checksum IS 'The sha256 of the file as applied.';
COMMENT ON COLUMN mdm.migration.installed_at IS 'When it was applied.';

-- Views ---------------------------------------------------------------------

COMMENT ON VIEW mdm.current_entity IS
    'The one read of every current master entity of every kind: Companies from company (and their aliases), the rest from current_record.';
COMMENT ON COLUMN mdm.current_entity.object_id IS 'The entity''s id.';
COMMENT ON COLUMN mdm.current_entity.body IS 'The whole current master record.';

COMMENT ON VIEW mdm.company_master_field IS
    'Each current Company, one row per field: its value and the source reading that won it.';

COMMENT ON VIEW mdm.stage_waiting IS
    'Source records still waiting for review, with the kind each probably is and the classification step that set it aside.';
COMMENT ON COLUMN mdm.stage_waiting.probable_kind IS 'The kind the record probably is.';
COMMENT ON COLUMN mdm.stage_waiting.reason IS 'Why it was set aside.';
COMMENT ON COLUMN mdm.stage_waiting.rule_id IS 'The classification rule that set it aside.';
COMMENT ON COLUMN mdm.stage_waiting.rule_version IS 'That rule''s version.';
COMMENT ON COLUMN mdm.stage_waiting.rule_step IS 'The step of that rule that set it aside.';
COMMENT ON COLUMN mdm.stage_waiting.blocking IS 'True when the record blocks its source from counting as complete.';
COMMENT ON COLUMN mdm.stage_waiting.raw_record IS 'The record as the source delivered it.';

-- Functions -----------------------------------------------------------------

COMMENT ON FUNCTION mdm.save_batch(text, uuid) IS
    'Save one batch of Merge Stage work atomically: whole or not at all. A batch that joins or merges must carry a ready match proposal whose snapshot still holds. Then write_batch saves it, and the proposal is marked applied. The one function the application login calls to change master data.';
COMMENT ON FUNCTION mdm.write_batch(text, uuid) IS
    'The writes of save_batch, without its match-proposal check: refuses a batch that is unbounded (over 16 MiB, 1,000 readings or decisions, 10,000 current records), stale or from an unregistered source; then saves the batch, its readings, entities, decisions, current records, checkpoint, outbox rows, set-aside records and Stage. Called by save_batch and preview_batch only; not granted to the application login.';
COMMENT ON FUNCTION mdm.preview_batch(text, uuid) IS
    'Run write_batch on a batch and roll it back, returning what it would have saved. Lets the Merge Stage check a batch before proposing it.';
COMMENT ON FUNCTION mdm.record_match_proposal(text, uuid) IS
    'Record a match proposal (proposed joins and merges) with its snapshot, as ready or rejected. Returns its id.';
COMMENT ON FUNCTION mdm.supersede_match_proposal(text, uuid) IS
    'Mark a ready match proposal superseded when what it was checked against has changed.';
COMMENT ON FUNCTION mdm.match_proposal_snapshot(jsonb) IS
    'The hash of everything a match proposal depends on (readings, decisions, entities and current records in its scope, and the reader''s checkpoint). If it changes, the proposal is stale.';
COMMENT ON FUNCTION mdm.claim_outbox(text, text, integer) IS
    'Claim the oldest undelivered outbox row for a consumer, for a lease, in batch order. Returns it, or nothing when none is free.';
COMMENT ON FUNCTION mdm.finish_outbox(text, text, bigint, text, text) IS
    'Record that a claimed outbox row was delivered (and verified against its hash) or failed.';
COMMENT ON FUNCTION mdm.record_attempt(uuid, uuid, text, text, jsonb) IS
    'Record one try at saving a batch: started, finished or error.';
COMMENT ON FUNCTION mdm.start_run(uuid, jsonb) IS
    'Register a Merge Stage run and its frozen scope. Registering it again with the same scope changes nothing; a changed scope is refused.';
COMMENT ON FUNCTION mdm.finish_run(uuid, jsonb, boolean) IS
    'Record a run''s reconciled outcome, and mark it succeeded when complete. A succeeded run stays succeeded.';
COMMENT ON FUNCTION mdm.record_company_version(jsonb, text, timestamp with time zone) IS
    'Write a Company''s new version to company (closing the old one) and its aliases to company_alias. Called by write_batch.';
COMMENT ON FUNCTION mdm.keep_stage(jsonb) IS
    'Update the Stage for a saved batch: each reading''s record, then revocations, then new joins. Called by write_batch.';
COMMENT ON FUNCTION mdm.record_stage(jsonb, text, jsonb) IS
    'Keep a source reading in the Stage when it wins over the record''s current reading. Called by keep_stage.';
COMMENT ON FUNCTION mdm.record_binding(jsonb) IS
    'Join a Stage record to the entity a bind decision names. A join never moves. Called by keep_stage.';
COMMENT ON FUNCTION mdm.release_binding(jsonb) IS
    'Undo a join that a revoke decision names, once. Called by keep_stage.';
COMMENT ON FUNCTION mdm.stage_fold(jsonb, jsonb) IS
    'Fold a new reading into a Stage record''s snapshot, field by field.';
COMMENT ON FUNCTION mdm.stage_claim(jsonb, jsonb) IS
    'One field value from a reading, labelled with the reading that stated it.';
COMMENT ON FUNCTION mdm.stage_profile_key(jsonb) IS
    'The key of a profile (role, authority, registration, jurisdiction, valid from) within a Stage field.';
COMMENT ON FUNCTION mdm.immutable_row() IS
    'Trigger function: refuses any change or delete of a row in a table that is never changed.';

-- Columns that mean the same in every table and view ------------------------
--
-- Applied to every column of mdm that has no comment of its own above.
DO $columns$
DECLARE
    shared jsonb := jsonb_build_object(
        'assertion_id', 'The source reading (source_reading.assertion_id).',
        'source_code', 'The source, e.g. sec.submissions.company or gleif.golden_copy (dataset.source_code).',
        'record_key', 'The source''s own key for the record, e.g. a CIK or an LEI.',
        'publication_key', 'The source publication (delivered file or release) the record came in.',
        'revision', 'The source''s revision of the record; a higher revision supersedes a lower one.',
        'mapping_version', 'The version of the source''s mapping (dataset_mapping) that read it.',
        'effective_at', 'When the source says the reading took effect.',
        'batch_id', 'The saved batch that wrote this row (batch.batch_id).',
        'subject', 'The source record''s subject: its source and record key, the name the Merge Stage joins to an entity.',
        'schema_version', 'The source''s schema version the record was read under.',
        'kind', 'The kind of master entity: company, person, security, fund_structure, branch, government, international_organization or venue.',
        'entity_id', 'The master entity (master_entity.entity_id).',
        'canonical_id', 'The entity this one points to after a merge; itself when it survived.',
        'status', 'accepted, or review when a person must look at it.',
        'field_name', 'The MDM field, e.g. name or address.',
        'field_value', 'The field''s value, as text.',
        'operation', 'What the reading does to the field: states a value, clears it, or leaves it unknown.',
        'cleared', 'True when the winning reading cleared the field.',
        'policy_digest', 'The Mastering Policy (policy.digest) in force.',
        'kind_version', 'The version of the kind''s merge rules that chose the winner.',
        'conflict_count', 'How many other readings disagreed with the winner.',
        'body', 'The whole record, as JSON.',
        'deferred_id', 'The set-aside record (set_aside_record.deferred_id).',
        'record_locator', 'Where in the publication the record sits, e.g. a file member and line.',
        'run_id', 'The Merge Stage run (run.run_id).',
        'occurred_at', 'When it happened.',
        'event_id', 'The event''s number, in order.',
        'created_at', 'When it was recorded.',
        'consumer', 'The reader the work is for, e.g. journal.',
        'source_family', 'The source family read, e.g. gleif; empty for a reader of no family.',
        'publication_family', 'The publication family within it, e.g. golden_copy; empty for a reader of no family.');
    col record;
BEGIN
    FOR col IN
        SELECT c.relname, a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'mdm' AND c.relkind IN ('r', 'v') AND a.attnum > 0
          AND NOT a.attisdropped AND col_description(c.oid, a.attnum) IS NULL
    LOOP
        IF shared ? col.attname THEN
            EXECUTE format('COMMENT ON COLUMN mdm.%I.%I IS %L',
                           col.relname, col.attname, shared->>col.attname);
        END IF;
    END LOOP;
END;
$columns$;
