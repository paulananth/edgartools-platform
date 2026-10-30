-- Frozen control storage only. Opaque documents retain their exact JSON text.
CREATE TABLE IF NOT EXISTS bookkeeping_pipeline_run (
 run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 submission LONGTEXT NOT NULL, submission_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 expected_count BIGINT NOT NULL, state VARCHAR(16) NOT NULL DEFAULT 'running',
 checks LONGTEXT NOT NULL DEFAULT ('{}'), summary LONGTEXT NOT NULL DEFAULT ('{}'),
 pinned BOOLEAN NOT NULL DEFAULT FALSE, created_at DATETIME(6) NOT NULL,
 completed_at DATETIME(6), compacted_at DATETIME(6), runtimes LONGTEXT NOT NULL DEFAULT ('{}'),
 document_hash BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(CONCAT(
  JSON_UNQUOTE(JSON_EXTRACT(submission,'$.kind')),':',JSON_UNQUOTE(JSON_EXTRACT(submission,'$.name')),':',
  JSON_UNQUOTE(JSON_EXTRACT(submission,'$.target'))),256))) STORED,
 KEY run_document_lookup(document_hash,created_at,run_id),
 CHECK (expected_count>=0), CHECK (state IN ('running','waiting','blocked','complete')),
 CHECK (JSON_VALID(submission)), CHECK (JSON_VALID(checks)), CHECK (JSON_VALID(summary)), CHECK (JSON_VALID(runtimes))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='bookkeeping-storage-v1'
-- statement boundary
CREATE TABLE IF NOT EXISTS bookkeeping_work_item (
 run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 step LONGTEXT NOT NULL, unit_key LONGTEXT NOT NULL, ordinal BIGINT NOT NULL,
 resources LONGTEXT NOT NULL, unit LONGTEXT NOT NULL, _cursor LONGTEXT NOT NULL,
 state VARCHAR(16) NOT NULL DEFAULT 'pending', attempt CHAR(32) CHARACTER SET ascii COLLATE ascii_bin,
 attempts BIGINT NOT NULL DEFAULT 0, authority_until DATETIME(6), receipt LONGTEXT,
 checks LONGTEXT NOT NULL DEFAULT ('{}'), error LONGTEXT, generated_count BIGINT,
 candidate LONGTEXT, reporter LONGTEXT, verifier LONGTEXT,
 _identity BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(CAST(JSON_ARRAY(run_id,step,unit_key) AS BINARY),256))) STORED PRIMARY KEY,
 _step BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(step,256))) STORED,
 UNIQUE KEY work_ordinal(run_id,_step,ordinal), KEY pending_work(run_id,state,_step,ordinal),
 FOREIGN KEY(run_id) REFERENCES bookkeeping_pipeline_run(run_id),
 CHECK (ordinal>=0), CHECK (attempts>=0), CHECK (generated_count IS NULL OR generated_count>=0),
 CHECK (state IN ('pending','running','reported','waiting','verified')),
 CHECK (JSON_VALID(resources)), CHECK (JSON_VALID(unit)), CHECK (JSON_VALID(checks)),
 CHECK (receipt IS NULL OR JSON_VALID(receipt)), CHECK (candidate IS NULL OR JSON_VALID(candidate))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='bookkeeping-storage-v1'
-- statement boundary
CREATE TABLE IF NOT EXISTS bookkeeping_lease (
 resource LONGTEXT NOT NULL, token BIGINT NOT NULL DEFAULT 0,
 run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin, attempt CHAR(32) CHARACTER SET ascii COLLATE ascii_bin,
 expires_at DATETIME(6) NOT NULL DEFAULT '1000-01-01', heartbeat_at DATETIME(6),
 _resource BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(resource,256))) STORED PRIMARY KEY,
 KEY lease_attempt(run_id,attempt), FOREIGN KEY(run_id) REFERENCES bookkeeping_pipeline_run(run_id), CHECK (token>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='bookkeeping-storage-v1'
-- statement boundary
CREATE TABLE IF NOT EXISTS bookkeeping_checkpoint (
 run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, scope LONGTEXT NOT NULL,
 ordinal BIGINT NOT NULL DEFAULT -1, `cursor` LONGTEXT, receipt LONGTEXT, resource LONGTEXT,
 revision BIGINT NOT NULL DEFAULT 0,
 _identity BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(CAST(JSON_ARRAY(run_id,scope) AS BINARY),256))) STORED PRIMARY KEY,
 _resource BINARY(32) GENERATED ALWAYS AS (IF(resource IS NULL,NULL,UNHEX(SHA2(resource,256)))) STORED,
 UNIQUE KEY one_resource_checkpoint(_resource), KEY run_progress(run_id),
 FOREIGN KEY(run_id) REFERENCES bookkeeping_pipeline_run(run_id), CHECK (revision>=0), CHECK (ordinal>=-1),
 CHECK (`cursor` IS NULL OR JSON_VALID(`cursor`)), CHECK (receipt IS NULL OR JSON_VALID(receipt))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='bookkeeping-storage-v1'
-- statement boundary
CREATE TABLE IF NOT EXISTS bookkeeping_journal_outbox (
 event_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, step LONGTEXT NOT NULL, unit_key LONGTEXT NOT NULL,
 payload LONGTEXT NOT NULL, attempts BIGINT NOT NULL DEFAULT 0, error LONGTEXT,
 created_at DATETIME(6) NOT NULL, delivered_at DATETIME(6), event_type LONGTEXT NOT NULL DEFAULT ('work.verified'),
 _identity BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(CAST(JSON_ARRAY(run_id,step,unit_key,event_type) AS BINARY),256))) STORED,
 UNIQUE KEY one_work_event(_identity), KEY pending_delivery(run_id,delivered_at,created_at),
 FOREIGN KEY(run_id) REFERENCES bookkeeping_pipeline_run(run_id), CHECK (attempts>=0), CHECK (JSON_VALID(payload))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='bookkeeping-storage-v1'
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_require_ready
-- statement boundary
CREATE PROCEDURE bookkeeping_require_ready()
SQL SECURITY DEFINER
BEGIN
 IF (SELECT COUNT(*) FROM bookkeeping_migrations)<>1 OR NOT EXISTS(
  SELECT 1 FROM bookkeeping_migrations WHERE id=1 AND complete=1
  AND checksum REGEXP '^[0-9a-f]{64}$' AND table_checksum REGEXP '^[0-9a-f]{64}$'
  AND guard_checksum REGEXP '^[0-9a-f]{64}$') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Control migration incomplete'; END IF;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_start_run
