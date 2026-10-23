-- Candidate routes are chosen by the build-pinned comparison profile, not by
-- source-specific JSON expressions. Probe one bounded document per key.
-- The current reading remains authoritative; no second candidate write path.
CREATE INDEX stage_record_matching ON mdm.stage_record
    USING gin ((reading->'provenance'->'matching') jsonb_path_ops)
    WITH (fastupdate = off);
COMMENT ON INDEX mdm.stage_record_matching IS
    'Finds current candidate readings through configured matching metadata paths, one key per indexed probe, with no pending list. The caller checks exact scalar/array positions after containment.';
