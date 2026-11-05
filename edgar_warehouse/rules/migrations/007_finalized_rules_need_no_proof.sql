-- Finalized rules need no proof to activate (operator, 2026-11-04: "you dont need proof to activate once the rules
-- are finalized"; asked: "Rules merged on main (Recommended)"). A version whose rules are merged on main is approved
-- on that reference alone (`finalized_ref`, the merge), in the operator's name and exact words, and activates with
-- no recorded test run. Every other version keeps the lifecycle of migrations 003 to 006: proof, approval and the
-- MDM handoff receipt. The reference is set once, with the approval.
ALTER TABLE rules.rule_version ADD COLUMN finalized_ref text;

CREATE OR REPLACE FUNCTION rules.govern_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,rules AS $$
DECLARE approval_required boolean; rank_old integer; rank_new integer; passed boolean; overruled boolean;
  one_to_one boolean; final boolean;
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Rule history is retained'; END IF;
  IF NEW.kind='source' AND NEW.body::jsonb ? 'mdm' AND (TG_OP='INSERT' OR NEW.status IN ('proven','active')) THEN
    RAISE EXCEPTION 'Dataset Contracts are in dataset_contracts, not mdm (ticket 171); save the source again'; END IF;
  IF TG_OP='INSERT' THEN
    IF NEW.status<>'draft' OR NEW.created_by<>session_user OR NEW.proof IS NOT NULL
      OR NEW.approved_by IS NOT NULL OR NEW.approved_at IS NOT NULL OR NEW.proved_at IS NOT NULL
      OR NEW.approved_words IS NOT NULL OR NEW.approval_overrule IS NOT NULL
      OR NEW.approval_evidence IS NOT NULL OR NEW.approval_recorded_by IS NOT NULL OR NEW.finalized_ref IS NOT NULL
      OR NEW.activated_at IS NOT NULL OR NEW.retired_at IS NOT NULL THEN
      RAISE EXCEPTION 'New rules must be unapproved drafts'; END IF;
    RETURN NEW;
  END IF;
  IF (NEW.kind,NEW.name,NEW.version,NEW.body,NEW.digest,NEW.created_by,NEW.created_at)
    IS DISTINCT FROM (OLD.kind,OLD.name,OLD.version,OLD.body,OLD.digest,OLD.created_by,OLD.created_at) THEN
    RAISE EXCEPTION 'Rule content and identity are immutable'; END IF;
  one_to_one := NEW.kind='source' AND NOT (NEW.body::jsonb ? 'dataset_contracts') AND NOT (NEW.body::jsonb ? 'acquisition')
    AND NOT EXISTS(SELECT 1 FROM jsonb_object_keys(coalesce(NEW.body::jsonb#>'{bookkeeping,targets}','{}')) target WHERE target='mdm');
  rank_old := array_position(ARRAY['draft','proven','active','retired'],OLD.status);
  rank_new := array_position(ARRAY['draft','proven','active','retired'],NEW.status);
  IF rank_new<rank_old OR (rank_new>rank_old+1 AND NOT (one_to_one AND OLD.status='draft' AND NEW.status='active')) THEN RAISE EXCEPTION 'Invalid rules lifecycle transition'; END IF;
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
  -- Finalized rules (merged on main) are approved on that reference, with no test run (operator, 2026-11-04:
  -- "you dont need proof to activate once the rules are finalized"). The reference is set only with an approval.
  IF NEW.finalized_ref IS DISTINCT FROM OLD.finalized_ref AND (OLD.approved_by IS NOT NULL OR NEW.approved_by IS NULL
     OR coalesce(btrim(NEW.finalized_ref),'')='') THEN
    RAISE EXCEPTION 'A finalized reference is set once, with the approval, and is not blank'; END IF;
  final := coalesce(btrim(NEW.finalized_ref),'')<>'';
  IF (NEW.approved_by,NEW.approved_at,NEW.approved_words,NEW.approval_overrule,NEW.approval_evidence,NEW.approval_recorded_by)
    IS DISTINCT FROM (OLD.approved_by,OLD.approved_at,OLD.approved_words,OLD.approval_overrule,OLD.approval_evidence,OLD.approval_recorded_by) THEN
    IF OLD.approved_by IS NOT NULL THEN RAISE EXCEPTION 'An approval is never changed'; END IF;
    IF coalesce(btrim(NEW.approved_by),'')='' OR coalesce(btrim(NEW.approved_words),'')='' THEN
      RAISE EXCEPTION 'An approval names who approved and holds their exact words'; END IF;
    IF (NEW.proof IS NULL AND NOT final) OR NEW.status NOT IN ('draft','proven') THEN
      RAISE EXCEPTION 'No approval without test evidence'; END IF;
    IF NEW.proof->'passed'='false'::jsonb AND coalesce(btrim(NEW.approval_overrule),'')='' THEN
      RAISE EXCEPTION 'A failing proof is approved only with an overrule reason'; END IF;
    IF NEW.proof->'passed'='true'::jsonb AND NEW.approval_overrule IS NOT NULL THEN
      RAISE EXCEPTION 'A passing proof has nothing to overrule'; END IF;
    NEW.approved_at := clock_timestamp();
    NEW.approval_evidence := CASE WHEN NEW.proof IS NULL THEN btrim(NEW.finalized_ref)
      ELSE encode(sha256(convert_to(NEW.proof::text,'UTF8')),'hex') END;
    NEW.approval_recorded_by := session_user;
  END IF;
  IF NEW.status IN ('proven','active') AND NOT ((one_to_one OR (final AND NEW.approved_by IS NOT NULL)) AND NEW.proof IS NULL) THEN
    passed := NEW.proof->'passed'='true'::jsonb;
    overruled := NEW.approved_by IS NOT NULL AND NEW.approval_overrule IS NOT NULL;
    IF NEW.proof IS NULL OR NEW.proof->>'digest' IS DISTINCT FROM NEW.digest
      OR NOT coalesce(passed OR overruled,false)
      OR NEW.batch_hash IS NULL OR NEW.batch_hash !~ '^[0-9a-f]{64}$'
      OR NEW.proof->>'batch_hash' IS DISTINCT FROM NEW.batch_hash THEN
      RAISE EXCEPTION 'Proof must pass, or be overruled on approval, and pin the exact rule and input batch'; END IF;
  END IF;
  approval_required := NEW.kind='merge' OR (NEW.body::jsonb ? 'dataset_contracts') OR
    EXISTS(SELECT 1 FROM jsonb_object_keys(coalesce(NEW.body::jsonb#>'{bookkeeping,targets}','{}')) target WHERE target='mdm');
  IF NEW.status='active' THEN
    IF NOT one_to_one AND NOT (final AND NEW.approved_by IS NOT NULL AND NEW.proof IS NULL)
       AND (NEW.proof IS NULL OR (approval_required AND NEW.approved_by IS NULL)) THEN
      RAISE EXCEPTION 'Activation requires proof and MDM approval'; END IF;
    IF (NEW.kind='merge' OR (NEW.kind='source' AND NEW.body::jsonb ? 'dataset_contracts')) AND
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