-- statement boundary
CREATE PROCEDURE bookkeeping_start_run(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
main: BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE h LONGTEXT; DECLARE items LONGTEXT;
 DECLARE prior_s LONGTEXT; DECLARE prior_h LONGTEXT; DECLARE compacted DATETIME(6); DECLARE expected BIGINT;
 DECLARE i BIGINT DEFAULT 0; DECLARE entry LONGTEXT; DECLARE entry_step LONGTEXT; DECLARE entry_key LONGTEXT;
 DECLARE entry_ordinal BIGINT; DECLARE entry_resources LONGTEXT; DECLARE entry_unit LONGTEXT; DECLARE entry_cursor LONGTEXT;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''),
     s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')), h=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.h')),
     items=JSON_EXTRACT(p_wire,'$.i');
 IF r IS NULL OR NOT REGEXP_LIKE(r,'^[0-9a-f]{32}$','c') OR NOT COALESCE(JSON_VALID(s),FALSE)
  OR NOT (h<=>SHA2(s,256)) OR NOT (JSON_TYPE(items)<=>'ARRAY') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid frozen submission'; END IF;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
 START TRANSACTION; CALL bookkeeping_require_ready();
 INSERT INTO bookkeeping_pipeline_run(run_id,submission,submission_hash,expected_count,created_at)
  VALUES(r,s,h,JSON_LENGTH(items),UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE run_id=run_id;
 SELECT submission,submission_hash,compacted_at,expected_count INTO prior_s,prior_h,compacted,expected
  FROM bookkeeping_pipeline_run WHERE run_id=r FOR UPDATE;
 IF NOT (BINARY prior_s<=>BINARY s) OR NOT (prior_h<=>h) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Frozen submission changed'; END IF;
 IF compacted IS NOT NULL THEN COMMIT; LEAVE main; END IF;
 WHILE i<JSON_LENGTH(items) DO
  SET entry=JSON_EXTRACT(items,CONCAT('$[',i,']')),
      entry_step=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.step')), entry_key=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.key')),
      entry_ordinal=CAST(JSON_UNQUOTE(JSON_EXTRACT(entry,'$.ordinal')) AS SIGNED),
      entry_resources=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.resources')), entry_unit=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.unit')),
      entry_cursor=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.cursor'));
  IF entry_step IS NULL OR entry_key IS NULL OR entry_ordinal IS NULL OR entry_ordinal<0
   OR NOT (JSON_TYPE(CAST(entry_resources AS JSON))<=>'ARRAY') OR JSON_LENGTH(entry_resources)=0
   OR NOT (JSON_TYPE(CAST(entry_unit AS JSON))<=>'OBJECT') THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Malformed frozen work'; END IF;
  INSERT INTO bookkeeping_work_item(run_id,step,unit_key,ordinal,resources,unit,_cursor)
   VALUES(r,entry_step,entry_key,entry_ordinal,entry_resources,entry_unit,entry_cursor) ON DUPLICATE KEY UPDATE run_id=run_id;
  IF NOT EXISTS(SELECT 1 FROM bookkeeping_work_item WHERE run_id=r AND step=entry_step AND unit_key=entry_key
   AND ordinal=entry_ordinal AND BINARY resources=BINARY entry_resources AND BINARY unit=BINARY entry_unit AND BINARY _cursor=BINARY entry_cursor) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Frozen worklist changed'; END IF;
  INSERT INTO bookkeeping_checkpoint(run_id,scope) VALUES(r,entry_step) ON DUPLICATE KEY UPDATE run_id=run_id;
  SET i=i+1;
 END WHILE;
 IF (SELECT COUNT(*) FROM bookkeeping_work_item WHERE run_id=r)<>expected THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Work accounting mismatch'; END IF;
 COMMIT;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_require
-- statement boundary
CREATE PROCEDURE bookkeeping_require(IN r CHAR(32), IN s LONGTEXT, IN duty LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE profile LONGTEXT; DECLARE actor LONGTEXT; DECLARE actor_host LONGTEXT;
 SELECT JSON_UNQUOTE(JSON_EXTRACT(submission,CONCAT('$.profiles.',JSON_QUOTE(s)))) INTO profile
  FROM bookkeeping_pipeline_run WHERE run_id=r;
 SET actor=SUBSTRING_INDEX(SESSION_USER(),'@',1);
 IF (SELECT COUNT(*) FROM mysql.user WHERE User=actor)<>1 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Control login must name one unambiguous account'; END IF;
 SELECT Host INTO actor_host FROM mysql.user WHERE User=actor;
 IF profile IS NULL OR NOT EXISTS(SELECT 1 FROM mysql.role_edges WHERE TO_USER=actor AND TO_HOST=actor_host
  AND FROM_HOST='%' AND (FROM_USER=CONCAT('bk_',duty,'_',LEFT(SHA2(profile,256),20))
   OR (duty='either' AND FROM_USER IN(CONCAT('bk_worker_',LEFT(SHA2(profile,256),20)),CONCAT('bk_verifier_',LEFT(SHA2(profile,256),20)))))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='This login has no required role for the frozen profile'; END IF;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_lock_work
-- statement boundary
CREATE PROCEDURE bookkeeping_lock_work(IN r CHAR(32), IN s LONGTEXT, IN k LONGTEXT, OUT w LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE root_id CHAR(32);
 SELECT run_id INTO root_id FROM bookkeeping_pipeline_run WHERE run_id=r FOR UPDATE NOWAIT;
 IF root_id IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unknown control run'; END IF;
 SELECT JSON_OBJECT('state',state,'attempt',attempt,'resources',resources,'unit',unit,'candidate',candidate,
  'reporter',reporter,'receipt',receipt,'checks',checks,'ordinal',ordinal,'generated_count',generated_count,'cursor',_cursor)
  INTO w FROM bookkeeping_work_item WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,s,k) AS BINARY),256))
  AND run_id=r AND step=s AND unit_key=k FOR UPDATE NOWAIT;
 IF w IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unknown control unit'; END IF;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_live
-- statement boundary
CREATE PROCEDURE bookkeeping_live(IN r CHAR(32))
SQL SECURITY DEFINER
BEGIN
 IF NOT EXISTS(SELECT 1 FROM bookkeeping_pipeline_run WHERE run_id=r AND state IN('running','waiting')) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Run is not executable'; END IF;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_authority
