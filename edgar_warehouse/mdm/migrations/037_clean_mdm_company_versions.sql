-- One dated Company read authority. Projection remains the Merge Stage's
-- working state; this table is maintained inside commit_batch's transaction.
-- valid_from/to describe when MDM recorded a decision, not source effective time.
CREATE TABLE mdm_v2.company (
    entity_id uuid NOT NULL REFERENCES mdm_v2.identity(entity_id),
    from_generation bigint NOT NULL REFERENCES mdm_v2.batch(generation),
    to_generation bigint REFERENCES mdm_v2.batch(generation),
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    status text NOT NULL CHECK (status IN ('accepted','review')),
    quarantined boolean NOT NULL DEFAULT false,
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
    -- Every selected value, including future policy fields, remains here with
    -- its winning assertion, authority digest and conflicting evidence.
    fields jsonb NOT NULL,
    body jsonb NOT NULL,
    PRIMARY KEY(entity_id,from_generation),
    CHECK ((valid_to IS NULL) = (to_generation IS NULL)),
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (to_generation IS NULL OR from_generation < to_generation)
);
CREATE UNIQUE INDEX company_current_entity ON mdm_v2.company(entity_id)
    WHERE valid_to IS NULL;
-- An identifier can already appear on two separately reviewed identities.
-- Preserve that conflict for the Merge Stage to adjudicate; only entity ID
-- uniqueness is enforced here.
CREATE INDEX company_current_cik ON mdm_v2.company(cik)
    WHERE valid_to IS NULL AND status='accepted' AND cik IS NOT NULL;
CREATE INDEX company_current_lei ON mdm_v2.company(lei)
    WHERE valid_to IS NULL AND status='accepted' AND lei IS NOT NULL;
CREATE INDEX company_generation_page ON mdm_v2.company(from_generation,to_generation,entity_id);

-- Alias routing is metadata, not a second Company record. It lets a reader
-- resolve a merged-away immutable ID without consulting engine projections.
CREATE TABLE mdm_v2.company_alias (
    alias_id uuid NOT NULL REFERENCES mdm_v2.identity(entity_id),
    canonical_id uuid NOT NULL REFERENCES mdm_v2.identity(entity_id),
    from_generation bigint NOT NULL REFERENCES mdm_v2.batch(generation),
    to_generation bigint REFERENCES mdm_v2.batch(generation),
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    PRIMARY KEY(alias_id,from_generation),
    CHECK (alias_id <> canonical_id),
    CHECK ((valid_to IS NULL) = (to_generation IS NULL)),
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (to_generation IS NULL OR from_generation < to_generation)
);
CREATE UNIQUE INDEX company_alias_current ON mdm_v2.company_alias(alias_id)
    WHERE valid_to IS NULL;

CREATE FUNCTION mdm_v2.record_company_projection(
    projected jsonb, source_batch text, recorded_at timestamptz
) RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    previous mdm_v2.company%ROWTYPE;
    old_alias mdm_v2.company_alias%ROWTYPE;
    generation_number bigint;
    starts_at timestamptz;
    refs jsonb;
    selected jsonb;
BEGIN
    IF projected->>'kind' IS DISTINCT FROM 'company' THEN RETURN; END IF;
    SELECT generation INTO generation_number FROM mdm_v2.batch WHERE batch_id=source_batch;
    IF generation_number IS NULL THEN RAISE EXCEPTION 'Company projection has no committed batch'; END IF;
    SELECT * INTO previous FROM mdm_v2.company
      WHERE entity_id=(projected->>'entity_id')::uuid AND valid_to IS NULL FOR UPDATE;
    SELECT * INTO old_alias FROM mdm_v2.company_alias
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
        UPDATE mdm_v2.company SET valid_to=starts_at,to_generation=generation_number
          WHERE entity_id=previous.entity_id AND valid_to IS NULL;
    END IF;
    IF old_alias.alias_id IS NOT NULL THEN
        UPDATE mdm_v2.company_alias SET valid_to=starts_at,to_generation=generation_number
          WHERE alias_id=old_alias.alias_id AND valid_to IS NULL;
    END IF;
    -- A merged-away ID is only routing metadata, not another Company row.
    IF projected->>'status' = 'alias' THEN
        INSERT INTO mdm_v2.company_alias(
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
    INSERT INTO mdm_v2.company (
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
        selected->'jurisdiction'->>'value',selected->'address'->'value',
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

-- Rebuild every historical Company version, in generation order, on a
-- populated store. One batch's repeated projection is a no-op in the helper.
DO $$
DECLARE item record;
BEGIN
    FOR item IN
        SELECT b.batch_id,b.created_at,p.value->'body' AS body
        FROM mdm_v2.batch b
        CROSS JOIN LATERAL jsonb_array_elements(b.effects->'projections') p
        WHERE p.value->>'object_type'='entity'
          AND p.value->'body'->>'kind'='company'
        ORDER BY b.generation,p.value->>'object_id'
    LOOP
        PERFORM mdm_v2.record_company_projection(item.body,item.batch_id,item.created_at);
    END LOOP;
END;
$$;

CREATE FUNCTION mdm_v2.project_company_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE recorded_at timestamptz;
BEGIN
    IF NEW.object_type='entity' AND NEW.body->>'kind'='company' THEN
        SELECT created_at INTO recorded_at FROM mdm_v2.batch WHERE batch_id=NEW.batch_id;
        PERFORM mdm_v2.record_company_projection(NEW.body,NEW.batch_id,recorded_at);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER project_company_version AFTER INSERT OR UPDATE ON mdm_v2.projection
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.project_company_version();

-- Company field provenance is now read from the dated Company authority.
DROP VIEW mdm_v2.company_master_field;
DROP VIEW mdm_v2.company_master;
CREATE VIEW mdm_v2.company_master_field AS
SELECT c.entity_id,c.batch_id,c.status,f.key AS field_name,
       f.value->>'value' AS field_value,(f.value->>'cleared')::boolean AS cleared,
       f.value->'winner'->>'source_code' AS source_code,
       f.value->'winner'->>'record_key' AS record_key,
       (f.value->'winner'->>'effective_at')::timestamptz AS effective_at,
       f.value->>'policy_digest' AS policy_digest,
       f.value->>'kind_version' AS kind_version,
       jsonb_array_length(coalesce(f.value->'conflicts','[]'::jsonb)) AS conflict_count
FROM mdm_v2.company c
CROSS JOIN LATERAL jsonb_each(c.fields) f
WHERE c.valid_to IS NULL;
REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM PUBLIC;
