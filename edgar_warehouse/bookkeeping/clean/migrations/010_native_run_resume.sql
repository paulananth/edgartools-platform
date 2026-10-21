-- Frozen destination enforcement for native-prepared run resumption.
DROP FUNCTION bookkeeping.resume_run(uuid);
CREATE OR REPLACE FUNCTION bookkeeping.resume_run_prepared(p_wire text) RETURNS void
                LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $control$
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
UPDATE bookkeeping.pipeline_run AS p SET state=v_state,checks=CAST(v_checks AS jsonb),completed_at=NULL WHERE p.run_id=v_run_id AND NOT (p.state=v_state AND p.checks=CAST(v_checks AS jsonb) AND p.completed_at IS NULL); END $control$;;
REVOKE ALL ON FUNCTION bookkeeping.resume_run_prepared(text) FROM PUBLIC;
