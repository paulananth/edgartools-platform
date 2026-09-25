-- The records waiting in the Stage, with the kind each probably is.
--
-- A record no kind has accepted is kept in mdm_v2.deferred_record with the
-- reason it waits. The per-kind Stage views (033, 034) show only records a
-- kind accepted, so a waiting record appeared in none of them. This view shows
-- every record still waiting, with its Probable Kind (CONTEXT.md): the kind
-- the rule step or contract that held it back names for it. It sorts the Stage
-- and never creates an identity. Null means no step named one.
--
-- Shape only: no new storage. "Still waiting" is its review being open and
-- not retired, the same disposition commit_batch_evidence checks (030).
--
-- The columns are listed rather than SELECT *, for the reason 033 gives.
CREATE VIEW mdm_v2.stage_waiting AS
SELECT d.deferred_id,
       d.source_code,
       d.publication_key,
       d.record_locator,
       d.batch_id,
       d.body->>'probable_kind' AS probable_kind,
       d.body->>'reason' AS reason,
       d.body->'provenance'->'classification'->>'rule_id' AS rule_id,
       d.body->'provenance'->'classification'->>'version' AS rule_version,
       d.body->'provenance'->'classification'->>'step' AS rule_step,
       (r.body->>'blocking')::boolean AS blocking,
       d.body->'raw_record' AS raw_record
FROM mdm_v2.deferred_record d
JOIN mdm_v2.projection r
  ON r.object_type = 'review' AND r.object_id = d.deferred_id
WHERE r.body->'open' = 'true'::jsonb
  AND coalesce(r.body->'retired', 'false'::jsonb) = 'false'::jsonb;

-- Listing the records waiting as one Probable Kind reads this key.
CREATE INDEX clean_deferred_probable_kind
    ON mdm_v2.deferred_record ((body->>'probable_kind'));

-- As in 033: close PUBLIC on the new view; store.migrate() re-grants SELECT.
REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM PUBLIC;
