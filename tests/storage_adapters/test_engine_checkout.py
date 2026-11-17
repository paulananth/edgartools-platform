"""MDM's engine does not ping every checkout: on a hosted store each ping is three round trips (BEGIN, SELECT 1, ROLLBACK)."""
from sqlalchemy import event

from tests.storage_adapters.conftest import api


def test_a_checkout_sends_no_ping(server_connection):
    engine = api.connect(server_connection.url, server_connection.engine)
    pings = []
    engine.dialect.do_ping = lambda connection: pings.append(1) or True
    try:
        for _ in range(5):
            with engine.connect():
                pass
        assert pings == []
    finally:
        engine.dispose()


def test_a_connection_older_than_the_bound_is_replaced_at_checkout(server_connection):
    """The bound is what finds a connection the server dropped while it sat idle, in place of a ping."""
    engine = api.connect(server_connection.url, server_connection.engine)
    connects = []
    event.listen(engine, "connect", lambda *args: connects.append(1))
    try:
        with engine.connect() as conn:
            conn.connection._connection_record.starttime -= 10_000
        with engine.connect():
            pass
        assert len(connects) == 2
        with engine.connect():
            pass
        assert len(connects) == 2  # a young connection is reused
    finally:
        engine.dispose()
