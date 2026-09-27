-- Fresh Bookkeeping only. Exactly five control tables, no source records.
CREATE SCHEMA bookkeeping;
REVOKE ALL ON SCHEMA bookkeeping FROM PUBLIC;

CREATE TABLE bookkeeping.pipeline_run (
  run_id uuid PRIMARY KEY,
  submission jsonb NOT NULL,
  submission_hash text NOT NULL CHECK (submission_hash ~ '^[0-9a-f]{64}$'),
  expected_count bigint NOT NULL CHECK (expected_count >= 0),
  state text NOT NULL DEFAULT 'running' CHECK (state IN ('running','waiting','blocked','complete')),
  checks jsonb NOT NULL DEFAULT '{}',
  summary jsonb NOT NULL DEFAULT '{}',
  pinned boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  completed_at timestamptz,
  compacted_at timestamptz
);
CREATE TABLE bookkeeping.work_item (
  run_id uuid REFERENCES bookkeeping.pipeline_run,
  step text NOT NULL, unit_key text NOT NULL, ordinal bigint NOT NULL CHECK (ordinal >= 0),
  resources jsonb NOT NULL, unit jsonb NOT NULL,
  state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','running','waiting','verified')),
  attempt uuid, attempts bigint NOT NULL DEFAULT 0,
  authority_until timestamptz,
  receipt jsonb, checks jsonb NOT NULL DEFAULT '{}', error text,
  PRIMARY KEY (run_id,step,unit_key), UNIQUE (run_id,step,ordinal)
);
CREATE TABLE bookkeeping.lease (
  resource text PRIMARY KEY,
  token bigint NOT NULL DEFAULT 0 CHECK (token >= 0),
  run_id uuid REFERENCES bookkeeping.pipeline_run,
  attempt uuid, expires_at timestamptz NOT NULL DEFAULT '-infinity',
  heartbeat_at timestamptz
);
CREATE TABLE bookkeeping.checkpoint (
  run_id uuid REFERENCES bookkeeping.pipeline_run, scope text NOT NULL,
  ordinal bigint NOT NULL DEFAULT -1, cursor jsonb, receipt jsonb,
  PRIMARY KEY (run_id,scope)
);
CREATE TABLE bookkeeping.journal_outbox (
  event_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES bookkeeping.pipeline_run,
  step text NOT NULL, unit_key text NOT NULL,
  payload jsonb NOT NULL,
  attempts bigint NOT NULL DEFAULT 0, error text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(), delivered_at timestamptz,
  UNIQUE (run_id,step,unit_key)
);
CREATE INDEX pending_work ON bookkeeping.work_item(run_id,step,ordinal) WHERE state <> 'verified';
CREATE INDEX pending_delivery ON bookkeeping.journal_outbox(created_at) WHERE delivered_at IS NULL;

CREATE FUNCTION bookkeeping.completion_authority() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  IF NEW.state='verified' AND (NEW.authority_until IS NULL OR NEW.authority_until<=clock_timestamp()) THEN
    RAISE EXCEPTION 'Completion authority expired before commit'; END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER completion_valid_at_commit AFTER UPDATE OF state ON bookkeeping.work_item
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION bookkeeping.completion_authority();

