"""The data skill installed whole, from a git ref, with no checkout (mastering to-do 21).

The four wheels (the bundle, Bookkeeping, the Change Journal and the engine)
are installed from this repository's committed HEAD by URL with the
`uv tool install` command the data-platform skill's Setup writes, the way an
agent with no checkout installs them. Every command
then runs from that installation, in isolated mode, from a folder outside
the repository, so nothing here can stand in for a missing file.

- G1: no file ships in two wheels; every shipped module imports; no domain
  library (edgartools, spaCy) is installed; `doctor` passes on PG16 stores.
- G2: the rules creator runs from the bundle against an empty Rules Database.
- G3 (parse): a Rules-submitted run is read by the configured engine and
  verified by separate worker and verifier processes, all from the bundle.
- G5: `doctor` names a command a skill writes that does not exist.
"""
import json
import copy
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.rules import files
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.journal_isolation import ROOT

WHEELS = {
    "edgartools-data": "packages/data-skill",
    "edgartools-bookkeeping": "packages/bookkeeping",
    "edgartools-change-journal": "packages/change-journal",
    "source-contract": "crates/source-contract",
}
DOMAIN = ("edgartools", "spacy", "pandas", "streamlit", "snowflake-connector-python")


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """The install command data-platform's Setup writes, word for word, from this commit."""
    assert shutil.which("uv") and shutil.which("cargo"), "The bundle install needs uv and cargo"
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    root = tmp_path_factory.mktemp("bundle")
    repo = f"git+file://{ROOT}@{head}"
    first, *others = [f"{name} @ {repo}#subdirectory={folder}" for name, folder in WHEELS.items()]
    command = ["uv", "tool", "install", "--python", "3.12", first, *(a for o in others for a in ("--with", o))]
    setup = (ROOT / "skills/data-platform/SKILL.md").read_text()
    for name, folder in WHEELS.items():
        assert f"{name} @ $REPO#subdirectory={folder}" in setup, f"Setup no longer installs {name}"
    env = {**os.environ, "UV_TOOL_DIR": str(root / "tools"), "UV_TOOL_BIN_DIR": str(root / "bin")}
    done = subprocess.run(command, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    python = root / "tools" / "edgartools-data" / "bin" / "python"
    assert (root / "bin" / "edgar-warehouse").is_file() and python.is_file()
    return python, root


def _run(python, *arguments, env=None, cwd=None, document=None):
    if arguments[:2] == ("-m", "edgar_warehouse.cli"):  # the `edgar-warehouse` entry point
        arguments = ("-c", "import sys; from edgar_warehouse.cli import main; sys.exit(main(sys.argv[1:]))",
                     *arguments[2:])
    return subprocess.run([str(python), "-I", *arguments], capture_output=True, text=True, cwd=cwd,
                          env={**os.environ, **(env or {})},
                          input=None if document is None else json.dumps(document))


def test_the_bundle_installs_whole_with_no_file_in_two_wheels(installed):
    python, root = installed
    result = _run(python, "-c", f'''
import importlib, importlib.metadata as m, json, pkgutil, edgar_warehouse
names = {{d.metadata["Name"].lower() for d in m.distributions()}}
assert not names & set({DOMAIN!r}), names & set({DOMAIN!r})
shipped = [str(p) for dist in {list(WHEELS)!r} for p in m.files(dist)
           if str(p).startswith("edgar_warehouse/") and not str(p).endswith(".pyc")]
modules = [info.name for info in pkgutil.walk_packages(edgar_warehouse.__path__, "edgar_warehouse.")
           if not info.name.endswith(".__main__")]  # a __main__ runs its command line on import
for name in modules:
    importlib.import_module(name)
print(json.dumps({{"shipped": shipped, "modules": modules}}))
''', cwd=root)
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    twice = [path for path, count in Counter(found["shipped"]).items() if count > 1]
    assert twice == []
    assert {"edgar_warehouse.cli", "edgar_warehouse.workers.source_read", "edgar_warehouse.mdm.clean.merge",
            "edgar_warehouse.rules.cli"} <= set(found["modules"])
    assert any(p.endswith("bundle_data/skills/data-onboarding/SKILL.md") for p in found["shipped"])


def _stores(databases):
    url = lambda engine: engine.url.render_as_string(hide_password=False)
    return {"RULES_DATABASE_URL": url(databases.rules.engine),
            "BOOKKEEPING_CLEAN_DATABASE_URL": url(databases.runtime),
            "CHANGE_JOURNAL_DATABASE_URL": url(databases.ledger.engine)}


def test_doctor_passes_from_the_installed_bundle(installed, databases):
    python, root = installed
    # The console script itself, as an agent runs it; nothing from this checkout.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV", "EDGAR_RULES_ROOT"))}
    result = subprocess.run([str(root / "bin" / "edgar-warehouse"), "doctor"], capture_output=True, text=True,
                            cwd=root, env={**env, **_stores(databases)})
    report = json.loads(result.stdout)
    assert result.returncode == 0, report
    assert report["unresolved"] == [] and report["commands_named"] > 20 and report["engine"] == "loads"
    assert "bundle_data" in report["skills"]
    assert report["rules_root"]["bundled_read_only"] is True
    assert set(report["stores"].values()) == {"answers", "not set"}
    # The bundled rules are read, never written: a write names the way out.
    refused = subprocess.run([str(root / "bin" / "edgar-warehouse"), "rules", "mapdoc", "write"],
                             capture_output=True, text=True, cwd=root, env=env)
    assert refused.returncode == 2 and "EDGAR_RULES_ROOT" in refused.stderr


def test_doctor_names_a_command_no_skill_may_write(installed, tmp_path):
    python, root = installed
    home = tmp_path / "home"
    install = lambda *extra: _run(python, "-m", "edgar_warehouse.cli", "skill", "install", "--home", str(home),
                                  *extra, cwd=root)
    assert install().returncode == 0
    skills = home / ".agents/skills"
    assert (skills / "data-platform/SKILL.md").is_file() and (home / ".claude/skills/data-platform/SKILL.md").is_file()
    assert install().returncode == 0  # its own unchanged copy is replaced
    page = skills / "data-onboarding" / "SKILL.md"
    page.write_text("\n".join([
        "Run `edgar-warehouse rules invent --root x`.",
        "Run `edgar-warehouse change-journal recover bookkeeping <run-id> --nope 1`.",
        "Run `edgar-warehouse workers work|invent <profile> <run>`.",
        "Run `python -m edgar_warehouse.workers work`.",
        "See [the steps](../missing/STEPS.md).",
    ]))
    probe = _run(python, "-c", f"""
import json, pathlib
from edgar_warehouse import bundle, cli
print(json.dumps(bundle.unresolved(cli.build_parser(), pathlib.Path({str(skills)!r}))))
""", cwd=root)
    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == [
        "data-onboarding/SKILL.md: checkout-only command 'python -m edgar_warehouse'",
        "data-onboarding/SKILL.md: edgar-warehouse change-journal recover bookkeeping --nope",
        "data-onboarding/SKILL.md: edgar-warehouse rules invent",
        "data-onboarding/SKILL.md: edgar-warehouse workers invent",
        "data-onboarding/SKILL.md: link ../missing/STEPS.md",
    ]
    # A changed copy is never overwritten, and a refusal writes nothing.
    rules = tmp_path / "rules"
    refused = install("--rules", str(rules))
    assert refused.returncode != 0 and "was changed after it was installed" in refused.stderr
    assert not rules.exists()


@pytest.fixture
def empty_rules_database():
    """A PG16 server of its own: the Rules Database must be named `rules`."""
    name = f"bundle-rules-{uuid4().hex[:10]}"
    subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432",
                    "-e", "POSTGRES_PASSWORD=test", "postgres:16-alpine"], capture_output=True, check=True)
    try:
        # The image runs a temporary server while it initializes, then
        # restarts: wait for its own "init process complete", then readiness.
        deadline = time.monotonic() + 60
        def ready():
            logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout
            return "init process complete" in logs and subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres", "-h", "127.0.0.1"],
                capture_output=True).returncode == 0

        while not ready():
            if time.monotonic() > deadline:
                pytest.fail("PostgreSQL 16 did not finish initializing")
            time.sleep(0.2)
        for statement in ("CREATE ROLE rules_agent LOGIN PASSWORD 'test'", "CREATE ROLE rules_approver NOLOGIN",
                          "CREATE DATABASE rules"):
            subprocess.run(["docker", "exec", name, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1",
                            "-c", statement], capture_output=True, check=True)
        port = subprocess.run(["docker", "port", name, "5432/tcp"], capture_output=True, text=True,
                              check=True).stdout.strip().rsplit(":", 1)[1]
        yield f"postgresql://postgres:test@127.0.0.1:{port}/rules"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def test_the_rules_creator_runs_from_the_bundle_on_an_empty_rules_database(installed, empty_rules_database, tmp_path):
    python, root = installed
    url = empty_rules_database
    env = {"RULES_MIGRATION_DATABASE_URL": url, "RULES_DATABASE_URL": url}
    cli = lambda *a: _run(python, "-m", "edgar_warehouse.cli", *a, env=env, cwd=root)
    folder = tmp_path / "rules"
    assert cli("skill", "install", "--home", str(tmp_path / "home"), "--rules", str(folder)).returncode == 0
    for command in (("rules", "init"), ("rules", "migrate")):
        done = cli(*command)
        assert done.returncode == 0, done.stderr
    loaded = cli("rules", "load", "--root", str(folder), "--version", "bundle-1")
    assert loaded.returncode == 0, loaded.stderr
    saved = cli("rules", "save", "--source", "gleif", "--version", "bundle-2", str(folder / "sources/gleif/source.yaml"))
    assert saved.returncode == 0, saved.stderr
    status = cli("rules", "status", "--source", "gleif")
    assert status.returncode == 0, status.stderr
    rows = {row["version"]: row["digest"] for row in json.loads(status.stdout)}
    gleif = [d["digest"] for d in json.loads(loaded.stdout) if (d["kind"], d["name"]) == ("source", "gleif")]
    assert [rows["bundle-1"]] == gleif and rows["bundle-2"] == json.loads(saved.stdout)["digest"] == gleif[0]


