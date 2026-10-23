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
