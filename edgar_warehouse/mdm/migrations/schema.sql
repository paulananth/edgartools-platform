-- MDM's own schema: the init stamp, the record of what init installed. `mdm init` creates it in an empty database,
-- then installs the mastering tables, which hold the golden records. The rules MDM runs by are registered in the
-- Rules Database (control).
SET LOCAL check_function_bodies = false;

CREATE SCHEMA mdm;

COMMENT ON SCHEMA mdm IS 'Master Data Management''s install record: what init installed. The application login reads it.';

CREATE TABLE mdm.migration (
    name text NOT NULL,
    checksum text NOT NULL,
    installed_at timestamp with time zone DEFAULT now() NOT NULL
);

COMMENT ON TABLE mdm.migration IS 'Which migration files are applied, with their checksums. A changed file is refused. Written and read by mdm init.';

COMMENT ON COLUMN mdm.migration.name IS 'The migration file''s name.';

COMMENT ON COLUMN mdm.migration.checksum IS 'The sha256 of the file as applied.';

COMMENT ON COLUMN mdm.migration.installed_at IS 'When it was applied.';

ALTER TABLE ONLY mdm.migration
    ADD CONSTRAINT migration_pkey PRIMARY KEY (name);
