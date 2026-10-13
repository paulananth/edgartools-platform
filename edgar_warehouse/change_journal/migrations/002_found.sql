-- Which of many event keys a producer has recorded (Issue 20 ticket 22: the
-- files a source already processed). The keys join the unique
-- (producer,event_key) index one at a time: never a whole-list search, never
-- a table scan. Custom plans, so each call plans for its own list.
CREATE FUNCTION journal.found(p text,k text[]) RETURNS text[]
LANGUAGE plpgsql SECURITY DEFINER STABLE SET search_path=pg_catalog,journal
SET plan_cache_mode=force_custom_plan AS $$
DECLARE result text[];
BEGIN
  IF p IS NULL OR k IS NULL OR cardinality(k)>10000 THEN
    RAISE EXCEPTION 'Journal lookup requires a producer and at most 10000 keys'; END IF;
  SELECT coalesce(array_agg(e.event_key ORDER BY e.event_key),'{}') INTO result
    FROM (SELECT DISTINCT key FROM unnest(k) AS u(key)) u
    JOIN journal.event e ON e.producer=p AND e.event_key=u.key;
  RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION journal.found(text,text[]) FROM PUBLIC;
