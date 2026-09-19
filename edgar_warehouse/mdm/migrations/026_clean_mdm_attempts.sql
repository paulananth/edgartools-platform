-- Operational attempts refer to the existing Bookkeeping root, not a new run.
CREATE TABLE mdm_v2.attempt_event (
    attempt_id uuid NOT NULL,
    event text NOT NULL CHECK (event IN ('started','finished','error')),
    run_id uuid NOT NULL,
    batch_id text NOT NULL,
    detail jsonb NOT NULL CHECK (jsonb_typeof(detail) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (attempt_id,event)
);
CREATE INDEX clean_attempt_run ON mdm_v2.attempt_event(run_id,batch_id);
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON mdm_v2.attempt_event
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.immutable_row();

CREATE FUNCTION mdm_v2.record_attempt(attempt uuid, root_run uuid, batch text, phase text, body jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE old mdm_v2.attempt_event%ROWTYPE;
BEGIN
    IF attempt IS NULL OR root_run IS NULL OR batch IS NULL OR length(batch)=0
       OR phase IS NULL OR phase NOT IN ('started','finished','error')
       OR body IS NULL OR jsonb_typeof(body)<>'object' OR octet_length(body::text)>16384 THEN
        RAISE EXCEPTION 'Invalid attempt event';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(attempt::text,26));
    IF phase<>'started' THEN
        SELECT * INTO old FROM mdm_v2.attempt_event WHERE attempt_id=attempt AND event='started';
        IF NOT FOUND OR old.run_id<>root_run OR old.batch_id<>batch THEN
            RAISE EXCEPTION 'Attempt has no matching start';
        END IF;
        IF EXISTS(SELECT 1 FROM mdm_v2.attempt_event WHERE attempt_id=attempt AND event NOT IN ('started',phase)) THEN
            RAISE EXCEPTION 'Attempt already has another terminal event';
        END IF;
    END IF;
    INSERT INTO mdm_v2.attempt_event(attempt_id,event,run_id,batch_id,detail)
        VALUES(attempt,phase,root_run,batch,body) ON CONFLICT DO NOTHING;
    SELECT * INTO old FROM mdm_v2.attempt_event WHERE attempt_id=attempt AND event=phase;
    IF old.run_id<>root_run OR old.batch_id<>batch OR old.detail<>body THEN
        RAISE EXCEPTION 'Attempt event identity reused with different content';
    END IF;
END;
$$;
REVOKE ALL ON FUNCTION mdm_v2.record_attempt(uuid,uuid,text,text,jsonb) FROM PUBLIC;
