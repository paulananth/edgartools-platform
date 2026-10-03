-- Who may work and who may verify (mastering to-do 20b). A run freezes each
-- step's worker profile in its submission (`profiles`). Each profile has two
-- group roles: its worker role may claim, renew, report and give up its work;
-- its verifier role may verify and complete it. The login that completes a
-- unit is never the one that reported it. Profiles are granted with
-- `bookkeeping grant-profile`; a profile nobody was granted does nothing.
ALTER TABLE bookkeeping.work_item ADD COLUMN reporter text;
ALTER TABLE bookkeeping.work_item ADD COLUMN verifier text;

-- One role per profile and duty: readable, within PostgreSQL's 63-byte limit,
-- and distinct for names that read alike ("a.b" and "a_b").
CREATE FUNCTION bookkeeping.profile_role(profile text,duty text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
  SELECT 'bk_'||duty||'_'||left(regexp_replace(profile,'[^a-z0-9]','_','g'),32)||'_'||left(md5(profile),8)
$$;

CREATE FUNCTION bookkeeping.frozen_profile(r uuid,s text) RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,bookkeeping AS $$
  SELECT submission->'profiles'->>s FROM bookkeeping.pipeline_run WHERE run_id=r
$$;

CREATE FUNCTION bookkeeping.issuer(profile text,duty text) RETURNS boolean
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,bookkeeping AS $$
DECLARE role text := bookkeeping.profile_role(profile,duty);
BEGIN
  RETURN profile IS NOT NULL AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role)
    AND pg_has_role(session_user,role,'MEMBER');
END;
$$;

CREATE FUNCTION bookkeeping.require(r uuid,s text,duties text[]) RETURNS void
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,bookkeeping AS $$
DECLARE profile text := bookkeeping.frozen_profile(r,s); duty text;
BEGIN
  FOREACH duty IN ARRAY duties LOOP
    IF bookkeeping.issuer(profile,duty) THEN RETURN; END IF;
  END LOOP;
  RAISE EXCEPTION 'This login has no % role for profile %', array_to_string(duties,' or '), coalesce(profile,'(none)');
END;
$$;

-- The 001 lifecycle functions keep their bodies; each now checks the caller
-- first. Their old names are owner-only.
ALTER FUNCTION bookkeeping.claim(uuid,text,text,uuid,integer,jsonb) RENAME TO claim_unit;
ALTER FUNCTION bookkeeping.heartbeat(uuid,text,text,uuid,jsonb,integer) RENAME TO renew_unit;
ALTER FUNCTION bookkeeping.wait_work(uuid,text,text,text,uuid,jsonb) RENAME TO release_unit;

