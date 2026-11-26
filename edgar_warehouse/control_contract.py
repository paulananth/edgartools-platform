"""Pure control-envelope primitives shared without importing a runtime owner."""

from __future__ import annotations

import json
import os
import socket
import sys

# Each database engine's driver, when a URL names none.
DRIVERS = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql", "mssql": "mssql+pymssql"}
# A connection whose server or path went silent fails within about two minutes: the kernel probes it after a minute idle,
# every ten seconds, six times, and on Linux gives up on data the server has not acknowledged after two minutes, well
# before the operating system's own keepalive (two hours idle) or a step's bound.
_TCP = socket.IPPROTO_TCP
KEEPALIVE = ((socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
             (_TCP, socket.TCP_KEEPALIVE if sys.platform == "darwin" else socket.TCP_KEEPIDLE, 60),
             (_TCP, socket.TCP_KEEPINTVL, 10), (_TCP, socket.TCP_KEEPCNT, 6),
             *(((_TCP, socket.TCP_USER_TIMEOUT, 120_000),) if hasattr(socket, "TCP_USER_TIMEOUT") else ()))


def connection_socket(dbapi_connection) -> int | None:
    """A driver connection's socket: psycopg2's `fileno()`, PyMySQL's `_sock`; pymssql gives none."""
    if hasattr(dbapi_connection, "fileno"):
        return dbapi_connection.fileno()
    sock = getattr(dbapi_connection, "_sock", None)
    return sock.fileno() if sock is not None else None


def keep_alive(dbapi_connection, _record=None) -> None:
    """A pool's `connect` listener: the connection's socket keeps `KEEPALIVE`. A driver with no socket keeps the
    operating system's keepalive."""
    fileno = connection_socket(dbapi_connection)
    if fileno is None:
        return
    with socket.socket(fileno=os.dup(fileno)) as sock:
        for level, option, value in KEEPALIVE:
            sock.setsockopt(level, option, value)


class Blocked(ValueError):
    """Execution cannot safely reconstruct or verify its frozen scope."""


def canonical(value) -> str:
    import edgar_control
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    try:
        return edgar_control.canonicalize(encoded)
    except UnicodeEncodeError:
        # Opaque processing metadata may contain lone surrogates until unused
        # columns are dropped. Preserve Python code points for native equality;
        # durable UTF-8 hashes and publication retain their existing refusal.
        return edgar_control.canonicalize_opaque(value)


def digest(value) -> str:
    import edgar_control
    return edgar_control.digest_json(json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False))


def source_policy_digest(policy: dict, source: str) -> str:
    """The digest of the part of the merge policy that acts on one source's files (the Rust crate slices it)."""
    import edgar_control
    return edgar_control.source_policy_digest(
        json.dumps(policy, separators=(",", ":"), ensure_ascii=False, allow_nan=False), source)


def reference(value: dict) -> dict:
    import edgar_control
    try:
        edgar_control.check_reference(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except ValueError as error:
        raise Blocked(str(error)) from None
    return value
