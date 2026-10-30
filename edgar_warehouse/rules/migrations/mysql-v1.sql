-- Immutable Rules documents and database-authoritative lifecycle enforcement.
CREATE TABLE IF NOT EXISTS rule_version (
  kind LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  name LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  version LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  body LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'draft',
  created_by LONGTEXT NOT NULL DEFAULT (''),
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  proved_at DATETIME(6), proof LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  batch_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin,
  approved_by LONGTEXT, approved_at DATETIME(6), approved_words LONGTEXT,
  approval_overrule LONGTEXT, approval_evidence CHAR(64) CHARACTER SET ascii COLLATE ascii_bin,
  approval_recorded_by LONGTEXT, activated_at DATETIME(6), retired_at DATETIME(6),
  clean_mdm LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  _version_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin GENERATED ALWAYS AS
    (SHA2(CAST(JSON_ARRAY(kind,name,version) AS BINARY),256)) STORED PRIMARY KEY,
  _document_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin GENERATED ALWAYS AS
    (SHA2(CAST(JSON_ARRAY(kind,name) AS BINARY),256)) STORED,
  _active_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin GENERATED ALWAYS AS
    (IF(status='active',SHA2(CAST(JSON_ARRAY(kind,name) AS BINARY),256),NULL)) STORED,
  UNIQUE KEY one_active (_active_key), KEY document_versions (_document_key), KEY lifecycle (status,proved_at),
  CHECK (kind IN ('source','merge','pipeline')),
  CHECK (status IN ('draft','proven','active','retired')),
  CHECK (digest=SHA2(body,256)), CHECK (JSON_VALID(body)),
  CHECK (proof IS NULL OR JSON_VALID(proof)), CHECK (clean_mdm IS NULL OR JSON_VALID(clean_mdm))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='rules-storage-v1'
-- statement boundary
DROP PROCEDURE IF EXISTS guard_rules_acquisition
-- statement boundary
CREATE PROCEDURE guard_rules_acquisition(IN p_kind LONGTEXT, IN p_body LONGTEXT, IN p_status LONGTEXT,
                                         IN p_proof LONGTEXT, IN p_approved LONGTEXT)
SQL SECURITY INVOKER
BEGIN
  DECLARE a LONGTEXT; DECLARE feeds LONGTEXT; DECLARE supplied LONGTEXT;
  DECLARE feed LONGTEXT; DECLARE definition LONGTEXT; DECLARE evidence LONGTEXT;
  DECLARE producers LONGTEXT; DECLARE counts LONGTEXT; DECLARE producer LONGTEXT;
  DECLARE checks LONGTEXT; DECLARE check_names LONGTEXT; DECLARE check_name LONGTEXT;
  DECLARE i BIGINT DEFAULT 0; DECLARE j BIGINT; DECLARE k BIGINT;
  DECLARE expected LONGTEXT; DECLARE verified LONGTEXT;
  IF JSON_CONTAINS_PATH(p_body,'one','$.acquisition') THEN
    SET a=JSON_EXTRACT(p_body,'$.acquisition');
    IF p_kind<>'source' OR NOT (JSON_EXTRACT(a,'$.version')<=>CAST('1' AS JSON))
      OR NOT (JSON_TYPE(JSON_EXTRACT(a,'$.feeds'))<=>'OBJECT') OR JSON_LENGTH(JSON_EXTRACT(a,'$.feeds'))=0 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Acquisition requires versioned source feeds';
    END IF;
    IF p_status IN ('proven','active') AND JSON_CONTAINS_PATH(p_proof,'one','$.acquisition') THEN
      SET feeds=JSON_KEYS(JSON_EXTRACT(a,'$.feeds')), supplied=JSON_EXTRACT(p_proof,'$.acquisition');
      IF NOT (JSON_TYPE(supplied)<=>'OBJECT') OR JSON_LENGTH(feeds)<>JSON_LENGTH(supplied)
        OR NOT COALESCE(JSON_CONTAINS(JSON_KEYS(supplied),feeds),FALSE) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Every acquisition feed requires matching validation evidence';
      END IF;
      WHILE i<JSON_LENGTH(feeds) DO
        SET feed=JSON_UNQUOTE(JSON_EXTRACT(feeds,CONCAT('$[',i,']')));
        SET definition=JSON_EXTRACT(a,CONCAT('$.feeds.',JSON_QUOTE(feed))),
            evidence=JSON_EXTRACT(supplied,CONCAT('$.',JSON_QUOTE(feed)));
        SET checks=JSON_EXTRACT(evidence,'$.checks'), check_names=JSON_KEYS(checks);
        IF JSON_UNQUOTE(JSON_EXTRACT(evidence,'$.manifest.sha256')) IS NULL
          OR NOT REGEXP_LIKE(JSON_UNQUOTE(JSON_EXTRACT(evidence,'$.manifest.sha256')),'^[0-9a-f]{64}$','c')
          OR COALESCE(JSON_UNQUOTE(JSON_EXTRACT(evidence,'$.manifest.uri')),'')=''
          OR NOT (JSON_TYPE(checks)<=>'OBJECT') OR JSON_LENGTH(checks)=0 THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid acquisition baseline proof';
        END IF;
        SET k=0;
        WHILE k<JSON_LENGTH(check_names) DO
          SET check_name=JSON_UNQUOTE(JSON_EXTRACT(check_names,CONCAT('$[',k,']')));
          IF NOT (JSON_EXTRACT(checks,CONCAT('$.',JSON_QUOTE(check_name)))<=>CAST('true' AS JSON)) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid acquisition baseline proof';
          END IF;
          SET k=k+1;
        END WHILE;
        SET producers=JSON_EXTRACT(definition,'$.required_producers'), counts=JSON_EXTRACT(evidence,'$.counts');
        IF NOT (JSON_TYPE(producers)<=>'ARRAY') OR JSON_LENGTH(producers)=0
          OR NOT (JSON_TYPE(counts)<=>'OBJECT') OR JSON_LENGTH(producers)<>JSON_LENGTH(counts)
          OR NOT COALESCE(JSON_CONTAINS(JSON_KEYS(counts),producers),FALSE) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Acquisition proof requires exactly the declared producers';
        END IF;
        SET j=0;
        WHILE j<JSON_LENGTH(producers) DO
          SET producer=JSON_UNQUOTE(JSON_EXTRACT(producers,CONCAT('$[',j,']')));
          SET expected=JSON_EXTRACT(counts,CONCAT('$.',JSON_QUOTE(producer),'.expected')),
              verified=JSON_EXTRACT(counts,CONCAT('$.',JSON_QUOTE(producer),'.verified'));
          IF expected IS NULL OR JSON_TYPE(expected) NOT IN ('INTEGER','DOUBLE','DECIMAL','UNSIGNED INTEGER')
            OR NOT REGEXP_LIKE(JSON_UNQUOTE(expected),'^[0-9]+$','c')
            OR verified IS NULL OR NOT REGEXP_LIKE(JSON_UNQUOTE(verified),'^[0-9]+$','c')
            OR NOT (CAST(expected AS JSON)<=>CAST(verified AS JSON)) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Incomplete acquisition producer proof';
          END IF;
          SET j=j+1;
        END WHILE;
        SET i=i+1;
      END WHILE;
    END IF;
    IF p_status='active' AND p_approved IS NULL THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Acquisition activation requires approval of this exact Rules body';
    END IF;
  END IF;
END
-- statement boundary
DROP TRIGGER IF EXISTS rules_insert
-- statement boundary
CREATE TRIGGER rules_insert BEFORE INSERT ON rule_version FOR EACH ROW
BEGIN
  IF NEW.status<>'draft' OR NEW.proof IS NOT NULL OR NEW.batch_hash IS NOT NULL
    OR NEW.approved_by IS NOT NULL OR NEW.approved_at IS NOT NULL OR NEW.proved_at IS NOT NULL
    OR NEW.approved_words IS NOT NULL OR NEW.approval_overrule IS NOT NULL
    OR NEW.approval_evidence IS NOT NULL OR NEW.approval_recorded_by IS NOT NULL
    OR NEW.activated_at IS NOT NULL OR NEW.retired_at IS NOT NULL OR NEW.clean_mdm IS NOT NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='New rules must be unapproved drafts';
  END IF;
  IF NEW.name NOT REGEXP '^[a-z][a-z0-9_.-]*$' OR NEW.version NOT REGEXP '^[A-Za-z0-9][A-Za-z0-9_.-]*$'
    OR JSON_TYPE(CAST(NEW.body AS JSON))<>'OBJECT' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid Rules identity or body';
  END IF;
  CALL guard_rules_acquisition(NEW.kind,NEW.body,NEW.status,NEW.proof,NEW.approved_by);
  SET NEW.created_by=SUBSTRING_INDEX(SESSION_USER(),'@',1), NEW.created_at=UTC_TIMESTAMP(6);
END
-- statement boundary
DROP TRIGGER IF EXISTS rules_update
-- statement boundary
CREATE TRIGGER rules_update BEFORE UPDATE ON rule_version FOR EACH ROW
BEGIN
  DECLARE old_rank BIGINT; DECLARE new_rank BIGINT;
  IF NOT (NEW.kind<=>OLD.kind) OR NOT (NEW.name<=>OLD.name) OR NOT (NEW.version<=>OLD.version)
    OR NOT (NEW.body<=>OLD.body) OR NOT (NEW.digest<=>OLD.digest)
    OR NOT (NEW.created_by<=>OLD.created_by) OR NOT (NEW.created_at<=>OLD.created_at) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Rule content and identity are immutable';
  END IF;
  SET old_rank=FIELD(OLD.status,'draft','proven','active','retired'), new_rank=FIELD(NEW.status,'draft','proven','active','retired');
  IF new_rank=0 OR new_rank<old_rank OR new_rank>old_rank+1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid rules lifecycle transition';
  END IF;
  IF NOT (NEW.proof<=>OLD.proof) OR NOT (NEW.batch_hash<=>OLD.batch_hash) OR NOT (NEW.proved_at<=>OLD.proved_at) THEN
    IF OLD.proof IS NOT NULL AND (OLD.status<>'draft' OR OLD.approved_by IS NOT NULL) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Rule proof is immutable';
    END IF;
    IF NEW.proof IS NULL OR NOT (JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.digest'))<=>NEW.digest)
      OR NOT (JSON_TYPE(JSON_EXTRACT(NEW.proof,'$.passed'))<=>'BOOLEAN')
      OR NEW.batch_hash IS NULL OR NEW.batch_hash NOT REGEXP '^[0-9a-f]{64}$'
      OR NOT (JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.batch_hash'))<=>NEW.batch_hash) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Proof must pin the exact rule and input batch and say whether it passed';
    END IF;
    SET NEW.proved_at=UTC_TIMESTAMP(6);
  END IF;
  IF NOT (NEW.approved_by<=>OLD.approved_by) OR NOT (NEW.approved_at<=>OLD.approved_at)
    OR NOT (NEW.approved_words<=>OLD.approved_words) OR NOT (NEW.approval_overrule<=>OLD.approval_overrule)
    OR NOT (NEW.approval_evidence<=>OLD.approval_evidence) OR NOT (NEW.approval_recorded_by<=>OLD.approval_recorded_by) THEN
    IF OLD.approved_by IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='An approval is never changed'; END IF;
    IF COALESCE(TRIM(NEW.approved_by),'')='' OR COALESCE(TRIM(NEW.approved_words),'')='' THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='An approval names who approved and holds their exact words';
    END IF;
    IF NEW.proof IS NULL OR NEW.status NOT IN ('draft','proven') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='No approval without test evidence';
    END IF;
    IF JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.passed'))='false' AND COALESCE(TRIM(NEW.approval_overrule),'')='' THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A failing proof is approved only with an overrule reason';
    END IF;
    IF JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.passed'))='true' AND NEW.approval_overrule IS NOT NULL THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A passing proof has nothing to overrule';
    END IF;
    SET NEW.approved_at=UTC_TIMESTAMP(6), NEW.approval_evidence=SHA2(NEW.proof,256), NEW.approval_recorded_by=SUBSTRING_INDEX(SESSION_USER(),'@',1);
  END IF;
  IF NEW.status IN ('proven','active') THEN
    IF NEW.proof IS NULL OR NOT (JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.digest'))<=>NEW.digest)
      OR NOT COALESCE(JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.passed'))='true'
                       OR (NEW.approved_by IS NOT NULL AND NEW.approval_overrule IS NOT NULL),FALSE)
      OR NEW.batch_hash IS NULL OR NEW.batch_hash NOT REGEXP '^[0-9a-f]{64}$'
      OR NOT (JSON_UNQUOTE(JSON_EXTRACT(NEW.proof,'$.batch_hash'))<=>NEW.batch_hash) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Proof must pass, or be overruled on approval, and pin the exact rule and input batch';
    END IF;
  END IF;
  IF NEW.status='active' THEN
    IF NEW.proof IS NULL OR ((NEW.kind='merge' OR JSON_CONTAINS_PATH(NEW.body,'one','$.mdm','$.bookkeeping.targets.mdm'))
                             AND NEW.approved_by IS NULL) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Activation requires proof and MDM approval';
    END IF;
    IF (NEW.kind='merge' OR (NEW.kind='source' AND JSON_CONTAINS_PATH(NEW.body,'one','$.mdm')))
      AND NOT (JSON_UNQUOTE(JSON_EXTRACT(NEW.clean_mdm,'$.rules_digest'))<=>NEW.digest) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Activation requires an MDM handoff receipt for this rule';
    END IF;
    SET NEW.activated_at=COALESCE(OLD.activated_at,UTC_TIMESTAMP(6));
  END IF;
  IF OLD.status IN ('active','retired') AND NOT (NEW.clean_mdm<=>OLD.clean_mdm) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MDM registration evidence is immutable';
  END IF;
  IF NEW.status='retired' THEN SET NEW.retired_at=COALESCE(OLD.retired_at,UTC_TIMESTAMP(6)); END IF;
  CALL guard_rules_acquisition(NEW.kind,NEW.body,NEW.status,NEW.proof,NEW.approved_by);
END
-- statement boundary
DROP TRIGGER IF EXISTS rules_delete
-- statement boundary
CREATE TRIGGER rules_delete BEFORE DELETE ON rule_version FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Rule history is retained'
