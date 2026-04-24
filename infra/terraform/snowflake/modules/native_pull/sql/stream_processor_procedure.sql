CREATE OR REPLACE PROCEDURE __STREAM_PROCESSOR_PROCEDURE_NAME__()
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
  FOR manifest_record IN (
    SELECT DISTINCT workflow_name, run_id
    FROM __SOURCE_SCHEMA__.__MANIFEST_STREAM_NAME__
    WHERE METADATA$ACTION = 'INSERT'
  ) DO
    CALL __SOURCE_SCHEMA__.__SOURCE_LOAD_PROCEDURE_NAME__(manifest_record.workflow_name, manifest_record.run_id);
    CALL __GOLD_SCHEMA__.__REFRESH_PROCEDURE_NAME__(manifest_record.workflow_name, manifest_record.run_id);
  END FOR;

  RETURN OBJECT_CONSTRUCT('status', 'succeeded');
END;
$$;
