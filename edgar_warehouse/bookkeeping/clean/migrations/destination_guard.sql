-- Applied in each transactional destination, never in bookkeeping_clean.
CREATE SCHEMA bookkeeping_guard;
REVOKE ALL ON SCHEMA bookkeeping_guard FROM PUBLIC;
CREATE TABLE bookkeeping_guard.resource (
  resource text PRIMARY KEY, token bigint NOT NULL,
  run_id uuid NOT NULL, attempt uuid NOT NULL, expires_at timestamptz NOT NULL
);
CREATE FUNCTION bookkeeping_guard.authorize(proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping_guard AS $$
DECLARE p jsonb; prior bookkeeping_guard.resource%ROWTYPE;
BEGIN
  IF jsonb_typeof(proof)<>'array' OR jsonb_array_length(proof)=0 THEN
    RAISE EXCEPTION 'Lease proof required'; END IF;
  FOR p IN SELECT value FROM jsonb_array_elements(proof) ORDER BY value->>'resource' LOOP
    IF (p->>'expires_at')::timestamptz<=clock_timestamp() OR (p->>'token')::bigint<1 THEN
      RAISE EXCEPTION 'Expired destination authority'; END IF;
    INSERT INTO bookkeeping_guard.resource(resource,token,run_id,attempt,expires_at)
      VALUES(p->>'resource',(p->>'token')::bigint,(p->>'run_id')::uuid,(p->>'attempt')::uuid,
        (p->>'expires_at')::timestamptz) ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT prior FROM bookkeeping_guard.resource WHERE resource=p->>'resource' FOR UPDATE;
    IF prior.token>(p->>'token')::bigint OR (prior.token=(p->>'token')::bigint AND
      (prior.attempt IS DISTINCT FROM (p->>'attempt')::uuid OR prior.run_id IS DISTINCT FROM (p->>'run_id')::uuid)) THEN
      RAISE EXCEPTION 'Stale destination fence'; END IF;
    UPDATE bookkeeping_guard.resource SET token=(p->>'token')::bigint,run_id=(p->>'run_id')::uuid,
      attempt=(p->>'attempt')::uuid,expires_at=(p->>'expires_at')::timestamptz WHERE resource=p->>'resource';
  END LOOP;
END;
$$;
CREATE FUNCTION bookkeeping_guard.valid_at_commit() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,bookkeeping_guard AS $$
BEGIN
  -- Deferred check rejects a destination transaction that outlives its proof.
  IF NEW.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'Destination lease expired before commit'; END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER lease_valid_at_commit AFTER INSERT OR UPDATE ON bookkeeping_guard.resource
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION bookkeeping_guard.valid_at_commit();

-- Narrow an existing MDM publication fence to a configured batch without
-- bypassing the existing per-consumer generation order. No new fence state.
CREATE FUNCTION bookkeeping_guard.claim_publication(destination text,owner_name text,seconds integer,batch_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping_guard AS $$
DECLARE next_batch text;
BEGIN
  SELECT q.batch_id INTO next_batch FROM mdm.outbox q JOIN mdm.batch b USING(batch_id)
    WHERE q.consumer=destination AND q.verified_at IS NULL ORDER BY b.generation LIMIT 1 FOR UPDATE OF q;
  IF next_batch IS DISTINCT FROM batch_key THEN RETURN NULL; END IF;
  RETURN mdm.claim_outbox(destination,owner_name,seconds);
END;
$$;
REVOKE ALL ON ALL TABLES IN SCHEMA bookkeeping_guard FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA bookkeeping_guard FROM PUBLIC;
