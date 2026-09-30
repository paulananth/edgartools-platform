-- Approval on test evidence, by saying so (rules skill ticket 14, operator
-- 2026-09-29): "Rules can't be approved without test evidence, it can be
-- overruled but test evidence must exist". A proof may now be recorded
-- failing; approval needs a recorded proof, and a failing one only with an
-- overrule reason. The approver is named with their exact words; the login
-- that recorded it is kept beside them. Rows approved before this keep their
-- approval: the new columns are checked only when an approval is made.
ALTER TABLE rules.rule_version
  ADD COLUMN approved_words text,
  ADD COLUMN approval_overrule text,
  ADD COLUMN approval_evidence text,
  ADD COLUMN approval_recorded_by text;

CREATE OR REPLACE FUNCTION rules.govern_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,rules AS $$
DECLARE approval_required boolean; rank_old integer; rank_new integer; passed boolean; overruled boolean;
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Rule history is retained'; END IF;
  IF TG_OP='INSERT' THEN
    IF NEW.status<>'draft' OR NEW.created_by<>session_user OR NEW.proof IS NOT NULL
      OR NEW.approved_by IS NOT NULL OR NEW.approved_at IS NOT NULL OR NEW.proved_at IS NOT NULL
      OR NEW.approved_words IS NOT NULL OR NEW.approval_overrule IS NOT NULL
      OR NEW.approval_evidence IS NOT NULL OR NEW.approval_recorded_by IS NOT NULL
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
  -- A failing proof may be replaced by a new run until the version is proven
  -- or approved; from then on the evidence is fixed.
  IF (NEW.proof,NEW.batch_hash,NEW.proved_at) IS DISTINCT FROM (OLD.proof,OLD.batch_hash,OLD.proved_at) THEN
    IF OLD.proof IS NOT NULL AND (OLD.status<>'draft' OR OLD.approved_by IS NOT NULL) THEN
      RAISE EXCEPTION 'Rule proof is immutable'; END IF;
    IF NEW.proof IS NULL OR NEW.proof->>'digest' IS DISTINCT FROM NEW.digest
      OR jsonb_typeof(NEW.proof->'passed') IS DISTINCT FROM 'boolean'
      OR NEW.batch_hash IS NULL OR NEW.batch_hash !~ '^[0-9a-f]{64}$'
      OR NEW.proof->>'batch_hash' IS DISTINCT FROM NEW.batch_hash THEN
      RAISE EXCEPTION 'Proof must pin the exact rule and input batch and say whether it passed'; END IF;
    NEW.proved_at := clock_timestamp();
  END IF;
  IF (NEW.approved_by,NEW.approved_at,NEW.approved_words,NEW.approval_overrule,NEW.approval_evidence,NEW.approval_recorded_by)
    IS DISTINCT FROM (OLD.approved_by,OLD.approved_at,OLD.approved_words,OLD.approval_overrule,OLD.approval_evidence,OLD.approval_recorded_by) THEN
    IF OLD.approved_by IS NOT NULL THEN RAISE EXCEPTION 'An approval is never changed'; END IF;
    IF coalesce(btrim(NEW.approved_by),'')='' OR coalesce(btrim(NEW.approved_words),'')='' THEN
      RAISE EXCEPTION 'An approval names who approved and holds their exact words'; END IF;
    IF NEW.proof IS NULL OR NEW.status NOT IN ('draft','proven') THEN
      RAISE EXCEPTION 'No approval without test evidence'; END IF;
    IF NEW.proof->'passed'='false'::jsonb AND coalesce(btrim(NEW.approval_overrule),'')='' THEN
      RAISE EXCEPTION 'A failing proof is approved only with an overrule reason'; END IF;
    IF NEW.proof->'passed'='true'::jsonb AND NEW.approval_overrule IS NOT NULL THEN
      RAISE EXCEPTION 'A passing proof has nothing to overrule'; END IF;
    NEW.approved_at := clock_timestamp();
    NEW.approval_evidence := encode(sha256(convert_to(NEW.proof::text,'UTF8')),'hex');
    NEW.approval_recorded_by := session_user;
  END IF;
  IF NEW.status IN ('proven','active') THEN
    passed := NEW.proof->'passed'='true'::jsonb;
    overruled := NEW.approved_by IS NOT NULL AND NEW.approval_overrule IS NOT NULL;
    IF NEW.proof IS NULL OR NEW.proof->>'digest' IS DISTINCT FROM NEW.digest
      OR NOT coalesce(passed OR overruled,false)
      OR NEW.batch_hash IS NULL OR NEW.batch_hash !~ '^[0-9a-f]{64}$'
      OR NEW.proof->>'batch_hash' IS DISTINCT FROM NEW.batch_hash THEN
      RAISE EXCEPTION 'Proof must pass, or be overruled on approval, and pin the exact rule and input batch'; END IF;
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
REVOKE ALL ON FUNCTION rules.govern_version() FROM PUBLIC;
