"""Configuration-selected database connections, independent of any store."""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

DRIVERS = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql", "mssql": "mssql+pymssql"}


def connect(value: str, selected: str, *, runtime_role: str | None = None):
    """An engine for one URL on the selected database engine. With `runtime_role`, every connection acts as that role:
    PostgreSQL sets it; MySQL and SQL Server must have logged in as it, and a connection that did not is refused."""
    url = make_url(value)
    if selected not in DRIVERS or url.get_backend_name() != selected:
        raise ValueError("Connection does not match the selected database engine")
    if "+" not in url.drivername:
        url = url.set(drivername=DRIVERS[selected])
    # A connection older than the bound is replaced at checkout, which finds one the server dropped while it sat
    # idle; a ping on every checkout is three round trips (BEGIN, SELECT 1, ROLLBACK), each a delay on a hosted store.
    engine = create_engine(url, hide_parameters=True, pool_recycle=30)
    if runtime_role is not None:
        quoted = engine.dialect.identifier_preparer.quote(runtime_role)

        @event.listens_for(engine, "connect")
        def select_runtime_principal(dbapi_connection, _):
            try:
                with dbapi_connection.cursor() as cursor:
                    if selected == "postgresql":
                        cursor.execute(f"SET ROLE {quoted}")
                    else:
                        # These stores authenticate the runtime login directly; never emulate SET ROLE.
                        cursor.execute("SELECT CURRENT_USER()" if selected == "mysql"
                                       else "SELECT USER_NAME(), ORIGINAL_LOGIN()")
                        principal = cursor.fetchone()
                        valid = (principal[0].rsplit("@", 1)[0] == runtime_role if selected == "mysql"
                                 else principal == (runtime_role, runtime_role))
                        if not valid:
                            raise ValueError("Authenticate as the configured runtime principal")
                dbapi_connection.commit()
            except BaseException:
                # The pool has not adopted this connection yet: a rejected login keeps no session.
                dbapi_connection.close()
                raise
    return engine


STORES = ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")
# Three databases, each store in its own schema: what consumers read (one mirror carries it), what runs the platform, and
# what says how data is processed. A reset of the data or the control database never reaches the configuration.
DATA_STORES = ("mdm", "rdm", "silver")
CONTROL_STORES = ("bookkeeping", "change_journal")
CONFIG_STORES = ("rules",)
DATABASES = {"data": DATA_STORES, "control": CONTROL_STORES, "config": CONFIG_STORES}  # the database each group shares


def database_of(store: str) -> str:
    """The database that holds this store's schema: data, control or config."""
    for database, stores in DATABASES.items():
        if store in stores:
            return database
    raise ValueError(f"unknown store {store!r}")


def url_variable(store: str) -> str:
    """The duty file's variable that names this store's database: DATA_URL, CONTROL_URL or CONFIG_URL."""
    return database_of(store).upper() + "_URL"


def configured(store: str, environment=None) -> bool:
    """Whether the sourced duty file names this store's database."""
    return bool((os.environ if environment is None else environment).get(url_variable(store)))


def instance_url(environment=None, database: str = "postgres"):
    """The instance, not a store: the data URL with another database (monitoring, role guards, the reset, the audit)."""
    return store_url("mdm", environment).set(database=database)


def store_url(store: str, environment=None):
    """The URL of the database that holds this store: `DATA_URL` for mdm, rdm and silver, `CONTROL_URL` for bookkeeping
    and change_journal, `CONFIG_URL` for rules, from the duty's file. Each must name its database; nothing is guessed."""
    variable = url_variable(store)
    env = os.environ if environment is None else environment
    value = env.get(variable)
    if not value:
        raise KeyError(f"{variable} is not set: source the duty's file in the stores folder (its value is never printed)")
    url = make_url(value)
    if not url.database:
        raise ValueError(f"{variable} must name its database")
    return own_database(url, store)


def own_database(url, store: str):
    """MySQL keeps its own database per store (a MySQL database is a schema), named after the URL's: `control_bookkeeping`.
    Operator: "kiss, mysql keep its own database per store". Every other engine keeps the stores as schemas of the URL's database."""
    return url.set(database=f"{url.database}_{store}") if url.get_backend_name() == "mysql" else url


def owner_url(store: str, environment=None) -> str:
    return store_url(store, environment).render_as_string(hide_password=False)


def store_engine(store: str, *, runtime_role=None, environment=None):
    """An engine for one store, from its group's URL in whichever duty's file was sourced; credentials are never rendered."""
    value = owner_url(store, environment)
    return connect(value, make_url(value).get_backend_name(), runtime_role=runtime_role)


owner_engine = store_engine  # the owner file's URLs are read the same way: the duty is the file, not the function
