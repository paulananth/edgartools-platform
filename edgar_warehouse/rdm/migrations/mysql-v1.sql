CREATE TABLE IF NOT EXISTS code_set (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	name LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	definition LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	authority LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	steward LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)), 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_set_check_0 CHECK (REGEXP_LIKE(code_set,'^[a-z0-9][a-z0-9_.-]*$','c')), 
	CONSTRAINT code_set_check_1 CHECK (trim(name)<>'')
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE TABLE IF NOT EXISTS code_set_version (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	created_by LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	status LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT ('draft'), 
	supersedes LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	approved_by LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	approved_words LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	sha256 LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	evidence LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)), 
	valid_from DATETIME(6), 
	valid_to DATETIME(6), 
	approved_at DATETIME(6), 
	published_at DATETIME(6), 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	_set_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`) as binary),256)) STORED, 
	_current_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (case when status='published' and valid_to is null then sha2(cast(json_array(`code_set`) as binary),256) else null end) STORED, 
	_catalog_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`) as binary),256)) STORED, 
	_supersedes_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (case when `supersedes` is null then null else sha2(cast(json_array(`code_set`,`supersedes`) as binary),256) end) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_set_version_check_0 CHECK (REGEXP_LIKE(version,'^[A-Za-z0-9][A-Za-z0-9_.-]*$','c')), 
	CONSTRAINT code_set_version_check_1 CHECK (status IN ('draft','approved','published','retired')), 
	CONSTRAINT code_set_version_check_2 CHECK (trim(created_by)<>''), 
	CONSTRAINT code_set_version_check_3 CHECK (valid_to IS NULL OR valid_to>=valid_from), 
	CONSTRAINT code_set_version_check_4 CHECK (JSON_VALID(evidence) AND JSON_TYPE(evidence)='OBJECT'), 
	CONSTRAINT code_set_version_check_5 CHECK (sha256 IS NULL OR REGEXP_LIKE(sha256,'^[0-9a-f]{64}$','c')), 
	FOREIGN KEY(_catalog_key) REFERENCES code_set (_row_key), 
	FOREIGN KEY(_supersedes_key) REFERENCES code_set_version (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX code_set_version_version_lookup ON code_set_version (_version_key)
-- statement boundary
CREATE UNIQUE INDEX one_current_published ON code_set_version (_current_key)
-- statement boundary
CREATE INDEX version_set_lookup ON code_set_version (_set_key)
-- statement boundary
CREATE TABLE IF NOT EXISTS code (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	code LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	label LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	definition LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	status LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	parent_code LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	invalid_reason LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	valid_from DATE, 
	valid_to DATE, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	_search_text LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL DEFAULT (''), 
	_parent_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (case when `parent_code` is null then null else sha2(cast(json_array(`code_set`,`version`,`parent_code`) as binary),256) end) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_check_0 CHECK (code<>''), 
	CONSTRAINT code_check_1 CHECK (status IN ('valid','invalid')), 
	CONSTRAINT code_check_2 CHECK (valid_to IS NULL OR valid_to>=valid_from), 
	CONSTRAINT code_check_3 CHECK ((status='invalid')=(invalid_reason IS NOT NULL)), 
	CONSTRAINT code_check_4 CHECK (parent_code IS NULL OR parent_code<>code), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key), 
	FOREIGN KEY(_parent_key) REFERENCES code (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX code_version_lookup ON code (_version_key)
-- statement boundary
CREATE FULLTEXT INDEX code_words ON code (_search_text)
-- statement boundary
CREATE TABLE IF NOT EXISTS code_label (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	code LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	language LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	label LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	kind LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	source LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	_preferred_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (case when kind='preferred' then sha2(cast(json_array(`code_set`,`version`,`code`,`language`) as binary),256) else null end) STORED, 
	_search_text LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL DEFAULT (''), 
	_code_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`,`code`) as binary),256)) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_label_check_0 CHECK (REGEXP_LIKE(language,'^[a-z]{2,3}(-[A-Za-z0-9]+)*$','c')), 
	CONSTRAINT code_label_check_1 CHECK (trim(label)<>''), 
	CONSTRAINT code_label_check_2 CHECK (kind IN ('preferred','synonym')), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key), 
	FOREIGN KEY(_code_key) REFERENCES code (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX code_label_version_lookup ON code_label (_version_key)
-- statement boundary
CREATE FULLTEXT INDEX code_label_words ON code_label (_search_text)
-- statement boundary
CREATE UNIQUE INDEX one_preferred_label ON code_label (_preferred_key)
-- statement boundary
CREATE TABLE IF NOT EXISTS level (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	name LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	definition LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	depth INTEGER NOT NULL, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT level_check_0 CHECK (depth>=1), 
	CONSTRAINT level_check_1 CHECK (trim(name)<>''), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX level_version_lookup ON level (_version_key)
-- statement boundary
CREATE TABLE IF NOT EXISTS code_path (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	code LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	path LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	label_path LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	level LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin, 
	depth INTEGER NOT NULL, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	_code_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`,`code`) as binary),256)) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_path_check_0 CHECK (depth>=1), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key), 
	FOREIGN KEY(_code_key) REFERENCES code (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX code_path_version_lookup ON code_path (_version_key)
-- statement boundary
CREATE TABLE IF NOT EXISTS crosswalk_row (
	from_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	from_version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	from_code LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	to_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	to_version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	to_code LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	match_type LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	evidence LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`from_set`,`from_version`) as binary),256)) STORED, 
	_code_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`from_set`,`from_version`,`from_code`) as binary),256)) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT crosswalk_row_check_0 CHECK (REGEXP_LIKE(to_set,'^[a-z0-9][a-z0-9_.-]*$','c')), 
	CONSTRAINT crosswalk_row_check_1 CHECK (trim(to_version)<>''), 
	CONSTRAINT crosswalk_row_check_2 CHECK (to_code<>''), 
	CONSTRAINT crosswalk_row_check_3 CHECK (match_type IN ('exact','close','broad','narrow')), 
	CONSTRAINT crosswalk_row_check_4 CHECK (JSON_VALID(evidence) AND JSON_TYPE(evidence)='OBJECT'), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key), 
	FOREIGN KEY(_code_key) REFERENCES code (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX crosswalk_row_version_lookup ON crosswalk_row (_version_key)
-- statement boundary
CREATE TABLE IF NOT EXISTS code_set_usage (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	store LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	object LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	field LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	`match` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	note LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_set_usage_check_0 CHECK (store IN ('mdm','silver','source','other')), 
	CONSTRAINT code_set_usage_check_1 CHECK (trim(`object`)<>''), 
	CONSTRAINT code_set_usage_check_2 CHECK (trim(field)<>''), 
	CONSTRAINT code_set_usage_check_3 CHECK (`match` IN ('exact','upper_trimmed')), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX code_set_usage_version_lookup ON code_set_usage (_version_key)
-- statement boundary
CREATE TABLE IF NOT EXISTS code_set_hint (
	code_set LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	kind LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	text LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL, 
	ordinal INTEGER NOT NULL, 
	_row_key VARCHAR(64) COLLATE ascii_bin NOT NULL DEFAULT '', 
	_version_key VARCHAR(64) COLLATE ascii_bin GENERATED ALWAYS AS (sha2(cast(json_array(`code_set`,`version`) as binary),256)) STORED, 
	PRIMARY KEY (_row_key), 
	CONSTRAINT code_set_hint_check_0 CHECK (kind IN ('meaning','use_when','avoid_when','example_question')), 
	CONSTRAINT code_set_hint_check_1 CHECK (ordinal>=1), 
	CONSTRAINT code_set_hint_check_2 CHECK (trim(text)<>''), 
	FOREIGN KEY(_version_key) REFERENCES code_set_version (_row_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin
-- statement boundary
CREATE INDEX code_set_hint_version_lookup ON code_set_hint (_version_key)
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_insert_guard`
-- statement boundary
CREATE TRIGGER `code_set_insert_guard` BEFORE INSERT ON `code_set` FOR EACH ROW BEGIN 
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`) as binary),256);
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_update_guard`
-- statement boundary
CREATE TRIGGER `code_set_update_guard` BEFORE UPDATE ON `code_set` FOR EACH ROW BEGIN 
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`) as binary),256);
IF TRUE THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Code set words are immutable'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_delete_guard` BEFORE DELETE ON `code_set` FOR EACH ROW BEGIN 
IF TRUE THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Code set words are immutable'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_version_insert_guard`
-- statement boundary
CREATE TRIGGER `code_set_version_insert_guard` BEFORE INSERT ON `code_set_version` FOR EACH ROW BEGIN DECLARE replaced LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256);
IF NEW.status<>'draft' OR NEW.approved_by IS NOT NULL OR NEW.approved_words IS NOT NULL OR NEW.approved_at IS NOT NULL OR NEW.published_at IS NOT NULL OR NEW.sha256 IS NOT NULL OR NEW.valid_from IS NOT NULL OR NEW.valid_to IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A new version must be an unapproved draft'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_version_update_guard`
-- statement boundary
CREATE TRIGGER `code_set_version_update_guard` BEFORE UPDATE ON `code_set_version` FOR EACH ROW BEGIN DECLARE replaced LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256);
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) OR NOT (NEW.`created_by` <=> OLD.`created_by`) OR NOT (NEW.`created_at` <=> OLD.`created_at`) OR NOT (NEW.`supersedes` <=> OLD.`supersedes`) OR NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A version''s identity is immutable'; END IF;
IF OLD.status<>'draft' AND NOT (NEW.evidence <=> OLD.evidence) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Evidence is fixed once a version is approved'; END IF;
IF FIELD(NEW.status,'draft','approved','published','retired') < FIELD(OLD.status,'draft','approved','published','retired') OR FIELD(NEW.status,'draft','approved','published','retired') > FIELD(OLD.status,'draft','approved','published','retired')+1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid reference data lifecycle transition'; END IF;
IF NOT (NEW.`approved_by` <=> OLD.`approved_by`) OR NOT (NEW.`approved_words` <=> OLD.`approved_words`) OR NOT (NEW.`approved_at` <=> OLD.`approved_at`) THEN IF OLD.status<>'draft' OR NEW.status<>'approved' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Approval is recorded once, on a draft'; END IF; SET NEW.approved_at=UTC_TIMESTAMP(6); END IF;
IF NEW.status='approved' AND (trim(coalesce(NEW.approved_by,''))='' OR trim(coalesce(NEW.approved_words,''))='') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='An approval names who approved and holds their exact words'; END IF;
IF NEW.status='approved' AND OLD.status='draft' AND NEW.approved_by=NEW.created_by THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='The drafter cannot approve its own draft'; END IF;
IF (NOT (NEW.`sha256` <=> OLD.`sha256`) OR NOT (NEW.`published_at` <=> OLD.`published_at`) OR NOT (NEW.`valid_from` <=> OLD.`valid_from`)) AND (OLD.status<>'approved' OR NEW.status<>'published') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='The sha256 and valid_from are set once, when published'; END IF;
IF NEW.status='published' AND OLD.status='approved' THEN IF NEW.sha256 IS NULL OR NEW.valid_from IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Publishing needs the sha256 and valid_from'; END IF; SELECT v.version INTO replaced FROM code_set_version v WHERE v._set_key=sha2(cast(json_array(NEW.`code_set`) as binary),256) AND v.code_set=NEW.code_set AND v.status IN ('published','retired') AND v.version<>NEW.version ORDER BY v.valid_from DESC LIMIT 1; IF NOT (NEW.supersedes <=> replaced) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A published version must supersede the version it replaces'; END IF;IF EXISTS (SELECT 1 FROM code c WHERE c._version_key=NEW._row_key AND c.code_set=NEW.code_set AND c.version=NEW.version AND NOT EXISTS (SELECT 1 FROM code_path p WHERE p._row_key=c._row_key AND p.code_set=c.code_set AND p.version=c.version AND p.code=c.code)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Publishing needs a path for every code'; END IF; SET NEW.published_at=UTC_TIMESTAMP(6); END IF;
IF NOT (NEW.valid_to <=> OLD.valid_to) AND (OLD.valid_to IS NOT NULL OR OLD.status<>'published') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='valid_to is set once, on a published version'; END IF;
IF NEW.status='retired' AND OLD.status='published' AND NEW.valid_to IS NULL THEN SET NEW.valid_to=UTC_TIMESTAMP(6); END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_version_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_version_delete_guard` BEFORE DELETE ON `code_set_version` FOR EACH ROW BEGIN DECLARE replaced LONGTEXT DEFAULT NULL;
IF TRUE THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Reference data history is retained'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_insert_guard`
-- statement boundary
CREATE TRIGGER `code_insert_guard` BEFORE INSERT ON `code` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`code`) as binary),256);
SET NEW._search_text=NEW.label;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_update_guard`
-- statement boundary
CREATE TRIGGER `code_update_guard` BEFORE UPDATE ON `code` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`code`) as binary),256);
SET NEW._search_text=NEW.label;
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_delete_guard`
-- statement boundary
CREATE TRIGGER `code_delete_guard` BEFORE DELETE ON `code` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_label_insert_guard`
-- statement boundary
CREATE TRIGGER `code_label_insert_guard` BEFORE INSERT ON `code_label` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`code`,NEW.`language`,NEW.`label`) as binary),256);
SET NEW._search_text=NEW.label;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_label_update_guard`
-- statement boundary
CREATE TRIGGER `code_label_update_guard` BEFORE UPDATE ON `code_label` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`code`,NEW.`language`,NEW.`label`) as binary),256);
SET NEW._search_text=NEW.label;
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_label_delete_guard`
-- statement boundary
CREATE TRIGGER `code_label_delete_guard` BEFORE DELETE ON `code_label` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `level_insert_guard`
-- statement boundary
CREATE TRIGGER `level_insert_guard` BEFORE INSERT ON `level` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`depth`) as binary),256);
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `level_update_guard`
-- statement boundary
CREATE TRIGGER `level_update_guard` BEFORE UPDATE ON `level` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`depth`) as binary),256);
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `level_delete_guard`
-- statement boundary
CREATE TRIGGER `level_delete_guard` BEFORE DELETE ON `level` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_path_insert_guard`
-- statement boundary
CREATE TRIGGER `code_path_insert_guard` BEFORE INSERT ON `code_path` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`code`) as binary),256);
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'approved') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Paths are written once, while an approved version is published'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_path_update_guard`
-- statement boundary
CREATE TRIGGER `code_path_update_guard` BEFORE UPDATE ON `code_path` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`code`) as binary),256);
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF TRUE THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Paths are written once, while an approved version is published'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_path_delete_guard`
-- statement boundary
CREATE TRIGGER `code_path_delete_guard` BEFORE DELETE ON `code_path` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF TRUE THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Paths are written once, while an approved version is published'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `crosswalk_row_insert_guard`
-- statement boundary
CREATE TRIGGER `crosswalk_row_insert_guard` BEFORE INSERT ON `crosswalk_row` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`from_set`,NEW.`from_version`,NEW.`from_code`,NEW.`to_set`,NEW.`to_version`,NEW.`to_code`) as binary),256);
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`from_set`,NEW.`from_version`) as binary),256) AND code_set=NEW.`from_set` AND version=NEW.`from_version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `crosswalk_row_update_guard`
-- statement boundary
CREATE TRIGGER `crosswalk_row_update_guard` BEFORE UPDATE ON `crosswalk_row` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`from_set`,NEW.`from_version`,NEW.`from_code`,NEW.`to_set`,NEW.`to_version`,NEW.`to_code`) as binary),256);
IF NOT (NEW.`from_set` <=> OLD.`from_set`) OR NOT (NEW.`from_version` <=> OLD.`from_version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`from_set`,NEW.`from_version`) as binary),256) AND code_set=NEW.`from_set` AND version=NEW.`from_version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `crosswalk_row_delete_guard`
-- statement boundary
CREATE TRIGGER `crosswalk_row_delete_guard` BEFORE DELETE ON `crosswalk_row` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`from_set`,OLD.`from_version`) as binary),256) AND code_set=OLD.`from_set` AND version=OLD.`from_version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_usage_insert_guard`
-- statement boundary
CREATE TRIGGER `code_set_usage_insert_guard` BEFORE INSERT ON `code_set_usage` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`store`,NEW.`object`,NEW.`field`) as binary),256);
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_usage_update_guard`
-- statement boundary
CREATE TRIGGER `code_set_usage_update_guard` BEFORE UPDATE ON `code_set_usage` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`store`,NEW.`object`,NEW.`field`) as binary),256);
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_usage_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_usage_delete_guard` BEFORE DELETE ON `code_set_usage` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_hint_insert_guard`
-- statement boundary
CREATE TRIGGER `code_set_hint_insert_guard` BEFORE INSERT ON `code_set_hint` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`kind`,NEW.`ordinal`) as binary),256);
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_hint_update_guard`
-- statement boundary
CREATE TRIGGER `code_set_hint_update_guard` BEFORE UPDATE ON `code_set_hint` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
IF NOT (NEW.`_row_key` <=> OLD.`_row_key`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row''s storage key is immutable'; END IF;
SET NEW._row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`,NEW.`kind`,NEW.`ordinal`) as binary),256);
IF NOT (NEW.`code_set` <=> OLD.`code_set`) OR NOT (NEW.`version` <=> OLD.`version`) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A row stays in its version'; END IF;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(NEW.`code_set`,NEW.`version`) as binary),256) AND code_set=NEW.`code_set` AND version=NEW.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_hint_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_hint_delete_guard` BEFORE DELETE ON `code_set_hint` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL;
SELECT status INTO held_status FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP PROCEDURE IF EXISTS lock_code_set
-- statement boundary
CREATE PROCEDURE lock_code_set(IN wanted_set LONGTEXT) SQL SECURITY DEFINER BEGIN DECLARE held LONGTEXT; SELECT code_set INTO held FROM code_set WHERE _row_key=sha2(cast(json_array(wanted_set) as binary),256) AND code_set=wanted_set FOR UPDATE; END
-- statement boundary
CREATE OR REPLACE SQL SECURITY INVOKER VIEW code_context AS SELECT c._row_key,c.code_set,s.name AS code_set_name,c.code,c.label,c.definition,coalesce((SELECT JSON_ARRAYAGG(l.label) FROM code_label l WHERE l._version_key=c._version_key AND l.code_set=c.code_set AND l.version=c.version AND l.code=c.code AND l.kind='synonym'),JSON_ARRAY()) AS synonyms,p.path,p.label_path,p.level,p.depth,c.parent_code,coalesce((SELECT JSON_ARRAYAGG(JSON_OBJECT('to_set',x.to_set,'to_version',x.to_version,'to_code',x.to_code,'match_type',x.match_type)) FROM crosswalk_row x WHERE x._code_key=c._row_key AND x.from_set=c.code_set AND x.from_version=c.version AND x.from_code=c.code),JSON_ARRAY()) AS crosswalk,c.version,v.sha256,v.valid_from,v.valid_to,v.status AS version_status,c.status AS code_status,c.valid_from AS code_valid_from,c.valid_to AS code_valid_to,c.invalid_reason,v.approved_by,v.approved_at,v.published_at FROM code c JOIN code_set_version v ON v._row_key=c._version_key AND v.code_set=c.code_set AND v.version=c.version JOIN code_set s ON s._row_key=v._catalog_key AND s.code_set=c.code_set JOIN code_path p ON p._row_key=c._row_key AND p.code_set=c.code_set AND p.version=c.version AND p.code=c.code WHERE v.status IN ('published','retired')