CREATE FUNCTION bookkeeping.start_run(r uuid,s jsonb,h text,items jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE prior bookkeeping.pipeline_run%ROWTYPE; i jsonb;
BEGIN
  INSERT INTO bookkeeping.pipeline_run(run_id,submission,submission_hash,expected_count)
    VALUES(r,s,h,jsonb_array_length(items)) ON CONFLICT DO NOTHING;
  SELECT * INTO STRICT prior FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  IF prior.submission<>s OR prior.submission_hash<>h THEN RAISE EXCEPTION 'Frozen submission changed'; END IF;
  IF prior.compacted_at IS NOT NULL THEN RETURN; END IF;
  FOR i IN SELECT value FROM jsonb_array_elements(items) LOOP
    INSERT INTO bookkeeping.work_item(run_id,step,unit_key,ordinal,resources,unit)
      VALUES(r,i->>'step',i->>'key',(i->>'ordinal')::bigint,i->'resources',i->'unit') ON CONFLICT DO NOTHING;
    IF NOT EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r AND step=i->>'step'
       AND unit_key=i->>'key' AND ordinal=(i->>'ordinal')::bigint
       AND resources=i->'resources' AND unit=i->'unit') THEN
      RAISE EXCEPTION 'Frozen worklist changed';
    END IF;
    INSERT INTO bookkeeping.checkpoint(run_id,scope) VALUES(r,i->>'step') ON CONFLICT DO NOTHING;
  END LOOP;
  IF (SELECT count(*) FROM bookkeeping.work_item WHERE run_id=r)<>prior.expected_count THEN
    RAISE EXCEPTION 'Work accounting mismatch';
  END IF;
END;
$$;

-- Claim one specified bounded unit. Lock work first, then resources sorted.
-- Resource contention raises 55P03 so the entire acquisition rolls back.
CREATE FUNCTION bookkeeping.claim(r uuid,s text,k text,a uuid,seconds integer,prereqs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping SET lock_timeout='100ms' AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; l bookkeeping.lease%ROWTYPE;
        resource_key text; result jsonb := '[]'; dependency text;
BEGIN
  IF seconds < 2 OR seconds > 86400 THEN RAISE EXCEPTION 'Invalid lease duration'; END IF;
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r AND state IN ('running','waiting') FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Run is not executable'; END IF;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state='verified' THEN RETURN NULL; END IF;
  FOR dependency IN SELECT jsonb_array_elements_text(prereqs) LOOP
    IF EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r AND step=dependency AND state<>'verified') THEN
      RAISE EXCEPTION 'Prerequisite incomplete' USING ERRCODE='55P03';
    END IF;
  END LOOP;
  IF jsonb_array_length(w.resources)=0 THEN RAISE EXCEPTION 'Missing resources'; END IF;
  FOR resource_key IN SELECT jsonb_array_elements_text(w.resources) ORDER BY 1 LOOP
    INSERT INTO bookkeeping.lease(resource) VALUES(resource_key) ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT l FROM bookkeeping.lease WHERE resource=resource_key FOR UPDATE NOWAIT;
    IF l.expires_at>clock_timestamp() THEN RAISE EXCEPTION 'Lease contention' USING ERRCODE='55P03'; END IF;
    UPDATE bookkeeping.lease SET token=token+1,run_id=r,attempt=a,
      expires_at=clock_timestamp()+make_interval(secs=>seconds),heartbeat_at=clock_timestamp()
      WHERE resource=resource_key RETURNING * INTO l;
    result := result || jsonb_build_array(jsonb_build_object('resource',l.resource,'token',l.token,
      'run_id',l.run_id,'attempt',l.attempt,'expires_at',l.expires_at));
  END LOOP;
  UPDATE bookkeeping.work_item SET state='running',attempt=a,attempts=attempts+1,error=NULL
    WHERE run_id=r AND step=s AND unit_key=k;
  RETURN result;
END;
$$;

