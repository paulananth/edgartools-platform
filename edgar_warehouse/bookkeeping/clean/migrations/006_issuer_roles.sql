-- Who may report and who may verify (mastering to-do 20b). Each worker profile
-- has two group roles: bk_worker_<profile> may report its work, and
-- bk_verifier_<profile> may verify and complete it. The login that verifies a
-- unit is never the login that reported it. Profiles are granted with
-- `bookkeeping grant-profile`; a profile nobody was granted reports nothing.
ALTER TABLE bookkeeping.work_item ADD COLUMN profile text;
ALTER TABLE bookkeeping.work_item ADD COLUMN reporter text;

CREATE FUNCTION bookkeeping.profile_role(profile text,duty text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
  SELECT 'bk_'||duty||'_'||regexp_replace(profile,'[^a-z0-9]','_','g')
$$;

CREATE FUNCTION bookkeeping.issuer(profile text,duty text) RETURNS boolean
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,bookkeeping AS $$
DECLARE role text := bookkeeping.profile_role(profile,duty);
BEGIN
  RETURN profile IS NOT NULL AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role)
    AND pg_has_role(session_user,role,'MEMBER');
END;
$$;

CREATE OR REPLACE FUNCTION bookkeeping.report(r uuid,s text,k text,a uuid,proof jsonb,candidate jsonb,profile text,runtime text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; pinned text;
BEGIN
  IF candidate IS NULL OR jsonb_typeof(candidate) IS DISTINCT FROM 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(candidate))<>2
     OR jsonb_typeof(candidate->'uri') IS DISTINCT FROM 'string' OR candidate->>'uri'=''
     OR coalesce(candidate->>'sha256','') !~ '^[0-9a-f]{64}$'
     OR coalesce(profile,'') !~ '^[a-z][a-z0-9_.-]*$' OR coalesce(runtime,'') !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'A report names a candidate URI and hash, its profile and runtime'; END IF;
  IF NOT bookkeeping.issuer(profile,'worker') THEN
    RAISE EXCEPTION 'This login may not report work for profile %', profile; END IF;
  PERFORM bookkeeping.authority(r,s,k,a,proof);
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state='reported' THEN
    IF w.candidate IS DISTINCT FROM candidate OR w.reporter IS DISTINCT FROM session_user THEN
      RAISE EXCEPTION 'Conflicting candidate for this attempt'; END IF;
    RETURN;  -- a lost acknowledgement
  END IF;
  SELECT runtimes->>profile INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r;
  IF pinned IS NULL THEN
    -- Only the first report of a profile takes the run row's lock.
    SELECT runtimes->>profile INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
    IF pinned IS NULL THEN
      UPDATE bookkeeping.pipeline_run SET runtimes=runtimes||jsonb_build_object(profile,runtime) WHERE run_id=r;
      pinned := runtime;
    END IF;
  END IF;
  IF pinned<>runtime THEN RAISE EXCEPTION 'Pinned worker runtime changed; start a new run'; END IF;
  UPDATE bookkeeping.work_item SET state='reported',candidate=report.candidate,error=NULL,
    profile=report.profile,reporter=session_user
    WHERE run_id=r AND step=s AND unit_key=k;
END;
$$;

CREATE OR REPLACE FUNCTION bookkeeping.verify_claim(r uuid,s text,k text,a uuid,seconds integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping SET lock_timeout='100ms' AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; l bookkeeping.lease%ROWTYPE; resource_key text; result jsonb := '[]';
BEGIN
  IF seconds < 2 OR seconds > 86400 THEN RAISE EXCEPTION 'Invalid lease duration'; END IF;
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r AND state IN ('running','waiting') FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Run is not executable'; END IF;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state<>'reported' OR w.attempt IS DISTINCT FROM a THEN RETURN NULL; END IF;
  IF NOT bookkeeping.issuer(w.profile,'verifier') OR session_user=w.reporter THEN
    RAISE EXCEPTION 'This login may not verify work for profile %', w.profile; END IF;
  FOR resource_key IN SELECT jsonb_array_elements_text(w.resources) ORDER BY 1 LOOP
    SELECT * INTO STRICT l FROM bookkeeping.lease WHERE resource=resource_key FOR UPDATE NOWAIT;
    IF l.attempt IS DISTINCT FROM a AND l.expires_at>clock_timestamp() THEN
      RAISE EXCEPTION 'Lease contention' USING ERRCODE='55P03'; END IF;
    UPDATE bookkeeping.lease SET token=CASE WHEN l.attempt=a AND l.expires_at>clock_timestamp() THEN token ELSE token+1 END,
      run_id=r,attempt=a,expires_at=clock_timestamp()+make_interval(secs=>seconds),heartbeat_at=clock_timestamp()
      WHERE resource=resource_key RETURNING * INTO l;
    result := result || jsonb_build_array(jsonb_build_object('resource',l.resource,'token',l.token,
      'run_id',l.run_id,'attempt',l.attempt,'expires_at',l.expires_at));
  END LOOP;
  RETURN result;
END;
$$;

-- A verifier's runtime is pinned for the run, as a worker's is.
CREATE FUNCTION bookkeeping.pin_verifier(r uuid,profile text,runtime text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE pinned text; slot text := 'verify:'||profile;
BEGIN
  IF coalesce(runtime,'') !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'A verifier names its runtime digest'; END IF;
  IF NOT bookkeeping.issuer(profile,'verifier') THEN
    RAISE EXCEPTION 'This login may not verify work for profile %', profile; END IF;
  SELECT runtimes->>slot INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  IF pinned IS NULL THEN
    UPDATE bookkeeping.pipeline_run SET runtimes=runtimes||jsonb_build_object(slot,runtime) WHERE run_id=r;
  ELSIF pinned<>runtime THEN
    RAISE EXCEPTION 'Pinned verifier runtime changed; start a new run';
  END IF;
END;
$$;
REVOKE ALL ON FUNCTION bookkeeping.pin_verifier(uuid,text,text) FROM PUBLIC;

-- Completion: the reported candidate, completed by a verifier login of its
-- profile that did not report it.
CREATE OR REPLACE FUNCTION bookkeeping.reported_candidate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  IF NEW.state='verified' AND OLD.state<>'verified' THEN
    IF OLD.state<>'reported' OR OLD.candidate IS NULL
       OR NEW.receipt->>'uri' IS DISTINCT FROM OLD.candidate->>'uri'
       OR NEW.receipt->>'sha256' IS DISTINCT FROM OLD.candidate->>'sha256' THEN
      RAISE EXCEPTION 'Completion must be the reported candidate';
    END IF;
    IF NOT bookkeeping.issuer(OLD.profile,'verifier') OR session_user=OLD.reporter THEN
      RAISE EXCEPTION 'Completion needs a verifier of this profile other than its reporter';
    END IF;
  END IF;
  IF NEW.state='running' AND OLD.state<>'running' THEN
    NEW.candidate := NULL; NEW.profile := NULL; NEW.reporter := NULL;
  END IF;
  RETURN NEW;
END;
$$;
