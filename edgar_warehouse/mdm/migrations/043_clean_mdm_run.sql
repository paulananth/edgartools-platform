-- A Merge Stage run's frozen scope and its reconciled outcome, kept in MDM
-- itself (platform validation slice 2a). The run was kept in the legacy
-- Bookkeeping `pipeline_run`, which is retired. The application login writes
-- it only through the two functions below.
CREATE TABLE mdm_v2.run (
    run_id uuid PRIMARY KEY,
    scope jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
    started_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','succeeded')),
    report jsonb CHECK (report IS NULL OR jsonb_typeof(report) = 'object'),
    completed_at timestamptz
);

-- Registers a run's frozen scope once; the same run with another scope is refused.
CREATE FUNCTION mdm_v2.start_run(root_run uuid, body jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE old jsonb;
BEGIN
    IF root_run IS NULL OR body IS NULL OR jsonb_typeof(body)<>'object'
       OR octet_length(body::text)>1048576 THEN
        RAISE EXCEPTION 'Invalid run scope';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(root_run::text,43));
    SELECT scope INTO old FROM mdm_v2.run WHERE run_id=root_run;
    IF FOUND THEN
        IF old<>body THEN RAISE EXCEPTION 'Root run scope changed'; END IF;
        RETURN;
    END IF;
    INSERT INTO mdm_v2.run(run_id,scope) VALUES(root_run,body);
END;
$$;

-- Records a reconciliation. A complete run is succeeded; an incomplete one
-- stays running. The scope never changes.
CREATE FUNCTION mdm_v2.finish_run(root_run uuid, body jsonb, complete boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
BEGIN
    IF root_run IS NULL OR body IS NULL OR jsonb_typeof(body)<>'object' OR complete IS NULL THEN
        RAISE EXCEPTION 'Invalid run report';
    END IF;
    UPDATE mdm_v2.run SET report=body,
        status=CASE WHEN complete THEN 'succeeded' ELSE 'running' END,
        completed_at=CASE WHEN complete THEN coalesce(completed_at,now()) ELSE NULL END
    WHERE run_id=root_run;
    IF NOT FOUND THEN RAISE EXCEPTION 'Root run was not registered'; END IF;
END;
$$;
REVOKE ALL ON FUNCTION mdm_v2.start_run(uuid,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION mdm_v2.finish_run(uuid,jsonb,boolean) FROM PUBLIC;
