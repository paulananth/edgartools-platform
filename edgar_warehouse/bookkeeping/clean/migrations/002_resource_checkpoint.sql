-- Resource progress spans runs; the existing ordered per-run cursor remains.
-- No new table and no legacy cursor import. First advancement starts at -1.
ALTER TABLE bookkeeping.checkpoint ADD COLUMN resource text;
ALTER TABLE bookkeeping.checkpoint ADD COLUMN revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0);
CREATE UNIQUE INDEX one_resource_checkpoint ON bookkeeping.checkpoint(resource) WHERE resource IS NOT NULL;

CREATE FUNCTION bookkeeping.finish_resource(r uuid,s text,k text,a uuid,proof jsonb,
  receipt jsonb,checks jsonb,e uuid,resource_key text,expected_revision bigint,expected_position bigint)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
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
REVOKE ALL ON FUNCTION bookkeeping.finish_resource(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid,text,bigint,bigint) FROM PUBLIC;
