-- A run its frozen inputs can never finish is closed as abandoned: not open, so no load drives it again, and kept as evidence.
ALTER TABLE bookkeeping.pipeline_run DROP CONSTRAINT pipeline_run_state_check;

ALTER TABLE bookkeeping.pipeline_run ADD CONSTRAINT pipeline_run_state_check
    CHECK ((state = ANY (ARRAY['running'::text, 'waiting'::text, 'blocked'::text, 'complete'::text, 'abandoned'::text])));

CREATE FUNCTION bookkeeping.abandon_run(r uuid, message text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'bookkeeping'
    AS $$
BEGIN
  UPDATE bookkeeping.pipeline_run SET state='abandoned',completed_at=NULL,
    checks=jsonb_build_object('abandoned',message) WHERE run_id=r AND state IN ('running','waiting','blocked');
END;
$$;