-- statement boundary
CREATE PROCEDURE bookkeeping_authority(IN r CHAR(32), IN s LONGTEXT, IN k LONGTEXT, IN a CHAR(32), IN proof LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE w LONGTEXT; DECLARE resources LONGTEXT; DECLARE i BIGINT DEFAULT 0; DECLARE p LONGTEXT;
 DECLARE resource_key LONGTEXT; DECLARE held_resource LONGTEXT; DECLARE held_run CHAR(32); DECLARE held_attempt CHAR(32);
 DECLARE held_token BIGINT; DECLARE expiry DATETIME(6); DECLARE seen LONGTEXT DEFAULT '[]'; DECLARE raw_token LONGTEXT;
 CALL bookkeeping_lock_work(r,s,k,w);
 CALL bookkeeping_live(r);
 SET resources=JSON_UNQUOTE(JSON_EXTRACT(w,'$.resources'));
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state')) NOT IN('running','reported')
  OR NOT (JSON_UNQUOTE(JSON_EXTRACT(w,'$.attempt'))<=>a) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Stale attempt'; END IF;
 IF NOT (JSON_TYPE(CAST(proof AS JSON))<=>'ARRAY') OR JSON_LENGTH(proof)<>JSON_LENGTH(resources) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Incomplete lease proof'; END IF;
 WHILE i<JSON_LENGTH(proof) DO
  SET p=JSON_EXTRACT(proof,CONCAT('$[',i,']')), resource_key=JSON_UNQUOTE(JSON_EXTRACT(p,'$.resource')),
   raw_token=JSON_UNQUOTE(JSON_EXTRACT(p,'$.token'));
  IF resource_key IS NULL OR NOT JSON_CONTAINS(resources,JSON_QUOTE(resource_key))
   OR JSON_CONTAINS(seen,JSON_QUOTE(resource_key)) OR raw_token IS NULL
   OR NOT REGEXP_LIKE(raw_token,'^[0-9]+$','c')
   OR NOT (REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p,'$.run_id')),'-','')<=>r)
   OR NOT (REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p,'$.attempt')),'-','')<=>a) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Incomplete lease proof'; END IF;
  SET held_resource=NULL;
  SELECT resource,run_id,attempt,token,expires_at INTO held_resource,held_run,held_attempt,held_token,expiry
   FROM bookkeeping_lease WHERE _resource=UNHEX(SHA2(resource_key,256)) AND resource=resource_key FOR UPDATE NOWAIT;
  IF held_resource IS NULL OR NOT (held_run<=>r) OR NOT (held_attempt<=>a)
   OR NOT (CAST(raw_token AS UNSIGNED)<=>held_token) OR expiry<=UTC_TIMESTAMP(6) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Stale lease'; END IF;
  SET seen=JSON_ARRAY_APPEND(seen,'$',resource_key), i=i+1;
 END WHILE;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_claim
-- statement boundary
CREATE PROCEDURE bookkeeping_claim(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
main: BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE k LONGTEXT; DECLARE a CHAR(32); DECLARE seconds BIGINT;
 DECLARE w LONGTEXT; DECLARE resources LONGTEXT; DECLARE prereqs LONGTEXT; DECLARE dependency LONGTEXT;
 DECLARE i BIGINT DEFAULT 0; DECLARE resource_key LONGTEXT; DECLARE held_resource LONGTEXT;
 DECLARE expiry DATETIME(6); DECLARE held_token BIGINT; DECLARE result LONGTEXT DEFAULT '[]';
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''), s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')),
  k=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.k')), a=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),'-',''),
  seconds=CAST(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.d')) AS SIGNED), prereqs=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.p'));
 IF seconds IS NULL OR seconds<2 OR seconds>86400 OR a IS NULL OR NOT REGEXP_LIKE(a,'^[0-9a-f]{32}$','c')
  OR NOT (JSON_TYPE(CAST(prereqs AS JSON))<=>'ARRAY') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid claim'; END IF;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION; CALL bookkeeping_require_ready();
 CALL bookkeeping_require(r,s,'worker'); CALL bookkeeping_lock_work(r,s,k,w); CALL bookkeeping_live(r);
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state')) IN('verified','reported') THEN COMMIT; SELECT NULL; LEAVE main; END IF;
 WHILE i<JSON_LENGTH(prereqs) DO
  SET dependency=JSON_UNQUOTE(JSON_EXTRACT(prereqs,CONCAT('$[',i,']')));
  IF EXISTS(SELECT 1 FROM bookkeeping_work_item WHERE run_id=r AND step=dependency AND state<>'verified') THEN
   SIGNAL SQLSTATE 'HY000' SET MYSQL_ERRNO=3572,MESSAGE_TEXT='Prerequisite contention'; END IF;
  SET i=i+1;
 END WHILE;
 SET resources=JSON_UNQUOTE(JSON_EXTRACT(w,'$.resources')), i=0;
 IF JSON_LENGTH(resources)=0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Missing resources'; END IF;
 WHILE i<JSON_LENGTH(resources) DO
  -- Source preparation sorts resources; retain the original identity on lookup.
  SET resource_key=JSON_UNQUOTE(JSON_EXTRACT(resources,CONCAT('$[',i,']')));
  INSERT INTO bookkeeping_lease(resource) VALUES(resource_key) ON DUPLICATE KEY UPDATE token=token;
  SELECT resource,token,expires_at INTO held_resource,held_token,expiry FROM bookkeeping_lease
   WHERE _resource=UNHEX(SHA2(resource_key,256)) FOR UPDATE NOWAIT;
  IF NOT (held_resource<=>resource_key) OR expiry>UTC_TIMESTAMP(6) THEN
   SIGNAL SQLSTATE 'HY000' SET MYSQL_ERRNO=3572,MESSAGE_TEXT='Lease contention'; END IF;
  SET expiry=TIMESTAMPADD(SECOND,seconds,UTC_TIMESTAMP(6)), held_token=held_token+1;
  UPDATE bookkeeping_lease SET token=held_token,run_id=r,attempt=a,expires_at=expiry,heartbeat_at=UTC_TIMESTAMP(6)
   WHERE _resource=UNHEX(SHA2(resource_key,256));
  SET result=JSON_ARRAY_APPEND(result,'$',JSON_OBJECT('resource',resource_key,'token',held_token,
   'run_id',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'attempt',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),
   'expires_at',DATE_FORMAT(expiry,'%Y-%m-%dT%H:%i:%s.%f+00:00'))), i=i+1;
 END WHILE;
 UPDATE bookkeeping_work_item SET state='running',attempt=a,attempts=attempts+1,error=NULL,candidate=NULL,reporter=NULL,verifier=NULL
  WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,s,k) AS BINARY),256));
 COMMIT; SELECT result;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_heartbeat
-- statement boundary
CREATE PROCEDURE bookkeeping_heartbeat(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE k LONGTEXT; DECLARE a CHAR(32); DECLARE seconds BIGINT;
 DECLARE result LONGTEXT;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''), s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')),
  k=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.k')), a=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),'-',''),
  seconds=CAST(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.d')) AS SIGNED);
 IF seconds IS NULL OR seconds<2 OR seconds>86400 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid lease duration'; END IF;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION; CALL bookkeeping_require_ready();
 CALL bookkeeping_require(r,s,'either');
 CALL bookkeeping_authority(r,s,k,a,JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.p')));
 UPDATE bookkeeping_lease SET expires_at=TIMESTAMPADD(SECOND,seconds,UTC_TIMESTAMP(6)),heartbeat_at=UTC_TIMESTAMP(6)
  WHERE run_id=r AND attempt=a;
 SELECT JSON_ARRAYAGG(JSON_OBJECT('resource',resource,'token',token,
  'run_id',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'attempt',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),
  'expires_at',DATE_FORMAT(expires_at,'%Y-%m-%dT%H:%i:%s.%f+00:00'))) INTO result
  FROM bookkeeping_lease WHERE run_id=r AND attempt=a;
 COMMIT; SELECT result;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_wait_work
-- statement boundary
CREATE PROCEDURE bookkeeping_wait_work(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
main: BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE k LONGTEXT; DECLARE a CHAR(32); DECLARE w LONGTEXT; DECLARE held CHAR(32);
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''), s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')),
  k=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.k')), a=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),'-','');
 IF a='null' THEN SET a=NULL; END IF;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION; CALL bookkeeping_require_ready();
 CALL bookkeeping_require(r,s,'either'); CALL bookkeeping_lock_work(r,s,k,w);
 IF a IS NOT NULL THEN
  CALL bookkeeping_authority(r,s,k,a,JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.p')));
  UPDATE bookkeeping_lease SET expires_at=UTC_TIMESTAMP(6) WHERE run_id=r AND attempt=a;
 ELSE
  SET held=JSON_UNQUOTE(JSON_EXTRACT(w,'$.attempt'));
  IF EXISTS(SELECT 1 FROM bookkeeping_lease WHERE run_id=r AND attempt=held AND expires_at>UTC_TIMESTAMP(6)) THEN
   COMMIT; LEAVE main; END IF;
 END IF;
 UPDATE bookkeeping_work_item SET state='waiting',error=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.m'))
  WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,s,k) AS BINARY),256)) AND state<>'verified';
 COMMIT;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_report
