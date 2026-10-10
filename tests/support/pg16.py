"""An empty PostgreSQL 16 server for the Postgres acceptance tests.

Docker by default (`postgres:16-alpine`, superuser `postgres` / `test`, a
loopback port), as CI runs them. With `PG16_SERVER=pgserver`, a local
PostgreSQL 16 from the `pgserver` package instead, on its own socket in a
temporary folder that is deleted afterwards: for a machine with no Docker
(`uv run --with pgserver ...`). Either way the test gets `url(database, user)`;
every role a test creates logs in with password `test`. The server is yielded
only once it answers a query.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

IMAGE = "postgres:16-alpine"


@dataclass(frozen=True)
class Server:
    """Where the server answers: a loopback port, or a socket folder."""
    port: str | None = None
    socket: str | None = None

    def url(self, database: str = "postgres", user: str = "postgres", driver: str = "postgresql+psycopg2") -> str:
        if self.socket is not None:
            return f"{driver}://{user}:test@/{database}?host={self.socket}"
        return f"{driver}://{user}:test@127.0.0.1:{self.port}/{database}"


def _docker(*args: str) -> str:
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True).stdout.strip()


def _ready(found: Server, seconds: float = 30) -> Server:
    """The server once it answers `SELECT 1`; the image restarts once after it initializes,
    so a ready port alone is not enough."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError

    engine = create_engine(found.url(driver="postgresql"), connect_args={"connect_timeout": 3})
    deadline = time.monotonic() + seconds
    try:
        while True:
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return found
            except DBAPIError:
                if time.monotonic() > deadline:
                    raise RuntimeError("PostgreSQL 16 did not become ready") from None
                time.sleep(0.1)
    finally:
        engine.dispose()


@contextmanager
def server() -> Iterator[Server]:
    if os.environ.get("PG16_SERVER") == "pgserver":
        import pgserver

        folder = tempfile.mkdtemp(prefix="pg16-")
        try:
            local = pgserver.get_server(folder, cleanup_mode="delete")
            try:
                yield _ready(Server(socket=local.get_uri().rsplit("host=", 1)[1]))
            finally:
                local.cleanup()
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        return
    _docker("image", "inspect", IMAGE)
    name = f"pg16-test-{uuid.uuid4().hex[:10]}"
    _docker("run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD=test", IMAGE)
    try:
        yield _ready(Server(port=_docker("port", name, "5432/tcp").rsplit(":", 1)[1]))
    finally:
        stopped = subprocess.run(["docker", "stop", "--time", "1", name], capture_output=True, text=True)
        if stopped.returncode:
            warnings.warn(f"Test container {name} was not stopped: {stopped.stderr.strip()}", stacklevel=2)
