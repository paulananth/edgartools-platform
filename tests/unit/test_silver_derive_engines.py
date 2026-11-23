"""silver.derive opens the silver engine and, when configured, the MDM engine: a measure reads the Company master."""
from edgar_warehouse import database_connections
from edgar_warehouse.workers import silver_derive


def test_derive_opens_silver_and_mdm_when_the_duty_file_names_the_data_database(monkeypatch):
    monkeypatch.setattr(database_connections, "store_engine", lambda store: f"engine:{store}")
    monkeypatch.setenv("DATA_URL", "postgresql://invented/data")
    silver, mdm = silver_derive.engines()
    assert (silver, mdm) == ("engine:silver", "engine:mdm")


def test_derive_has_no_mdm_engine_when_no_data_database_is_named(monkeypatch):
    monkeypatch.setattr(database_connections, "store_engine", lambda store: f"engine:{store}")
    monkeypatch.delenv("DATA_URL", raising=False)
    assert silver_derive.engines() == ("engine:silver", None)