-- statement boundary
CREATE PROCEDURE bookkeeping_report(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
main: BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE k LONGTEXT; DECLARE a CHAR(32);
 DECLARE candidate LONGTEXT; DECLARE profile LONGTEXT; DECLARE runtime LONGTEXT; DECLARE pinned LONGTEXT;
 DECLARE w LONGTEXT; DECLARE actor LONGTEXT;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''), s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')),
  k=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.k')), a=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),'-',''),
  candidate=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.c')), profile=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.f')),
  runtime=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.t')), actor=SUBSTRING_INDEX(SESSION_USER(),'@',1);
 IF NOT (JSON_TYPE(CAST(candidate AS JSON))<=>'OBJECT') OR JSON_LENGTH(candidate)<>2
  OR NOT (JSON_TYPE(JSON_EXTRACT(candidate,'$.uri'))<=>'STRING') OR JSON_UNQUOTE(JSON_EXTRACT(candidate,'$.uri'))=''
  OR NOT COALESCE(REGEXP_LIKE(JSON_UNQUOTE(JSON_EXTRACT(candidate,'$.sha256')),'^[0-9a-f]{64}$','c'),FALSE)
  OR NOT COALESCE(REGEXP_LIKE(runtime,'^[0-9a-f]{64}$','c'),FALSE) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A report names a candidate URI/hash and runtime'; END IF;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION; CALL bookkeeping_require_ready();
 CALL bookkeeping_require(r,s,'worker'); CALL bookkeeping_authority(r,s,k,a,JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.p')));
 CALL bookkeeping_lock_work(r,s,k,w);
 IF NOT EXISTS(SELECT 1 FROM bookkeeping_pipeline_run WHERE run_id=r
  AND JSON_UNQUOTE(JSON_EXTRACT(submission,CONCAT('$.profiles.',JSON_QUOTE(s))))=profile) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Report differs from the frozen profile'; END IF;
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))='reported' THEN
  IF NOT (BINARY JSON_UNQUOTE(JSON_EXTRACT(w,'$.candidate'))<=>BINARY candidate)
   OR NOT (JSON_UNQUOTE(JSON_EXTRACT(w,'$.reporter'))<=>actor) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Conflicting candidate for this attempt'; END IF;
  COMMIT; LEAVE main;
 END IF;
 SELECT JSON_UNQUOTE(JSON_EXTRACT(runtimes,CONCAT('$.',JSON_QUOTE(profile)))) INTO pinned
  FROM bookkeeping_pipeline_run WHERE run_id=r;
 IF pinned IS NULL THEN
  UPDATE bookkeeping_pipeline_run SET runtimes=JSON_SET(runtimes,CONCAT('$.',JSON_QUOTE(profile)),runtime) WHERE run_id=r;
 ELSEIF BINARY pinned<>BINARY runtime THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Pinned worker runtime changed; start a new run';
 END IF;
 UPDATE bookkeeping_work_item SET state='reported',candidate=candidate,error=NULL,reporter=actor
  WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,s,k) AS BINARY),256));
 COMMIT;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_verify_claim
-- statement boundary
CREATE PROCEDURE bookkeeping_verify_claim(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
main: BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE k LONGTEXT; DECLARE a CHAR(32); DECLARE seconds BIGINT;
 DECLARE w LONGTEXT; DECLARE resources LONGTEXT; DECLARE i BIGINT DEFAULT 0; DECLARE resource_key LONGTEXT;
 DECLARE held_resource LONGTEXT; DECLARE held_run CHAR(32); DECLARE held_attempt CHAR(32);
 DECLARE held_token BIGINT; DECLARE expiry DATETIME(6); DECLARE result LONGTEXT DEFAULT '[]';
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''), s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')),
  k=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.k')), a=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),'-',''),
  seconds=CAST(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.d')) AS SIGNED);
 IF seconds IS NULL OR seconds<2 OR seconds>86400 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid lease duration'; END IF;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION; CALL bookkeeping_require_ready();
 CALL bookkeeping_require(r,s,'verifier'); CALL bookkeeping_lock_work(r,s,k,w); CALL bookkeeping_live(r);
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))<>'reported' OR NOT (JSON_UNQUOTE(JSON_EXTRACT(w,'$.attempt'))<=>a) THEN
  COMMIT; SELECT NULL; LEAVE main; END IF;
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.reporter'))=SUBSTRING_INDEX(SESSION_USER(),'@',1) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='This login may not verify its own report'; END IF;
 SET resources=JSON_UNQUOTE(JSON_EXTRACT(w,'$.resources'));
 WHILE i<JSON_LENGTH(resources) DO
  SET resource_key=JSON_UNQUOTE(JSON_EXTRACT(resources,CONCAT('$[',i,']'))), held_resource=NULL;
  SELECT resource,run_id,attempt,token,expires_at INTO held_resource,held_run,held_attempt,held_token,expiry
   FROM bookkeeping_lease WHERE _resource=UNHEX(SHA2(resource_key,256)) FOR UPDATE NOWAIT;
  IF held_resource IS NULL OR NOT (held_resource<=>resource_key) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Missing lease'; END IF;
  IF expiry>UTC_TIMESTAMP(6) AND (NOT (held_run<=>r) OR NOT (held_attempt<=>a)) THEN
   SIGNAL SQLSTATE 'HY000' SET MYSQL_ERRNO=3572,MESSAGE_TEXT='Lease contention'; END IF;
  IF expiry<=UTC_TIMESTAMP(6) OR NOT (held_attempt<=>a) OR NOT (held_run<=>r) THEN SET held_token=held_token+1; END IF;
  SET expiry=TIMESTAMPADD(SECOND,seconds,UTC_TIMESTAMP(6));
  UPDATE bookkeeping_lease SET token=held_token,run_id=r,attempt=a,expires_at=expiry,heartbeat_at=UTC_TIMESTAMP(6)
   WHERE _resource=UNHEX(SHA2(resource_key,256));
  SET result=JSON_ARRAY_APPEND(result,'$',JSON_OBJECT('resource',resource_key,'token',held_token,
   'run_id',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'attempt',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),
   'expires_at',DATE_FORMAT(expiry,'%Y-%m-%dT%H:%i:%s.%f+00:00'))), i=i+1;
 END WHILE;
 COMMIT; SELECT result;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_prepare_children
