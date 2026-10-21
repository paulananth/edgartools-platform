IF SCHEMA_ID('journal') IS NULL EXEC('CREATE SCHEMA journal')
-- journal migration statement boundary --
IF OBJECT_ID('journal.event','U') IS NULL CREATE TABLE journal.event (
          id BIGINT IDENTITY PRIMARY KEY,
          producer NVARCHAR(256) COLLATE Latin1_General_100_BIN2 NOT NULL,
          event_key NVARCHAR(MAX) COLLATE Latin1_General_100_BIN2 NOT NULL, key_hash BINARY(32) NOT NULL,
          run_id CHAR(36) COLLATE Latin1_General_100_BIN2 NOT NULL,
          source VARCHAR(256) COLLATE Latin1_General_100_BIN2 NOT NULL,
          feed VARCHAR(256) COLLATE Latin1_General_100_BIN2 NOT NULL,
          event_type VARCHAR(256) COLLATE Latin1_General_100_BIN2 NOT NULL, occurred_at VARCHAR(100) NOT NULL,
          recorded_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
          canonical_body VARBINARY(MAX) NOT NULL,
          canonical_hash CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
          CONSTRAINT event_key_unique UNIQUE(producer,key_hash),
          CHECK(canonical_hash=LOWER(CONVERT(VARCHAR(64),HASHBYTES('SHA2_256',canonical_body),2)))
        )
-- journal migration statement boundary --
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('journal.event') AND name='event_scope') CREATE INDEX event_scope ON journal.event(source,feed,id)
-- journal migration statement boundary --
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('journal.event') AND name='event_run') CREATE INDEX event_run ON journal.event(run_id,id)
-- journal migration statement boundary --
CREATE OR ALTER VIEW journal.event_records AS SELECT e.* FROM journal.event e
          JOIN journal.migrations m ON m.id=1 AND m.complete=1
-- journal migration statement boundary --
CREATE OR ALTER VIEW journal.readiness AS SELECT complete FROM journal.migrations WHERE id=1
-- journal migration statement boundary --
CREATE OR ALTER TRIGGER journal.protect_history ON journal.event AFTER UPDATE,DELETE AS
          THROW 51000,'Journal history is immutable',1
-- journal migration statement boundary --
CREATE OR ALTER PROCEDURE journal.record_event @body NVARCHAR(MAX),@content_hash CHAR(64)
        WITH EXECUTE AS OWNER AS
        BEGIN
          SET NOCOUNT ON; SET XACT_ABORT ON;
          BEGIN TRY
            BEGIN TRANSACTION;
            IF NOT EXISTS(SELECT 1 FROM journal.migrations WITH(HOLDLOCK) WHERE id=1 AND complete=1)
              THROW 51000,'Journal migration incomplete',1;
            DECLARE @bytes VARBINARY(MAX)=CONVERT(VARBINARY(MAX),CONVERT(VARCHAR(MAX),@body COLLATE Latin1_General_100_BIN2_UTF8));
            IF @content_hash IS NULL OR DATALENGTH(@bytes)>1048576 OR ISJSON(@body)<>1
              OR LOWER(CONVERT(VARCHAR(64),HASHBYTES('SHA2_256',@bytes),2))<>@content_hash
              OR JSON_VALUE(@body,'$.version')<>'1' OR (SELECT count(*) FROM OPENJSON(@body))<>10
              THROW 51000,'Invalid prepared journal event',1;
            DECLARE @producer NVARCHAR(256)=JSON_VALUE(@body,'$.producer');
            DECLARE @key NVARCHAR(MAX)=(SELECT event_key FROM OPENJSON(@body) WITH(event_key NVARCHAR(MAX) '$.event_key'));
            DECLARE @hash BINARY(32)=HASHBYTES('SHA2_256',CONVERT(VARCHAR(MAX),@key COLLATE Latin1_General_100_BIN2_UTF8));
            IF @key IS NULL OR DATALENGTH(@key) NOT BETWEEN 2 AND 8192 THROW 51000,'Invalid prepared journal event',1;
            DECLARE @prior VARBINARY(MAX),@prior_key NVARCHAR(MAX),@prior_hash CHAR(64);
            SELECT @prior=CONVERT(VARBINARY(MAX),canonical_body),@prior_key=event_key,@prior_hash=canonical_hash FROM journal.event WITH(UPDLOCK,HOLDLOCK)
              WHERE producer=@producer AND key_hash=@hash;
            IF @prior IS NULL
              INSERT INTO journal.event(producer,event_key,key_hash,run_id,source,feed,event_type,occurred_at,canonical_body,canonical_hash)
                VALUES(@producer,@key,@hash,JSON_VALUE(@body,'$.run_id'),JSON_VALUE(@body,'$.source'),JSON_VALUE(@body,'$.feed'),
                  JSON_VALUE(@body,'$.event_type'),JSON_VALUE(@body,'$.occurred_at'),@bytes,@content_hash);
            ELSE IF CONVERT(VARBINARY(MAX),@prior)<>CONVERT(VARBINARY(MAX),@bytes)
              OR CONVERT(VARBINARY(MAX),@prior_key)<>CONVERT(VARBINARY(MAX),@key) OR @prior_hash<>@content_hash
              THROW 51000,'journal_content_conflict',1;
            COMMIT;
          END TRY
          BEGIN CATCH
            IF @@TRANCOUNT>0 ROLLBACK;
            THROW;
          END CATCH;
        END