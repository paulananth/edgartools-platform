-- Applied only to CHANGE_LEDGER_DATABASE_URL. This is a verified projection of
-- committed MDM journal events, never the authority for an MDM transaction.
CREATE SCHEMA mdm_mirror;
REVOKE ALL ON SCHEMA mdm_mirror FROM PUBLIC;
CREATE TABLE mdm_mirror.migration(name text PRIMARY KEY,checksum text NOT NULL);
CREATE TABLE mdm_mirror.event (
    delivery_key text PRIMARY KEY,
    run_id uuid NOT NULL,
    generation bigint NOT NULL,
    payload_hash text NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION mdm_mirror.deliver(k text,h text,p jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_mirror AS $$
DECLARE prior mdm_mirror.event%ROWTYPE;
BEGIN
    IF p->>'contract_version' IS DISTINCT FROM '2' OR NOT p ? 'effects' THEN
        RAISE EXCEPTION 'Unsupported MDM journal envelope';
    END IF;
    IF encode(sha256(convert_to(p::text,'UTF8')),'hex')<>h THEN RAISE EXCEPTION 'Mirror hash mismatch'; END IF;
    INSERT INTO mdm_mirror.event(delivery_key,run_id,generation,payload_hash,payload)
      VALUES(k,(p->>'run_id')::uuid,(p->>'generation')::bigint,h,p) ON CONFLICT DO NOTHING;
    SELECT * INTO prior FROM mdm_mirror.event WHERE delivery_key=k;
    IF prior.payload_hash<>h OR prior.payload<>p THEN RAISE EXCEPTION 'Conflicting mirror delivery'; END IF;
END;
$$;
CREATE FUNCTION mdm_mirror.immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'MDM commit mirror is append-only'; END;
$$;
CREATE TRIGGER immutable_event BEFORE UPDATE OR DELETE ON mdm_mirror.event
FOR EACH ROW EXECUTE FUNCTION mdm_mirror.immutable_row();
REVOKE ALL ON ALL TABLES IN SCHEMA mdm_mirror FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_mirror FROM PUBLIC;
