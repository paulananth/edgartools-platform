-- Three Company columns leave MDM (ticket 129, fixes 2 and 3; operator,
-- 2026-10-22: "date that changes usually should not be in MDM unless it adds
-- meaning to the entity or turn on or off", "Fix 3").
--   gleif_last_update, gleif_next_renewal: GLEIF's record-keeping dates. They
--     change at each renewal and gave the Company a new version with no change
--     in the entity. GLEIF's LastUpdateDate is already the GLEIF record's
--     effective time, which the census matching rules now read.
--   sic_description: a code's label; it lives in RDM's sec-sic-codes code set,
--     and silver keeps the description as filed. The Company keeps `sic`.
-- The Company writer is recreated without them first (same signature and
-- return as 017's), then the columns are dropped; their comments go with them.
-- Stored versions keep their whole projection in `body`, unchanged.

CREATE OR REPLACE FUNCTION mdm.record_company_version(projected jsonb, source_batch text, recorded_at timestamp with time zone) RETURNS boolean
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
    IF projected->>'kind' IS DISTINCT FROM 'company' THEN RETURN false; END IF;
    SELECT generation INTO generation_number FROM mdm.batch WHERE batch_id=source_batch;
    IF generation_number IS NULL THEN RAISE EXCEPTION 'Company projection has no committed batch'; END IF;
    SELECT * INTO previous FROM mdm.company
      WHERE entity_id=(projected->>'entity_id')::uuid AND valid_to IS NULL FOR UPDATE;
    SELECT * INTO old_alias FROM mdm.company_alias
      WHERE alias_id=(projected->>'entity_id')::uuid AND valid_to IS NULL FOR UPDATE;
    IF projected->>'status'='alias' AND old_alias.alias_id IS NOT NULL
       AND old_alias.canonical_id::text=projected->>'canonical_id' THEN RETURN false; END IF;
    IF projected->>'status'<>'alias' AND previous.entity_id IS NOT NULL
       AND previous.body=projected THEN RETURN false; END IF;
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
        RETURN true;
    END IF;
    IF projected->>'status' NOT IN ('accepted','review') OR projected->>'canonical_id' IS DISTINCT FROM projected->>'entity_id' THEN
        RAISE EXCEPTION 'Invalid Company projection';
    END IF;
    refs := coalesce(projected->'identifiers','{}'::jsonb);
    selected := coalesce(projected->'fields','{}'::jsonb);
    INSERT INTO mdm.company (
        entity_id,from_generation,valid_from,batch_id,status,quarantined,
        cik,lei,identifiers,name,sic,state_of_incorporation,
        fiscal_year_end,description,jurisdiction,address,gleif_legal_form,
        gleif_entity_status,gleif_registration_status,gleif_initial_registration,
        gleif_managing_lou,
        gleif_validation_source,gleif_registration_authority,
        gleif_registration_authority_entity_id,gleif_entity_creation_date,body
    ) VALUES (
        (projected->>'entity_id')::uuid,generation_number,starts_at,source_batch,
        projected->>'status',coalesce((projected->>'quarantined')::boolean,false),
        CASE WHEN jsonb_array_length(coalesce(refs->'cik','[]'::jsonb))=1 THEN refs->'cik'->>0 END,
        CASE WHEN jsonb_array_length(coalesce(refs->'lei','[]'::jsonb))=1 THEN refs->'lei'->>0 END,
        refs,selected->'name'->>'value',selected->'sic'->>'value',
        selected->'state_of_incorporation'->>'value',
        selected->'fiscal_year_end'->>'value',selected->'description'->>'value',
        selected->'jurisdiction'->>'value',
        CASE WHEN selected->'address'->'value'='null'::jsonb THEN NULL
             ELSE selected->'address'->'value' END,
        selected->'gleif_legal_form'->>'value',selected->'gleif_entity_status'->>'value',
        selected->'gleif_registration_status'->>'value',
        selected->'gleif_initial_registration'->>'value',
        selected->'gleif_managing_lou'->>'value',selected->'gleif_validation_source'->>'value',
        selected->'gleif_registration_authority'->>'value',
        selected->'gleif_registration_authority_entity_id'->>'value',
        selected->'gleif_entity_creation_date'->>'value',projected
    );
    RETURN true;
END;
$$;

ALTER TABLE mdm.company
    DROP COLUMN sic_description,
    DROP COLUMN gleif_last_update,
    DROP COLUMN gleif_next_renewal;
