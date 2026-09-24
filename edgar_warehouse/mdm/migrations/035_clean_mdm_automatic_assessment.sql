-- Company mastering ticket 04: an automatic proposal is assessed too (Q13).
--
-- A matching rule's proposals (bindings and new Companies) are kept in the
-- assessment beside the caller's command, under `automatic`, never inside it:
-- they carry fresh ids, and putting them in the command would change its hash
-- and make a redelivered batch look like a different command.
--
-- 028's record_assessment accepted only a command carrying its own bind or
-- merge, so a load batch whose only identity work is a rule's was refused.
-- This replaces it with one change: the proposals may come from the command,
-- from `automatic`, or both. Every other check is 028's, unchanged.
-- CREATE OR REPLACE keeps the function's owner and privileges. The caller and
-- automatic lists are each bounded at 1000, so up to 2000 together.
--
-- It also indexes the two identifiers a matching rule looks up, so the lookup
-- the Merge Stage runs under its lock is not a scan of every Stage record.

CREATE OR REPLACE FUNCTION mdm_v2.record_assessment(body_text text,root_run uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
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
    INSERT INTO mdm_v2.assessment(assessment_id,body) VALUES(key,b) ON CONFLICT DO NOTHING;
    IF NOT EXISTS(SELECT 1 FROM mdm_v2.assessment WHERE assessment_id=key AND body=b) THEN
        RAISE EXCEPTION 'Assessment digest collision';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM mdm_v2.assessment_event WHERE assessment_id=key) THEN
        INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event)
            VALUES(key,root_run,b->>'outcome') ON CONFLICT DO NOTHING;
    END IF;
    INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event)
        VALUES(key,root_run,'observed') ON CONFLICT DO NOTHING;
    RETURN key;
END;
$$;

CREATE INDEX clean_assertion_identifier_cik
    ON mdm_v2.assertion ((body->'identifiers'->>'cik'));
CREATE INDEX clean_assertion_identifier_lei
    ON mdm_v2.assertion ((body->'identifiers'->>'lei'));
