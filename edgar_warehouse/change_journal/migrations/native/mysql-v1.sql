CREATE TABLE IF NOT EXISTS journal_event (
          id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          producer VARBINARY(256) NOT NULL, event_key VARBINARY(8192) NOT NULL,
          key_hash BINARY(32) NOT NULL, run_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          source VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          feed VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          event_type VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          occurred_at VARCHAR(100) NOT NULL,
          recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          canonical_body LONGBLOB NOT NULL, canonical_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          UNIQUE KEY event_key_unique(producer,key_hash), KEY event_scope(source,feed,id), KEY event_run(run_id,id),
          CHECK(canonical_hash=LOWER(SHA2(canonical_body,256)))
        ) ENGINE=InnoDB
-- journal migration statement boundary --
CREATE OR REPLACE SQL SECURITY DEFINER VIEW journal_records AS
          SELECT e.* FROM journal_event e JOIN journal_migrations m ON m.id=1 AND m.complete=1
-- journal migration statement boundary --
CREATE OR REPLACE SQL SECURITY DEFINER VIEW journal_readiness AS SELECT complete FROM journal_migrations WHERE id=1
-- journal migration statement boundary --
DROP TRIGGER IF EXISTS journal_protect_update
-- journal migration statement boundary --
CREATE TRIGGER journal_protect_update BEFORE UPDATE ON journal_event FOR EACH ROW
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Journal history is immutable'
-- journal migration statement boundary --
DROP TRIGGER IF EXISTS journal_protect_delete
-- journal migration statement boundary --
CREATE TRIGGER journal_protect_delete BEFORE DELETE ON journal_event FOR EACH ROW
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Journal history is immutable'
-- journal migration statement boundary --
DROP PROCEDURE IF EXISTS journal_record_event
-- journal migration statement boundary --
CREATE PROCEDURE journal_record_event(IN body LONGTEXT CHARACTER SET utf8mb4,IN h CHAR(64))
        SQL SECURITY DEFINER
        BEGIN
          DECLARE duplicate_key BOOL DEFAULT FALSE;
          DECLARE p VARBINARY(256); DECLARE k VARBINARY(8192); DECLARE kh BINARY(32);
          DECLARE prior_body LONGBLOB; DECLARE prior_hash CHAR(64); DECLARE prior_key VARBINARY(8192);
          DECLARE ready INT;
          DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
          START TRANSACTION;
          SELECT complete INTO ready FROM journal_migrations WHERE id=1 FOR SHARE;
          IF ready IS NULL OR ready<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Journal migration incomplete'; END IF;
          IF h IS NULL OR NOT REGEXP_LIKE(h,'^[0-9a-f]{64}$','c') OR OCTET_LENGTH(body)>1048576
            OR LOWER(SHA2(CONVERT(body USING binary),256))<>h OR NOT JSON_VALID(body)
            OR JSON_TYPE(CAST(body AS JSON))<>'OBJECT' OR JSON_LENGTH(body)<>10
            OR JSON_EXTRACT(body,'$.version')<>1
            OR CHAR_LENGTH(JSON_UNQUOTE(JSON_EXTRACT(body,'$.event_key'))) NOT BETWEEN 1 AND 2048 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid prepared journal event';
          END IF;
          SET p=CONVERT(JSON_UNQUOTE(JSON_EXTRACT(body,'$.producer')) USING binary);
          SET k=CONVERT(JSON_UNQUOTE(JSON_EXTRACT(body,'$.event_key')) USING binary);
          SET kh=UNHEX(SHA2(k,256));
          BEGIN
            DECLARE CONTINUE HANDLER FOR 1062 SET duplicate_key=TRUE;
            INSERT INTO journal_event(producer,event_key,key_hash,run_id,source,feed,event_type,occurred_at,canonical_body,canonical_hash)
              VALUES(p,k,kh,JSON_UNQUOTE(JSON_EXTRACT(body,'$.run_id')),JSON_UNQUOTE(JSON_EXTRACT(body,'$.source')),
                JSON_UNQUOTE(JSON_EXTRACT(body,'$.feed')),JSON_UNQUOTE(JSON_EXTRACT(body,'$.event_type')),
                JSON_UNQUOTE(JSON_EXTRACT(body,'$.occurred_at')),CONVERT(body USING binary),h);
          END;
          SELECT event_key,canonical_body,canonical_hash INTO prior_key,prior_body,prior_hash
            FROM journal_event WHERE producer=p AND key_hash=kh;
          IF prior_key<>k OR prior_body<>CONVERT(body USING binary) OR prior_hash<>h THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='journal_content_conflict';
          END IF;
          COMMIT;
        END