"""Configuration registrars retain no master-save, gate or record mutation rights."""

from contextlib import ExitStack
import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import registration
from edgar_warehouse.mdm.clean.prepared_registry import require_installed
from edgar_warehouse.mdm.clean.store import Conflict, migrate, register_policy

CASES = ["rights", "rollback", "definition"] if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "postgresql" else ["unsupported"]


@pytest.mark.parametrize("case", CASES)
def test_configuration_registration_authority(case, database_factory, storage_api):
    with ExitStack() as stack:
        _, governor, governor_role = stack.enter_context(database_factory())
        owner, runtime, role = stack.enter_context(database_factory())
        if case == "unsupported":
            with pytest.raises(Conflict, match="PostgreSQL local-store setup only"):
                registration.grant(owner, governor_role)
            return
        migrate(owner, application_role=role)
        quote = owner.dialect.identifier_preparer.quote
        with owner.begin() as conn:
            api = require_installed(conn)
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA mdm,public TO {quote(governor_role)}")
            conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA mdm,public TO {quote(governor_role)}")
            conn.exec_driver_sql(f"GRANT INSERT ON mdm.policy,mdm.dataset,mdm.dataset_mapping TO {quote(governor_role)}")
        registration.grant(owner, governor_role)
        delegated = storage_api.connect(governor.url.set(database=owner.url.database), "postgresql")
        body = {"version": "invented-approved", "required_consumers": ["invented"], "automatic_rules": []}
        try:
            with delegated.begin() as conn:
                pin = register_policy(conn, body)
            with delegated.begin() as conn:
                assert register_policy(conn, body) == pin
            with runtime.connect() as conn:
                api = require_installed(conn)
                saved = conn.execute(select(api.tables["pin"])).mappings().all()
                assert any(bytes(r["name_bytes"]) == b"policy" and bytes(r["value_bytes"]).decode() == pin and r["active"] == 1 for r in saved)
            if case == "rights":
                for engine, sql in ((runtime, "SELECT public.mdm_store_register_pin('policy',:pin)"),
                                    (delegated, "UPDATE public.mdm_store_gate SET generation=generation+1"),
                                    (delegated, "DELETE FROM public.mdm_store_current")):
                    with pytest.raises(DBAPIError), engine.begin() as conn:
                        conn.execute(text(sql), {"pin": pin})
                with pytest.raises(DBAPIError, match="invalid_registration_pin"), delegated.begin() as conn:
                    conn.execute(text("SELECT public.mdm_store_register_pin('catalog',:pin)"), {"pin": pin})
            elif case == "rollback":
                with pytest.raises(RuntimeError, match="invented interruption"), delegated.begin() as conn:
                    rejected = register_policy(conn, {**body, "version": "invented-rolled-back"})
                    raise RuntimeError("invented interruption")
                with owner.connect() as conn:
                    assert storage_api.registered_policy(conn, rejected) is None
            elif case == "definition":
                with owner.begin() as conn:
                    conn.execute(text("ALTER FUNCTION public.mdm_store_register_pin(text,text) SECURITY INVOKER"))
                with pytest.raises(Conflict, match="owner registration migration"), runtime.connect() as conn:
                    require_installed(conn)
                with pytest.raises(Conflict, match="owner registration migration"):
                    migrate(owner, application_role=role)
                return
            with runtime.connect() as conn:
                assert conn.execute(select(api.tables["pin"])).mappings().all() == saved
                assert api.generation(connection=conn) == 0
        finally:
            delegated.dispose()
