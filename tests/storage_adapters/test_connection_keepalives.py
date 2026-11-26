"""Every store's connection fails within about two minutes once the path to its server goes silent, not after the operating
system's two hours: its socket probes an idle connection after a minute, every ten seconds, six times, and on Linux gives up
on data the server has not acknowledged after two minutes."""
import os
import socket
import sys

import pytest

from edgar_warehouse.bookkeeping.clean import database as bookkeeping
from edgar_warehouse.change_journal import store as journal
from edgar_warehouse.database_connections import connect

FACTORIES = {
    "a store": lambda target: connect(target.url, target.engine),
    "bookkeeping": lambda target: bookkeeping.get_engine(target.url),
    "the change journal": lambda target: journal.get_engine(target.url),
}
IDLE = socket.TCP_KEEPALIVE if sys.platform == "darwin" else socket.TCP_KEEPIDLE
EXPECTED = {(socket.SOL_SOCKET, socket.SO_KEEPALIVE): True,(socket.IPPROTO_TCP, IDLE): 60,
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL): 10, (socket.IPPROTO_TCP, socket.TCP_KEEPCNT): 6}
if hasattr(socket, "TCP_USER_TIMEOUT"):
    EXPECTED[(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT)] = 120_000


def _socket_options(dbapi_connection) -> dict:
    fileno = dbapi_connection.fileno() if hasattr(dbapi_connection, "fileno") else dbapi_connection._sock.fileno()
    with socket.socket(fileno=os.dup(fileno)) as sock:
        # SO_KEEPALIVE reads back as any non-zero value when on
        return {key: bool(sock.getsockopt(*key)) if key[1] == socket.SO_KEEPALIVE else sock.getsockopt(*key)
                for key in EXPECTED}


@pytest.mark.parametrize("name", FACTORIES)
def test_a_connection_gives_up_on_a_silent_server_within_minutes(name, server_connection):
    engine = FACTORIES[name](server_connection)
    try:
        with engine.connect() as conn:
            found = _socket_options(conn.connection.dbapi_connection)
        assert found == EXPECTED
    finally:
        engine.dispose()
