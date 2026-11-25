"""Three URLs a duty file: DATA_URL names the data database (mdm, rdm, silver), CONTROL_URL the control database (bookkeeping,
change_journal) and CONFIG_URL the config database (rules). Each store finds its database by its group, in one place."""
import pytest

from edgar_warehouse import database_connections as connections
from edgar_warehouse.bookkeeping.clean import database as bookkeeping
from edgar_warehouse.change_journal import store as journal

ENV = {"DATA_URL": "postgresql://worker:invented@host:5432/data", "CONTROL_URL": "postgresql://worker:invented@host:5432/control",
       "CONFIG_URL": "postgresql://worker:invented@host:5432/config"}


@pytest.mark.parametrize("store, database", [
    ("mdm", "data"), ("rdm", "data"), ("silver", "data"),
    ("rules", "config"), ("bookkeeping", "control"), ("change_journal", "control"),
])
def test_each_store_takes_the_url_of_its_group(store, database):
    assert connections.store_url(store, ENV).database == database


def test_the_bookkeeping_and_journal_stores_ask_the_same_resolver(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DB_URL", raising=False)
    assert bookkeeping.default_url().endswith("/control")
    assert journal._default_url("change_journal").endswith("/control")


@pytest.mark.parametrize("missing, store", [("DATA_URL", "silver"), ("CONTROL_URL", "bookkeeping"), ("CONFIG_URL", "rules")])
def test_a_missing_url_is_named_and_its_value_never_shown(missing, store):
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(KeyError, match=missing) as caught:
        connections.store_url(store, env)
    assert "invented" not in str(caught.value)


def test_a_url_that_names_no_database_is_refused():
    with pytest.raises(ValueError, match="DATA_URL must name its database"):
        connections.store_url("mdm", {**ENV, "DATA_URL": "postgresql://worker:invented@host:5432"})


def test_an_unknown_store_is_refused():
    with pytest.raises(ValueError, match="unknown store"):
        connections.store_url("elsewhere", ENV)


@pytest.mark.parametrize("store, database", [("mdm", "data_mdm"), ("silver", "data_silver"), ("bookkeeping", "control_bookkeeping"),
                                             ("change_journal", "control_change_journal"), ("rules", "config_rules")])
def test_mysql_keeps_its_own_database_per_store(store, database, monkeypatch):
    """Operator: "kiss, mysql keep its own database per store"; PostgreSQL keeps them as schemas of the three databases."""
    env = {"DATA_URL": "mysql://worker:invented@host:3306/data", "CONTROL_URL": "mysql://worker:invented@host:3306/control",
           "CONFIG_URL": "mysql://worker:invented@host:3306/config"}
    assert connections.store_url(store, env).database == database
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if store == "bookkeeping":
        assert bookkeeping.default_url().endswith("/control_bookkeeping")
    if store == "change_journal":
        assert journal._default_url("change_journal").endswith("/control_change_journal")