def test_parsing_runs_through_the_installed_bundle(installed, databases, tmp_path):
    python, root = installed
    store = Artifacts()
    grant_profile(databases.admin, profile="source.read", worker="bk_runtime", verifier="bk_verifier")
    body = files.pipeline("sec-13f-reading")
    saved = databases.rules.save("pipeline", "sec-13f-reading", "1", body)
    contract_path = ROOT / "crates/source-contract/contracts/thirteenf/contract.yaml"
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), contract_path.read_bytes())
    xml = store.put_bytes((tmp_path / "filing.xml").as_uri(),
                          (contract_path.parent / "fixtures/one-row.xml").read_bytes())
    input_ref = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": [xml]})
    output = (tmp_path / "holdings.json").as_uri()
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "units": [{
        "keys": {"batch_id": "sample"}, "input": input_ref, "output": output, "cursor": {"offset": 0}}]})
    databases.rules.prove("pipeline", "sec-13f-reading", "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("pipeline", "sec-13f-reading", "1")
    folder = tmp_path / "rules"
    assert _run(python, "-m", "edgar_warehouse.cli", "skill", "install", "--home", str(tmp_path / "home"),
                "--rules", str(folder), cwd=root).returncode == 0
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri(),
           "EDGAR_RULES_ROOT": str(folder)}

    def command(*args, **extra):
        done = _run(python, "-m", *args, env={**env, **extra}, cwd=root)
        assert done.returncode == 0, done.stderr
        return done.stdout

    submitted = command("edgar_warehouse.cli", "rules", "run", "--pipeline", "sec-13f-reading", "--target", "read",
                        "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"])
    run_id = json.loads(submitted)["run"]["run_id"]
    command("edgar_warehouse.cli", "workers", "work", "source.read", run_id)
    verifier = databases.verifier.url.render_as_string(hide_password=False)
    command("edgar_warehouse.cli", "workers", "verify", "source.read", run_id, "--reports", (tmp_path / "reports").as_uri(),
            BOOKKEEPING_CLEAN_DATABASE_URL=verifier)
    state = json.loads(command("edgar_warehouse.cli", "bookkeeping", "finalize", run_id))
    assert state["counts"] == {"verified": 1} and state["run"]["state"] == "complete"
    assert json.loads((tmp_path / "holdings.json").read_bytes())["artifacts"][0]["tables"][
        "sec_thirteenf_holding"][0]["share_type"] == "SH"


