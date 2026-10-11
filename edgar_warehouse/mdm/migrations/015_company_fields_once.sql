-- A Company version keeps its chosen fields once, in its body (MDM write
-- duplication ticket, 2026-10-11).
--
-- `company.fields` held exactly `body->'fields'` a second time: 2.5 MB of a
-- 919-Company batch's 5 MB Company rows. Its one reader, the
-- `company_master_field` view, now reads the fields from `body`. Rows stored
-- before this lose nothing: their body holds the same fields.

CREATE OR REPLACE VIEW mdm.company_master_field AS
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
     CROSS JOIN LATERAL jsonb_each(c.body -> 'fields'::text) f(key, value))
  WHERE (c.valid_to IS NULL);

CREATE OR REPLACE FUNCTION mdm.record_company_version(projected jsonb, source_batch text, recorded_at timestamp with time zone) RETURNS void
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
        gleif_registration_authority_entity_id,gleif_entity_creation_date,body
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
        selected->'gleif_entity_creation_date'->>'value',projected
    );
END;
$$;

ALTER TABLE mdm.company DROP COLUMN fields;
