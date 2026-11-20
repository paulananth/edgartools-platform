-- A code set keeps exactly one version: a version whose valid_to is set (replaced or retired), and its content, may be deleted;
-- nothing else may. The supersedes key is dropped by the step that follows (supersedes names a version that is deleted).
DROP TRIGGER IF EXISTS `code_set_version_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_version_delete_guard` BEFORE DELETE ON `code_set_version` FOR EACH ROW BEGIN DECLARE replaced LONGTEXT DEFAULT NULL;
IF OLD.valid_to IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a replaced or retired version is deleted'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_delete_guard`
-- statement boundary
CREATE TRIGGER `code_delete_guard` BEFORE DELETE ON `code` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft' OR held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_label_delete_guard`
-- statement boundary
CREATE TRIGGER `code_label_delete_guard` BEFORE DELETE ON `code_label` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft' OR held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `level_delete_guard`
-- statement boundary
CREATE TRIGGER `level_delete_guard` BEFORE DELETE ON `level` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft' OR held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_path_delete_guard`
-- statement boundary
CREATE TRIGGER `code_path_delete_guard` BEFORE DELETE ON `code_path` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Paths are written once, while an approved version is published'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `crosswalk_row_delete_guard`
-- statement boundary
CREATE TRIGGER `crosswalk_row_delete_guard` BEFORE DELETE ON `crosswalk_row` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`from_set`,OLD.`from_version`) as binary),256) AND code_set=OLD.`from_set` AND version=OLD.`from_version` FOR SHARE;
IF NOT (held_status <=> 'draft' OR held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_usage_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_usage_delete_guard` BEFORE DELETE ON `code_set_usage` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft' OR held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS `code_set_hint_delete_guard`
-- statement boundary
CREATE TRIGGER `code_set_hint_delete_guard` BEFORE DELETE ON `code_set_hint` FOR EACH ROW BEGIN DECLARE held_status LONGTEXT DEFAULT NULL; DECLARE held_closed INT DEFAULT 0;
SELECT status, valid_to IS NOT NULL INTO held_status, held_closed FROM code_set_version WHERE _row_key=sha2(cast(json_array(OLD.`code_set`,OLD.`version`) as binary),256) AND code_set=OLD.`code_set` AND version=OLD.`version` FOR SHARE;
IF NOT (held_status <=> 'draft' OR held_closed = 1) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only a draft version''s content may change'; END IF;
END
