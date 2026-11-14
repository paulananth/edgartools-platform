from edgar_warehouse.mastering import store as stores

from tests.storage_adapters.test_mastering import test_two_writers_on_the_same_identifiers_leave_one_master_each


def test_probe_without_the_lock(database_factory, monkeypatch):
    monkeypatch.setattr(stores.Store, "take_lock", lambda self, kind=None: None)
    test_two_writers_on_the_same_identifiers_leave_one_master_each(database_factory)
