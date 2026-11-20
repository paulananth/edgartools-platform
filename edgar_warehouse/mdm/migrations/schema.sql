-- MDM's own schema: the registered rules (each Mastering Policy and Dataset Contract under its digest) and
-- the record of what init installed. `mdm init` creates it in an empty database, then installs governed
-- storage, the registration function (registration_authority.sql) and the mastering tables, which hold the
-- golden records.
SET LOCAL check_function_bodies = false;

CREATE SCHEMA mdm;

COMMENT ON SCHEMA mdm IS 'Master Data Management''s registered rules: each Mastering Policy and Dataset Contract under its digest, and what init installed. The application login reads it; the registration login adds to it.';

CREATE FUNCTION mdm.immutable_row() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'MDM rows of this table are never changed (append-only)'; END;
$$;

COMMENT ON FUNCTION mdm.immutable_row() IS 'Trigger function: refuses any change or delete of a row in a table that is never changed.';

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

CREATE TABLE mdm.migration (
    name text NOT NULL,
    checksum text NOT NULL,
    installed_at timestamp with time zone DEFAULT now() NOT NULL
);

COMMENT ON TABLE mdm.migration IS 'Which migration files are applied, with their checksums. A changed file is refused. Never changed. Written and read by mdm migrate.';

COMMENT ON COLUMN mdm.migration.name IS 'The migration file''s name.';

COMMENT ON COLUMN mdm.migration.checksum IS 'The sha256 of the file as applied.';

COMMENT ON COLUMN mdm.migration.installed_at IS 'When it was applied.';

CREATE TABLE mdm.policy (
    digest text NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT policy_body_check CHECK ((jsonb_typeof(body) = 'object'::text))
);

COMMENT ON TABLE mdm.policy IS 'Each Mastering Policy (the merge rules), stored by its fingerprint as approved. Never changed. Written by register_policy when rules activate runs; read by save_batch and the Merge Stage.';

COMMENT ON COLUMN mdm.policy.digest IS 'The policy''s fingerprint: the sha256 of its body.';

COMMENT ON COLUMN mdm.policy.body IS 'The whole policy: kinds, matching rules, field winners, required consumers and approvals.';

ALTER TABLE ONLY mdm.dataset_mapping
    ADD CONSTRAINT dataset_mapping_pkey PRIMARY KEY (source_code, mapping_version);

ALTER TABLE ONLY mdm.dataset
    ADD CONSTRAINT dataset_pkey PRIMARY KEY (source_code);

ALTER TABLE ONLY mdm.migration
    ADD CONSTRAINT migration_pkey PRIMARY KEY (name);

ALTER TABLE ONLY mdm.policy
    ADD CONSTRAINT policy_pkey PRIMARY KEY (digest);

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.dataset FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.dataset_mapping FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.migration FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

CREATE TRIGGER immutable_row BEFORE DELETE OR UPDATE ON mdm.policy FOR EACH ROW EXECUTE FUNCTION mdm.immutable_row();

ALTER TABLE ONLY mdm.dataset_mapping
    ADD CONSTRAINT dataset_mapping_source_code_fkey FOREIGN KEY (source_code) REFERENCES mdm.dataset(source_code);
