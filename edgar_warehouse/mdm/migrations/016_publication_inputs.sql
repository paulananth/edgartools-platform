-- Publication prepares payloads in programs from indexed immutable inputs.
-- Commit-time expected hashes still come from write_batch's authoritative
-- expression. No worker-supplied hash can alter that durable intent.
-- Existing outbox_delivery/claim_outbox remain compatible for frozen clients.
CREATE VIEW mdm.outbox_input AS
 SELECT o.batch_id, o.consumer, o.payload_hash, b.created_at,
        o.payload::text AS payload_text,
        b.generation, b.run_id::text AS run_id,
        CASE WHEN o.payload IS NULL THEN b.effects->>'policy_digest' END AS policy_digest,
        CASE WHEN o.payload IS NULL THEN (b.effects->'projections')::text END AS projections_text,
        CASE WHEN o.payload IS NULL AND o.consumer='journal' THEN b.effects::text END AS effects_text
 FROM mdm.outbox o JOIN mdm.batch b USING(batch_id);
COMMENT ON VIEW mdm.outbox_input IS
 'Indexed immutable publication inputs. Programs shape/hash them against the committed payload_hash before sending. Raw JSON text preserves numeric precision/scale. Previously stored payloads are sent as stored.';

-- Preserve existing publication readers on upgrade, including SELECT granted
-- to a group role. Copy only SELECT, never any write or function authority.
DO $$
DECLARE reader text;
BEGIN
    FOR reader IN
        SELECT DISTINCT pg_get_userbyid(a.grantee)
        FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        WHERE c.oid='mdm.outbox_delivery'::regclass AND a.privilege_type='SELECT' AND a.grantee<>0
    LOOP
        EXECUTE format('GRANT SELECT ON mdm.outbox_input TO %I',reader);
    END LOOP;
END;
$$;

CREATE FUNCTION mdm.claim_outbox_input(destination text, owner_name text, lease_seconds integer, batch_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm AS $$
DECLARE p mdm.outbox%ROWTYPE;
BEGIN
    IF lease_seconds NOT BETWEEN 1 AND 3600 OR nullif(owner_name,'') IS NULL THEN
        RAISE EXCEPTION 'Invalid lease';
    END IF;
    -- A requested batch cannot jump an earlier generation. Same row, fence,
    -- lease and event history as claim_outbox, without payload computation.
    SELECT q.* INTO p FROM mdm.outbox q JOIN mdm.batch b USING(batch_id)
      WHERE q.consumer=destination AND q.verified_at IS NULL
      ORDER BY b.generation LIMIT 1 FOR UPDATE OF q;
    IF NOT FOUND OR p.lease_until > clock_timestamp()
       OR (batch_key IS NOT NULL AND p.batch_id IS DISTINCT FROM batch_key) THEN
        RETURN NULL;
    END IF;
    UPDATE mdm.outbox SET fence=fence+1, worker=owner_name,
      lease_until=clock_timestamp()+make_interval(secs=>lease_seconds)
      WHERE batch_id=p.batch_id AND consumer=p.consumer RETURNING * INTO p;
    INSERT INTO mdm.outbox_event(batch_id,consumer,fence,event,detail)
      VALUES(p.batch_id,p.consumer,p.fence,'claimed',jsonb_build_object('worker',owner_name));
    RETURN (to_jsonb(p)-'payload') ||
      (SELECT to_jsonb(i) FROM mdm.outbox_input i
       WHERE i.batch_id=p.batch_id AND i.consumer=p.consumer);
END;
$$;
