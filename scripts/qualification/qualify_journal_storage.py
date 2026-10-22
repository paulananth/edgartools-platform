"""Qualify an installed Journal on an existing authorized local test database.

Reads owner connections privately, preserves runtime credentials on rerun and
records one invented qualification event. It starts no pipeline or provider work.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys


def read_environment(path):
    values={}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key,value=line.removeprefix("export ").split("=",1)
            parts=shlex.split(value)
            if parts:values[key]=parts[0]
    return values


def private_write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(path,"w",opener=lambda name,flags:os.open(name,flags,0o600)) as handle:
        handle.write(body)
    path.chmod(0o600)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine",choices=("postgresql","mysql","mssql"),required=True)
    parser.add_argument("--connection-file",type=Path,required=True)
    parser.add_argument("--journal-python",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    # Provisioning uses the existing generic, source-independent principal helper.
    scripts=Path(__file__).resolve().parents[2]/"skills/mdm-engineering/scripts"
    sys.path.insert(0,str(scripts))
    import database_adapter as storage
    from sqlalchemy import inspect,text
    owner_values=read_environment(args.connection_file)
    owner=storage.connect(owner_values["CHANGE_JOURNAL_DATABASE_URL"],args.engine)
    role="journal_native_runtime"
    credentials=args.evidence_dir/"runtime.env"
    saved=read_environment(credentials) if credentials.exists() else {}
    password=saved.get("JOURNAL_RUNTIME_PASSWORD") or "Aa8!"+secrets.token_urlsafe(24)
    try:
        with owner.connect() as conn:
            schema=None if args.engine=="mysql" else "journal"
            table="journal_event" if args.engine=="mysql" else "event"
            exists=inspect(conn).has_table(table,schema=schema)
            qualified=table if schema is None else schema+"."+table
            before=conn.scalar(text("SELECT count(*) FROM "+qualified)) if exists else 0
            if args.engine=="postgresql":
                definitions=[row[0] for row in conn.execute(text("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace=to_regnamespace('journal')"))]
                comment=conn.scalar(text("SELECT obj_description(to_regnamespace('journal'),'pg_namespace')"))
                backup=args.evidence_dir/"original-schema.json"
                if not backup.exists():private_write(backup,json.dumps({"comment":comment,"functions":definitions},indent=2))
        if not saved:
            query={"postgresql":"SELECT COUNT(*) FROM pg_roles WHERE rolname=:r",
                "mysql":"SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'",
                "mssql":"SELECT COUNT(*) FROM sys.sql_logins WHERE name=:r"}[args.engine]
            with owner.connect() as conn:
                if conn.scalar(text(query),{"r":role}):
                    raise RuntimeError("Existing runtime credentials are required; principal preserved")
        runtime_url=owner.url.set(username=role,password=password).render_as_string(hide_password=False)
        if not saved:
            # Save before provisioning, so interruption cannot strand a created login.
            private_write(credentials,"JOURNAL_RUNTIME_PASSWORD="+shlex.quote(password)+"\n"+
                "CHANGE_JOURNAL_DATABASE_URL="+shlex.quote(runtime_url)+"\n"+
                "CHANGE_JOURNAL_MIGRATION_DATABASE_URL="+shlex.quote(owner_values["CHANGE_JOURNAL_DATABASE_URL"])+"\n")
        result=storage.provision_runtime(owner,runtime_role=role,password=password)
        environment={**os.environ,"CHANGE_JOURNAL_DATABASE_URL":runtime_url,
            "CHANGE_JOURNAL_MIGRATION_DATABASE_URL":owner_values["CHANGE_JOURNAL_DATABASE_URL"]}
        for mode in ("init","migrate"):
            done=subprocess.run([str(args.journal_python),"-I","-m","edgar_warehouse.change_journal.cli",mode,"--runtime-role",role],
                env=environment,capture_output=True,text=True,timeout=60,cwd=args.evidence_dir)
            private_write(args.evidence_dir/(mode+".log"),done.stdout+done.stderr)
            if done.returncode:raise RuntimeError("Installed journal migration failed; private evidence retained")
        proof_code = r'''
import importlib.metadata,json,sys
from datetime import UTC,datetime
from pathlib import Path
from uuid import uuid4
from edgar_warehouse.change_journal import ChangeJournal,envelope
from edgar_warehouse.change_journal.store import get_engine
assert not any(importlib.metadata.packages_distributions().get(name) for name in ("edgar","pyarrow","lxml","ijson","boto3","source_contract"))
engine=get_engine()
try:
    journal=ChangeJournal(engine)
    path=Path(sys.argv[1])
    if path.exists():value=json.loads(path.read_text())["event"]
    else:
        value=envelope(producer="platform.qualification",event_key="installed-journal-"+uuid4().hex,run_id=str(uuid4()),
            source="invented.source",feed="local-storage-proof",event_type="storage.qualified",occurred_at=datetime.now(UTC).isoformat(),
            evidence=[{"uri":"s3://invented/qualification","sha256":"a"*64}])
    receipt=journal.append(value)
    assert journal.append(value)==receipt and journal.verify(receipt,expected=value)==receipt
    assert journal.found(value["producer"],[value["event_key"]])=={value["event_key"]}
    assert journal.list(run_id=value["run_id"],limit=1)==[receipt]
    path.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True))
    path.chmod(0o600)
    print(json.dumps({"events":journal.status()["events"],"independent_install":True,"same_receipt_on_retry":True}))
finally:engine.dispose()
'''
        done=subprocess.run([str(args.journal_python),"-I","-c",proof_code,str(args.evidence_dir/"receipt.json")],
            env=environment,capture_output=True,text=True,timeout=60,cwd=args.evidence_dir)
        private_write(args.evidence_dir/"installed-proof.log",done.stdout+done.stderr)
        if done.returncode:raise RuntimeError("Installed journal readback failed; private evidence retained")
        summary={"engine":args.engine,"before_events":before,**json.loads(done.stdout)}
        private_write(args.evidence_dir/"qualification.json",json.dumps(summary,indent=2))
        print(json.dumps(summary,sort_keys=True))
    finally:owner.dispose()
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as error:
        # Private logs contain diagnostic detail; never emit connection data.
        import traceback
        if "--evidence-dir" in sys.argv:
            destination=Path(sys.argv[sys.argv.index("--evidence-dir")+1])
            private_write(destination/"failure.log",traceback.format_exc())
        print("Journal qualification failed: "+type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
