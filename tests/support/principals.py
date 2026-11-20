"""Test principals: a separate login per isolated test store, on PostgreSQL, MySQL or SQL Server."""
import re

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


class AdapterError(ValueError):
    pass


def provision_runtime(
    engine, *, runtime_role: str, password: str, runtime_host="%"
) -> dict:
    """Provision a separate local-test principal without changing an existing password."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", runtime_role) or not password:
        raise AdapterError(
            "A valid runtime principal and private password are required"
        )
    if not re.fullmatch(r"[A-Za-z0-9_.%:-]+", runtime_host):
        raise AdapterError("A valid runtime host is required")
    name = engine.dialect.name
    if name not in {"postgresql", "mysql", "mssql"}:
        raise AdapterError("Unsupported selected database engine")
    quote = engine.dialect.identifier_preparer.quote
    role = quote(runtime_role)
    created = False
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if name == "postgresql":
            if conn.scalar(text("SELECT current_user=:r"), {"r": runtime_role}):
                raise AdapterError("Migration owner and runtime principal must differ")
            if not conn.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"),
                {"r": runtime_role},
            ):
                conn.execute(
                    text(
                        f"CREATE ROLE {role} LOGIN PASSWORD :password NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION"
                    ),
                    {"password": password},
                )
                created = True
        elif name == "mysql":
            if len(runtime_role) > 32 or conn.scalar(
                text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:r"),
                {"r": runtime_role},
            ):
                raise AdapterError(
                    "A separate MySQL runtime account of at most 32 characters is required"
                )
            if not conn.scalar(
                text("SELECT COUNT(*) FROM mysql.user WHERE User=:u AND Host=:h"),
                {"u": runtime_role, "h": runtime_host},
            ):
                conn.execute(
                    text("CREATE USER :user@:host IDENTIFIED BY :password"),
                    {"user": runtime_role, "host": runtime_host, "password": password},
                )
                created = True
        else:
            if conn.scalar(
                text("SELECT CASE WHEN SUSER_SNAME()=:r THEN 1 ELSE 0 END"),
                {"r": runtime_role},
            ):
                raise AdapterError("Migration owner and runtime principal must differ")
            if not conn.scalar(
                text("SELECT COUNT(*) FROM sys.sql_logins WHERE name=:r"),
                {"r": runtime_role},
            ):
                conn.execute(
                    text(
                        f"CREATE LOGIN {role} WITH PASSWORD=:password,CHECK_POLICY=ON"
                    ),
                    {"password": password},
                )
                created = True
            if not conn.scalar(text("SELECT USER_ID(:r)"), {"r": runtime_role}):
                conn.execute(text(f"CREATE USER {role} FOR LOGIN {role}"))
    url = engine.url.set(username=runtime_role, password=password)
    if name == "mysql":
        url = url.set(database="")  # Authenticate before schema-specific grants exist.
    candidate = create_engine(url, hide_parameters=True)
    try:
        with candidate.connect() as conn:
            if conn.scalar(text("SELECT 1")) != 1:
                raise AdapterError("Runtime credential validation failed")
    except DBAPIError:
        raise AdapterError(
            "Runtime credential validation failed; existing passwords were not changed"
        ) from None
    finally:
        candidate.dispose()
    return {"created": created, "engine": name}