-- statement boundary
CREATE PROCEDURE bookkeeping_prepare_children(IN r CHAR(32), IN s LONGTEXT, IN w LONGTEXT, IN p_wire LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE children LONGTEXT; DECLARE child_step LONGTEXT; DECLARE parent_cursor LONGTEXT;
 DECLARE i BIGINT DEFAULT 0; DECLARE entry LONGTEXT; DECLARE entry_key LONGTEXT; DECLARE entry_ordinal BIGINT;
 DECLARE entry_resources LONGTEXT; DECLARE entry_unit LONGTEXT; DECLARE entry_cursor LONGTEXT;
 DECLARE prior_ordinal BIGINT; DECLARE prior_resources LONGTEXT; DECLARE prior_unit LONGTEXT; DECLARE prior_cursor LONGTEXT;
 DECLARE ordinal_base BIGINT; DECLARE sealed BOOLEAN; DECLARE seen LONGTEXT DEFAULT '[]';
 SET children=JSON_EXTRACT(p_wire,'$.children'), child_step=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.child_step')),
  parent_cursor=JSON_UNQUOTE(JSON_EXTRACT(w,'$.cursor')), ordinal_base=CAST(JSON_UNQUOTE(JSON_EXTRACT(parent_cursor,'$.ordinal_base')) AS SIGNED),
  sealed=JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))='verified';
 IF NOT (JSON_TYPE(children)<=>'ARRAY') OR JSON_LENGTH(children)>128 OR child_step IS NULL OR child_step='' OR child_step=s
  OR NOT (child_step<=>JSON_UNQUOTE(JSON_EXTRACT(parent_cursor,'$.generated_step'))) OR ordinal_base IS NULL OR ordinal_base<0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid bounded expansion'; END IF;
 IF sealed AND (JSON_TYPE(JSON_EXTRACT(w,'$.generated_count')) NOT IN('INTEGER','UNSIGNED INTEGER')
  OR CAST(JSON_UNQUOTE(JSON_EXTRACT(w,'$.generated_count')) AS SIGNED)<>JSON_LENGTH(children)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Expansion completion evidence changed'; END IF;
 WHILE i<JSON_LENGTH(children) DO
  SET entry=JSON_EXTRACT(children,CONCAT('$[',i,']')), entry_key=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.key')),
   entry_ordinal=CAST(JSON_UNQUOTE(JSON_EXTRACT(entry,'$.ordinal')) AS SIGNED),
   entry_resources=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.resources')), entry_unit=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.unit')),
   entry_cursor=JSON_UNQUOTE(JSON_EXTRACT(entry,'$.cursor'));
  IF NOT (JSON_TYPE(entry)<=>'OBJECT') OR NOT (JSON_UNQUOTE(JSON_EXTRACT(entry,'$.step'))<=>child_step)
   OR NOT (JSON_TYPE(JSON_EXTRACT(entry,'$.key'))<=>'STRING') OR entry_key=''
   OR JSON_CONTAINS(seen,JSON_QUOTE(entry_key)) OR entry_ordinal IS NULL OR entry_ordinal<>ordinal_base+i
   OR NOT (JSON_TYPE(CAST(entry_resources AS JSON))<=>'ARRAY') OR JSON_LENGTH(entry_resources)=0
   OR NOT (JSON_TYPE(CAST(entry_unit AS JSON))<=>'OBJECT') OR NOT COALESCE(JSON_VALID(entry_cursor),FALSE) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Malformed generated child'; END IF;
  IF NOT sealed THEN
   INSERT INTO bookkeeping_work_item(run_id,step,unit_key,ordinal,resources,unit,_cursor)
    VALUES(r,child_step,entry_key,entry_ordinal,entry_resources,entry_unit,entry_cursor);
  ELSE
   SET prior_ordinal=NULL;
   SELECT item.ordinal,item.resources,item.unit,item._cursor INTO prior_ordinal,prior_resources,prior_unit,prior_cursor
    FROM bookkeeping_work_item item WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,child_step,entry_key) AS BINARY),256))
    AND run_id=r AND step=child_step AND unit_key=entry_key;
   IF prior_ordinal IS NULL OR prior_ordinal<>entry_ordinal OR NOT (BINARY prior_resources<=>BINARY entry_resources)
    OR NOT (BINARY prior_unit<=>BINARY entry_unit) OR NOT (BINARY prior_cursor<=>BINARY entry_cursor) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Generated child changed'; END IF;
  END IF;
  SET seen=JSON_ARRAY_APPEND(seen,'$',entry_key), i=i+1;
 END WHILE;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_compare_checkpoint
