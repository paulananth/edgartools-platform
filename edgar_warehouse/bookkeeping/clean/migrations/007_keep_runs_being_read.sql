-- A run another live run reads is kept (ticket 121; operator, 2026-10-20: "All runs of latest
-- capture (Recommended)", kept while read). A step may fill a slot from another run's verified
-- unit ({run, step, key}, ticket 120); compaction deletes a run's units, so while a run that
-- names one is not complete, the run it names is not compacted. Otherwise as in 001.
CREATE OR REPLACE FUNCTION bookkeeping.compact(days integer DEFAULT 30) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping AS $$
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
$$;
REVOKE ALL ON FUNCTION bookkeeping.compact(integer) FROM PUBLIC;
