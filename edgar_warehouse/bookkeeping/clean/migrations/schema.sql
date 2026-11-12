-- Bookkeeping's schema: five control tables and the functions that move a run
-- and its units. No source record is stored here. `bookkeeping init` creates it
-- in an empty database; a later change is a numbered file beside this one.
--
-- A unit goes pending -> running -> verified (or waiting, to be claimed again).
-- A worker of the step's frozen profile claims it, renews its leases while it
-- works, checks its own result and completes it.
SET LOCAL check_function_bodies = false;


CREATE SCHEMA bookkeeping;

CREATE FUNCTION bookkeeping.authority(r uuid, s text, k text, a uuid, proof jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
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

CREATE FUNCTION bookkeeping.block_run(r uuid, message text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  UPDATE bookkeeping.pipeline_run SET state='blocked',completed_at=NULL,
    checks=jsonb_build_object('blocked',message) WHERE run_id=r;
END;
$$;

CREATE FUNCTION bookkeeping.claim(r uuid, s text, k text, a uuid, seconds integer, prereqs jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    SET lock_timeout TO '100ms'
    AS $$
BEGIN
  PERFORM bookkeeping.require(r,s,ARRAY['worker']);
  RETURN bookkeeping.claim_unit(r,s,k,a,seconds,prereqs);
END;
$$;

CREATE FUNCTION bookkeeping.claim_unit(r uuid, s text, k text, a uuid, seconds integer, prereqs jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    SET lock_timeout TO '100ms'
    AS $$
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

CREATE FUNCTION bookkeeping.compact(days integer DEFAULT 30) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $_$
DECLARE r uuid; total bigint := 0; refs jsonb;
BEGIN
  IF days<30 THEN RAISE EXCEPTION 'Retention must be at least 30 days'; END IF;
  -- The runs live runs name, gathered once: only live runs' work is read, then
  -- each candidate is compared by equality.
  FOR r IN WITH read AS (SELECT DISTINCT jsonb_path_query(w.unit->'input', '$.**.run') #>> '{}' AS run_id
             FROM bookkeeping.pipeline_run l JOIN bookkeeping.work_item w ON w.run_id=l.run_id
             WHERE l.state<>'complete')
    SELECT p.run_id FROM bookkeeping.pipeline_run p WHERE state='complete' AND NOT pinned
    AND completed_at<clock_timestamp()-make_interval(days=>days) AND compacted_at IS NULL
    AND NOT EXISTS(SELECT 1 FROM bookkeeping.journal_outbox j WHERE j.run_id=p.run_id AND delivered_at IS NULL)
    AND NOT EXISTS(SELECT 1 FROM read WHERE read.run_id=p.run_id::text)
    FOR UPDATE OF p LOOP
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
$_$;

CREATE FUNCTION bookkeeping.completion_authority() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  IF NEW.state='verified' AND (NEW.authority_until IS NULL OR NEW.authority_until<=clock_timestamp()) THEN
    RAISE EXCEPTION 'Completion authority expired before commit'; END IF;
  RETURN NULL;
END;
$$;

CREATE FUNCTION bookkeeping.completion_by_worker() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  IF NEW.state='verified' AND OLD.state<>'verified' AND (OLD.state<>'running'
     OR NOT bookkeeping.issuer(bookkeeping.frozen_profile(OLD.run_id,OLD.step),'worker')) THEN
    RAISE EXCEPTION 'Completion needs the running attempt and a worker of this profile';
  END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION bookkeeping.delivery(e uuid, message text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  UPDATE bookkeeping.journal_outbox SET attempts=attempts+1,error=message,
    delivered_at=CASE WHEN message IS NULL THEN clock_timestamp() ELSE NULL END
    WHERE event_id=e AND delivered_at IS NULL;
END;
$$;

CREATE FUNCTION bookkeeping.document_lookup_key(s jsonb) RETURNS bytea
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $$
  SELECT sha256(convert_to((s->>'kind')||':'||(s->>'name')||':'||(s->>'target'),'UTF8'))
$$;

CREATE FUNCTION bookkeeping.finish(r uuid, s text, k text, a uuid, proof jsonb, receipt jsonb, checks jsonb, e uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $_$
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
$_$;

CREATE FUNCTION bookkeeping.finish_expand(r uuid, s text, k text, a uuid, proof jsonb, receipt jsonb, checks jsonb, e uuid, children jsonb, child_step text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
DECLARE parent bookkeeping.work_item%ROWTYPE; child jsonb; existing bookkeeping.work_item%ROWTYPE;
        inserted bigint := 0; ordinal_seen bigint; key_seen text;
BEGIN
  IF jsonb_typeof(children) IS DISTINCT FROM 'array' OR jsonb_array_length(children)>128
     OR child_step IS NULL OR child_step='' OR child_step=s THEN
    RAISE EXCEPTION 'Invalid bounded expansion';
  END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(children) AS entry(value)
            GROUP BY entry.value->>'key' HAVING count(*)>1) THEN
    RAISE EXCEPTION 'Repeated generated child key';
  END IF;
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  SELECT * INTO STRICT parent FROM bookkeeping.work_item
    WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF parent.unit#>>'{cursor,generated_step}' IS DISTINCT FROM child_step THEN
    RAISE EXCEPTION 'Expansion differs from frozen parent';
  END IF;
  IF parent.state<>'verified' THEN
    PERFORM bookkeeping.authority(r,s,k,a,proof);
  ELSIF parent.generated_count IS NULL OR parent.receipt IS DISTINCT FROM receipt
     OR parent.checks IS DISTINCT FROM checks THEN
    RAISE EXCEPTION 'Expansion completion evidence changed';
  END IF;
  FOR child IN SELECT value FROM jsonb_array_elements(children) LOOP
    IF jsonb_typeof(child) IS DISTINCT FROM 'object'
       OR child->>'step' IS DISTINCT FROM child_step
       OR jsonb_typeof(child->'key') IS DISTINCT FROM 'string'
       OR child->>'key'=''
       OR jsonb_typeof(child->'ordinal') IS DISTINCT FROM 'number'
       OR jsonb_typeof(child->'resources') IS DISTINCT FROM 'array'
       OR jsonb_array_length(child->'resources')=0
       OR jsonb_typeof(child->'unit') IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION 'Malformed generated child';
    END IF;
    ordinal_seen := (child->>'ordinal')::bigint;
    key_seen := child->>'key';
    IF ordinal_seen<0 OR EXISTS(SELECT 1 FROM bookkeeping.work_item
       WHERE run_id=r AND step=child_step AND ordinal=ordinal_seen AND unit_key<>key_seen) THEN
      RAISE EXCEPTION 'Generated ordinal conflicts';
    END IF;
    IF parent.state<>'verified' AND EXISTS(SELECT 1 FROM bookkeeping.work_item
       WHERE run_id=r AND step=child_step AND unit_key=key_seen) THEN
      RAISE EXCEPTION 'Generated child already belongs to another expansion';
    END IF;
    INSERT INTO bookkeeping.work_item(run_id,step,unit_key,ordinal,resources,unit)
      VALUES(r,child_step,key_seen,ordinal_seen,child->'resources',child->'unit')
      ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT existing FROM bookkeeping.work_item
      WHERE run_id=r AND step=child_step AND unit_key=key_seen;
    IF existing.ordinal<>ordinal_seen OR existing.resources IS DISTINCT FROM child->'resources'
       OR existing.unit IS DISTINCT FROM child->'unit' THEN
      RAISE EXCEPTION 'Generated child changed';
    END IF;
    inserted := inserted+1;
  END LOOP;
  IF parent.state<>'verified' THEN
    PERFORM bookkeeping.finish(r,s,k,a,proof,receipt,checks,e);
    UPDATE bookkeeping.work_item SET generated_count=inserted
      WHERE run_id=r AND step=s AND unit_key=k;
    UPDATE bookkeeping.pipeline_run SET expected_count=expected_count+inserted WHERE run_id=r;
    INSERT INTO bookkeeping.checkpoint(run_id,scope) VALUES(r,child_step) ON CONFLICT DO NOTHING;
  END IF;
END;
$$;

CREATE FUNCTION bookkeeping.finish_resource(r uuid, s text, k text, a uuid, proof jsonb, receipt jsonb, checks jsonb, e uuid, resource_key text, expected_revision bigint, expected_position bigint) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
DECLARE w bookkeeping.work_item%ROWTYPE; c bookkeeping.checkpoint%ROWTYPE; next_revision bigint;
BEGIN
  -- Same lock order as ordinary finish: root, work, sorted leases, checkpoint.
  PERFORM 1 FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  SELECT * INTO STRICT w FROM bookkeeping.work_item WHERE run_id=r AND step=s AND unit_key=k FOR UPDATE;
  IF resource_key IS NULL OR resource_key='' OR expected_revision IS NULL OR expected_position IS NULL
    OR expected_revision<0 OR expected_position< -1 THEN
    RAISE EXCEPTION 'Invalid resource checkpoint comparison'; END IF;
  IF w.state='verified' THEN
    PERFORM bookkeeping.finish(r,s,k,a,proof,receipt,checks,e);
    SELECT * INTO STRICT c FROM bookkeeping.checkpoint WHERE resource=resource_key;
    IF c.run_id<>r OR c.receipt IS DISTINCT FROM receipt OR c.ordinal<>expected_position+1 THEN
      RAISE EXCEPTION 'Resource checkpoint no longer names this completion'; END IF;
    RETURN c.revision;
  END IF;
  PERFORM bookkeeping.authority(r,s,k,a,proof);
  IF NOT w.resources ? resource_key THEN RAISE EXCEPTION 'Checkpoint requires matching resource lease'; END IF;
  IF EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r AND step=s AND ordinal<w.ordinal AND state<>'verified') THEN
    RAISE EXCEPTION 'Resource checkpoint cannot skip a work hole'; END IF;
  INSERT INTO bookkeeping.checkpoint(run_id,scope,resource)
    VALUES(r,'resource:'||resource_key,resource_key) ON CONFLICT(resource) WHERE resource IS NOT NULL DO NOTHING;
  SELECT * INTO STRICT c FROM bookkeeping.checkpoint WHERE resource=resource_key FOR UPDATE;
  IF c.revision<>expected_revision OR c.ordinal<>expected_position THEN
    RAISE EXCEPTION 'Resource checkpoint comparison failed' USING ERRCODE='40001'; END IF;
  PERFORM bookkeeping.finish(r,s,k,a,proof,receipt,checks,e);
  UPDATE bookkeeping.checkpoint SET run_id=r,ordinal=expected_position+1,revision=revision+1,
    cursor=w.unit->'cursor',receipt=finish_resource.receipt WHERE resource=resource_key
    RETURNING revision INTO next_revision;
  RETURN next_revision;
END;
$$;

CREATE FUNCTION bookkeeping.frozen_profile(r uuid, s text) RETURNS text
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
  SELECT submission->'profiles'->>s FROM bookkeeping.pipeline_run WHERE run_id=r
$$;

CREATE FUNCTION bookkeeping.heartbeat(r uuid, s text, k text, a uuid, proof jsonb, seconds integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  PERFORM bookkeeping.require(r,s,ARRAY['worker']);
  RETURN bookkeeping.renew_unit(r,s,k,a,proof,seconds);
END;
$$;

CREATE FUNCTION bookkeeping.issuer(profile text, duty text) RETURNS boolean
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
DECLARE role text := bookkeeping.profile_role(profile,duty);
BEGIN
  RETURN profile IS NOT NULL AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role)
    AND pg_has_role(session_user,role,'MEMBER');
END;
$$;

CREATE FUNCTION bookkeeping.pin_runtime(r uuid, s text, runtime text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $_$
DECLARE profile text := bookkeeping.frozen_profile(r,s); pinned text;
BEGIN
  IF coalesce(runtime,'') !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'A worker names its runtime digest'; END IF;
  PERFORM bookkeeping.require(r,s,ARRAY['worker']);
  SELECT runtimes->>profile INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r;
  IF pinned IS NULL THEN
    -- Only the first completion of a profile takes the run row's lock.
    SELECT runtimes->>profile INTO pinned FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
    IF pinned IS NULL THEN
      UPDATE bookkeeping.pipeline_run SET runtimes=runtimes||jsonb_build_object(profile,runtime) WHERE run_id=r;
      RETURN;
    END IF;
  END IF;
  IF pinned<>runtime THEN RAISE EXCEPTION 'Pinned worker runtime changed; start a new run'; END IF;
END;
$_$;

CREATE FUNCTION bookkeeping.profile_role(profile text, duty text) RETURNS text
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $$
  SELECT 'bk_'||duty||'_'||left(regexp_replace(profile,'[^a-z0-9]','_','g'),32)||'_'||left(md5(profile),8)
$$;

CREATE FUNCTION bookkeeping.record_run_checks(p_wire text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $_$
                DECLARE v_run_id uuid;
v_raw_run text;
v_state text;
v_checks text;
v_summary text;
v_compacted BIGINT;
v_expected BIGINT;
v_actual BIGINT;
v_verified BIGINT;
v_pending BIGINT;
v_unsealed BIGINT;
v_observed_expected BIGINT;
v_observed_actual BIGINT;
v_observed_verified BIGINT;
v_observed_pending BIGINT;
v_observed_unsealed BIGINT;
v_raw_expected text;
v_raw_actual text;
v_raw_verified text;
v_raw_pending text;
v_raw_unsealed text; BEGIN v_raw_expected := (p_wire::jsonb->>'expected');
IF (v_raw_expected IS NULL OR v_raw_expected !~ '^[0-9]+$') THEN RAISE EXCEPTION 'invalid_control_counter'; END IF;
v_expected := CAST(v_raw_expected AS BIGINT);
v_raw_actual := (p_wire::jsonb->>'actual');
IF (v_raw_actual IS NULL OR v_raw_actual !~ '^[0-9]+$') THEN RAISE EXCEPTION 'invalid_control_counter'; END IF;
v_actual := CAST(v_raw_actual AS BIGINT);
v_raw_verified := (p_wire::jsonb->>'verified');
IF (v_raw_verified IS NULL OR v_raw_verified !~ '^[0-9]+$') THEN RAISE EXCEPTION 'invalid_control_counter'; END IF;
v_verified := CAST(v_raw_verified AS BIGINT);
v_raw_pending := (p_wire::jsonb->>'pending');
IF (v_raw_pending IS NULL OR v_raw_pending !~ '^[0-9]+$') THEN RAISE EXCEPTION 'invalid_control_counter'; END IF;
v_pending := CAST(v_raw_pending AS BIGINT);
v_raw_unsealed := (p_wire::jsonb->>'unsealed');
IF (v_raw_unsealed IS NULL OR v_raw_unsealed !~ '^[0-9]+$') THEN RAISE EXCEPTION 'invalid_control_counter'; END IF;
v_unsealed := CAST(v_raw_unsealed AS BIGINT);
v_raw_run := (p_wire::jsonb->>'run_id');
IF v_raw_run IS NULL THEN RAISE EXCEPTION 'invalid_control_run'; END IF;
v_run_id := CAST(v_raw_run AS uuid);
v_state := (p_wire::jsonb->>'state');
v_checks := convert_from(decode((p_wire::jsonb->>'checks'),'hex'),'UTF8');
v_summary := convert_from(decode((p_wire::jsonb->>'summary'),'hex'),'UTF8');
IF v_state IS NULL OR NOT (v_state='complete' OR v_state='waiting') THEN RAISE EXCEPTION 'invalid_control_state'; END IF;
IF v_checks IS NULL OR NOT ((v_checks='{"journal.delivered":false,"manifest.hash":false,"work.accounting":false}') OR (v_checks='{"journal.delivered":false,"manifest.hash":false,"work.accounting":true}') OR (v_checks='{"journal.delivered":false,"manifest.hash":false}') OR (v_checks='{"journal.delivered":false,"manifest.hash":true,"work.accounting":false}') OR (v_checks='{"journal.delivered":false,"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":false,"manifest.hash":true}') OR (v_checks='{"journal.delivered":false,"work.accounting":false}') OR (v_checks='{"journal.delivered":false,"work.accounting":true}') OR (v_checks='{"journal.delivered":false}') OR (v_checks='{"journal.delivered":true,"manifest.hash":false,"work.accounting":false}') OR (v_checks='{"journal.delivered":true,"manifest.hash":false,"work.accounting":true}') OR (v_checks='{"journal.delivered":true,"manifest.hash":false}') OR (v_checks='{"journal.delivered":true,"manifest.hash":true,"work.accounting":false}') OR (v_checks='{"journal.delivered":true,"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":true,"manifest.hash":true}') OR (v_checks='{"journal.delivered":true,"work.accounting":false}') OR (v_checks='{"journal.delivered":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":true}') OR (v_checks='{"manifest.hash":false,"work.accounting":false}') OR (v_checks='{"manifest.hash":false,"work.accounting":true}') OR (v_checks='{"manifest.hash":false}') OR (v_checks='{"manifest.hash":true,"work.accounting":false}') OR (v_checks='{"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"manifest.hash":true}') OR (v_checks='{"work.accounting":false}') OR (v_checks='{"work.accounting":true}') OR (v_checks='{}')) THEN RAISE EXCEPTION 'invalid_control_checks'; END IF;
SELECT p.expected_count,CASE WHEN p.compacted_at IS NULL THEN 0 ELSE 1 END INTO v_observed_expected,v_compacted FROM bookkeeping.pipeline_run p WHERE p.run_id=v_run_id FOR UPDATE NOWAIT;
IF v_observed_expected IS NULL THEN RAISE EXCEPTION 'unknown_control_run'; END IF;
IF v_compacted<>0 THEN RAISE EXCEPTION 'compacted_control_run'; END IF;
SELECT COUNT(*),COALESCE(SUM(CASE WHEN w.state='verified' THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END),0) INTO v_observed_actual,v_observed_verified FROM bookkeeping.work_item w WHERE w.run_id=v_run_id;
SELECT COUNT(*) INTO v_observed_unsealed FROM bookkeeping.work_item w WHERE w.run_id=v_run_id AND w.generated_count IS NULL AND (w.unit->'cursor' ? 'generated_step');
SELECT COUNT(*) INTO v_observed_pending FROM bookkeeping.journal_outbox j WHERE j.run_id=v_run_id AND j.delivered_at IS NULL;
IF v_expected<>v_observed_expected OR v_actual<>v_observed_actual OR v_verified<>v_observed_verified OR v_pending<>v_observed_pending OR v_unsealed<>v_observed_unsealed THEN RAISE EXCEPTION 'control_observations_changed'; END IF;
IF v_state='complete' AND (v_actual<>v_expected OR v_verified<>v_actual OR v_pending<>0 OR v_unsealed<>0 OR NOT ((v_checks='{"journal.delivered":true,"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":true,"manifest.hash":true}') OR (v_checks='{"journal.delivered":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":true}') OR (v_checks='{"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"manifest.hash":true}') OR (v_checks='{"work.accounting":true}'))) THEN RAISE EXCEPTION 'unverified_control_completion'; END IF;
IF v_state='waiting' AND NOT (v_actual<>v_expected OR v_verified<>v_actual OR v_pending<>0 OR v_unsealed<>0 OR NOT ((v_checks='{"journal.delivered":true,"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":true,"manifest.hash":true}') OR (v_checks='{"journal.delivered":true,"work.accounting":true}') OR (v_checks='{"journal.delivered":true}') OR (v_checks='{"manifest.hash":true,"work.accounting":true}') OR (v_checks='{"manifest.hash":true}') OR (v_checks='{"work.accounting":true}'))) THEN RAISE EXCEPTION 'invalid_control_state'; END IF;
IF v_summary IS NULL OR NOT (v_summary='{"expected":' || CAST(v_expected AS text) || ',"pending_deliveries":' || CAST(v_pending AS text) || ',"verified":' || CAST(v_verified AS text) || '}') THEN RAISE EXCEPTION 'invalid_control_summary'; END IF;
UPDATE bookkeeping.pipeline_run AS p SET checks=CAST(v_checks AS jsonb),summary=CAST(v_summary AS jsonb),state=v_state,completed_at=CASE WHEN v_state='complete' THEN COALESCE(p.completed_at,clock_timestamp()) ELSE NULL END WHERE p.run_id=v_run_id AND NOT (p.state=v_state AND p.checks=CAST(v_checks AS jsonb) AND p.summary=CAST(v_summary AS jsonb)); END $_$;

CREATE FUNCTION bookkeeping.release_unit(r uuid, s text, k text, message text, a uuid, proof jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
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

CREATE FUNCTION bookkeeping.renew_unit(r uuid, s text, k text, a uuid, proof jsonb, seconds integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
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

CREATE FUNCTION bookkeeping.require(r uuid, s text, duties text[]) RETURNS void
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
DECLARE profile text := bookkeeping.frozen_profile(r,s); duty text;
BEGIN
  FOREACH duty IN ARRAY duties LOOP
    IF bookkeeping.issuer(profile,duty) THEN RETURN; END IF;
  END LOOP;
  RAISE EXCEPTION 'This login has no % role for profile %', array_to_string(duties,' or '), coalesce(profile,'(none)');
END;
$$;

CREATE FUNCTION bookkeeping.resume_run_prepared(p_wire text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
                DECLARE v_raw_run text;
v_run_id uuid;
v_state text;
v_expected_state text;
v_checks text;
v_observed_state text;
v_observed_checks text;
v_observed_completed text;
v_expected_checks text;
v_expected_completion text;
v_compacted BIGINT; BEGIN v_raw_run := (p_wire::jsonb->>'run_id');
IF v_raw_run IS NULL THEN RAISE EXCEPTION 'invalid_control_run'; END IF;
v_run_id := CAST(v_raw_run AS uuid);
v_state := (p_wire::jsonb->>'state');
v_expected_state := (p_wire::jsonb->>'expected_state');
v_expected_checks := convert_from(decode((p_wire::jsonb->>'expected_checks'),'hex'),'UTF8');
v_expected_completion := (p_wire::jsonb->>'expected_completion');
v_checks := convert_from(decode((p_wire::jsonb->>'checks'),'hex'),'UTF8');
IF v_state IS NULL OR NOT (v_state='running') OR v_checks IS NULL OR NOT (v_checks='{}') OR v_expected_checks IS NULL OR v_expected_completion IS NULL OR v_expected_state IS NULL OR NOT ((v_expected_state='running') OR (v_expected_state='waiting') OR (v_expected_state='blocked') OR (v_expected_state='complete')) THEN RAISE EXCEPTION 'invalid_control_resume'; END IF;
SELECT p.state,CAST(p.checks AS text),COALESCE(encode(timestamptz_send(p.completed_at),'hex'),''),CASE WHEN p.compacted_at IS NULL THEN 0 ELSE 1 END INTO v_observed_state,v_observed_checks,v_observed_completed,v_compacted FROM bookkeeping.pipeline_run p WHERE p.run_id=v_run_id FOR UPDATE NOWAIT;
IF v_observed_state IS NULL THEN RAISE EXCEPTION 'unknown_control_run'; END IF;
IF v_compacted<>0 THEN RAISE EXCEPTION 'compacted_control_run'; END IF;
IF NOT (v_observed_state=v_expected_state AND v_observed_checks=v_expected_checks AND v_observed_completed=v_expected_completion) AND NOT (v_observed_state=v_state AND v_observed_checks=v_checks AND v_observed_completed='') THEN RAISE EXCEPTION 'control_observations_changed'; END IF;
UPDATE bookkeeping.pipeline_run AS p SET state=v_state,checks=CAST(v_checks AS jsonb),completed_at=NULL WHERE p.run_id=v_run_id AND NOT (p.state=v_state AND p.checks=CAST(v_checks AS jsonb) AND p.completed_at IS NULL); END $$;

CREATE FUNCTION bookkeeping.start_run(r uuid, s jsonb, h text, items jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
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

CREATE FUNCTION bookkeeping.wait_work(r uuid, s text, k text, message text, a uuid, proof jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  PERFORM bookkeeping.require(r,s,ARRAY['worker']);
  PERFORM bookkeeping.release_unit(r,s,k,message,a,proof);
END;
$$;

CREATE TABLE bookkeeping.checkpoint (
    run_id uuid NOT NULL,
    scope text NOT NULL,
    ordinal bigint DEFAULT '-1'::integer NOT NULL,
    cursor jsonb,
    receipt jsonb,
    resource text,
    revision bigint DEFAULT 0 NOT NULL,
    CONSTRAINT checkpoint_revision_check CHECK ((revision >= 0))
);

CREATE TABLE bookkeeping.journal_outbox (
    event_id uuid NOT NULL,
    run_id uuid NOT NULL,
    step text NOT NULL,
    unit_key text NOT NULL,
    payload jsonb NOT NULL,
    attempts bigint DEFAULT 0 NOT NULL,
    error text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    delivered_at timestamp with time zone,
    event_type text DEFAULT 'work.verified'::text NOT NULL
);

CREATE TABLE bookkeeping.lease (
    resource text NOT NULL,
    token bigint DEFAULT 0 NOT NULL,
    run_id uuid,
    attempt uuid,
    expires_at timestamp with time zone DEFAULT '-infinity'::timestamp with time zone NOT NULL,
    heartbeat_at timestamp with time zone,
    CONSTRAINT lease_token_check CHECK ((token >= 0))
);

CREATE TABLE bookkeeping.pipeline_run (
    run_id uuid NOT NULL,
    submission jsonb NOT NULL,
    submission_hash text NOT NULL,
    expected_count bigint NOT NULL,
    state text DEFAULT 'running'::text NOT NULL,
    checks jsonb DEFAULT '{}'::jsonb NOT NULL,
    summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    pinned boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    completed_at timestamp with time zone,
    compacted_at timestamp with time zone,
    runtimes jsonb DEFAULT '{}'::jsonb NOT NULL,
    document_hash bytea GENERATED ALWAYS AS (bookkeeping.document_lookup_key(submission)) STORED,
    CONSTRAINT pipeline_run_expected_count_check CHECK ((expected_count >= 0)),
    CONSTRAINT pipeline_run_state_check CHECK ((state = ANY (ARRAY['running'::text, 'waiting'::text, 'blocked'::text, 'complete'::text]))),
    CONSTRAINT pipeline_run_submission_hash_check CHECK ((submission_hash ~ '^[0-9a-f]{64}$'::text))
);

CREATE TABLE bookkeeping.work_item (
    run_id uuid NOT NULL,
    step text NOT NULL,
    unit_key text NOT NULL,
    ordinal bigint NOT NULL,
    resources jsonb NOT NULL,
    unit jsonb NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    attempt uuid,
    attempts bigint DEFAULT 0 NOT NULL,
    authority_until timestamp with time zone,
    receipt jsonb,
    checks jsonb DEFAULT '{}'::jsonb NOT NULL,
    error text,
    generated_count integer,
    CONSTRAINT work_item_ordinal_check CHECK ((ordinal >= 0)),
    CONSTRAINT work_item_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'running'::text, 'waiting'::text, 'verified'::text])))
);

ALTER TABLE ONLY bookkeeping.checkpoint
    ADD CONSTRAINT checkpoint_pkey PRIMARY KEY (run_id, scope);

ALTER TABLE ONLY bookkeeping.journal_outbox
    ADD CONSTRAINT journal_outbox_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY bookkeeping.journal_outbox
    ADD CONSTRAINT journal_outbox_run_id_step_unit_key_event_type_key UNIQUE (run_id, step, unit_key, event_type);

ALTER TABLE ONLY bookkeeping.lease
    ADD CONSTRAINT lease_pkey PRIMARY KEY (resource);

ALTER TABLE ONLY bookkeeping.pipeline_run
    ADD CONSTRAINT pipeline_run_pkey PRIMARY KEY (run_id);

ALTER TABLE ONLY bookkeeping.work_item
    ADD CONSTRAINT work_item_pkey PRIMARY KEY (run_id, step, unit_key);

ALTER TABLE ONLY bookkeeping.work_item
    ADD CONSTRAINT work_item_run_id_step_ordinal_key UNIQUE (run_id, step, ordinal);

CREATE UNIQUE INDEX one_resource_checkpoint ON bookkeeping.checkpoint USING btree (resource) WHERE (resource IS NOT NULL);

CREATE INDEX pending_delivery ON bookkeeping.journal_outbox USING btree (created_at) WHERE (delivered_at IS NULL);

CREATE INDEX pending_work ON bookkeeping.work_item USING btree (run_id, step, ordinal) WHERE (state <> 'verified'::text);

CREATE INDEX run_document_lookup ON bookkeeping.pipeline_run USING btree (document_hash, created_at, run_id);

CREATE TRIGGER completion_is_by_worker BEFORE UPDATE OF state ON bookkeeping.work_item FOR EACH ROW EXECUTE FUNCTION bookkeeping.completion_by_worker();

CREATE CONSTRAINT TRIGGER completion_valid_at_commit AFTER UPDATE OF state ON bookkeeping.work_item DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION bookkeeping.completion_authority();

ALTER TABLE ONLY bookkeeping.checkpoint
    ADD CONSTRAINT checkpoint_run_id_fkey FOREIGN KEY (run_id) REFERENCES bookkeeping.pipeline_run(run_id);

ALTER TABLE ONLY bookkeeping.journal_outbox
    ADD CONSTRAINT journal_outbox_run_id_fkey FOREIGN KEY (run_id) REFERENCES bookkeeping.pipeline_run(run_id);

ALTER TABLE ONLY bookkeeping.lease
    ADD CONSTRAINT lease_run_id_fkey FOREIGN KEY (run_id) REFERENCES bookkeeping.pipeline_run(run_id);

ALTER TABLE ONLY bookkeeping.work_item
    ADD CONSTRAINT work_item_run_id_fkey FOREIGN KEY (run_id) REFERENCES bookkeeping.pipeline_run(run_id);

