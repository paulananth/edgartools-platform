"""Checksummed owner migrations for journal storage on selected engines."""
from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import inspect, text
from edgar_warehouse.control_contract import Blocked, canonical
from .storage_sql import statements as migration_statements


def _execute_sql(conn, sql):
    return conn.execute(text(sql))


def _restricted_mssql(conn, runtime_role):
    """Inspect effective rights before installing any owner-executed capability."""
    if conn.scalar(text("""SELECT COUNT(*) FROM sys.server_role_members m
        JOIN sys.server_principals p ON p.principal_id=m.member_principal_id
        WHERE p.name=:r"""), {"r": runtime_role}):
        raise Blocked("Runtime inherits server role privileges")
    schema_exists = conn.scalar(text("SELECT SCHEMA_ID('journal')")) is not None
    # Inspect the login token as well as its database user: database-only
    # impersonation masks direct server grants. Inspection requires owner
    # permission to impersonate this login; failure never falls back to guesses.
    conn.exec_driver_sql("EXECUTE AS LOGIN = '" + runtime_role.replace("'", "''") + "'")
    try:
        unsafe = conn.scalar(text("""SELECT COUNT(*) FROM sys.fn_my_permissions(NULL,'SERVER')
            WHERE permission_name<>'CONNECT SQL' AND permission_name NOT LIKE 'VIEW %'"""))
        unsafe += conn.scalar(text("""SELECT COUNT(*) FROM sys.fn_my_permissions(NULL,'DATABASE')
            WHERE permission_name NOT IN ('CONNECT','SELECT','EXECUTE','SHOWPLAN')
            AND permission_name NOT LIKE 'VIEW %'"""))
        unsafe += conn.scalar(text("""SELECT COUNT(*) FROM sys.database_principals p
            WHERE p.principal_id<>USER_ID() AND (
              (p.type IN ('S','U','G','E','X') AND
               HAS_PERMS_BY_NAME(p.name,'USER','IMPERSONATE')=1) OR
              (p.type='R' AND (HAS_PERMS_BY_NAME(p.name,'ROLE','ALTER')=1 OR
                              HAS_PERMS_BY_NAME(p.name,'ROLE','CONTROL')=1)))"""))
        if schema_exists:
            unsafe += conn.scalar(text("""SELECT COUNT(*) FROM sys.fn_my_permissions('journal','SCHEMA')
                WHERE permission_name NOT IN ('SELECT','EXECUTE')
                AND permission_name NOT LIKE 'VIEW %'"""))
            unsafe += conn.scalar(text("""SELECT COUNT(*) FROM sys.objects o
                WHERE o.schema_id=SCHEMA_ID('journal') AND (
                  HAS_PERMS_BY_NAME('journal.'+QUOTENAME(o.name),'OBJECT','ALTER')=1 OR
                  HAS_PERMS_BY_NAME('journal.'+QUOTENAME(o.name),'OBJECT','CONTROL')=1 OR
                  HAS_PERMS_BY_NAME('journal.'+QUOTENAME(o.name),'OBJECT','TAKE OWNERSHIP')=1)"""))
        if unsafe:
            raise Blocked("Runtime can administer Journal capabilities or privileges")
    finally:
        conn.exec_driver_sql("REVERT")


