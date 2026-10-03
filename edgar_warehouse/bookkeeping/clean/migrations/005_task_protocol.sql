-- The task protocol (mastering to-do 20a). A worker in another process reports
-- a candidate; only an admitted verifier report completes it. The five control
-- tables stay the whole boundary: this adds two columns and one state.
ALTER TABLE bookkeeping.pipeline_run ADD COLUMN runtimes jsonb NOT NULL DEFAULT '{}';
ALTER TABLE bookkeeping.work_item ADD COLUMN candidate jsonb;
ALTER TABLE bookkeeping.work_item DROP CONSTRAINT work_item_state_check;
ALTER TABLE bookkeeping.work_item ADD CONSTRAINT work_item_state_check
  CHECK (state IN ('pending','running','reported','waiting','verified'));

-- Live authority covers a reported unit until it is verified or its lease ends.
CREATE OR REPLACE FUNCTION bookkeeping.authority(r uuid,s text,k text,a uuid,proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; p jsonb; l bookkeeping.lease%ROWTYPE;
BEGIN
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r AND state IN ('running','waiting') FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Run is not executable'; END IF;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state NOT IN ('running','reported') OR w.attempt IS DISTINCT FROM a THEN RAISE EXCEPTION 'Stale attempt'; END IF;
  IF proof IS NULL OR jsonb_typeof(proof) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Lease proof must be an explicit array'; END IF;
  IF jsonb_array_length(proof)<>jsonb_array_length(w.resources) OR
    (SELECT count(DISTINCT value->>'resource') FROM jsonb_array_elements(proof))<>jsonb_array_length(w.resources)
    THEN RAISE EXCEPTION 'Incomplete lease proof'; END IF;
  FOR p IN SELECT value FROM jsonb_array_elements(proof) ORDER BY value->>'resource' LOOP
    IF NOT w.resources ? (p->>'resource') THEN RAISE EXCEPTION 'Unexpected resource'; END IF;
    SELECT * INTO STRICT l FROM bookkeeping.lease WHERE resource=p->>'resource' FOR UPDATE;
    IF l.run_id IS DISTINCT FROM r OR l.attempt IS DISTINCT FROM a
      OR l.token IS DISTINCT FROM (p->>'token')::bigint OR l.expires_at<=clock_timestamp() THEN
      RAISE EXCEPTION 'Stale lease';
    END IF;
  END LOOP;
END;
$$;

-- A worker reports its candidate under live authority. The first report of a
-- profile pins its runtime for the run; another runtime later is refused.
CREATE FUNCTION bookkeeping.report(r uuid,s text,k text,a uuid,proof jsonb,candidate jsonb,profile text,runtime text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; pinned text;
BEGIN
  IF candidate IS NULL OR jsonb_typeof(candidate) IS DISTINCT FROM 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(candidate))<>2
     OR jsonb_typeof(candidate->'uri') IS DISTINCT FROM 'string' OR candidate->>'uri'=''
     OR coalesce(candidate->>'sha256','') !~ '^[0-9a-f]{64}$'
     OR coalesce(profile,'') !~ '^[a-z][a-z0-9_.-]*$' OR coalesce(runtime,'') !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'A report names a candidate URI and hash, its profile and runtime'; END IF;
  PERFORM bookkeeping.authority(r,s,k,a,proof);
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state='reported' THEN
    IF w.candidate IS DISTINCT FROM candidate THEN RAISE EXCEPTION 'Conflicting candidate for this attempt'; END IF;
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
  UPDATE bookkeeping.work_item SET state='reported',candidate=report.candidate,error=NULL
    WHERE run_id=r AND step=s AND unit_key=k;
END;
$$;
REVOKE ALL ON FUNCTION bookkeeping.report(uuid,text,text,uuid,jsonb,jsonb,text,text) FROM PUBLIC;

-- A reported unit belongs to verifiers. The verifier holds the same attempt's
-- leases: renewed while live, re-taken with a new token once they lapse, and
-- refused while another attempt holds a resource.
CREATE FUNCTION bookkeeping.verify_claim(r uuid,s text,k text,a uuid,seconds integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping SET lock_timeout='100ms' AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; l bookkeeping.lease%ROWTYPE; resource_key text; result jsonb := '[]';
BEGIN
  IF seconds < 2 OR seconds > 86400 THEN RAISE EXCEPTION 'Invalid lease duration'; END IF;
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r AND state IN ('running','waiting') FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Run is not executable'; END IF;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state<>'reported' OR w.attempt IS DISTINCT FROM a THEN RETURN NULL; END IF;
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
REVOKE ALL ON FUNCTION bookkeeping.verify_claim(uuid,text,text,uuid,integer) FROM PUBLIC;

-- Acquisition authorization belongs to the acquisition worker's own Journal
-- intent (mastering to-do 20c); control no longer writes it.
DROP FUNCTION bookkeeping.authorize_request(uuid,text,text,uuid,jsonb,uuid,jsonb);

-- Completion is only ever the reported candidate: no path verifies work that
-- skipped the report, whichever finish function commits it.
CREATE FUNCTION bookkeeping.reported_candidate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  IF NEW.state='verified' AND OLD.state<>'verified' AND (OLD.state<>'reported' OR OLD.candidate IS NULL
     OR NEW.receipt->>'uri' IS DISTINCT FROM OLD.candidate->>'uri'
     OR NEW.receipt->>'sha256' IS DISTINCT FROM OLD.candidate->>'sha256') THEN
    RAISE EXCEPTION 'Completion must be the reported candidate';
  END IF;
  IF NEW.state='running' AND OLD.state<>'running' THEN NEW.candidate := NULL; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER completion_is_reported BEFORE UPDATE OF state ON bookkeeping.work_item
  FOR EACH ROW EXECUTE FUNCTION bookkeeping.reported_candidate();
