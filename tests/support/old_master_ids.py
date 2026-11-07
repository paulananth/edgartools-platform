"""Master ids of records seeded through the old merge. It leaves with that merge in stage 5."""


class OldIds:
    def __init__(self, engine):
        self.engine = engine

    def __call__(self, source_code: str, kind: str, keys: set[str]) -> dict:
        if not keys:
            return {}
        from edgar_warehouse.mdm.record_reads import for_connection

        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            return for_connection(conn).master_ids(source_code, kind, keys)
