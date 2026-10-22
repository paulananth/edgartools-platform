CREATE TABLE IF NOT EXISTS table_spec (
 table_name VARCHAR(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin PRIMARY KEY,
 spec LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
 sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 registered_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
 CHECK (JSON_VALID(spec)),
 CHECK (JSON_UNQUOTE(JSON_EXTRACT(spec,'$.table')) = table_name),
 CHECK (sha256 REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB;
-- statement boundary
DROP PROCEDURE IF EXISTS lock_silver_table;
-- statement boundary
CREATE PROCEDURE lock_silver_table(IN wanted VARCHAR(63)) SQL SECURITY DEFINER
BEGIN
 DECLARE held VARCHAR(63);
 SELECT table_name INTO held FROM table_spec WHERE table_name=wanted FOR UPDATE;
 IF held IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Silver table is not registered'; END IF;
END;