CREATE FUNCTION bookkeeping.claim(r uuid,s text,k text,a uuid,seconds integer,prereqs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping SET lock_timeout='100ms' AS $$
BEGIN
  PERFORM bookkeeping.require(r,s,ARRAY['worker']);
  RETURN bookkeeping.claim_unit(r,s,k,a,seconds,prereqs);
END;
$$;
CREATE FUNCTION bookkeeping.heartbeat(r uuid,s text,k text,a uuid,proof jsonb,seconds integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  PERFORM bookkeeping.require(r,s,ARRAY['worker','verifier']);
  RETURN bookkeeping.renew_unit(r,s,k,a,proof,seconds);
END;
$$;
CREATE FUNCTION bookkeeping.wait_work(r uuid,s text,k text,message text,a uuid,proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  PERFORM bookkeeping.require(r,s,ARRAY['worker','verifier']);
  PERFORM bookkeeping.release_unit(r,s,k,message,a,proof);
END;
$$;
REVOKE ALL ON FUNCTION bookkeeping.claim_unit(uuid,text,text,uuid,integer,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION bookkeeping.renew_unit(uuid,text,text,uuid,jsonb,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION bookkeeping.release_unit(uuid,text,text,text,uuid,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION bookkeeping.claim(uuid,text,text,uuid,integer,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION bookkeeping.heartbeat(uuid,text,text,uuid,jsonb,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION bookkeeping.wait_work(uuid,text,text,text,uuid,jsonb) FROM PUBLIC;

-- A report is for the run's frozen profile, by a login of its worker role.
CREATE OR REPLACE FUNCTION bookkeeping.report(r uuid,s text,k text,a uuid,proof jsonb,candidate jsonb,profile text,runtime text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; pinned text;
BEGIN
  IF candidate IS NULL OR jsonb_typeof(candidate) IS DISTINCT FROM 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(candidate))<>2
     OR jsonb_typeof(candidate->'uri') IS DISTINCT FROM 'string' OR candidate->>'uri'=''
     OR coalesce(candidate->>'sha256','') !~ '^[0-9a-f]{64}$'
     OR coalesce(runtime,'') !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'A report names a candidate URI and hash, and its runtime'; END IF;
  IF profile IS DISTINCT FROM bookkeeping.frozen_profile(r,s) THEN
    RAISE EXCEPTION 'A report names the profile the run froze for its step'; END IF;
  PERFORM bookkeeping.require(r,s,ARRAY['worker']);
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
  UPDATE bookkeeping.work_item SET state='reported',candidate=report.candidate,error=NULL,reporter=session_user
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
  PERFORM bookkeeping.require(r,s,ARRAY['verifier']);
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state<>'reported' OR w.attempt IS DISTINCT FROM a THEN RETURN NULL; END IF;
  IF session_user=w.reporter THEN RAISE EXCEPTION 'This login may not verify its own report'; END IF;
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

-- A verifier's runtime is pinned for the run, as a worker's is; it is called
-- in the completion's own transaction.
CREATE FUNCTION bookkeeping.pin_verifier(r uuid,s text,runtime text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE profile text := bookkeeping.frozen_profile(r,s); slot text; pinned text;
BEGIN
  IF coalesce(runtime,'') !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'A verifier names its runtime digest'; END IF;
  PERFORM bookkeeping.require(r,s,ARRAY['verifier']);
  slot := 'verify:'||profile;
  SELECT runtimes->>slot INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r;
  IF pinned IS NULL THEN
    SELECT runtimes->>slot INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
    IF pinned IS NULL THEN
      UPDATE bookkeeping.pipeline_run SET runtimes=runtimes||jsonb_build_object(slot,runtime) WHERE run_id=r;
      RETURN;
    END IF;
  END IF;
  IF pinned<>runtime THEN RAISE EXCEPTION 'Pinned verifier runtime changed; start a new run'; END IF;
END;
$$;
REVOKE ALL ON FUNCTION bookkeeping.pin_verifier(uuid,text,text) FROM PUBLIC;

-- Completion: the reported candidate, completed by a verifier of the frozen
-- profile that did not report it; the verifying login is kept with it.
CREATE OR REPLACE FUNCTION bookkeeping.reported_candidate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  IF NEW.state='verified' AND OLD.state<>'verified' THEN
    IF OLD.state<>'reported' OR OLD.candidate IS NULL
       OR NEW.receipt->>'uri' IS DISTINCT FROM OLD.candidate->>'uri'
       OR NEW.receipt->>'sha256' IS DISTINCT FROM OLD.candidate->>'sha256' THEN
      RAISE EXCEPTION 'Completion must be the reported candidate';
    END IF;
    IF NOT bookkeeping.issuer(bookkeeping.frozen_profile(OLD.run_id,OLD.step),'verifier')
       OR session_user IS NOT DISTINCT FROM OLD.reporter THEN
      RAISE EXCEPTION 'Completion needs a verifier of this profile other than its reporter';
    END IF;
    NEW.verifier := session_user;
  END IF;
  IF NEW.state='running' AND OLD.state<>'running' THEN
    NEW.candidate := NULL; NEW.reporter := NULL;
  END IF;
  RETURN NEW;
END;
$$;
