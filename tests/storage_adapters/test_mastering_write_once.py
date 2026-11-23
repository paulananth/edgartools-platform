"""A golden record is written once with its change number; the number comes from a counter that never waits on a merge.

Ticket mastering-locks/03, part 1. On each engine, invented records, the runtime role.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager

import pytest

from edgar_warehouse.mastering import lookups, merge, store as stores
from edgar_warehouse.mastering.store import open_store
from tests.storage_adapters.test_mastering import FIGI, SECURITY, record
from tests.support.masters import figi

ONE, TWO, THREE = figi("00WNC001"), figi("00WNC002"), figi("00WNC003")


@contextmanager
def opened(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        opened_stores = []

        def another():
            opened_stores.append(open_store(runtime))
            return opened_stores[-1]

        try:
            yield another
        finally:
            for each in opened_stores:
                each.rollback()
                each.close()


class Spy:
    """Records each statement a store's cursor runs, and passes it on."""

    def __init__(self, cursor):
        self.cursor, self.sql = cursor, []

    def execute(self, statement, *args):
        self.sql.append(" ".join(str(statement).split()).lower())
        return self.cursor.execute(statement, *args)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


def test_a_merge_writes_each_golden_record_once_with_its_number(database_factory):
    with opened(database_factory) as another:
        db = another()
        db.cursor = spy = Spy(db.cursor)
        merge.merge_file(db, SECURITY, [record(FIGI, "one", "security", figi=ONE), record(FIGI, "two", "security", figi=TWO)])
        assert not [s for s in spy.sql if s.startswith("update mastering_master")], "a golden record was written a second time"
        numbers = {n for (n,) in db.rows("select changed_file from mastering_master")}
        assert len(numbers) == 1 and 0 not in numbers  # one merge, one number, none left pending
        merge.merge_file(db, SECURITY, [record(FIGI, "three", "security", figi=THREE)])
        assert max(n for (n,) in db.rows("select changed_file from mastering_master")) > next(iter(numbers))
        assert db.last_file() == max(n for (n,) in db.rows("select changed_file from mastering_master"))


def test_two_open_transactions_take_numbers_without_waiting_on_each_other(database_factory):
    with opened(database_factory) as another:
        first, second = another(), another()
        held = first.take_number()  # the first transaction stays open
        with ThreadPoolExecutor(1) as pool:
            try:
                taken = pool.submit(second.take_number).result(timeout=5)
            except TimeoutError:
                pytest.fail("the second transaction waited on the first for its number")
        assert taken != held


def test_a_transaction_keeps_its_number_and_a_rollback_leaves_a_gap(database_factory):
    with opened(database_factory) as another:
        db = another()
        first = db.take_number()
        assert db.take_number() == first
        db.rollback()
        assert db.take_number() > first  # the rolled-back number is never reused


def test_quiet_sees_another_sessions_kind_lock_and_never_its_own(database_factory):
    with opened(database_factory) as another:
        merging, caller = another(), another()
        assert caller.quiet()
        merging.take_lock("company")
        assert not caller.quiet()
        merging.commit()
        assert caller.quiet()
        caller.take_lock("company")
        assert caller.quiet()  # its own kind lock is not another merge
        caller.commit()


def test_building_the_lookups_refuses_while_another_session_merges(database_factory):
    with opened(database_factory) as another:
        merging, builder = another(), another()
        merging.take_lock("company")
        with pytest.raises(lookups.NotQuiet):
            lookups.build(builder)
        merging.commit()
        assert lookups.build(builder)["masters"] == 0
