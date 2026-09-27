-- Decision intent and work authority commit locally before journal delivery.
ALTER TABLE bookkeeping.journal_outbox ADD COLUMN event_type text NOT NULL DEFAULT 'work.verified';
ALTER TABLE bookkeeping.journal_outbox DROP CONSTRAINT journal_outbox_run_id_step_unit_key_key;
ALTER TABLE bookkeeping.journal_outbox ADD UNIQUE(run_id,step,unit_key,event_type);

CREATE FUNCTION bookkeeping.authorize_request(r uuid,s text,k text,a uuid,proof jsonb,e uuid,input_ref jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; p jsonb;
BEGIN
  PERFORM bookkeeping.authority(r,s,k,a,proof);
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k;
  IF w.unit->'input' ? 'from' THEN
    IF NOT EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r
      AND step=w.unit#>>'{input,from,step}' AND unit_key=w.unit#>>'{input,from,key}' AND state='verified'
      AND receipt->>'uri'=input_ref->>'uri' AND receipt->>'sha256'=input_ref->>'sha256') THEN
      RAISE EXCEPTION 'Authorization input differs from verified prerequisite'; END IF;
  ELSIF w.unit->'input' IS DISTINCT FROM input_ref THEN
    RAISE EXCEPTION 'Authorization input differs from frozen work';
  END IF;
  p := jsonb_build_object('version',1,'run_id',r,'event_id',e,'step',s,'unit_key',k,'input',input_ref,
    'candidate_id',w.unit#>>'{keys,candidate_id}');
  IF coalesce(p->>'candidate_id','')='' THEN RAISE EXCEPTION 'Original candidate identity is required'; END IF;
  INSERT INTO bookkeeping.journal_outbox(event_id,run_id,step,unit_key,payload,event_type)
    VALUES(e,r,s,k,p,'fetch.authorized') ON CONFLICT DO NOTHING;
  IF NOT EXISTS(SELECT 1 FROM bookkeeping.journal_outbox WHERE event_id=e AND payload=p
    AND run_id=r AND step=s AND unit_key=k AND event_type='fetch.authorized') THEN
    RAISE EXCEPTION 'Conflicting authorization intent'; END IF;
END;
$$;

-- Replace completion conflict key without changing the installed 001 checksum.
CREATE OR REPLACE FUNCTION bookkeeping.finish(r uuid,s text,k text,a uuid,proof jsonb,receipt jsonb,checks jsonb,e uuid)
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
  IF receipt IS NULL OR jsonb_typeof(receipt) IS DISTINCT FROM 'object'
     OR jsonb_typeof(receipt->'uri') IS DISTINCT FROM 'string' OR receipt->>'uri'=''
     OR jsonb_typeof(receipt->'sha256') IS DISTINCT FROM 'string'
     OR jsonb_typeof(receipt->'evidence') IS DISTINCT FROM 'object'
     OR jsonb_typeof(checks) IS DISTINCT FROM 'object'
     OR NOT receipt ? 'uri' OR NOT receipt ? 'sha256'
     OR NOT receipt ? 'evidence' OR receipt->>'sha256' !~ '^[0-9a-f]{64}$'
     OR checks='{}' OR EXISTS(SELECT 1 FROM jsonb_each(checks) WHERE value<>'true'::jsonb) THEN
    RAISE EXCEPTION 'Unverified completion';
  END IF;
  UPDATE bookkeeping.work_item SET state='verified',receipt=finish.receipt,checks=finish.checks,error=NULL,
    authority_until=(SELECT min(expires_at) FROM bookkeeping.lease WHERE run_id=r AND attempt=a)
    WHERE run_id=r AND step=s AND unit_key=k;
  INSERT INTO bookkeeping.journal_outbox(event_id,run_id,step,unit_key,payload)
    VALUES(e,r,s,k,jsonb_build_object('version',1,'event_id',e,'run_id',r,'step',s,'unit_key',k,
      'receipt',receipt,'checks',checks)) ON CONFLICT(run_id,step,unit_key,event_type) DO NOTHING;
  UPDATE bookkeeping.lease SET expires_at=clock_timestamp() WHERE run_id=r AND attempt=a;
  SELECT coalesce(min(ordinal)-1,(SELECT max(ordinal) FROM bookkeeping.work_item WHERE run_id=r AND step=s))
    INTO last_ordinal FROM bookkeeping.work_item WHERE run_id=r AND step=s AND state<>'verified';
  SELECT * INTO last_item FROM bookkeeping.work_item WHERE run_id=r AND step=s AND ordinal=last_ordinal;
  UPDATE bookkeeping.checkpoint SET ordinal=last_ordinal,cursor=last_item.unit->'cursor',receipt=last_item.receipt
    WHERE run_id=r AND scope=s AND ordinal<last_ordinal;
END;
$$;

REVOKE ALL ON FUNCTION bookkeeping.authorize_request(uuid,text,text,uuid,jsonb,uuid,jsonb) FROM PUBLIC;

-- Live authority also rejects blocked and completed roots.
CREATE OR REPLACE FUNCTION bookkeeping.authority(r uuid,s text,k text,a uuid,proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; p jsonb; l bookkeeping.lease%ROWTYPE;
BEGIN
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r AND state IN ('running','waiting') FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Run is not executable'; END IF;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF w.state<>'running' OR w.attempt IS DISTINCT FROM a THEN RAISE EXCEPTION 'Stale attempt'; END IF;
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