def migrate_storage(engine, *, runtime_role, existing_only=False, database_name="change_journal"):
    kind=engine.dialect.name
    if kind not in {"mysql","mssql"}:
        raise Blocked("Journal storage has not been qualified for this database engine")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}",runtime_role):
        raise Blocked("A valid restricted runtime principal is required")
    if engine.url.database!=database_name:
        raise Blocked("Journal migration requires the selected isolated journal database")
    statements=migration_statements(kind)
    checksum=hashlib.sha256("\n".join(statements).encode()).hexdigest()
    table="journal_migrations" if kind=="mysql" else "journal.migrations"
    quote=engine.dialect.identifier_preparer.quote
    role=f"'{runtime_role}'@'%'" if kind=="mysql" else quote(runtime_role)
    # DDL may commit implicitly in MySQL. A session lock and persistent incomplete
    # marker protect upgrades; interrupted installations re-enter the same statements.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        current=conn.scalar(text("SELECT DATABASE()" if kind=="mysql" else "SELECT DB_NAME()"))
        if current!=database_name:
            raise Blocked("Journal migration requires the selected isolated journal database")
        if kind=="mysql":
            version=conn.scalar(text("SELECT VERSION()"))
            if not version.startswith("8."):
                raise Blocked("Journal requires the qualified MySQL 8 capabilities")
            if conn.scalar(text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:r"),{"r":runtime_role}):
                raise Blocked("Separate migration owner and restricted runtime are required")
            if not conn.scalar(text("SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'"),{"r":runtime_role}):
                raise Blocked("An existing restricted runtime is required")
            grants=[row[0] for row in _execute_sql(conn, f"SHOW GRANTS FOR {role}")]
            if any((" ON *.* " in row and not row.startswith("GRANT USAGE ")) or "WITH GRANT OPTION" in row or " ON " not in row for row in grants):
                raise Blocked("Runtime inherits administrative or role privileges")
            lock="journal_"+hashlib.sha256(database_name.encode()).hexdigest()[:32]
            if conn.scalar(text("SELECT GET_LOCK(:n,30)"),{"n":lock})!=1:
                raise Blocked("Journal migration lock unavailable")
            release=("SELECT RELEASE_LOCK(:n)",{"n":lock})
            exists=inspect(conn).has_table(table)
            tables=set(inspect(conn).get_table_names())
            allowed={"journal_migrations","journal_event"}
            ddl="CREATE TABLE journal_migrations(id SMALLINT PRIMARY KEY,checksum CHAR(64) NOT NULL,complete SMALLINT NOT NULL) ENGINE=InnoDB"
        else:
            if int(conn.scalar(text("SELECT SERVERPROPERTY('ProductMajorVersion')")))<16:
                raise Blocked("Journal requires the qualified SQL Server 2022 capabilities")
            if conn.scalar(text("SELECT SUSER_SNAME()"))==runtime_role or not conn.scalar(text("SELECT USER_ID(:r)"),{"r":runtime_role}):
                raise Blocked("Separate owner and existing restricted runtime are required")
            if conn.scalar(text("SELECT IS_SRVROLEMEMBER('sysadmin',:r)"),{"r":runtime_role}) or conn.scalar(text("SELECT IS_ROLEMEMBER('db_owner',:r)"),{"r":runtime_role}):
                raise Blocked("Runtime inherits administrative privileges")
            _restricted_mssql(conn, runtime_role)
            code=conn.scalar(text("DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource='journal_migration',@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=30000; SELECT @r"))
            if code is None or code<0:
                raise Blocked("Journal migration lock unavailable")
            release=("EXEC sys.sp_releaseapplock @Resource='journal_migration',@LockOwner='Session'",{})
            exists=inspect(conn).has_table("migrations",schema="journal")
            tables={(row[0],row[1]) for row in conn.execute(text("SELECT TABLE_SCHEMA,TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'"))}
            allowed={("journal","migrations"),("journal","event")}
            ddl="CREATE TABLE journal.migrations(id SMALLINT PRIMARY KEY,checksum CHAR(64) NOT NULL,complete SMALLINT NOT NULL)"
        try:
            if existing_only and not exists:
                raise Blocked("Change Journal is not initialized; run change-journal init first")
            if tables-allowed or (not exists and tables):
                raise Blocked("Refusing an untracked or non-journal database")
            if not exists:
                if kind=="mssql":_execute_sql(conn, "IF SCHEMA_ID('journal') IS NULL EXEC('CREATE SCHEMA journal')")
                _execute_sql(conn, ddl)
                conn.execute(text(f"INSERT INTO {table}(id,checksum,complete) VALUES(1,:h,0)"),{"h":checksum})
            prior=conn.execute(text(f"SELECT checksum,complete FROM {table} WHERE id=1")).first()
            if not prior or prior[0]!=checksum:
                raise Blocked("Installed journal migration checksum differs")
            _execute_sql(conn, f"UPDATE {table} SET complete=0 WHERE id=1")
            for statement in statements:
                _execute_sql(conn, statement)
            if kind=="mysql":
                db=quote(database_name)
                # Revoke only this store's grants. Shared/global inherited grants are
                # checked, never silently removed from another application.
                for obj,privilege in (("journal_event","ALL PRIVILEGES"),("journal_migrations","ALL PRIVILEGES")):
                    grants=[row[0] for row in _execute_sql(conn, f"SHOW GRANTS FOR {role}")]
                    if any(f" ON {db}.{quote(obj)} " in row for row in grants):
                        _execute_sql(conn, f"REVOKE {privilege} ON {db}.{quote(obj)} FROM {role}")
                _execute_sql(conn, f"GRANT SELECT ON {db}.journal_records TO {role}")
                _execute_sql(conn, f"GRANT SELECT ON {db}.journal_readiness TO {role}")
                _execute_sql(conn, f"GRANT EXECUTE ON PROCEDURE {db}.journal_record_event TO {role}")
                grants=[row[0] for row in _execute_sql(conn, f"SHOW GRANTS FOR {role}")]
                if any(f" ON {db}.* " in row for row in grants):
                    raise Blocked("Runtime inherits direct journal storage privileges")
            else:
                _execute_sql(conn, f"DENY SELECT,INSERT,UPDATE,DELETE,ALTER,CONTROL ON OBJECT::journal.event TO {role}")
                _execute_sql(conn, f"DENY SELECT,INSERT,UPDATE,DELETE,ALTER,CONTROL ON OBJECT::journal.migrations TO {role}")
                _execute_sql(conn, f"GRANT SELECT ON OBJECT::journal.event_records TO {role}")
                _execute_sql(conn, f"GRANT SELECT ON OBJECT::journal.readiness TO {role}")
                _execute_sql(conn, f"GRANT EXECUTE ON OBJECT::journal.record_event TO {role}")
            _execute_sql(conn, f"UPDATE {table} SET complete=1 WHERE id=1")
        finally:
            conn.execute(text(release[0]),release[1])
    return {"001_native_storage":checksum}
