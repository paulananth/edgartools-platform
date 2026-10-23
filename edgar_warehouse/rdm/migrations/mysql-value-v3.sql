-- A code may carry one typed value for its period (ticket 133): exact decimal text with its unit, both or neither.
ALTER TABLE code ADD COLUMN value LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NULL COMMENT 'The code''s value for its period, as exact decimal text'
-- statement boundary
ALTER TABLE code ADD COLUMN unit LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NULL COMMENT 'What the value measures; set exactly when value is'
-- statement boundary
ALTER TABLE code ADD CONSTRAINT code_check_5 CHECK (value IS NULL OR REGEXP_LIKE(value,'^-?[0-9]+([.][0-9]+)?$','c'))
-- statement boundary
ALTER TABLE code ADD CONSTRAINT code_check_6 CHECK (unit IS NULL OR trim(unit)<>'')
-- statement boundary
ALTER TABLE code ADD CONSTRAINT code_check_7 CHECK ((value IS NULL)=(unit IS NULL))

-- statement boundary
CREATE OR REPLACE SQL SECURITY INVOKER VIEW code_context AS SELECT c._row_key,c.code_set,s.name AS code_set_name,c.code,c.label,c.definition,coalesce((SELECT JSON_ARRAYAGG(l.label) FROM code_label l WHERE l._version_key=c._version_key AND l.code_set=c.code_set AND l.version=c.version AND l.code=c.code AND l.kind='synonym'),JSON_ARRAY()) AS synonyms,p.path,p.label_path,p.level,p.depth,c.parent_code,coalesce((SELECT JSON_ARRAYAGG(JSON_OBJECT('to_set',x.to_set,'to_version',x.to_version,'to_code',x.to_code,'match_type',x.match_type)) FROM crosswalk_row x WHERE x._code_key=c._row_key AND x.from_set=c.code_set AND x.from_version=c.version AND x.from_code=c.code),JSON_ARRAY()) AS crosswalk,c.version,v.sha256,v.valid_from,v.valid_to,v.status AS version_status,c.status AS code_status,c.valid_from AS code_valid_from,c.valid_to AS code_valid_to,c.invalid_reason,v.approved_by,v.approved_at,v.published_at,c.value,c.unit FROM code c JOIN code_set_version v ON v._row_key=c._version_key AND v.code_set=c.code_set AND v.version=c.version JOIN code_set s ON s._row_key=v._catalog_key AND s.code_set=c.code_set JOIN code_path p ON p._row_key=c._row_key AND p.code_set=c.code_set AND p.version=c.version AND p.code=c.code WHERE v.status IN ('published','retired')
