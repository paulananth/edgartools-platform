-- One version table for source, merge and platform pipeline documents.
CREATE SCHEMA rules;
REVOKE ALL ON SCHEMA rules FROM PUBLIC;
CREATE TABLE rules.rule_version (
  kind text NOT NULL CHECK (kind IN ('source','merge','pipeline')),
  name text NOT NULL CHECK (name ~ '^[a-z][a-z0-9_.-]*$'),
  version text NOT NULL CHECK (version ~ '^[A-Za-z0-9][A-Za-z0-9_.-]*$'),
  body text NOT NULL, digest text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','proven','active','retired')),
  created_by text NOT NULL DEFAULT session_user, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  proved_at timestamptz, proof jsonb, batch_hash text,
  approved_by text, approved_at timestamptz,
  activated_at timestamptz, retired_at timestamptz, clean_mdm jsonb,
  PRIMARY KEY (kind,name,version),
  CHECK (digest=encode(sha256(convert_to(body,'UTF8')),'hex')),
  CHECK (jsonb_typeof(body::jsonb)='object')
);
CREATE UNIQUE INDEX one_active ON rules.rule_version(kind,name) WHERE status='active';

CREATE FUNCTION rules.govern_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,rules AS $$
DECLARE approval_required boolean; rank_old integer; rank_new integer;
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Rule history is retained'; END IF;
  IF TG_OP='INSERT' THEN
    IF NEW.status<>'draft' OR NEW.created_by<>session_user OR NEW.proof IS NOT NULL
      OR NEW.approved_by IS NOT NULL OR NEW.approved_at IS NOT NULL OR NEW.proved_at IS NOT NULL
      OR NEW.activated_at IS NOT NULL OR NEW.retired_at IS NOT NULL THEN
      RAISE EXCEPTION 'New rules must be unapproved drafts'; END IF;
    RETURN NEW;
  END IF;
  IF (NEW.kind,NEW.name,NEW.version,NEW.body,NEW.digest,NEW.created_by,NEW.created_at)
    IS DISTINCT FROM (OLD.kind,OLD.name,OLD.version,OLD.body,OLD.digest,OLD.created_by,OLD.created_at) THEN
    RAISE EXCEPTION 'Rule content and identity are immutable'; END IF;
  rank_old := array_position(ARRAY['draft','proven','active','retired'],OLD.status);
  rank_new := array_position(ARRAY['draft','proven','active','retired'],NEW.status);
  IF rank_new<rank_old OR rank_new>rank_old+1 THEN RAISE EXCEPTION 'Invalid rules lifecycle transition'; END IF;
  IF OLD.proof IS NOT NULL AND (NEW.proof,NEW.batch_hash,NEW.proved_at) IS DISTINCT FROM (OLD.proof,OLD.batch_hash,OLD.proved_at) THEN
    RAISE EXCEPTION 'Rule proof is immutable'; END IF;
  IF (NEW.approved_by,NEW.approved_at) IS DISTINCT FROM (OLD.approved_by,OLD.approved_at) THEN
    IF OLD.approved_by IS NOT NULL OR NEW.approved_by IS DISTINCT FROM session_user OR NEW.approved_at IS NULL
       OR NOT pg_has_role(session_user,'rules_approver','member') OR NEW.status<>'proven' THEN
      RAISE EXCEPTION 'Only an approver own login may approve a proven version'; END IF;
    NEW.approved_at := clock_timestamp();
  END IF;
  IF NEW.status='proven' THEN
    IF NEW.proof IS NULL OR NEW.proof->>'digest' IS DISTINCT FROM NEW.digest
      OR NEW.proof->'passed' IS DISTINCT FROM 'true'::jsonb OR NEW.batch_hash IS NULL OR NEW.batch_hash !~ '^[0-9a-f]{64}$'
      OR NEW.proof->>'batch_hash' IS DISTINCT FROM NEW.batch_hash THEN
      RAISE EXCEPTION 'Proof must pass and pin the exact rule and input batch'; END IF;
    NEW.proved_at := coalesce(OLD.proved_at,clock_timestamp());
  END IF;
  approval_required := NEW.kind='merge' OR (NEW.body::jsonb ? 'mdm') OR
    EXISTS(SELECT 1 FROM jsonb_object_keys(coalesce(NEW.body::jsonb#>'{bookkeeping,targets}','{}')) target WHERE target='mdm');
  IF NEW.status='active' THEN
    IF NEW.proof IS NULL OR (approval_required AND NEW.approved_by IS NULL) THEN
      RAISE EXCEPTION 'Activation requires proof and MDM approval'; END IF;
    IF (NEW.kind='merge' OR (NEW.kind='source' AND NEW.body::jsonb ? 'mdm')) AND
       NEW.clean_mdm->>'rules_digest' IS DISTINCT FROM NEW.digest THEN
      RAISE EXCEPTION 'Activation requires an MDM handoff receipt for this rule'; END IF;
    NEW.activated_at := coalesce(OLD.activated_at,clock_timestamp());
  END IF;
  IF OLD.status IN ('active','retired') AND NEW.clean_mdm IS DISTINCT FROM OLD.clean_mdm THEN
    RAISE EXCEPTION 'MDM registration evidence is immutable'; END IF;
  IF NEW.status='retired' THEN NEW.retired_at := coalesce(OLD.retired_at,clock_timestamp()); END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER rule_governance BEFORE INSERT OR UPDATE OR DELETE ON rules.rule_version
  FOR EACH ROW EXECUTE FUNCTION rules.govern_version();
REVOKE ALL ON ALL TABLES IN SCHEMA rules FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA rules FROM PUBLIC;
