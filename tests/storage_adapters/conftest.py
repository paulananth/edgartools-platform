"""Real, isolated databases on an explicitly selected test server."""

from __future__ import annotations

import importlib
import os
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/mdm-engineering/scripts"
sys.path.insert(0, str(SCRIPTS))
api = importlib.import_module("database_adapter")


@dataclass(frozen=True)
class ConnectionTarget:
    engine: str
    url: str = field(repr=False)


@pytest.fixture(scope="session")
def server_connection():
    selected = os.environ.get("SKILL_ADAPTER_TEST_ENGINE")
    url = os.environ.get("SKILL_ADAPTER_TEST_URL")
    if selected not in {"postgresql", "mysql", "mssql"}:
        pytest.fail("Select SKILL_ADAPTER_TEST_ENGINE; prerequisites never skip")
    if url:
        yield ConnectionTarget(selected, url)
        return
    if os.environ.get("CI") != "true":
        pytest.fail(
            "Set private SKILL_ADAPTER_TEST_URL locally; CI creates its own disposable server"
        )
    password = "Aa7!" + secrets.token_urlsafe(24)
    configs = {
        "postgresql": (
            "postgres:16-alpine",
            5432,
            "postgres",
            "postgres",
            {"POSTGRES_PASSWORD": password},
        ),
        "mysql": ("mysql:8", 3306, "root", "mysql", {"MYSQL_ROOT_PASSWORD": password}),
        "mssql": (
            "mcr.microsoft.com/mssql/server:2022-latest",
            1433,
            "sa",
            "master",
            {"ACCEPT_EULA": "Y", "MSSQL_PID": "Express", "MSSQL_SA_PASSWORD": password},
        ),
    }
    image, port, user, initial_database, variables = configs[selected]
    name = "skill-adapter-proof-" + uuid4().hex[:12]
    started = False
    with tempfile.TemporaryDirectory(prefix="skill-adapter-server-") as folder:
        path = Path(folder) / "container.env"
        path.write_text("".join(f"{key}={value}\n" for key, value in variables.items()))
        path.chmod(0o600)
        try:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    name,
                    "-p",
                    f"127.0.0.1::{port}",
                    "--env-file",
                    str(path),
                    image,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode:
                pytest.fail(
                    "Selected test server could not start; no prerequisite is skipped"
                )
            started = True
            binding = subprocess.run(
                ["docker", "port", name, f"{port}/tcp"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
            url = URL.create(
                selected,
                username=user,
                password=password,
                host="127.0.0.1",
                port=int(binding.rsplit(":", 1)[1]),
                database=initial_database,
            ).render_as_string(hide_password=False)
            engine = api.connect(url, selected)
            deadline = time.monotonic() + 90
            try:
                while True:
                    try:
                        with engine.connect() as conn:
                            assert conn.scalar(text("SELECT 1")) == 1
                        break
                    except DBAPIError:
                        if time.monotonic() >= deadline:
                            pytest.fail(
                                "Selected test server exceeded its readiness deadline"
                            )
                        time.sleep(0.25)
            finally:
                engine.dispose()
            yield ConnectionTarget(selected, url)
        finally:
            if started:
                stopped = subprocess.run(
                    ["docker", "stop", "--time", "1", name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert stopped.returncode == 0, (
                    "Disposable proof server was not stopped"
                )


@pytest.fixture(scope="session")
def database(server_connection):
    selected, url = server_connection.engine, server_connection.url
    owner = api.connect(url, selected)
    suffix = uuid4().hex[:12]
    name, role = "adapter_proof_" + suffix, "adapter_rt_" + suffix
    password = "Aa7!" + secrets.token_urlsafe(24)
    quote = owner.dialect.identifier_preparer.quote
    role_sql = quote(role)
    admin = runtime = None
    created_db = created_role = absent_verified = False
    existence = (
        "SELECT COUNT(*) FROM pg_roles WHERE rolname=:r"
        if selected == "postgresql"
        else "SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'"
        if selected == "mysql"
        else "SELECT COUNT(*) FROM sys.sql_logins WHERE name=:r"
    )
    try:
        with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f"CREATE DATABASE {quote(name)}")
            created_db = True
            if conn.scalar(text(existence), {"r": role}):
                pytest.fail(
                    "The generated proof principal already exists; it will be preserved"
                )
            absent_verified = True
        admin = create_engine(owner.url.set(database=name), hide_parameters=True)
        provisioned = api.provision_runtime(admin, runtime_role=role, password=password)
        created_role = provisioned["created"]
        assert created_role
        assert not api.provision_runtime(admin, runtime_role=role, password=password)[
            "created"
        ]
        runtime = create_engine(
            owner.url.set(database=name, username=role, password=password),
            hide_parameters=True,
        )
        yield admin, runtime, role
    finally:
        if runtime is not None:
            runtime.dispose()
        if admin is not None:
            admin.dispose()
        try:
            with owner.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                if created_db:
                    conn.exec_driver_sql(f"DROP DATABASE {quote(name)}")
                if absent_verified and not created_role:
                    created_role = bool(conn.scalar(text(existence), {"r": role}))
                if created_role:
                    statement = (
                        f"DROP ROLE {role_sql}"
                        if selected == "postgresql"
                        else f"DROP USER '{role}'@'%'"
                        if selected == "mysql"
                        else f"DROP LOGIN {role_sql}"
                    )
                    conn.execute(text(statement))
        finally:
            owner.dispose()


@pytest.fixture
def adapters(database):
    admin, runtime, role = database
    prefix = "proof_" + uuid4().hex[:10]
    result = api.migrate(admin, runtime_role=role, prefix=prefix)
    assert result["initialized"]
    yield api.Adapter(admin, prefix=prefix), api.Adapter(runtime, prefix=prefix), role


@pytest.fixture
def storage_api():
    return api
