-- Acquisition uses the same source version lifecycle, never a config table.
CREATE FUNCTION rules.govern_acquisition() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,rules AS $$
DECLARE a jsonb := NEW.body::jsonb->'acquisition'; feed text; definition jsonb; evidence jsonb; producer text;
BEGIN
  IF a IS NULL THEN RETURN NEW; END IF;
  IF NEW.kind<>'source' OR a->'version' IS DISTINCT FROM '1'::jsonb
    OR jsonb_typeof(a->'feeds') IS DISTINCT FROM 'object' OR a->'feeds'='{}'::jsonb THEN
    RAISE EXCEPTION 'Acquisition requires versioned source feeds'; END IF;
  IF NEW.status IN ('proven','active') THEN
    IF jsonb_typeof(NEW.proof->'acquisition') IS DISTINCT FROM 'object'
      OR (SELECT array_agg(key ORDER BY key) FROM jsonb_each(a->'feeds')) IS DISTINCT FROM
         (SELECT array_agg(key ORDER BY key) FROM jsonb_each(NEW.proof->'acquisition')) THEN
      RAISE EXCEPTION 'Every acquisition feed requires matching validation evidence'; END IF;
    FOR feed,definition IN SELECT key,value FROM jsonb_each(a->'feeds') LOOP
      evidence := NEW.proof->'acquisition'->feed;
      IF evidence#>>'{manifest,sha256}' IS NULL OR evidence#>>'{manifest,sha256}' !~ '^[0-9a-f]{64}$'
        OR coalesce(evidence#>>'{manifest,uri}','')=''
        OR jsonb_typeof(evidence->'checks') IS DISTINCT FROM 'object' OR evidence->'checks'='{}'::jsonb
        OR EXISTS(SELECT 1 FROM jsonb_each(evidence->'checks') WHERE value<>'true'::jsonb) THEN
        RAISE EXCEPTION 'Invalid acquisition baseline proof'; END IF;
      IF jsonb_typeof(definition->'required_producers') IS DISTINCT FROM 'array'
        OR jsonb_array_length(definition->'required_producers')=0
        OR jsonb_typeof(evidence->'counts') IS DISTINCT FROM 'object'
        OR (SELECT array_agg(key ORDER BY key) FROM jsonb_each(evidence->'counts')) IS DISTINCT FROM
           (SELECT array_agg(value ORDER BY value) FROM jsonb_array_elements_text(definition->'required_producers')) THEN
        RAISE EXCEPTION 'Acquisition proof requires exactly the declared producers'; END IF;
      FOR producer IN SELECT jsonb_array_elements_text(definition->'required_producers') LOOP
        IF evidence->'counts'->producer->'expected' IS NULL
          OR jsonb_typeof(evidence->'counts'->producer->'expected') IS DISTINCT FROM 'number'
          OR evidence->'counts'->producer->>'expected' !~ '^[0-9]+$'
          OR evidence->'counts'->producer->>'verified' !~ '^[0-9]+$'
          OR evidence->'counts'->producer->'expected' IS DISTINCT FROM evidence->'counts'->producer->'verified' THEN
          RAISE EXCEPTION 'Incomplete acquisition producer proof'; END IF;
      END LOOP;
    END LOOP;
  END IF;
  IF NEW.status='active' AND NEW.approved_by IS NULL THEN
    RAISE EXCEPTION 'Acquisition activation requires approval of this exact Rules body'; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER acquisition_governance BEFORE INSERT OR UPDATE ON rules.rule_version
FOR EACH ROW EXECUTE FUNCTION rules.govern_acquisition();
REVOKE ALL ON FUNCTION rules.govern_acquisition() FROM PUBLIC;
