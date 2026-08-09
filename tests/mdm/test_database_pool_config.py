"""MDM Postgres connection pool sizing.

get_engine() previously relied on SQLAlchemy's QueuePool defaults
(pool_size=5, max_overflow=10 -> 15 total connections). Once MDMPipeline's
resolve loops (run_companies, run_securities, run_persons) each open a
bounded worker-thread pool of concurrent sessions against this same engine
(default 16 workers, see pipeline.py's _RESOLVE_MAX_WORKERS), 16 workers +
the pipeline's own primary session (17) already exceeds that old 15-
connection ceiling -- the pool budget must scale with the resolve
concurrency or workers start blocking/timing out on pool checkout under
real load.
"""
from __future__ import annotations

from unittest.mock import patch

from edgar_warehouse.mdm import database


class TestPoolSizeDefaults:
    def test_pool_size_and_max_overflow_cover_the_default_resolve_concurrency(self):
        # 16 workers (pipeline.py's _RESOLVE_MAX_WORKERS default) + 1
        # primary session must fit comfortably under pool_size+max_overflow.
        assert database._DB_POOL_SIZE + database._DB_MAX_OVERFLOW >= 16 + 1

    def test_get_engine_passes_pool_kwargs_to_create_engine_for_postgres(self, monkeypatch):
        monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://user:pass@host/db")
        with patch("edgar_warehouse.mdm.database.create_engine") as mock_create, \
             patch("edgar_warehouse.mdm.observability.install_mdm_sql_logging"):
            database.get_engine()
            _, kwargs = mock_create.call_args
            assert kwargs["pool_size"] == database._DB_POOL_SIZE
            assert kwargs["max_overflow"] == database._DB_MAX_OVERFLOW
            assert kwargs["pool_pre_ping"] is True

    def test_get_engine_omits_queuepool_kwargs_for_sqlite(self):
        """Regression: SQLite's default pool classes (SingletonThreadPool/
        NullPool) reject max_overflow/pool_size -- create_engine() raises
        TypeError if they're passed. Local/test sqlite:// URLs go through
        this same get_engine(), so the pool kwargs must be conditional."""
        engine = database.get_engine("sqlite:///:memory:")
        try:
            assert engine.dialect.name == "sqlite"
        finally:
            engine.dispose()