-- statement boundary
CREATE PROCEDURE bookkeeping_compare_checkpoint(IN r CHAR(32), IN s LONGTEXT, IN w LONGTEXT, IN p_wire LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE resource_key LONGTEXT; DECLARE expected_revision BIGINT; DECLARE expected_position BIGINT;
 DECLARE cursor_body LONGTEXT; DECLARE held_revision BIGINT; DECLARE held_position BIGINT;
 DECLARE held_run CHAR(32); DECLARE held_receipt LONGTEXT; DECLARE held_resource LONGTEXT;
 SET resource_key=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.resource')),
  expected_revision=CAST(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.revision')) AS SIGNED),
  expected_position=CAST(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.position')) AS SIGNED), cursor_body=JSON_UNQUOTE(JSON_EXTRACT(w,'$.cursor'));
 IF resource_key IS NULL OR resource_key='' OR expected_revision IS NULL OR expected_revision<0
  OR expected_position IS NULL OR expected_position< -1
  OR NOT (resource_key<=>JSON_UNQUOTE(JSON_EXTRACT(cursor_body,'$.resource_checkpoint.resource')))
  OR NOT (expected_revision<=>CAST(JSON_UNQUOTE(JSON_EXTRACT(cursor_body,'$.resource_checkpoint.revision')) AS SIGNED))
  OR NOT (expected_position<=>CAST(JSON_UNQUOTE(JSON_EXTRACT(cursor_body,'$.resource_checkpoint.position')) AS SIGNED))
  OR NOT JSON_CONTAINS(JSON_UNQUOTE(JSON_EXTRACT(w,'$.resources')),JSON_QUOTE(resource_key)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid resource checkpoint comparison'; END IF;
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))<>'verified' THEN
  IF EXISTS(SELECT 1 FROM bookkeeping_work_item WHERE run_id=r AND step=s
   AND ordinal<CAST(JSON_UNQUOTE(JSON_EXTRACT(w,'$.ordinal')) AS SIGNED) AND state<>'verified') THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Resource checkpoint cannot skip a work hole'; END IF;
  INSERT INTO bookkeeping_checkpoint(run_id,scope,resource) VALUES(r,CONCAT('resource:',resource_key),resource_key)
   ON DUPLICATE KEY UPDATE run_id=run_id;
 END IF;
 SELECT resource,run_id,revision,ordinal,receipt INTO held_resource,held_run,held_revision,held_position,held_receipt
  FROM bookkeeping_checkpoint WHERE _resource=UNHEX(SHA2(resource_key,256)) FOR UPDATE NOWAIT;
 IF NOT (held_resource<=>resource_key) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unknown resource checkpoint'; END IF;
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))='verified' THEN
  IF NOT (held_run<=>r) OR NOT (BINARY held_receipt<=>BINARY JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.v')))
   OR held_position<>expected_position+1 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Resource checkpoint no longer names this completion'; END IF;
 ELSEIF held_revision<>expected_revision OR held_position<>expected_position THEN
  SIGNAL SQLSTATE '40001' SET MESSAGE_TEXT='Resource checkpoint comparison failed';
 END IF;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_finish
-- statement boundary
CREATE PROCEDURE bookkeeping_finish(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
main: BEGIN
 DECLARE r CHAR(32); DECLARE s LONGTEXT; DECLARE k LONGTEXT; DECLARE a CHAR(32); DECLARE e CHAR(32);
 DECLARE w LONGTEXT; DECLARE receipt LONGTEXT; DECLARE checks LONGTEXT; DECLARE candidate LONGTEXT;
 DECLARE runtime LONGTEXT; DECLARE profile LONGTEXT; DECLARE slot LONGTEXT; DECLARE pinned LONGTEXT;
 DECLARE check_names LONGTEXT; DECLARE i BIGINT DEFAULT 0; DECLARE check_name LONGTEXT; DECLARE deadline DATETIME(6);
 DECLARE last_ordinal BIGINT; DECLARE last_cursor LONGTEXT; DECLARE last_receipt LONGTEXT;
 DECLARE operation LONGTEXT; DECLARE frozen_cursor LONGTEXT; DECLARE child_step LONGTEXT;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET r=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-',''), s=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.s')),
  k=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.k')), a=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.a')),'-',''),
  e=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.e')),'-',''), receipt=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.v')),
  checks=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.c')), runtime=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.t'));
 IF NOT (JSON_TYPE(CAST(receipt AS JSON))<=>'OBJECT') OR JSON_LENGTH(receipt)<>3
  OR NOT (JSON_TYPE(JSON_EXTRACT(receipt,'$.uri'))<=>'STRING') OR JSON_UNQUOTE(JSON_EXTRACT(receipt,'$.uri'))=''
  OR NOT COALESCE(REGEXP_LIKE(JSON_UNQUOTE(JSON_EXTRACT(receipt,'$.sha256')),'^[0-9a-f]{64}$','c'),FALSE)
  OR NOT (JSON_TYPE(JSON_EXTRACT(receipt,'$.evidence'))<=>'OBJECT')
  OR NOT (JSON_TYPE(CAST(checks AS JSON))<=>'OBJECT') OR JSON_LENGTH(checks)=0
  OR NOT COALESCE(REGEXP_LIKE(runtime,'^[0-9a-f]{64}$','c'),FALSE) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unverified completion'; END IF;
 SET check_names=JSON_KEYS(checks);
 WHILE i<JSON_LENGTH(check_names) DO
  SET check_name=JSON_UNQUOTE(JSON_EXTRACT(check_names,CONCAT('$[',i,']')));
  IF NOT (JSON_EXTRACT(checks,CONCAT('$.',JSON_QUOTE(check_name)))<=>CAST('true' AS JSON)) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unverified completion'; END IF;
  SET i=i+1;
 END WHILE;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION; CALL bookkeeping_require_ready();
 CALL bookkeeping_require(r,s,'verifier'); CALL bookkeeping_lock_work(r,s,k,w);
 SET operation=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.operation')), frozen_cursor=JSON_UNQUOTE(JSON_EXTRACT(w,'$.cursor'));
 IF JSON_CONTAINS_PATH(frozen_cursor,'one','$.generated_step') THEN
  IF NOT (operation<=>'finish_expand') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Expansion must seal its generated children'; END IF;
 ELSEIF JSON_CONTAINS_PATH(frozen_cursor,'one','$.resource_checkpoint') THEN
  IF NOT (operation<=>'finish_resource') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completion must advance its resource checkpoint'; END IF;
 ELSEIF NOT (operation<=>'finish') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completion differs from its frozen cursor'; END IF;
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))<>'verified' THEN
  CALL bookkeeping_authority(r,s,k,a,JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.p')));
 END IF;
 IF operation='finish_expand' THEN CALL bookkeeping_prepare_children(r,s,w,p_wire); END IF;
 IF operation='finish_resource' THEN CALL bookkeeping_compare_checkpoint(r,s,w,p_wire); END IF;
 SELECT JSON_UNQUOTE(JSON_EXTRACT(submission,CONCAT('$.profiles.',JSON_QUOTE(s)))) INTO profile
  FROM bookkeeping_pipeline_run WHERE run_id=r;
 SET slot=CONCAT('verify:',profile);
 SELECT JSON_UNQUOTE(JSON_EXTRACT(runtimes,CONCAT('$.',JSON_QUOTE(slot)))) INTO pinned FROM bookkeeping_pipeline_run WHERE run_id=r;
 IF pinned IS NULL THEN
  UPDATE bookkeeping_pipeline_run SET runtimes=JSON_SET(runtimes,CONCAT('$.',JSON_QUOTE(slot)),runtime) WHERE run_id=r;
 ELSEIF BINARY pinned<>BINARY runtime THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Pinned verifier runtime changed; start a new run'; END IF;
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))='verified' THEN
  IF NOT (BINARY JSON_UNQUOTE(JSON_EXTRACT(w,'$.receipt'))<=>BINARY receipt)
   OR NOT (BINARY JSON_UNQUOTE(JSON_EXTRACT(w,'$.checks'))<=>BINARY checks) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completion evidence changed'; END IF;
  COMMIT; LEAVE main;
 END IF;
 SET candidate=JSON_UNQUOTE(JSON_EXTRACT(w,'$.candidate'));
 IF JSON_UNQUOTE(JSON_EXTRACT(w,'$.state'))<>'reported'
  OR JSON_UNQUOTE(JSON_EXTRACT(w,'$.reporter'))=SUBSTRING_INDEX(SESSION_USER(),'@',1)
  OR NOT (JSON_UNQUOTE(JSON_EXTRACT(candidate,'$.uri'))<=>JSON_UNQUOTE(JSON_EXTRACT(receipt,'$.uri')))
  OR NOT (JSON_UNQUOTE(JSON_EXTRACT(candidate,'$.sha256'))<=>JSON_UNQUOTE(JSON_EXTRACT(receipt,'$.sha256'))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completion needs the reported candidate and a different verifier'; END IF;
 SELECT MIN(expires_at) INTO deadline FROM bookkeeping_lease WHERE run_id=r AND attempt=a;
 UPDATE bookkeeping_work_item SET state='verified',receipt=receipt,checks=checks,error=NULL,
  authority_until=deadline,verifier=SUBSTRING_INDEX(SESSION_USER(),'@',1)
  WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,s,k) AS BINARY),256));
 INSERT INTO bookkeeping_journal_outbox(event_id,run_id,step,unit_key,payload,created_at)
  VALUES(e,r,s,k,JSON_OBJECT('version',1,'event_id',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.e')),
   'run_id',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'step',s,'unit_key',k,'receipt',CAST(receipt AS JSON),'checks',CAST(checks AS JSON)),UTC_TIMESTAMP(6));
 UPDATE bookkeeping_lease SET expires_at=UTC_TIMESTAMP(6) WHERE run_id=r AND attempt=a;
 SELECT COALESCE(MIN(CASE WHEN state<>'verified' THEN ordinal END)-1,MAX(ordinal)) INTO last_ordinal
  FROM bookkeeping_work_item WHERE run_id=r AND step=s;
 SELECT item._cursor,item.receipt INTO last_cursor,last_receipt FROM bookkeeping_work_item item WHERE run_id=r AND step=s AND ordinal=last_ordinal;
 UPDATE bookkeeping_checkpoint SET ordinal=last_ordinal,`cursor`=last_cursor,receipt=last_receipt
  WHERE run_id=r AND scope=s AND ordinal<last_ordinal;
 IF operation='finish_expand' THEN
  SET child_step=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.child_step'));
  UPDATE bookkeeping_work_item SET generated_count=JSON_LENGTH(JSON_EXTRACT(p_wire,'$.children'))
   WHERE _identity=UNHEX(SHA2(CAST(JSON_ARRAY(r,s,k) AS BINARY),256));
  UPDATE bookkeeping_pipeline_run SET expected_count=expected_count+JSON_LENGTH(JSON_EXTRACT(p_wire,'$.children')) WHERE run_id=r;
  INSERT INTO bookkeeping_checkpoint(run_id,scope) VALUES(r,child_step) ON DUPLICATE KEY UPDATE run_id=run_id;
 ELSEIF operation='finish_resource' THEN
  UPDATE bookkeeping_checkpoint SET run_id=r,ordinal=CAST(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.position')) AS SIGNED)+1,
   revision=revision+1,`cursor`=frozen_cursor,receipt=receipt
   WHERE _resource=UNHEX(SHA2(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.resource')),256));
 END IF;
 IF deadline IS NULL OR deadline<=UTC_TIMESTAMP(6) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completion authority expired before commit'; END IF;
 COMMIT;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_delivery
-- statement boundary
CREATE PROCEDURE bookkeeping_delivery(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 DECLARE e CHAR(32); DECLARE message LONGTEXT;
 CALL bookkeeping_require_ready();
 SET e=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.e')),'-',''), message=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.m'));
 IF JSON_EXTRACT(p_wire,'$.m') IS NULL OR JSON_TYPE(JSON_EXTRACT(p_wire,'$.m'))='NULL' THEN SET message=NULL; END IF;
 UPDATE bookkeeping_journal_outbox SET attempts=attempts+1,error=message,
  delivered_at=IF(message IS NULL,UTC_TIMESTAMP(6),NULL) WHERE event_id=e AND delivered_at IS NULL;
END
-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_block_run
-- statement boundary
CREATE PROCEDURE bookkeeping_block_run(IN p_wire LONGTEXT)
SQL SECURITY DEFINER
BEGIN
 CALL bookkeeping_require_ready();
 UPDATE bookkeeping_pipeline_run SET state='blocked',completed_at=NULL,
  checks=JSON_OBJECT('blocked',JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.m')))
  WHERE run_id=REPLACE(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$.r')),'-','');
END

-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_record_run_checks

-- statement boundary
CREATE PROCEDURE bookkeeping_record_run_checks(IN p_wire LONGTEXT CHARACTER SET utf8mb4)
                SQL SECURITY DEFINER BEGIN DECLARE v_run_id CHAR(32);
DECLARE v_raw_run LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_state LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_checks LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_summary LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_compacted BIGINT;
DECLARE v_expected BIGINT;
DECLARE v_actual BIGINT;
DECLARE v_verified BIGINT;
DECLARE v_pending BIGINT;
DECLARE v_unsealed BIGINT;
DECLARE v_observed_expected BIGINT;
DECLARE v_observed_actual BIGINT;
DECLARE v_observed_verified BIGINT;
DECLARE v_observed_pending BIGINT;
DECLARE v_observed_unsealed BIGINT;
DECLARE v_raw_expected LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_raw_actual LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_raw_verified LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_raw_pending LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_raw_unsealed LONGTEXT CHARACTER SET utf8mb4;
                DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
                SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
                START TRANSACTION; CALL bookkeeping_require_ready(); SET v_raw_expected=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."expected"'));
IF (v_raw_expected IS NULL OR NOT (v_raw_expected REGEXP '^[0-9]+$')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_counter'; END IF;
SET v_expected=CAST(v_raw_expected AS SIGNED);
SET v_raw_actual=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."actual"'));
IF (v_raw_actual IS NULL OR NOT (v_raw_actual REGEXP '^[0-9]+$')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_counter'; END IF;
SET v_actual=CAST(v_raw_actual AS SIGNED);
SET v_raw_verified=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."verified"'));
IF (v_raw_verified IS NULL OR NOT (v_raw_verified REGEXP '^[0-9]+$')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_counter'; END IF;
SET v_verified=CAST(v_raw_verified AS SIGNED);
SET v_raw_pending=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."pending"'));
IF (v_raw_pending IS NULL OR NOT (v_raw_pending REGEXP '^[0-9]+$')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_counter'; END IF;
SET v_pending=CAST(v_raw_pending AS SIGNED);
SET v_raw_unsealed=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."unsealed"'));
IF (v_raw_unsealed IS NULL OR NOT (v_raw_unsealed REGEXP '^[0-9]+$')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_counter'; END IF;
SET v_unsealed=CAST(v_raw_unsealed AS SIGNED);
SET v_raw_run=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."run_id"'));
IF v_raw_run IS NULL OR CHAR_LENGTH(v_raw_run)<>36 OR NOT IS_UUID(v_raw_run) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_run'; END IF;
SET v_run_id=REPLACE(v_raw_run,'-','');
SET v_state=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."state"'));
SET v_checks=CONVERT(UNHEX(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."checks"'))) USING utf8mb4);
SET v_summary=CONVERT(UNHEX(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."summary"'))) USING utf8mb4);
IF v_state IS NULL OR NOT (CAST(v_state AS BINARY)=CAST('complete' AS BINARY) OR CAST(v_state AS BINARY)=CAST('waiting' AS BINARY)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_state'; END IF;
IF v_checks IS NULL OR NOT ((CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"manifest.hash":false,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"manifest.hash":false,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"manifest.hash":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"manifest.hash":true,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":false,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":false,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":false,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":false,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true,"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"work.accounting":false}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{}' AS BINARY))) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_checks'; END IF;
SELECT p.expected_count,CASE WHEN p.compacted_at IS NULL THEN 0 ELSE 1 END INTO v_observed_expected,v_compacted FROM bookkeeping_pipeline_run p WHERE p.run_id=v_run_id FOR UPDATE NOWAIT;
IF v_observed_expected IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='unknown_control_run'; END IF;
IF v_compacted<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='compacted_control_run'; END IF;
SELECT COUNT(*),COALESCE(SUM(CASE WHEN w.state='verified' THEN CAST(1 AS SIGNED) ELSE CAST(0 AS SIGNED) END),0) INTO v_observed_actual,v_observed_verified FROM bookkeeping_work_item w WHERE w.run_id=v_run_id;
SELECT COUNT(*) INTO v_observed_unsealed FROM bookkeeping_work_item w WHERE w.run_id=v_run_id AND w.generated_count IS NULL AND JSON_CONTAINS_PATH(w.unit,'one','$.cursor.generated_step')=1;
SELECT COUNT(*) INTO v_observed_pending FROM bookkeeping_journal_outbox j WHERE j.run_id=v_run_id AND j.delivered_at IS NULL;
IF v_expected<>v_observed_expected OR v_actual<>v_observed_actual OR v_verified<>v_observed_verified OR v_pending<>v_observed_pending OR v_unsealed<>v_observed_unsealed THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='control_observations_changed'; END IF;
IF CAST(v_state AS BINARY)=CAST('complete' AS BINARY) AND (v_actual<>v_expected OR v_verified<>v_actual OR v_pending<>0 OR v_unsealed<>0 OR NOT ((CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"work.accounting":true}' AS BINARY)))) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='unverified_control_completion'; END IF;
IF CAST(v_state AS BINARY)=CAST('waiting' AS BINARY) AND NOT (v_actual<>v_expected OR v_verified<>v_actual OR v_pending<>0 OR v_unsealed<>0 OR NOT ((CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"journal.delivered":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true,"work.accounting":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"manifest.hash":true}' AS BINARY)) OR (CAST(v_checks AS BINARY)=CAST('{"work.accounting":true}' AS BINARY)))) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_state'; END IF;
IF v_summary IS NULL OR NOT (CAST(v_summary AS BINARY)=CAST(CONCAT('{"expected":',CAST(v_expected AS CHAR),',"pending_deliveries":',CAST(v_pending AS CHAR),',"verified":',CAST(v_verified AS CHAR),'}') AS BINARY)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_summary'; END IF;
UPDATE bookkeeping_pipeline_run p SET checks=v_checks,summary=v_summary,state=v_state,completed_at=CASE WHEN CAST(v_state AS BINARY)=CAST('complete' AS BINARY) THEN COALESCE(p.completed_at,UTC_TIMESTAMP(6)) ELSE NULL END WHERE p.run_id=v_run_id AND NOT (p.state=v_state AND CAST(p.checks AS BINARY)=CAST(v_checks AS BINARY) AND CAST(p.summary AS BINARY)=CAST(v_summary AS BINARY)); COMMIT; END

-- statement boundary
DROP PROCEDURE IF EXISTS bookkeeping_resume_run_prepared

-- statement boundary
CREATE PROCEDURE bookkeeping_resume_run_prepared(IN p_wire LONGTEXT CHARACTER SET utf8mb4)
                SQL SECURITY DEFINER BEGIN DECLARE v_raw_run LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_run_id CHAR(32);
DECLARE v_state LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_expected_state LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_checks LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_observed_state LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_observed_checks LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_observed_completed LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_expected_checks LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_expected_completion LONGTEXT CHARACTER SET utf8mb4;
DECLARE v_compacted BIGINT;
                DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
                SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
                START TRANSACTION; CALL bookkeeping_require_ready(); SET v_raw_run=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."run_id"'));
IF v_raw_run IS NULL OR CHAR_LENGTH(v_raw_run)<>36 OR NOT IS_UUID(v_raw_run) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_run'; END IF;
SET v_run_id=REPLACE(v_raw_run,'-','');
SET v_state=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."state"'));
SET v_expected_state=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."expected_state"'));
SET v_expected_checks=CONVERT(UNHEX(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."expected_checks"'))) USING utf8mb4);
SET v_expected_completion=JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."expected_completion"'));
SET v_checks=CONVERT(UNHEX(JSON_UNQUOTE(JSON_EXTRACT(p_wire,'$."checks"'))) USING utf8mb4);
IF v_state IS NULL OR NOT (CAST(v_state AS BINARY)=CAST('running' AS BINARY)) OR v_checks IS NULL OR NOT (CAST(v_checks AS BINARY)=CAST('{}' AS BINARY)) OR v_expected_checks IS NULL OR v_expected_completion IS NULL OR v_expected_state IS NULL OR NOT ((CAST(v_expected_state AS BINARY)=CAST('running' AS BINARY)) OR (CAST(v_expected_state AS BINARY)=CAST('waiting' AS BINARY)) OR (CAST(v_expected_state AS BINARY)=CAST('blocked' AS BINARY)) OR (CAST(v_expected_state AS BINARY)=CAST('complete' AS BINARY))) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_control_resume'; END IF;
SELECT p.state,CAST(p.checks AS CHAR),COALESCE(DATE_FORMAT(p.completed_at,'%Y-%m-%d %H:%i:%s.%f'),''),CASE WHEN p.compacted_at IS NULL THEN 0 ELSE 1 END INTO v_observed_state,v_observed_checks,v_observed_completed,v_compacted FROM bookkeeping_pipeline_run p WHERE p.run_id=v_run_id FOR UPDATE NOWAIT;
IF v_observed_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='unknown_control_run'; END IF;
IF v_compacted<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='compacted_control_run'; END IF;
IF NOT (CAST(v_observed_state AS BINARY)=CAST(v_expected_state AS BINARY) AND CAST(v_observed_checks AS BINARY)=CAST(v_expected_checks AS BINARY) AND CAST(v_observed_completed AS BINARY)=CAST(v_expected_completion AS BINARY)) AND NOT (CAST(v_observed_state AS BINARY)=CAST(v_state AS BINARY) AND CAST(v_observed_checks AS BINARY)=CAST(v_checks AS BINARY) AND v_observed_completed='') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='control_observations_changed'; END IF;
UPDATE bookkeeping_pipeline_run p SET state=v_state,checks=v_checks,completed_at=NULL WHERE p.run_id=v_run_id AND NOT (p.state=v_state AND CAST(p.checks AS BINARY)=CAST(v_checks AS BINARY) AND p.completed_at IS NULL); COMMIT; END
