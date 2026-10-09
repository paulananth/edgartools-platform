"""Ticket 06 done test: the silver specs profiling wrote for Trial B (Contoso V2,
not SEC) land through the silver writer on PG16, with no domain-specific change.

    PG16_ADMIN_URL=<superuser url> uv run python .scratch/profiling/trials/silver/land_trial_b.py \
        <findings.yaml> <csv folder> <out.json>

Each link's kind and Dataset Contract are filled the way data-onboarding fills
them: the master part's own name as its kind, and `contoso.<master part>` as its
Dataset Contract (the names onboarding would propose; none is onboarded here). MDM is a freshly migrated database in which no
Contoso master is onboarded, so every MDM id stays empty: an unmastered record
keeps its source key and an empty id. Resolution through mastered records is
proven by tests/integration/test_silver_writer_postgres.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import yaml
from sqlalchemy import create_engine, text

from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.rows import records
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land
from tests.integration.test_clean_mdm_postgres import initialize_database

findings, folder, out = (Path(a) for a in sys.argv[1:4])
admin = create_engine(os.environ["PG16_ADMIN_URL"])
silver_db, mdm_db = f"silver_{uuid4().hex[:8]}", f"mdm_{uuid4().hex[:8]}"
server = admin.execution_options(isolation_level="AUTOCOMMIT")
with server.connect() as conn:
    for role in ("silver_runtime", "clean_application"):
        if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:r"), {"r": role}):
            conn.exec_driver_sql(f"CREATE ROLE {role} LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
    conn.exec_driver_sql(f"CREATE DATABASE {silver_db}")
    conn.exec_driver_sql(f"CREATE DATABASE {mdm_db}")
owner = create_engine(admin.url.set(database=silver_db))
runtime = create_engine(admin.url.set(database=silver_db, username="silver_runtime", password="test"))
mdm_admin = create_engine(admin.url.set(database=mdm_db))
mdm_app = create_engine(admin.url.set(database=mdm_db, username="clean_application", password="test"))
initialize_database(mdm_admin, mdm_app)
silver.migrate(owner, runtime_role="silver_runtime")

body = yaml.safe_load(findings.read_text())
result = {"findings": str(findings.name), "tables": []}
for part in body["parts"]:
    spec = part.get("silver")
    if not spec:
        continue
    for link in spec["links"]:  # what data-onboarding fills from the onboarded master
        link["kind"], link["source_code"] = link["to_part"], f"contoso.{link['to_part']}"
    registered = silver.register(owner, spec, runtime_role="silver_runtime")
    started = time.monotonic()
    first = land(PostgresSink(runtime), spec["table"], records(folder / f"{part['part']}.csv"), MdmIds(mdm_app))
    again = land(PostgresSink(runtime), spec["table"], records(folder / f"{part['part']}.csv"), MdmIds(mdm_app))
    with runtime.connect() as conn:
        types = dict(conn.execute(text("SELECT column_name, data_type FROM information_schema.columns "
                                       "WHERE table_schema='silver' AND table_name=:t"), {"t": spec["table"]}).all())
        empty_ids = {link["mdm_id_column"]: conn.scalar(text(
            f'SELECT count(*) FROM silver."{spec["table"]}" WHERE "{link["mdm_id_column"]}" IS NULL '
            f'AND "{link["source_key"]}" IS NOT NULL')) for link in spec["links"]}
    result["tables"].append({
        "part": part["part"], "class": part["class"], "table": spec["table"], "sha256": registered["sha256"],
        "load_mode": spec["load_mode"], "key": spec["key"], "first": first, "rerun": again,
        "seconds": round(time.monotonic() - started, 2), "types": types,
        "links": [{k: link[k] for k in ("source_key", "to_part", "kind", "source_code", "mdm_id_column")}
                  for link in spec["links"]],
        "source_keys_with_empty_mdm_id": empty_ids})
out.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
for value in (owner, runtime, mdm_admin, mdm_app):
    value.dispose()
with server.connect() as conn:
    conn.exec_driver_sql(f"DROP DATABASE {silver_db} WITH (FORCE)")
    conn.exec_driver_sql(f"DROP DATABASE {mdm_db} WITH (FORCE)")
print(json.dumps([{t["table"]: [t["first"]["inserted"], t["rerun"]["inserted"], t["rerun"]["changed"]]}
                  for t in result["tables"]]))
