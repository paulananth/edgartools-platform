-- Delegate immutable configuration-pin approval without granting writes to
-- the save gate, master records, history, leases or publication state.
CREATE FUNCTION public.mdm_store_register_pin(pin_name text, pin_value text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $registration$
DECLARE
    name_hash text := encode(sha256(convert_to(pin_name, 'UTF8')), 'hex');
    value_hash text := encode(sha256(convert_to(pin_value, 'UTF8')), 'hex');
BEGIN
    IF pin_name IS NULL OR pin_value IS NULL
       OR NOT (pin_name = 'policy' OR starts_with(pin_name, 'mapping/') OR starts_with(pin_name, 'schema/'))
       OR pin_value !~ '^[a-f0-9]{64}$' THEN
        RAISE EXCEPTION 'invalid_registration_pin';
    END IF;
    PERFORM generation FROM public.mdm_store_gate WHERE id = 1 FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'missing_storage_gate'; END IF;
    INSERT INTO public.mdm_store_pin(name_key,value_key,name_bytes,value_bytes,active)
    VALUES (name_hash,value_hash,convert_to(pin_name,'UTF8'),convert_to(pin_value,'UTF8'),1)
    ON CONFLICT (name_key,value_key) DO UPDATE SET active=1
    WHERE mdm_store_pin.name_bytes=EXCLUDED.name_bytes AND mdm_store_pin.value_bytes=EXCLUDED.value_bytes;
    IF NOT FOUND THEN RAISE EXCEPTION 'frozen_pin_digest_collision'; END IF;
END;
$registration$;
REVOKE ALL ON FUNCTION public.mdm_store_register_pin(text,text) FROM PUBLIC;
COMMENT ON FUNCTION public.mdm_store_register_pin(text,text) IS
'Approve one opaque configuration reference under the save lock. Only delegated configuration registrars may execute; no master or save-gate write authority is delegated.';
