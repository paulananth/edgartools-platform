"""Request-dedup root cause (scratch, not collected by CI): where one batch's bytes land.
cm27 chunk 1 (919 Companies) mastered once into a fresh PG16 store; per table, rows and the
bytes of each jsonb column (uncompressed text, and as stored), plus the outbox per consumer."""
import json
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.mdm.clean.cli import batch_input
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database
BUNDLE = Path("~/.local/share/edgartools/clean-mdm/proving/cm27/bundles/chunk1").expanduser()


def test_where_bytes_go(database):
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    with database.admin.begin() as conn:
        digest = register_policy(conn, POLICY)
        register_dataset(conn, "sec.submissions.company.v1", str(uuid4()), CONTRACT)
    store = Store(database.application)
    (batch,) = manifest["batches"]
    found = batch_input(batch, BUNDLE.resolve(), store, policy_digest=digest)
    t0 = time.perf_counter()
    MergeStage(store).apply(batch_id="b0", run_id=str(uuid4()), consumer="trial", policy_digest=digest,
                            expected_checkpoint=0, checkpoint=1, as_of=manifest["as_of"],
                            assertions=found["assertions"], deferred=found["deferred"],
                            occurrences=found["occurrences"])
    print("MERGE_S", round(time.perf_counter() - t0, 2))
    with database.admin.connect() as conn:
        cols = conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='mdm' AND data_type='jsonb' ORDER BY 1, 2")).all()
        out = {}
        for table, column in cols:
            row = conn.execute(text(
                f'SELECT count(*), coalesce(sum(octet_length("{column}"::text)),0), '
                f'coalesce(sum(pg_column_size("{column}")),0) FROM mdm."{table}"')).one()
            if row[1]:
                out[f"{table}.{column}"] = {"rows": row[0], "text_mb": round(row[1] / 1e6, 2),
                                           "stored_mb": round(row[2] / 1e6, 2)}
        sizes = {r[0]: round(r[1] / 1e6, 2) for r in conn.execute(text(
            "SELECT relname, pg_total_relation_size(relid) FROM pg_stat_user_tables "
            "WHERE schemaname='mdm' AND pg_total_relation_size(relid) > 200000 ORDER BY 2 DESC")).all()}
        outbox = [tuple(r) for r in conn.execute(text(
            "SELECT consumer, count(*), round(sum(octet_length(payload::text))/1e6,2) FROM mdm.outbox GROUP BY 1")).all()]
        required = conn.execute(text("SELECT body->'required_consumers' FROM mdm.policy")).scalar()
    print("JSONB", json.dumps(out, sort_keys=True))
    print("TABLE_MB", json.dumps(sizes))
    print("OUTBOX", outbox, "REQUIRED", required)
