"""The control stores' engines do not ping every checkout: a hosted store costs a round trip a statement."""
import pytest

from edgar_warehouse.bookkeeping.clean import database as bookkeeping
from edgar_warehouse.change_journal import store as journal

# The Rules Database's engine is `database_connections.connect`, checked on real servers
# (tests/storage_adapters/test_engine_checkout.py).
FACTORIES = {"bookkeeping": bookkeeping.get_engine, "change journal": journal.get_engine}


@pytest.mark.parametrize("name", FACTORIES)
def test_a_checkout_sends_no_ping(name, tmp_path, monkeypatch):
    engine = FACTORIES[name](f"sqlite:///{tmp_path}/{name.replace(' ', '_')}.db")
    pings = []
    monkeypatch.setattr(engine.dialect, "do_ping", lambda connection: pings.append(1) or True)
    try:
        for _ in range(5):
            with engine.connect():
                pass
        assert pings == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("name", FACTORIES)
def test_a_connection_older_than_the_bound_is_replaced_at_checkout(name, tmp_path):
    """The bound is what finds a connection the server dropped while it sat idle, in place of a ping."""
    from sqlalchemy import event

    engine = FACTORIES[name](f"sqlite:///{tmp_path}/{name.replace(' ', '_')}.db")
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
