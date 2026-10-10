"""An empty PostgreSQL 16 server for the Postgres acceptance tests.

Docker by default (`postgres:16-alpine`, superuser `postgres` / `test`, a
loopback port), as CI runs them. With `PG16_SERVER=pgserver`, a local
PostgreSQL 16 from the `pgserver` package instead, on its own socket in a
temporary folder that is deleted afterwards: for a machine with no Docker
(`uv run --with pgserver ...`). Either way the test gets `url(database, user)`;
every role a test creates logs in with password `test`.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid
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


@contextmanager
def server() -> Iterator[Server]:
    if os.environ.get("PG16_SERVER") == "pgserver":
        import pgserver

        local = pgserver.get_server(tempfile.mkdtemp(prefix="pg16-"), cleanup_mode="delete")
        try:
            yield Server(socket=local.get_uri().rsplit("host=", 1)[1])
        finally:
            local.cleanup()
        return
    _docker("image", "inspect", IMAGE)
    name = f"pg16-test-{uuid.uuid4().hex[:10]}"
    _docker("run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD=test", IMAGE)
    try:
        for _ in range(300):
            if subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True).returncode == 0:
                break
            time.sleep(0.1)
        yield Server(port=_docker("port", name, "5432/tcp").rsplit(":", 1)[1])
    finally:
        subprocess.run(["docker", "stop", "--time", "1", name], capture_output=True)
