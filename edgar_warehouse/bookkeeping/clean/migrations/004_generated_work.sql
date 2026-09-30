-- Bounded children join the parent's completion and journal intent atomically.
-- The five existing control tables remain the entire Bookkeeping boundary.
ALTER TABLE bookkeeping.work_item ADD COLUMN generated_count integer;
CREATE FUNCTION bookkeeping.finish_expand(
  r uuid,s text,k text,a uuid,proof jsonb,receipt jsonb,checks jsonb,e uuid,
  children jsonb,child_step text
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,bookkeeping AS $$
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
REVOKE ALL ON FUNCTION bookkeeping.finish_expand(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid,jsonb,text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION bookkeeping.record_checks(r uuid,c jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
DECLARE complete boolean; actual bigint; expected bigint;
BEGIN
  SELECT expected_count INTO STRICT expected FROM bookkeeping.pipeline_run WHERE run_id=r FOR UPDATE;
  SELECT count(*) INTO actual FROM bookkeeping.work_item WHERE run_id=r;
  complete := c<>'{}' AND NOT EXISTS(SELECT 1 FROM jsonb_each(c) WHERE value<>'true'::jsonb)
    AND actual=expected AND NOT EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r AND state<>'verified')
    AND NOT EXISTS(SELECT 1 FROM bookkeeping.work_item WHERE run_id=r
      AND unit->'cursor' ? 'generated_step' AND generated_count IS NULL)
    AND NOT EXISTS(SELECT 1 FROM bookkeeping.journal_outbox WHERE run_id=r AND delivered_at IS NULL);
  UPDATE bookkeeping.pipeline_run SET checks=c,
    state=CASE WHEN complete THEN 'complete' ELSE 'waiting' END,
    completed_at=CASE WHEN complete THEN clock_timestamp() ELSE NULL END,
    summary=jsonb_build_object('expected',expected,'verified',(SELECT count(*) FROM bookkeeping.work_item
       WHERE run_id=r AND state='verified'),'pending_deliveries',(SELECT count(*) FROM bookkeeping.journal_outbox
       WHERE run_id=r AND delivered_at IS NULL)) WHERE run_id=r;
END;
$$;