MASTER = {
    "pipeline": "parse-and-master-fixture",
    "bookkeeping": {"version": 1, "targets": {"master": {
        "lease_seconds": 120, "heartbeat_seconds": 30,
        "retry": {"attempts": 5, "base_ms": 100, "cap_ms": 5000},
        "allow_zero_work": False,
        "steps": [
            {"name": "read", "operation": "source.read", "requires": [], "key": "{batch_id}",
             "leases": ["source-output:{batch_id}"], "checks": ["input.hash", "output.receipt", "source.output"]},
            {"name": "prepare", "operation": "mdm.prepare", "requires": ["read"], "key": "{batch_id}",
             "leases": ["mdm-prepare:{batch_id}"], "checks": ["input.hash", "output.receipt", "mdm.prepared"]},
            {"name": "merge", "operation": "mdm.merge", "requires": ["prepare"], "key": "{batch_id}",
             "leases": ["mdm:consumer:{consumer}"], "checks": ["input.hash", "output.receipt", "mdm.committed"]}],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}},
}
FILERS = b'{"cik": "320193", "name": "Apple Inc."}\n{"cik": "789019", "name": "Microsoft Corp"}\n'
READ_CONTRACT = b"""source: fixture.filers
execution: { profile: source.read, workers: 1, max_artifacts: 1 }
read:
  format: jsonl
  limits: { max_bytes: 1048576, max_records: 1000 }
  tables:
    filers:
      each: record
      columns:
        cik: { text: { path: cik } }
        name: { text: { path: name } }
"""


@pytest.mark.parametrize("trial_mode", ["configured", "custom-step", "parallel-records", "integer-records", "artifact-context", "source-coercion", "selected-sequences", "reference-lookup", "raw-person", "object-records", "combined-records", "choice-records"])
def test_parse_then_master_runs_through_the_installed_bundle(installed, databases, tmp_path, trial_mode):
    """G3: captured records, read by the engine, prepared and merged into Clean
    MDM in one Rules run, every step by a worker and a separate verifier from
    the installed bundle."""
    from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
    from edgar_warehouse.mdm.clean.store import migrate, register_policy
    from sqlalchemy import create_engine, text
    from tests.integration import test_clean_mdm_postgres as core
    from tests.support.rules_approval import approve
    from tests.support.rules_authority import register_dataset

    custom_trial = trial_mode == "custom-step"
    combined_trial = trial_mode == "combined-records"
    profiles = ("source.read", *(("source.combine",) if combined_trial else ()), "mdm.prepare", "mdm.merge")
    python, root = installed
    store = Artifacts()
    for profile in profiles:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    mdm_name = f"mdm_bundle_{uuid4().hex[:8]}"
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {mdm_name}")
    mdm_admin = create_engine(databases.admin.url.set(database=mdm_name))
    mdm_app = create_engine(mdm_admin.url.set(username="clean_application", password="test"))
    migrate(mdm_admin, application_role="clean_application")
    migrate_guard(mdm_admin, runtime_role="clean_application")
    with mdm_admin.begin() as conn:
        policy = register_policy(conn, {"version": 1, "required_consumers": ["export"], "automatic_rules": [],
                                        "fields": {"company": {"name": {"sources": ["fixture.filers"]}}}})
        register_dataset(conn, "fixture.filers", "1", core.contract_body(adapter={
            "version": "v1", "kind": "company", "record_key": ["cik"], "identifiers": {"cik": "cik"},
            "fields": {"name": "name"}}))

    if trial_mode in ("raw-person", "object-records"):
        with mdm_admin.begin() as conn:
            policy = register_policy(conn, files.policy())
            register_dataset(conn, "sec.submissions.person.v1", "1",
                             files.mdm_contract("sec.submissions.person", "sec.submissions.person.v1"))

    with mdm_admin.begin() as conn:
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO bk_verifier")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO bk_verifier")
    mdm_reader = create_engine(mdm_admin.url.set(username="bk_verifier", password="test"))
    pipeline_name = f"parse-and-master-{trial_mode}"
    pipeline = copy.deepcopy({**MASTER, "pipeline": pipeline_name})
    if combined_trial:
        steps = pipeline["bookkeeping"]["targets"]["master"]["steps"]
        steps.insert(1, {"name": "combine", "operation": "source.combine", "requires": ["read"], "key": "{batch_id}",
                         "leases": ["combined-output:{batch_id}"], "checks": ["input.hash", "output.receipt", "source.combined"]})
        next(step for step in steps if step["name"] == "prepare")["requires"] = ["combine"]
    saved = databases.rules.save("pipeline", pipeline_name, "1", pipeline)
    contract_bytes, filer_bytes = READ_CONTRACT, FILERS
    if trial_mode == "choice-records":
        spec = {"execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1}, "read": {
            "format": "jsonl", "limits": {"max_bytes": 1048576, "max_records": 10}, "tables": {
                "filers": {"each": "record", "columns": {"cik": {"text": {"path": "cik"}}, "name": {
                    "choose": {"condition": {"value": {"path": "active"}},
                               "then": {"coalesce": {"values": [{"value": {"path": "name"}}, {"value": {"path": "alternate"}}], "skip": "falsey"}},
                               "else": {"value": {"path": "alternate"}}}}}}}}}
        contract_bytes = json.dumps(spec).encode()
        filer_bytes = b"".join(json.dumps({**json.loads(line), "name": None, "alternate": json.loads(line)["name"], "active": n == 0}).encode() + b"\n"
                               for n, line in enumerate(FILERS.splitlines()))
    if combined_trial:
        spec = {"execution": {"profile": "source.read", "workers": 2, "max_artifacts": 2}, "read": {
            "format": "json", "limits": {"max_bytes": 1048576, "max_records": 10}, "tables": {
                "filers": {"each": "companies", "columns": {"cik": {"text": {"path": "cik"}}, "name": {"text": {"path": "name"}}}},
                "aliases": {"each": "aliases", "columns": {"cik": {"text": {"path": "cik"}}, "name": {"text": {"path": "name"}},
                                                       "rank": {"integer": {"path": "rank"}}}}}}}
        contract_bytes = json.dumps(spec).encode()
        filer_bytes = json.dumps({"companies": [json.loads(line) for line in FILERS.splitlines()], "aliases": []}).encode()
    if trial_mode in ("raw-person", "object-records"):
        spec = files.source("sec.submissions.person")
        spec["execution"]["max_artifacts"] = 2
        contract_bytes = json.dumps(spec).encode()
        raw_persons = [json.loads(line) for line in (ROOT / "tests/fixtures/clean_mdm/four_companies_v1/person_raw.jsonl").read_text().splitlines()]
        filer_bytes = json.dumps(raw_persons[0]).encode()
        if trial_mode == "object-records":
            fields = {name: {"value": {"path": name}} for name in raw_persons[0]}
            assert all(set(row) == set(fields) for row in raw_persons)
            spec["read"]["tables"]["submissions"]["columns"]["record"] = {"object": {"fields": fields}}
            contract_bytes = json.dumps(spec).encode()
    if custom_trial:
        contract_bytes += b"""        release_sequence:
          custom:
            step: epoch_microseconds@1
            inputs:
              value: { date: { path: released_at } }
"""
        filer_bytes = b"".join(json.dumps({**json.loads(line), "released_at": "2026-10-03T08:30:00.123456-04:00"}).encode() + b"\n"
                               for line in FILERS.splitlines())
    if trial_mode == "reference-lookup":
        spec = {"source": "fixture.filers", "execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1},
                "read": {"format": "jsonl", "limits": {"max_bytes": 1048576, "max_records": 1000},
                         "references": {"places": {"DE": {"iso": "US-DE"}, "WA": {"iso": "US-WA"}}},
                         "tables": {"filers": {"each": "record", "columns": {
                             "cik": {"text": {"path": "cik"}}, "name": {"text": {"path": "name"}},
                             "jurisdiction": {"lookup": {"reference": "places", "column": "iso",
                                                         "on_missing": "error", "key": {"text": {"path": "state", "case": "upper"}}}}}}}}}
        contract_bytes = json.dumps(spec).encode()
        filer_bytes = b"".join(json.dumps({**json.loads(line), "state": state}).encode() + b"\n"
                               for line, state in zip(FILERS.splitlines(), [" de ", "wa"], strict=True))
    if trial_mode == "integer-records":
        contract_bytes = contract_bytes.replace(b"cik: { text: { path: cik } }", b"cik: { integer: { path: cik } }")
        contract_bytes += b"""        is_xbrl: { integer: { path: is_xbrl, as: boolean, default: false, on_invalid: default } }
"""
        filer_bytes = b"".join(json.dumps({**json.loads(line), "is_xbrl": flag}).encode() + b"\n"
                               for line, flag in zip(FILERS.splitlines(), [0.9, True], strict=True))
    if trial_mode in {"parallel-records", "source-coercion"}:
        contract_bytes = b"""source: fixture.filers
execution: { profile: source.read, workers: 1, max_artifacts: 1 }
read:
  format: json
  limits: { max_bytes: 1048576, max_records: 1000 }
  tables:
    filers:
      each:
        parallel:
          path: "."
          anchor: cik
          fields: { cik: cik, name: name }
          lengths: equal
      columns:
        cik: { text: { path: cik } }
        name: { text: { path: name } }
"""
        rows = [json.loads(line) for line in FILERS.splitlines()]
        filer_bytes = json.dumps({key: [row[key] for row in rows] for key in ("cik", "name")}).encode()
        if trial_mode == "source-coercion":
            contract_bytes = contract_bytes.replace(b"fields: { cik: cik, name: name }", b"fields: { cik: cik, name: name, flag: flag, evidence: evidence, character: character }")
            contract_bytes = contract_bytes.replace(b"lengths: equal", b"lengths: equal\n          on_invalid_object: empty\n          strings: characters")
            contract_bytes += b"""        flag: {text: {path: flag, coerce: python}}
        evidence: {text: {path: evidence, coerce: python}}
        character: {text: {path: character, coerce: python}}
"""
            payload = json.loads(filer_bytes)
            payload.update(flag=[True, False], evidence=[{'z': 1, 'a': []}, [None, True]], character='é🦀')
            filer_bytes = json.dumps(payload).encode()
    if trial_mode == "artifact-context":
        contract_bytes = b"""source: fixture.filers
execution: { profile: source.read, workers: 2, max_artifacts: 2 }
read:
  format: json
  context:
    cik: {type: integer}
    name: {type: text}
  limits: { max_bytes: 1048576, max_records: 1000 }
  tables:
    filers:
      each: .
      columns:
        cik: {context: {name: cik}}
        name: {context: {name: name}}
"""
        filer_bytes = b'{"cik":0,"name":"document facts remain separate"}'
    if trial_mode == "selected-sequences":
        contract_bytes = b"""source: fixture.filers
execution: {profile: source.read, workers: 2, max_artifacts: 2}
read:
  format: json
  context:
    first_n: {type: integer}
  record_count: {path: count, table: filers}
  limits: {max_bytes: 1048576, max_records: 1000}
  tables:
    filers:
      take: {context: {name: first_n}}
      each:
        parallel:
          path: .
          anchor: cik
          fields: {cik: cik, name: name}
          lengths: anchor
          objects: indexed
          validation: selected
      columns:
        cik: {integer: {path: cik}}
        name: {text: {path: name}}
"""
        filer_bytes = b'{"count":2,"cik":[320193,789019],"name":["Apple Inc.","Microsoft Corp"]}'
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), contract_bytes)
    filers = store.put_bytes((tmp_path / "filers.jsonl").as_uri(), filer_bytes)
    read_manifest = {"version": 1, "contract": contract, "artifacts": [filers]}
    if trial_mode == "artifact-context":
        entries = []
        for values in ({"cik": 320193, "name": "Apple Inc."}, {"cik": 789019, "name": "Microsoft Corp"}):
            bound = store.put(tmp_path.as_uri(), {"version": 1, "input": filers, "values": values})
            entries.append({"input": filers, "context": bound})
        read_manifest = {"version": 2, "contract": contract, "artifacts": entries}
    if trial_mode == "selected-sequences":
        unselected = store.put_bytes((tmp_path / "unselected.json").as_uri(), b'{"count":1,"cik":{"0":"invalid indexed value"},"name":null}')
        entries = []
        for input_ref, first_n in [(filers, 2), (unselected, 0)]:
            bound = store.put(tmp_path.as_uri(), {"version": 1, "input": input_ref, "values": {"first_n": first_n}})
            entries.append({"input": input_ref, "context": bound})
        read_manifest = {"version": 2, "contract": contract, "artifacts": entries}
    if trial_mode in ("raw-person", "object-records"):
        second = store.put_bytes((tmp_path / "person2.json").as_uri(), json.dumps(raw_persons[1]).encode())
        read_manifest["artifacts"] = [filers, second]
    if combined_trial:
        aliases = [{"cik": "320193", "name": "Apple alt 2", "rank": 2}, {"cik": "320193", "name": "Apple alt 1", "rank": 1},
                   {"cik": "320193", "name": "Apple alt 1", "rank": 3}, {"cik": "789019", "name": "Microsoft alt", "rank": 1}]
        auxiliary = store.put_bytes((tmp_path / "aliases.json").as_uri(), json.dumps({"companies": [], "aliases": aliases}).encode())
        read_manifest["artifacts"] = [filers, auxiliary]
    read_input = store.put(tmp_path.as_uri(), read_manifest)
    out = tmp_path / "out"
    keys = {"batch_id": "filers", "consumer": "fixture/filers"}
    unit_body = {"version": 2, "steps": {
        "read": [{"keys": keys, "input": read_input, "output": (out / "reading.json").as_uri(), "cursor": {}}],
        "prepare": [{"keys": {**keys, "table": "submissions" if trial_mode in ("raw-person", "object-records") else "filers",
                              "dataset": "sec.submissions.person.v1" if trial_mode in ("raw-person", "object-records") else "fixture.filers",
                              **({"record_column": "record"} if trial_mode in ("raw-person", "object-records") else {}), "policy": policy,
                              "as_of": core.AS_OF},
                     "input": {"from": {"step": "read", "key": "filers"}},
                     "output": (out / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
        "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": "filers"}},
                   "output": (out / "merged.json").as_uri(), "cursor": {}}]}}
    if combined_trial:
        from tests.engine.test_source_combine import group, join, plan, table
        combine_contract = store.put(tmp_path.as_uri(), plan({"names": group("input", "aliases", "cik", "name", order_by=("rank", "name"), distinct=True)},
                                      {"filers": table("input", "filers", {"aliases": join("names")})}))
        unit_body["steps"]["combine"] = [{"keys": {**keys, "combine_contract_uri": combine_contract["uri"], "combine_contract_sha256": combine_contract["sha256"], "reading_name": "input"},
                                         "input": {"from": {"step": "read", "key": "filers"}},
                                         "output": (out / "combined.json").as_uri(), "cursor": {}}]
        unit_body["steps"]["prepare"][0]["input"] = {"from": {"step": "combine", "key": "filers"}}
    units = store.put(tmp_path.as_uri(), unit_body)
    databases.rules.prove("pipeline", pipeline_name, "1",
                          {"digest": saved["digest"], "batch_hash": units["sha256"], "passed": True})
    approve(databases.approver, "pipeline", pipeline_name, "1")
    databases.rules.activate("pipeline", pipeline_name, "1")

    url = lambda engine: engine.url.render_as_string(hide_password=False)
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    worker = {"MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {"BOOKKEEPING_CLEAN_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm_reader)}

    def cli(*args, **extra):
        done = _run(python, "-m", "edgar_warehouse.cli", *args, env={**env, **extra}, cwd=root)
        assert done.returncode == 0, done.stderr
        return done.stdout

    run_id = json.loads(cli("rules", "run", "--pipeline", pipeline_name, "--target", "master",
                            "--input-manifest", units["uri"], "--input-sha256", units["sha256"]))["run"]["run_id"]
    for profile in profiles:
        cli("workers", "work", profile, run_id, **worker)
        cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(), **verifier)
    if trial_mode == "choice-records":
        reading = json.loads((out / "reading.json").read_bytes())
        assert reading["artifacts"][0]["tables"]["filers"] == [json.loads(line) for line in FILERS.splitlines()]
    if combined_trial:
        combined = json.loads((out / "combined.json").read_bytes())
        rows = combined["artifacts"][0]["tables"]["filers"]
        assert rows == [{"cik": "320193", "name": "Apple Inc.", "aliases": ["Apple alt 1", "Apple alt 2"]},
                        {"cik": "789019", "name": "Microsoft Corp", "aliases": ["Microsoft alt"]}]
        assert len(store.json(combined["readings"]["input"])["artifacts"]) == 2
        scope = store.json(combined["artifacts"][0]["input"])
        assert scope["contract"] == combine_contract
        assert scope["readings"] == combined["readings"]
        prepared = json.loads((out / "mdm/manifest.json").read_bytes())
        assert [json.loads(line) for line in (out / "mdm" / prepared["batches"][0]["input"]["path"]).read_text().splitlines()] == rows
    if custom_trial:
        from edgar_warehouse.rules.steps import epoch_microseconds
        reading = json.loads((out / "reading.json").read_bytes())
        assert [row["release_sequence"] for row in reading["artifacts"][0]["tables"]["filers"]] == [
            epoch_microseconds("2026-10-03T08:30:00.123456-04:00")] * 2
    if trial_mode == "integer-records":
        reading = json.loads((out / "reading.json").read_bytes())
        rows = reading["artifacts"][0]["tables"]["filers"]
        assert [row["cik"] for row in rows] == [320193, 789019]
        assert all(type(row["cik"]) is int for row in rows)
        assert [row["is_xbrl"] for row in rows] == [False, True]
        assert all(type(row["is_xbrl"]) is bool for row in rows)
    if trial_mode == "artifact-context":
        reading = json.loads((out / "reading.json").read_bytes())
        rows = [artifact["tables"]["filers"][0] for artifact in reading["artifacts"]]
        assert rows == [{"cik": 320193, "name": "Apple Inc."}, {"cik": 789019, "name": "Microsoft Corp"}]
        assert reading["artifacts"][0]["input"] == reading["artifacts"][1]["input"]
        assert reading["artifacts"][0]["context"] != reading["artifacts"][1]["context"]
        prepared = json.loads((out / "mdm" / "manifest.json").read_bytes())
        assert len({b["input"]["path"] for b in prepared["batches"]}) == 2
        assert len({b["batch_id"] for b in prepared["batches"]}) == 2
    if trial_mode in ("raw-person", "object-records"):
        reading = json.loads((out / "reading.json").read_bytes())
        assert [artifact["tables"]["submissions"][0]["record"] for artifact in reading["artifacts"]] == raw_persons
        prepared = json.loads((out / "mdm" / "manifest.json").read_bytes())
        assert [json.loads((out / "mdm" / batch["input"]["path"]).read_bytes()) for batch in prepared["batches"]] == raw_persons
    if trial_mode == "reference-lookup":
        reading = json.loads((out / "reading.json").read_bytes())
        rows = reading["artifacts"][0]["tables"]["filers"]
        assert [row["jurisdiction"] for row in rows] == ["US-DE", "US-WA"]
    if trial_mode == "source-coercion":
        reading = json.loads((out / "reading.json").read_bytes())
        rows = reading["artifacts"][0]["tables"]["filers"]
        assert [row["flag"] for row in rows] == ['True', 'False']
        assert [row["evidence"] for row in rows] == ["{'z': 1, 'a': []}", '[None, True]']
        assert [row["character"] for row in rows] == ['é', '🦀']
    if trial_mode == "selected-sequences":
        reading = json.loads((out / "reading.json").read_bytes())
        assert reading["artifacts"][0]["tables"]["filers"] == [
            {"cik": 320193, "name": "Apple Inc."}, {"cik": 789019, "name": "Microsoft Corp"}]
        assert reading["artifacts"][1]["input"] == unselected
        assert reading["artifacts"][1]["tables"]["filers"] == []
        prepared = json.loads((out / "mdm" / "manifest.json").read_bytes())
        assert len(prepared["batches"]) == 1
        assert prepared["batches"][0]["input"]["record_count"] == 2
    state = json.loads(cli("bookkeeping", "finalize", run_id))
    assert state["counts"] == {"verified": len(profiles)} and state["run"]["state"] == "complete"
    with mdm_admin.connect() as conn:
        names = conn.execute(text("SELECT body->'fields'->'name'->>'value' FROM mdm.current_record "
                                  "WHERE object_type='stage_record' OR object_type='entity'")).scalars().all()
        records = conn.scalar(text("SELECT count(*) FROM mdm.stage_record"))
        if trial_mode in ("raw-person", "object-records"):
            assert conn.scalar(text("SELECT count(*) FROM mdm.current_entity WHERE kind='person'")) == 2
            assert conn.scalar(text("SELECT count(*) FROM mdm.current_entity WHERE kind='company'")) == 0

    mdm_admin.dispose()
    mdm_app.dispose()
    mdm_reader.dispose()
    assert records == 2, names