CREATE FUNCTION bookkeeping.authority(r uuid,s text,k text,a uuid,proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; p jsonb; l bookkeeping.lease%ROWTYPE;
BEGIN
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state<>'running' OR w.attempt IS DISTINCT FROM a THEN RAISE EXCEPTION 'Stale attempt'; END IF;
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

CREATE FUNCTION bookkeeping.heartbeat(r uuid,s text,k text,a uuid,proof jsonb,seconds integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE result jsonb;
BEGIN
  IF seconds < 2 OR seconds > 86400 THEN RAISE EXCEPTION 'Invalid lease duration'; END IF;
  PERFORM bookkeeping.authority(r,s,k,a,proof);
  UPDATE bookkeeping.lease SET expires_at=clock_timestamp()+make_interval(secs=>seconds),
    heartbeat_at=clock_timestamp() WHERE run_id=r AND attempt=a;
  SELECT jsonb_agg(jsonb_build_object('resource',resource,'token',token,'run_id',run_id,
    'attempt',attempt,'expires_at',expires_at) ORDER BY resource) INTO result
    FROM bookkeeping.lease WHERE run_id=r AND attempt=a;
  RETURN result;
END;
$$;

CREATE FUNCTION bookkeeping.finish(r uuid,s text,k text,a uuid,proof jsonb,receipt jsonb,checks jsonb,e uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; last_ordinal bigint; last_item bookkeeping.work_item%ROWTYPE;
BEGIN
  -- Same-run commits serialize briefly to advance ordered checkpoints. No
  -- global lock: independent runs and their destinations remain concurrent.
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state='verified' THEN
    IF w.receipt IS DISTINCT FROM receipt OR w.checks IS DISTINCT FROM checks THEN
      RAISE EXCEPTION 'Completion evidence changed'; END IF;
    RETURN;
  END IF;
  PERFORM bookkeeping.authority(r,s,k,a,proof);
  IF receipt IS NULL OR NOT receipt ? 'uri' OR NOT receipt ? 'sha256'
     OR NOT receipt ? 'evidence' OR receipt->>'sha256' !~ '^[0-9a-f]{64}$'
     OR checks='{}' OR EXISTS(SELECT 1 FROM jsonb_each(checks) WHERE value<>'true'::jsonb) THEN
    RAISE EXCEPTION 'Unverified completion';
  END IF;
  UPDATE bookkeeping.work_item SET state='verified',receipt=finish.receipt,checks=finish.checks,error=NULL,
    authority_until=(SELECT min(expires_at) FROM bookkeeping.lease WHERE run_id=r AND attempt=a)
    WHERE run_id=r AND step=s AND unit_key=k;
  INSERT INTO bookkeeping.journal_outbox(event_id,run_id,step,unit_key,payload)
    VALUES(e,r,s,k,jsonb_build_object('version',1,'event_id',e,'run_id',r,'step',s,'unit_key',k,
      'receipt',receipt,'checks',checks)) ON CONFLICT(run_id,step,unit_key) DO NOTHING;
  UPDATE bookkeeping.lease SET expires_at=clock_timestamp() WHERE run_id=r AND attempt=a;
  SELECT coalesce(min(ordinal)-1,(SELECT max(ordinal) FROM bookkeeping.work_item WHERE run_id=r AND step=s))
    INTO last_ordinal FROM bookkeeping.work_item WHERE run_id=r AND step=s AND state<>'verified';
  SELECT * INTO last_item FROM bookkeeping.work_item WHERE run_id=r AND step=s AND ordinal=last_ordinal;
  UPDATE bookkeeping.checkpoint SET ordinal=last_ordinal,cursor=last_item.unit->'cursor',receipt=last_item.receipt
    WHERE run_id=r AND scope=s AND ordinal<last_ordinal;
END;
$$;

CREATE FUNCTION bookkeeping.wait_work(r uuid,s text,k text,message text,a uuid,proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE current_attempt uuid;
BEGIN
  SELECT attempt INTO current_attempt FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF a IS NOT NULL THEN
    PERFORM bookkeeping.authority(r,s,k,a,proof);
    UPDATE bookkeeping.lease SET expires_at=clock_timestamp() WHERE run_id=r AND attempt=a;
  ELSIF current_attempt IS NOT NULL AND EXISTS(SELECT 1 FROM bookkeeping.lease
       WHERE run_id=r AND attempt=current_attempt AND expires_at>clock_timestamp()) THEN
    RETURN; -- contention must not rewrite the active owner's unit
  END IF;
  UPDATE bookkeeping.work_item SET state='waiting',error=message WHERE run_id=r AND step=s AND unit_key=k AND state<>'verified';
END;
$$;

CREATE FUNCTION bookkeeping.record_checks(r uuid,c jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE complete boolean; actual bigint; expected bigint;
BEGIN
  SELECT expected_count INTO STRICT expected FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  SELECT count(*) INTO actual FROM bookkeeping.work_item WHERE run_id=r;
  complete := c<>'{}' AND NOT EXISTS(SELECT 1 FROM jsonb_each(c) WHERE value<>'true'::jsonb)
    AND actual=expected AND NOT EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r AND state<>'verified')
    AND NOT EXISTS(SELECT 1 FROM bookkeeping.journal_outbox WHERE run_id=r AND delivered_at IS NULL);
  UPDATE bookkeeping.pipeline_run SET checks=c,
    state=CASE WHEN complete THEN 'complete' ELSE 'waiting' END,
    completed_at=CASE WHEN complete THEN clock_timestamp() ELSE NULL END,
    summary=jsonb_build_object('expected',expected,'verified',(SELECT count(*) FROM bookkeeping.work_item
       WHERE run_id=r AND state='verified'),'pending_deliveries',(SELECT count(*) FROM bookkeeping.journal_outbox
       WHERE run_id=r AND delivered_at IS NULL)) WHERE run_id=r;
END;
$$;

CREATE FUNCTION bookkeeping.resume_run(r uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  UPDATE bookkeeping.pipeline_run SET state='running',checks='{}',completed_at=NULL
    WHERE run_id=r AND compacted_at IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown or compacted run'; END IF;
END;
$$;
CREATE FUNCTION bookkeeping.block_run(r uuid,message text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  UPDATE bookkeeping.pipeline_run SET state='blocked',completed_at=NULL,
    checks=jsonb_build_object('blocked',message) WHERE run_id=r;
END;
$$;
CREATE FUNCTION bookkeeping.delivery(e uuid,message text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
BEGIN
  UPDATE bookkeeping.journal_outbox SET attempts=attempts+1,error=message,
    delivered_at=CASE WHEN message IS NULL THEN clock_timestamp() ELSE NULL END
    WHERE event_id=e AND delivered_at IS NULL;
END;
$$;

-- Maintenance is owner-only; leases keep their monotonically increasing
-- tokens forever, and pending delivery intent is never deleted.
CREATE FUNCTION bookkeeping.compact(days integer DEFAULT 30) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE r uuid; total bigint := 0; refs jsonb;
BEGIN
  IF days<30 THEN RAISE EXCEPTION 'Retention must be at least 30 days'; END IF;
  FOR r IN SELECT run_id FROM bookkeeping.pipeline_run p WHERE state='complete' AND NOT pinned
    AND completed_at<clock_timestamp()-make_interval(days=>days) AND compacted_at IS NULL
    AND NOT EXISTS(SELECT 1 FROM bookkeeping.journal_outbox j WHERE j.run_id=p.run_id AND delivered_at IS NULL)
    FOR UPDATE LOOP
    SELECT jsonb_agg(jsonb_build_object('step',step,'key',unit_key,'receipt',receipt) ORDER BY step,ordinal)
      INTO refs FROM bookkeeping.work_item WHERE run_id=r;
    UPDATE bookkeeping.pipeline_run SET summary=summary||jsonb_build_object('receipts',coalesce(refs,'[]'::jsonb)),
      compacted_at=clock_timestamp() WHERE run_id=r;
    DELETE FROM bookkeeping.work_item WHERE run_id=r;
    DELETE FROM bookkeeping.journal_outbox WHERE run_id=r AND delivered_at IS NOT NULL;
    total := total+1;
  END LOOP;
  RETURN total;
END;
$$;
REVOKE ALL ON ALL TABLES IN SCHEMA bookkeeping FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA bookkeeping FROM PUBLIC;
