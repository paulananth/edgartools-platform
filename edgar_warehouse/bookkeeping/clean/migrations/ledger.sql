-- Compact control-event projection in the existing Change Ledger database.
CREATE SCHEMA bookkeeping_mirror;
REVOKE ALL ON SCHEMA bookkeeping_mirror FROM PUBLIC;
CREATE TABLE bookkeeping_mirror.event (
  event_id uuid PRIMARY KEY, run_id uuid NOT NULL,
  payload_hash text NOT NULL, payload jsonb NOT NULL,
  received_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION bookkeeping_mirror.deliver(e uuid,p jsonb,h text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,bookkeeping_mirror AS $$
DECLARE prior bookkeeping_mirror.event%ROWTYPE;
BEGIN
  IF p->>'version' IS DISTINCT FROM '1' OR p->>'event_id' IS DISTINCT FROM e::text
    OR NOT p ? 'receipt' OR NOT p ? 'checks'
    OR encode(sha256(convert_to(p::text,'UTF8')),'hex')<>h THEN RAISE EXCEPTION 'Invalid control journal envelope'; END IF;
  INSERT INTO bookkeeping_mirror.event(event_id,run_id,payload_hash,payload)
    VALUES(e,(p->>'run_id')::uuid,h,p) ON CONFLICT DO NOTHING;
  SELECT * INTO STRICT prior FROM bookkeeping_mirror.event WHERE event_id=e;
  IF prior.payload<>p OR prior.payload_hash<>h THEN RAISE EXCEPTION 'Conflicting journal delivery'; END IF;
END;
$$;
CREATE FUNCTION bookkeeping_mirror.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Control journal is append-only'; END;
$$;
CREATE TRIGGER immutable_event BEFORE UPDATE OR DELETE ON bookkeeping_mirror.event
FOR EACH ROW EXECUTE FUNCTION bookkeeping_mirror.immutable();
REVOKE ALL ON ALL TABLES IN SCHEMA bookkeeping_mirror FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA bookkeeping_mirror FROM PUBLIC;
