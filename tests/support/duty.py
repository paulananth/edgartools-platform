"""The URL a duty file holds for a test's store database."""


def duty_url(engine, store: str) -> str:
    """On MySQL a store's database is the URL's plus `_<store>` (edgar_warehouse.database_connections.own_database), so the
    duty file names the database without it; every other engine names the store's database itself."""
    url = engine.url
    if url.get_backend_name() == "mysql":
        suffix = "_" + store
        assert url.database.endswith(suffix), "make the database with database_factory(store=...)"
        url = url.set(database=url.database[: -len(suffix)])
    return url.render_as_string(hide_password=False)
