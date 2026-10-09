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
import base64
import hashlib
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


def test_name_key_recipes_run_from_installed_bundle(installed):
    python, root = installed
    result = _run(python, "-c", '''
import hashlib, json
from pathlib import Path
from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read
assert files.ROOT == files.BUNDLED and files.ROOT.is_dir()
source_engine.STEPS = {}
store = Artifacts()
root = Path("name-key-proof").resolve()
root.mkdir()
names = ["Électricité Holdings Corporation /DE/", "THE A&B L.L.C.", "Wayfair Inc.", "WAYFAIR LLC"]
raw = store.put_bytes((root / "names.json").as_uri(), json.dumps({"names":[{"name":name} for name in names]}).encode())
context = store.put(root.as_uri(), {"version":1,"input":raw,"values":{}})
proof = {}
for source, first in [("sec.submissions.company", "ELECTRICITE HLDGS CORP"), ("gleif", "ELECTRICITE HLDGS CORP DE")]:
    config = files.load(files.ROOT / "sources" / source / "name-key.yaml")
    contract = store.put(root.as_uri(), config)
    manifest = store.put(root.as_uri(), {"version":2,"contract":contract,"artifacts":[{"input":raw,"context":context}]})
    task = {"input":manifest,"output":(root / (source + ".json")).as_uri(),"checks":["source.output"]}
    receipt = source_read.execute(task,store)
    assert source_read.verify({**task,"candidate":receipt},store) == ({"source.output":True},[])
    reading = store.json(receipt)
    rows = reading["artifacts"][0]["tables"]["names"]
    assert [row["key"] for row in rows] == [first,"A AND B LLC","WAYFAIR INC","WAYFAIR LLC"]
    assert reading["artifacts"][0]["input"] == raw and reading["artifacts"][0]["context"] == context
    assert not reading["artifacts"][0]["deferred"]
    proof[source] = {"contract":contract,"input":manifest,"reading":receipt}
print(json.dumps(proof))
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert set(json.loads(result.stdout)) == {"sec.submissions.company", "gleif"}


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
    retired = subprocess.run([str(python), "-I", "-c",
                              "import importlib.util; "
                              "assert importlib.util.find_spec('edgar_warehouse.loaders') is None; "
                              "assert importlib.util.find_spec('edgar_warehouse.silver_landing_store') is None"],
                             capture_output=True, text=True)
    assert retired.returncode == 0, retired.stderr
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


def test_streaming_boundary_runs_from_installed_bundle_without_checkout(installed):
    python, root = installed
    result = _run(python, "-c", '''
import hashlib, json
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules.source_engine import stream_json_array, SourceRejected
body = b'{"records":[{"n":9007199254740993,"flag":true,"nested":{"z":1,"a":2}},{"float":-3.1163038337286385e203}]}'
path = Path("captured.json")
path.write_bytes(body)
ref = {"uri": path.resolve().as_uri(), "sha256": hashlib.sha256(body).hexdigest()}
store, rows = Artifacts(), []
with store.verified_stream(ref, max_bytes=len(body)) as snapshot:
    path.write_bytes(b"changed after authentication")
    receipt = stream_json_array(snapshot, wrapper="records", on_record=lambda row, n: rows.append((n, row)),
        max_bytes=1024, max_record=512, max_records=2, record_encoding="python")
assert receipt == {"record_count": 2, "expanded_bytes": len(body)}
assert rows == [(0, {"n":9007199254740993,"flag":True,"nested":{"z":1,"a":2}}), (1, {"float":-3.1163038337286385e203})]
assert list(rows[0][1]) == ["n", "flag", "nested"]
assert list(rows[0][1]["nested"]) == ["z", "a"]
path.write_bytes(body + b" null")
bad = {"uri": path.resolve().as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
try:
    with store.verified_stream(bad, max_bytes=1024) as snapshot:
        stream_json_array(snapshot, wrapper="records", on_record=lambda row, n: None,
            max_bytes=1024, max_record=512, max_records=2)
except SourceRejected:
    pass
else:
    raise AssertionError("Trailing bytes produced a successful receipt")
print(json.dumps(receipt))
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["record_count"] == 2


def test_configured_stream_worker_runs_from_installed_bundle(installed):
    python, root = installed
    result = _run(python, "-c", '''
import json
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
store = Artifacts()
root = Path("configured-stream").resolve()
root.mkdir()
contract = {"execution":{"profile":"source.read","workers":1,"max_artifacts":1},
 "read":{"format":"json","limits":{"max_bytes":4096,"max_records":100},
  "context":{"publication_count":{"type":"integer"}},
  "tables":{"rows":{"each":".","columns":{"n":{"value":{"path":"n"}}}}},
  "stream":{"wrapper":"records","container":"none","max_input_bytes":4096,
   "max_bytes":4096,"max_record":1024,"max_records":100,"max_depth":64,
   "min_integer":-9223372036854775808,"record_encoding":"python","ordinal_context":None,"expected_records_context":"publication_count",
   "partition_bytes":4096,"partition_records":1,"max_partitions":10,
   "max_spool_bytes":65536,"max_output_rows":100}}}
ref = store.put_bytes((root / "captured.json").as_uri(), b'{"records":[{"n":1},{"n":2}]}')
rules = store.put_bytes((root / "rules.yaml").as_uri(), json.dumps(contract).encode())
context = store.put(root.as_uri(), {"version":1,"input":ref,"values":{"publication_count":2}})
manifest = store.put(root.as_uri(), {"version":2,"contract":rules,"artifacts":[{"input":ref,"context":context}]})
task = {"input":manifest,"output":(root / "index.json").as_uri(),"checks":["source.output"]}
receipt = source_read.execute(task, store)
assert source_read.verify({**task,"candidate":receipt},store) == ({"source.output":True},[])
reading = store.json(receipt)
parts = reading["artifacts"][0]["partitions"]
assert reading["version"] == 2 and len(parts) == 2
assert [store.json(part["receipt"])["tables"]["rows"][0]["n"] for part in parts] == [1,2]
combine_rules = store.put(root.as_uri(), {"execution":{"profile":"source.combine"},
 "combine":{"max_rows":100,"groups":{},"tables":{"rows":{"source":"streamed","table":"rows",
 "checks":{},"where":{},"joins":{}}}}})
combine_manifest = store.put(root.as_uri(), {"version":1,"contract":combine_rules,"readings":{"streamed":receipt}})
combine_task = {"input":combine_manifest,"output":(root / "combined.json").as_uri(),"checks":[source_combine.CHECK]}
combined = source_combine.execute(combine_task, store)
assert source_combine.verify({**combine_task,"candidate":combined}, store) == ({source_combine.CHECK:True},[])
prepare_task = {"input":combined,"output":(root / "mdm/manifest.json").as_uri(),"checks":[mdm_prepare.CHECK],
 "keys":{"table":"rows","dataset":"fixture.rows","policy":"0"*64,"consumer":"trial",
 "batch_id":"trial","as_of":"2026-10-05T00:00:00Z"}}
prepared = mdm_prepare.execute(prepare_task,store)
assert mdm_prepare.execute(prepare_task,store) == prepared
assert mdm_prepare.verify({**prepare_task,"candidate":prepared},store) == ({mdm_prepare.CHECK:True},[])
batch = store.json(prepared)["batches"][0]
assert [json.loads(line) for line in (root / "mdm" / batch["input"]["path"]).read_text().splitlines()] == [{"n":1},{"n":2}]
assert store.json(store.json(combined)["artifacts"][0]["input"])["readings"] == {"streamed":receipt}
bad_context = store.put(root.as_uri(), {"version":1,"input":ref,"values":{"publication_count":3}})
bad_manifest = store.put(root.as_uri(), {"version":2,"contract":rules,"artifacts":[{"input":ref,"context":bad_context}]})
try:
    source_read.execute({**task,"input":bad_manifest,"output":(root / "refused.json").as_uri()},store)
except ValueError as error:
    assert "record count differs" in str(error)
else:
    raise AssertionError("publication count mismatch accepted")
assert not (root / "refused.json").exists() and not (root / "refused.json.parts").exists()
print("configured stream passed")
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "configured stream passed"


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


@pytest.mark.parametrize('reading_mode', ['13f', 'company-main', 'company-page', 'company-catalog', 'company-dictionary'])
def test_parsing_runs_through_the_installed_bundle(installed, databases, tmp_path, reading_mode):
    python, root = installed
    store = Artifacts()
    grant_profile(databases.admin, profile="source.read", worker="bk_runtime", verifier="bk_verifier")
    body = files.pipeline("sec-13f-reading")
    pipeline_name = 'sec-13f-reading' if reading_mode == '13f' else f'{reading_mode}-reading'
    body['pipeline'] = pipeline_name
    saved = databases.rules.save("pipeline", pipeline_name, "1", body)
    contract_path = ROOT / "crates/source-contract/contracts/thirteenf/contract.yaml"
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), contract_path.read_bytes())
    xml = store.put_bytes((tmp_path / "filing.xml").as_uri(),
                          (contract_path.parent / "fixtures/one-row.xml").read_bytes())
    input_ref = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": [xml]})
    if reading_mode == 'company-main':
        probe = _run(python, '-c', 'import json; from edgar_warehouse.rules import files; print(json.dumps(files.source("sec.submissions.company")))', cwd=root)
        assert probe.returncode == 0, probe.stderr
        contract = store.put(tmp_path.as_uri(), json.loads(probe.stdout))
        raw = store.put_bytes((tmp_path / 'company.json').as_uri(), b'{"name":"Example","addresses":{"business":{"stateOrCountry":"DE"}}}')
        context = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': {
            'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': raw['sha256'], 'load_mode': 'default',
            'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'}})
        input_ref = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': context}]})
    if reading_mode == 'company-page':
        probe = _run(python, '-c', 'import json; from edgar_warehouse.rules import files; print(json.dumps(files.load(files.ROOT / "sources/sec.submissions.company/pagination.yaml")))', cwd=root)
        assert probe.returncode == 0, probe.stderr
        contract = store.put(tmp_path.as_uri(), json.loads(probe.stdout))
        raw = store.put_bytes((tmp_path / 'page.json').as_uri(), b'{"accessionNumber":["old","older"],"form":["20-F","10-K"],"size":["1234","1,234"]}')
        context = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': {
            'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': '0' * 64, 'load_mode': 'default'}})
        input_ref = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': context}]})
    if reading_mode in ('company-catalog', 'company-dictionary'):
        probe = _run(python, '-c', 'import json; from edgar_warehouse.rules import files; print(json.dumps(files.load(files.ROOT / "sources/sec.submissions.company/catalog.yaml")))', cwd=root)
        assert probe.returncode == 0, probe.stderr
        contract = store.put(tmp_path.as_uri(), json.loads(probe.stdout))
        payload = (b'{"fields":["ticker","exchange","cik"],"data":[["A","NYSE",1],["A-B",null,1]]}'
                   if reading_mode == 'company-catalog' else b'{"z":null,"b":{"cik_str":1,"ticker":"A","exchange":"NYSE"},"a":{"cik_str":1,"ticker":"A-B"}}')
        raw = store.put_bytes((tmp_path / 'catalog.json').as_uri(), payload)
        context = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': {
            'sync_run_id': 'catalog', 'source_name': 'company_tickers_exchange', 'last_synced_at': '2026-10-05T00:00:00Z'}})
        input_ref = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': context}]})
    output = (tmp_path / "holdings.json").as_uri()
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "units": [{
        "keys": {"batch_id": "sample"}, "input": input_ref, "output": output, "cursor": {"offset": 0}}]})
    databases.rules.prove("pipeline", pipeline_name, "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("pipeline", pipeline_name, "1")
    folder = tmp_path / "rules"
    assert _run(python, "-m", "edgar_warehouse.cli", "skill", "install", "--home", str(tmp_path / "home"),
                "--rules", str(folder), cwd=root).returncode == 0
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri(),
           "EDGAR_RULES_ROOT": str(folder)}

    def command(*args, **extra):
        done = _run(python, "-m", *args, env={**env, **extra}, cwd=root)
        assert done.returncode == 0, done.stderr
        return done.stdout

    submitted = command("edgar_warehouse.cli", "rules", "run", "--pipeline", pipeline_name, "--target", "read",
                        "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"])
    run_id = json.loads(submitted)["run"]["run_id"]
    command("edgar_warehouse.cli", "workers", "work", "source.read", run_id)
    verifier = databases.verifier.url.render_as_string(hide_password=False)
    command("edgar_warehouse.cli", "workers", "verify", "source.read", run_id, "--reports", (tmp_path / "reports").as_uri(),
            BOOKKEEPING_CLEAN_DATABASE_URL=verifier)
    state = json.loads(command("edgar_warehouse.cli", "bookkeeping", "finalize", run_id))
    assert state["counts"] == {"verified": 1} and state["run"]["state"] == "complete"
    tables = json.loads((tmp_path / "holdings.json").read_bytes())["artifacts"][0]["tables"]
    if reading_mode == '13f':
        assert tables['sec_thirteenf_holding'][0]['share_type'] == 'SH'
    elif reading_mode == 'company-main':
        assert tables['company'][0]['entity_name'] == 'Example'
        assert tables['company'][0]['raw_object_id'] == raw['sha256']
        assert tables['addresses'][0]['business_address']['country'] == 'US'
        assert tables['filings'] == []
    elif reading_mode == 'company-page':
        assert tables['filings'][0]['form'] == '20-F'
        assert tables['filings'][0]['size'] == 1234
        assert tables['filings'][1]['size'] is None
        assert tables['filings'][0]['raw_object_id'] == '0' * 64
    else:
        assert [row['ticker'] for row in tables['tickers']] == ['A', 'A-B']
        assert [row['source_rank'] for row in tables['tickers']] == [1, 2]
        assert tables['tickers'][1]['exchange'] is None
        assert all(row['last_sync_run_id'] == 'catalog' for row in tables['tickers'])


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


@pytest.mark.parametrize("trial_mode", ["configured", "parquet-records", "custom-step", "parallel-records", "integer-records", "artifact-context", "source-coercion", "selected-sequences", "reference-lookup", "raw-person", "object-records", "combined-records", "choice-records", "streamed-records", "xml-streamed-records", "xml-streamed-recovery"])
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
    recovery_trial = trial_mode == "xml-streamed-recovery"
    xml_trial = trial_mode in ("xml-streamed-records", "xml-streamed-recovery")
    streamed_trial = trial_mode == "streamed-records" or xml_trial
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
    if trial_mode == "parquet-records":
        import io
        import pyarrow as pa
        import pyarrow.parquet as pq
        stream = io.BytesIO()
        pq.write_table(pa.Table.from_pylist([json.loads(line) for line in FILERS.splitlines()]), stream)
        filer_bytes = stream.getvalue()
        contract_bytes = json.dumps({"execution": {"profile":"source.read", "workers":1, "max_artifacts":1},
            "read": {"format":"parquet", "parquet":{"columns":["cik","name"]},
                "limits":{"max_bytes":1048576,"max_records":1000},
                "tables":{"filers":{"each":"rows", "columns":{
                    "cik":{"text":{"path":"cik"}}, "name":{"text":{"path":"name"}}}}}}}).encode()
    if streamed_trial:
        spec = {"execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1}, "read": {
            "format": "json", "limits": {"max_bytes": 4096, "max_records": 10}, "tables": {
                "filers": {"each": ".", "columns": {"cik": {"text": {"path": "cik"}},
                                                     "name": {"text": {"path": "name"}}}}},
            "stream": {"wrapper": "records", "container": "none", "max_input_bytes": 4096,
                       "max_bytes": 4096, "max_record": 1024, "max_records": 10, "max_depth": 64,
                       "min_integer": -9223372036854775808, "record_encoding": "python",
                       "ordinal_context": None, "partition_bytes": 4096, "partition_records": 1,
                       "max_partitions": 10, "max_spool_bytes": 65536, "max_output_rows": 10}}}
        filer_bytes = json.dumps({"records": [json.loads(line) for line in FILERS.splitlines()]}).encode()
        if xml_trial:
            from xml.sax.saxutils import escape
            for column in spec["read"]["tables"]["filers"]["columns"].values():
                column["text"]["path"] += ".$"
            stream = spec["read"]["stream"]
            for name in ("wrapper", "min_integer", "record_encoding"):
                del stream[name]
            stream.update(framing="xml_records", xml={"namespace": "urn:filers", "root": "Data",
                "header": "Header", "container": "Records", "record": "Record", "record_wrapper": None},
                header_read={"format": "json", "limits": {"max_bytes": 1024, "max_records": 1},
                    "references": {"counts": {"2": {"valid": True}}},
                    "assertions": [{"test": {"lookup": {"reference": "counts", "column": "valid",
                        "key": {"text": {"path": "Count.$"}}, "on_missing": "null"}}, "reason": "pinned-count"}],
                    "tables": {"header": {"each": "no_rows", "columns": {}}}})
            rows = [json.loads(line) for line in FILERS.splitlines()]
            records = "".join(f"<Record><cik>{escape(row['cik'])}</cik><name>{escape(row['name'])}</name></Record>" for row in rows)
            filer_bytes = f"<Data xmlns='urn:filers'><Header><Count>2</Count></Header><Records>{records}</Records></Data>".encode()
            if recovery_trial:
                context = {"publication_count": {"type": "integer"}}
                spec["read"]["context"] = context
                stream["header_read"]["context"] = copy.deepcopy(context)
                stream["expected_records_context"] = "publication_count"
                stream["header_read"]["assertions"].append({"test": {"equal": {
                    "left": {"integer": {"path": "Count.$"}},
                    "right": {"context": {"name": "publication_count"}}}},
                    "reason": "Header count must equal the input-bound publication count"})
        contract_bytes = json.dumps(spec).encode()
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
    if recovery_trial:
        bound = store.put(tmp_path.as_uri(), {"version": 1, "input": filers, "values": {"publication_count": 2}})
        read_manifest = {"version": 2, "contract": contract, "artifacts": [{"input": filers, "context": bound}]}
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

    if recovery_trial:
        # An immutable malformed capture remains a failed run; correcting an
        # input creates a new run rather than changing its pinned manifest.
        bad_raw = store.put_bytes((tmp_path / "bad-filers.xml").as_uri(),
                                  filer_bytes.replace(b"<Count>2</Count>", b"<Count>3</Count>"))
        bad_context = store.put(tmp_path.as_uri(), {"version": 1, "input": bad_raw,
                                                  "values": {"publication_count": 2}})
        bad_read = store.put(tmp_path.as_uri(), {**read_manifest,
            "artifacts": [{"input": bad_raw, "context": bad_context}]})
        bad_units_body = copy.deepcopy(unit_body)
        bad_out = tmp_path / "refused"
        bad_units_body["steps"]["read"][0].update(input=bad_read, output=(bad_out / "reading.json").as_uri())
        bad_units_body["steps"]["prepare"][0]["output"] = (bad_out / "mdm/manifest.json").as_uri()
        bad_units_body["steps"]["merge"][0]["output"] = (bad_out / "merged.json").as_uri()
        bad_units = store.put(tmp_path.as_uri(), bad_units_body)
        bad_run = json.loads(cli("rules", "run", "--pipeline", pipeline_name, "--target", "master",
            "--input-manifest", bad_units["uri"], "--input-sha256", bad_units["sha256"]))["run"]["run_id"]
        rejected = _run(python, "-m", "edgar_warehouse.cli", "workers", "work", "source.read", bad_run,
                        env={**env, **worker}, cwd=root)
        assert rejected.returncode == 1 and "pinned-count" in rejected.stderr, rejected.stderr
        for downstream in ("mdm.prepare", "mdm.merge"):
            cli("workers", "work", downstream, bad_run, **worker)
        assert not (bad_out / "reading.json").exists() and not (bad_out / "reading.json.parts").exists()
        assert not (bad_out / "mdm/manifest.json").exists() and not (bad_out / "merged.json").exists()
        failed_state = json.loads(cli("bookkeeping", "status", bad_run))
        assert failed_state["counts"].get("verified", 0) == 0
        with mdm_reader.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM mdm.stage_record")) == 0
            assert conn.scalar(text("SELECT count(*) FROM mdm.current_record")) == 0

    run_id = json.loads(cli("rules", "run", "--pipeline", pipeline_name, "--target", "master",
                            "--input-manifest", units["uri"], "--input-sha256", units["sha256"]))["run"]["run_id"]
    if recovery_trial:
        from urllib.parse import unquote, urlparse
        from pathlib import Path
        captured = Path(unquote(urlparse(filers["uri"]).path))
        unavailable = tmp_path / "temporarily-unavailable.xml"
        captured.rename(unavailable)
        try:
            rejected = _run(python, "-m", "edgar_warehouse.cli", "workers", "work", "source.read", run_id,
                            env={**env, **worker}, cwd=root)
            assert rejected.returncode == 1 and "Artifact missing or unreadable" in rejected.stderr, rejected.stderr
            assert filers["uri"] in rejected.stderr
            assert not (out / "reading.json").exists() and not (out / "reading.json.parts").exists()
            with mdm_reader.connect() as conn:
                assert conn.scalar(text("SELECT count(*) FROM mdm.stage_record")) == 0
        finally:
            unavailable.rename(captured)
    for profile in profiles:
        if recovery_trial and profile == "source.read":
            deadline = time.monotonic() + 10
            while True:
                cli("workers", "work", profile, run_id, **worker)
                if (out / "reading.json").exists(): break
                if time.monotonic() >= deadline: pytest.fail("Source retry did not become claimable")
                time.sleep(0.01)
        else:
            cli("workers", "work", profile, run_id, **worker)
        cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(), **verifier)
    if recovery_trial:
        recovered = json.loads(cli("bookkeeping", "status", run_id))
        read_item = next(item for item in recovered["items"] if item["step"] == "read")
        assert read_item["state"] == "verified" and read_item["attempts"] == 2
    if streamed_trial:
        reading = json.loads((out / "reading.json").read_bytes())
        assert reading["version"] == 2
        assert len(reading["artifacts"][0]["partitions"]) == 2
        prepared = json.loads((out / "mdm/manifest.json").read_bytes())
        assert len(prepared["batches"]) == 1
        rows = [json.loads(line) for line in (out / "mdm" / prepared["batches"][0]["input"]["path"]).read_text().splitlines()]
        assert rows == [json.loads(line) for line in FILERS.splitlines()]
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


def test_all_gleif_member_contracts_read_from_installed_bundle(installed):
    """Packaged templates must execute without checkout or fixture imports."""
    python, root = installed
    result = _run(python, '-c', '''
import hashlib, io, json, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from edgar_warehouse.rules import files
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read
from edgar_warehouse.mdm.clean import gleif_source
from edgar_warehouse.mdm.clean.gleif_publication import attest_publication
assert not hasattr(gleif_source, "inspect_archive")
store = Artifacts()
lei = "5493001KJTIIGC8Y1R12"
date = "2026-09-11T16:00:00+00:00"
for member in ["level1", "relationships", "reporting-exceptions"]:
    for format in ["json", "xml"]:
        folder = Path(member + "-" + format).resolve()
        folder.mkdir()
        rules = files.load(files.ROOT / "sources" / "gleif" / f"{member}-{format}.yaml")
        rules["read"]["references"]["approved_scope"] = {lei:{"selected":True}}
        row = {"LEI":{"$":lei}}
        if member == "relationships":
            row = {"RelationshipRecord":{"Relationship":{"StartNode":{"NodeID":{"$":lei}},
                "EndNode":{"NodeID":{"$":lei}}}}}
        if format == "json":
            wrapper = {"level1":"records", "relationships":"relations", "reporting-exceptions":"exceptions"}[member]
            body = json.dumps({wrapper:[row]}).encode()
        else:
            spec = rules["read"]["stream"]["xml"]
            refs = rules["read"]["stream"]["header_read"]["references"]
            refs.update(content_dates={date:{"valid":True}}, record_counts={"1":{"valid":True}},
                file_content={"GLEIF_FULL_PUBLISHED":{"valid":True,"requires_delta":False}}, delta_starts={})
            def element(parent, name): return ET.SubElement(parent, "{" + spec["namespace"] + "}" + name)
            document = ET.Element("{" + spec["namespace"] + "}" + spec["root"])
            header = element(document, spec["header"])
            for name,text in [("ContentDate",date),("FileContent","GLEIF_FULL_PUBLISHED"),("RecordCount","1")]:
                element(header,name).text = text
            container = element(document,spec["container"])
            def fields(parent, value):
                for key,item in value.items():
                    if key == "$": parent.text = item
                    else: fields(element(parent,key),item)
            fields(element(container,spec["record"]), row["RelationshipRecord"] if member == "relationships" else row)
            body = ET.tostring(document,encoding="utf-8",xml_declaration=True)
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped,"w",compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("captured."+format,body)
        raw = store.put_bytes((folder / "captured.zip").as_uri(),zipped.getvalue())
        seen = []
        attestation = attest_publication(io.BytesIO(zipped.getvalue()), member=member.replace("-","_"),
            metadata={"format":format+".zip", "cdf_version":gleif_source.FORMATS[member.replace("-","_")][0],
                "content_date":date, "file_content":"GLEIF_FULL_PUBLISHED", "delta_start":None, "record_count":1},
            expected_sha256=raw["sha256"], on_record=lambda record,index: seen.append((record,index)))
        assert seen == [(row,0)] and attestation["record_count"] == 1
        assert attestation["canonical_source_hash"] == hashlib.sha256(
            (json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()).hexdigest()
        contract = store.put_bytes((folder / "contract.yaml").as_uri(),json.dumps(rules).encode())
        context = store.put(folder.as_uri(),{"version":1,"input":raw,"values":{"publication_count":1}})
        manifest = store.put(folder.as_uri(),{"version":2,"contract":contract,"artifacts":[{"input":raw,"context":context}]})
        task = {"input":manifest,"output":(folder / "reading.json").as_uri(),"checks":["source.output"]}
        receipt = source_read.execute(task,store)
        assert source_read.execute(task,store) == receipt
        assert source_read.verify({**task,"candidate":receipt},store) == ({"source.output":True},[])
        artifact = store.json(receipt)["artifacts"][0]
        rows = [row for part in artifact["partitions"] for row in store.json(part["receipt"])["tables"][member.replace("-","_")]]
        assert artifact["record_count"] == 1 and rows == [{"record":row,"source_index":1}]
print("six installed GLEIF member contracts passed")
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'six installed GLEIF member contracts passed'


@pytest.mark.parametrize("with_census", [False, True])
def test_company_combination_blueprint_runs_from_installed_bundle(installed, with_census):
    """Installed raw readings compose/prepare without retained Company loaders."""
    python, root = installed
    result = _run(python, '-c', '''
import json
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
store = Artifacts()
with_census = WITH_CENSUS
folder = Path("company-composition-census" if with_census else "company-composition").resolve()
folder.mkdir()
blueprints = files.ROOT / "sources/sec.submissions.company"
from edgar_warehouse.workers.source_mapping import project_record
from edgar_warehouse.mdm.clean import company_source
assert not hasattr(company_source,"business_address")
landed={"street1":"  Raw  ","street2":None,"city":"City","zip_code":"12345",
        "state_or_country":" de ","country_code":None}
assert project_record(landed,files.load(blueprints/"landed-address.yaml"),column="fields")=={
    "street":"  Raw  ","street2":None,"city":"City","postal_code":"12345","region":" de ","country":"US"}
date = "2026-10-04T00:00:00Z"
context = {"cik":1,"sync_run_id":"capture","raw_object_id":"0"*64,"load_mode":"default"}
def read(name, template, payload, context):
    raw = store.put_bytes((folder / (name+".json")).as_uri(), json.dumps(payload).encode())
    context = dict(context)
    if "raw_object_id" in context: context["raw_object_id"] = raw["sha256"]
    bound = store.put(folder.as_uri(),{"version":1,"input":raw,"values":context})
    rules = store.put(folder.as_uri(), files.load(blueprints / template))
    manifest = store.put(folder.as_uri(),{"version":2,"contract":rules,"artifacts":[{"input":raw,"context":bound}]})
    task = {"input":manifest,"output":(folder / (name+"-reading.json")).as_uri(),"checks":["source.output"]}
    receipt = source_read.execute(task,store)
    assert source_read.verify({**task,"candidate":receipt},store) == ({"source.output":True},[])
    return receipt
main = read("main","census-main.yaml" if with_census else "source.yaml",{"name":"Example","filings":{"recent":{
    "accessionNumber":["r1","r2"],"form":["8-K","10-K"]}},
    "addresses":{"business":{"street1":"Raw","stateOrCountry":"X0"}}},
    {**context,"recent_limit":None,"last_synced_at":date})
pages = read("pages","pagination.yaml",{"accessionNumber":["p1","p2"],"form":["20-F","10-K"]},context)
catalog_context = {"sync_run_id":"catalog","last_synced_at":date,"source_name":"exchange"}
exchange = read("catalog-exchange","catalog.yaml",{"fields":["cik","ticker"],"data":[[1,"B"],[1,"A"]]},catalog_context)
tickers = read("catalog-tickers","catalog.yaml",{"0":{"cik_str":1,"ticker":"A"},"1":{"cik_str":1,"ticker":"C"}},
    {**catalog_context,"source_name":"tickers"})
refs = {"main":main,"pages":pages,"catalog_exchange":exchange,"catalog_tickers":tickers}
rules = files.load(blueprints / ("combine-census.yaml" if with_census else "combine.yaml"))
if with_census:
    census = {"version":"sec-gleif-name-census-v1","sec":{"filers":1},
        "gleif":{"file_content":"GLEIF_FULL_PUBLISHED"},
        "normalizers":{"sec":"normalize_text@sec-legal-form-kept-v1","gleif":"normalize_text@legal-form-kept-v1"},
        "entries":{"EXAMPLE":{"cik_count":1,"lei_count":1,"ciks":["0000000001"],"leis":[["L1","2026-09-11"]]}},
        "cascade":{"version":"sec-gleif-cascade-v1","assignments":{"0000000001":{"lei":"L1","pass":"P1"}}}}
    raw = store.put(folder.as_uri(),census)
    def bind(value):
        if isinstance(value,str): return raw["sha256"] if value == "0"*64 else value
        if isinstance(value,list): return [bind(item) for item in value]
        if isinstance(value,dict): return {key:bind(item) for key,item in value.items()}
        return value
    config = bind(files.load(blueprints / "census.yaml"))
    scope = store.put(folder.as_uri(),{"version":1,"contract":store.put(folder.as_uri(),config),"artifacts":[raw]})
    task = {"input":scope,"output":(folder / "census-reading.json").as_uri(),"checks":["source.output"]}
    refs["census"] = source_read.execute(task,store)
    assert source_read.verify({**task,"candidate":refs["census"]},store) == ({"source.output":True},[])
    rules = bind(rules)
for spec in [*rules["combine"]["groups"].values(),*rules["combine"]["tables"].values()]:
    spec["checks"] = {key:{"APPROVED_COMPANY_CAPTURE_RUN":"capture","APPROVED_CATALOG_CAPTURE_RUN":"catalog"}.get(value,value)
        for key,value in spec["checks"].items()}
manifest = store.put(folder.as_uri(),{"version":1,"contract":store.put(folder.as_uri(),rules),"readings":refs})
task = {"input":manifest,"output":(folder / "combined.json").as_uri(),"checks":["source.combined"]}
combined = source_combine.execute(task,store)
assert source_combine.execute(task,store) == combined
assert source_combine.verify({**task,"candidate":combined},store) == ({"source.combined":True},[])
artifact = store.json(combined)["artifacts"][0]
assert store.json(artifact["input"])["readings"] == refs
row = artifact["tables"]["company"][0]
assert row["forms"] == ["10-K","20-F","8-K"]
assert row["tickers"] == ["A","B","C"]
assert row["business_address"]["country"] == "GB" and row["business_address"]["street"] == "Raw"
if with_census:
    expected = {"census":raw["sha256"],"version":census["version"],"key":"EXAMPLE",**census["entries"]["EXAMPLE"],
        "cascade":{"census":raw["sha256"],"version":census["cascade"]["version"],"lei":"L1","pass":"P1"}}
    assert row["name_census"] == expected and "_name_key" not in row
prepare = {"input":combined,"output":(folder / "mdm/manifest.json").as_uri(),"checks":["mdm.prepared"],
    "keys":{"table":"company","dataset":"sec.submissions.company.v1","policy":"0"*64,
        "consumer":"trial","batch_id":"composition","as_of":date}}
prepared = mdm_prepare.execute(prepare,store)
assert mdm_prepare.verify({**prepare,"candidate":prepared},store) == ({"mdm.prepared":True},[])
batch = store.json(prepared)["batches"][0]
assert json.loads((folder / "mdm" / batch["input"]["path"]).read_bytes()) == row
print("installed Company raw combination and preparation passed")
'''.replace('WITH_CENSUS', repr(with_census)), cwd=root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'installed Company raw combination and preparation passed'


def test_gleif_configured_mapping_publishes_and_recovers_from_installed_bundle(installed, databases, tmp_path):
    """Restricted PG16, installed native GLEIF fields, exact replay and lost ACK.

    Bounded fixture qualification; retained release semantics remain in use.
    This does not qualify the full captured Company/GLEIF population.
    """
    from sqlalchemy import create_engine
    from edgar_warehouse.mdm.clean.store import migrate, register_policy, digest
    from tests.support.fresh_mastering import cohort, FIXTURE, CHILD_LEI, PARENT_LEI
    from tests.support.rules_authority import register_dataset

    python, root = installed
    name = f"gleif_installed_{uuid4().hex[:8]}"
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    admin = create_engine(databases.admin.url.set(database=name))
    app = create_engine(admin.url.set(username="clean_application", password="test"))
    try:
        migrate(admin, application_role="clean_application")
        policy, contracts, readings = cohort()
        gleif = {f"gleif.{member}.v1": files.mdm_contract("gleif", f"gleif.{member}.v1")
                 for member in ("level1", "relationships", "reporting_exceptions")}
        with admin.begin() as conn:
            policy_digest = register_policy(conn, policy)
            for code, body in {**contracts, **gleif}.items():
                register_dataset(conn, code, str(uuid4()), body)
        rows = [row for row in json.loads(FIXTURE.read_text())["gleif"]
                if row["LEI"]["$"] in {CHILD_LEI, PARENT_LEI}]
        assert len(rows) == 2
        sec_records = [
            {"source": "sec.submissions.company", "row": row}
            for row in json.loads(FIXTURE.read_text())["sec"] if row["entity_type"] == "operating"
        ] + [
            {"source": "sec.submissions.person", "row": json.loads(line)}
            for line in FIXTURE.with_name("person_raw.jsonl").read_text().splitlines() if line.strip()
        ]
        from tests.support.retired_company_address import business_address
        from edgar_warehouse.mdm.clean.adapters import normalize
        landed_addresses=[]
        for record in sec_records:
            if record["source"]!="sec.submissions.company":continue
            row=record["row"]
            landed={"cik":row["cik"],"address_type":"business","last_sync_run_id":"installed-addresses",
                    "street1":"  Source Street  ","street2":None,"city":"City","zip_code":"12345",
                    "state_or_country":" de ","country_code":None}
            landed_addresses.append(landed)
            row["business_address"]=business_address(landed)
        readings=[]
        for record in sec_records:
            row=record["row"];code=f"{record['source']}.v1"
            readings.append(normalize(row,source_code=code,contract=contracts[code],policy=policy,
                publication={"publication_key":f"offline-cohort/{row['cik']}@{digest(row)}",
                             "revision":1,"artifact_sha256":digest(row),
                             "member":"four_companies_v1.json","record_locator":str(row["cik"])}))
        from io import BytesIO
        from tests.mdm.test_clean_name_census import archive, metadata
        from tests.support import retired_name_census
        census_archive = archive(rows)
        census_filers = [(f"{r['row']['cik']:010d}", r['row']['entity_name'], [])
                         for r in sec_records if r['source'] == 'sec.submissions.company']
        census_arguments = {"filers": census_filers,
                            "sec_population": {"capture_run_id": "installed-census", "filers": len(census_filers)},
                            "gleif_metadata": metadata(len(rows)),
                            "gleif_sha256": hashlib.sha256(census_archive).hexdigest()}
        historical_census = retired_name_census.build(gleif_archive=BytesIO(census_archive), **census_arguments)
        done = _run(python, "-c", r'''
import copy, hashlib, json, sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.mdm.clean import adapters, gleif_source, company_source
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.publication import LocalContractSink
from edgar_warehouse.mdm.clean.store import Store, digest
from edgar_warehouse.workers import source_mapping
body=json.load(sys.stdin)
assert files.ROOT == files.BUNDLED
source_engine.STEPS = {}
engine=create_engine(body["dsn"])
with engine.connect() as conn:
    assert conn.scalar(text("SHOW server_version_num")) >= "160000"
    assert conn.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")) is False
for member in ("level1","relationships","reporting_exceptions"):
    mapping=files.mdm_contract("gleif",f"gleif.{member}.v1")["adapter"]
    recipe=files.load(files.ROOT/"sources/gleif"/f"{member.replace('_','-')}-fields.yaml")
    assert digest(mapping["reading"]) == digest(recipe)
    assert isinstance(source_mapping.project_record({},mapping["reading"],column="fields"),dict)
# Exercise the actual retained preparation/census caller, with the custom
# derivation removed. Its configured address becomes the published SEC field.
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO
assert not hasattr(company_source,"business_address")
stream=BytesIO()
pq.write_table(pa.Table.from_pylist(body["landed_addresses"]),stream)
landed=company_source._business_addresses({"run_id":"installed-addresses"},pq.ParquetFile(BytesIO(stream.getvalue())))
for record in body["sec_records"]:
    if record["source"]=="sec.submissions.company":
        assert landed[record["row"]["cik"]]==record["row"]["business_address"]
        record["row"]["business_address"]=landed[record["row"]["cik"]]
# Rebuild SEC assertions from raw fixture documents inside the installation.
# Host-built assertions are only an oracle, never publication input.
sec_readings=[]
for record in body["sec_records"]:
    source=record["source"]; row=record["row"]; code=f"{source}.v1"
    contract=files.mdm_contract(source,code)
    recipe=files.load(files.ROOT/"sources"/source/"fields.yaml")
    assert digest(contract["adapter"]["reading"])==digest(recipe)
    retained=copy.deepcopy(contract); retained["adapter"].pop("reading")
    publication={"publication_key":f"offline-cohort/{row['cik']}@{digest(row)}",
                 "revision":1,"artifact_sha256":digest(row),
                 "member":"four_companies_v1.json","record_locator":str(row["cik"])}
    kwargs={"source_code":code,"publication":publication,"policy":files.policy()}
    actual=adapters.normalize(row,contract=contract,**kwargs)
    assert digest(actual)==digest(adapters.normalize(row,contract=retained,**kwargs))
    sec_readings.append(actual)
assert digest(sec_readings)==digest(body["readings"])
contract=files.mdm_contract("gleif","gleif.level1.v1")
retained=copy.deepcopy(contract); retained["adapter"].pop("reading")
assertions=[]
for ordinal,row in enumerate(body["rows"]):
    publication={"publication_key":"installed-gleif-fixture","revision":1,
                 "artifact_sha256":digest(row),"member":"level1"}
    kwargs={"member":"level1","source_code":"gleif.level1.v1","eligible_leis":body["leis"],
            "publication":publication,"ordinal":ordinal}
    actual=gleif_source.record_evidence(row,contract=contract,**kwargs)
    assert actual[0]=="assertion" and digest(actual)==digest(gleif_source.record_evidence(row,contract=retained,**kwargs))
    assertions.append(actual[1])
store=Store(engine); stage=MergeStage(store); run=str(uuid4())
command={"batch_id":"installed-gleif-fields","run_id":run,"consumer":"installed-gleif-qualification",
         "policy_digest":body["policy"],"expected_checkpoint":0,"checkpoint":1,
         "as_of":body["as_of"],"assertions":[*sec_readings,*assertions]}
first=stage.apply(**command)
with engine.connect() as conn:
    counts=dict(conn.execute(text("SELECT kind,count(*) FROM mdm.current_entity GROUP BY kind")).all())
    assert counts=={"company":2,"person":2},counts
    bindings=dict(conn.execute(text("SELECT subject,entity_id::text FROM mdm.stage_record")).all())
assert all(bindings[row["subject"]] is None for row in assertions)
companies=[row for row in sec_readings if row["kind"]=="company"]
decisions=[decision("bind",actor="steward",reason="offline fixture binding",at=body["as_of"],
    subject=row["subject"],entity_id=bindings[sec["subject"]],evidence=[row["assertion_id"]])
    for row,sec in zip(assertions,companies,strict=True)]
second_command={**command,"batch_id":"installed-gleif-bindings","assertions":[],"decisions":decisions,
                "expected_checkpoint":1,"checkpoint":2}
second=stage.apply(**second_command)
# Build a fresh census inside the installation and carry its exact evidence
# through actual SEC normalization, Merge Stage and publication/recovery.
import io, base64
from edgar_warehouse.mdm.clean import name_census
assert not any(hasattr(name_census,name) for name in ("_text","_other_names","sec_keys"))
packed=base64.b64decode(body["census_archive"],validate=True)
census_arguments=body["census_arguments"]
assert hashlib.sha256(packed).hexdigest()==census_arguments["gleif_sha256"]
census=name_census.build(gleif_archive=io.BytesIO(packed),**census_arguments)
expected=body["historical_census"]
assert census==expected
census_assertions=[]
for record in body["sec_records"]:
    if record["source"]!="sec.submissions.company":continue
    row=copy.deepcopy(record["row"])
    row["name_census"]=name_census.entry(census,row["entity_name"],census_digest=digest(census))
    old_row=copy.deepcopy(row)
    old_row["name_census"]=body["historical_entries"][str(row["cik"])]
    kwargs={"source_code":"sec.submissions.company.v1","contract":files.mdm_contract("sec.submissions.company","sec.submissions.company.v1"),
            "policy":files.policy(),"publication":{"publication_key":f"installed-census/{row['cik']}","revision":2,
            "artifact_sha256":digest(row),"member":"four_companies_v1.json","record_locator":str(row["cik"])}}
    actual=adapters.normalize(row,**kwargs)
    assert digest(actual)==digest(adapters.normalize(old_row,**kwargs))
    census_assertions.append(actual)
census_command={**command,"batch_id":"installed-census-reading","assertions":census_assertions,
                "expected_checkpoint":2,"checkpoint":3}
census_result=stage.apply(**census_command)
with engine.connect() as conn:
    for assertion in census_assertions:
        stored=conn.scalar(text("SELECT body FROM mdm.source_reading WHERE assertion_id=:id"),
                           {"id":assertion["assertion_id"]})
        assert digest(stored)==digest(assertion)
        assert stored["provenance"]["matching"]["name_census"]["census"]==digest(census)
class LostAcknowledgement:
    def __init__(self,sink): self.sink=sink
    def publish(self,*args): self.sink.publish(*args); raise OSError("simulated lost acknowledgement")
    def verify(self,*args): return self.sink.verify(*args)
for consumer in body["consumers"]:
    sink=LocalContractSink(Path("published")/consumer)
    try: store.deliver_one(consumer,"installed",LostAcknowledgement(sink))
    except OSError: pass
    else: raise AssertionError("lost acknowledgement was not exercised")
    assert not store.run_status(run)["publication_complete"]
    while store.deliver_one(consumer,"installed",sink): pass
    assert list(sink.directory.glob("*.json"))
assert store.run_status(run)["publication_complete"]
assert stage.apply(**command)["duplicate"] and stage.apply(**second_command)["duplicate"]
assert stage.apply(**census_command)["duplicate"]
with engine.connect() as conn:
    assert conn.scalar(text("SELECT count(*) FROM mdm.batch"))==3
    assert conn.scalar(text("SELECT count(*) FROM mdm.master_entity"))==4
for sql in ("DELETE FROM mdm.source_reading","DELETE FROM mdm.master_entity","CREATE TABLE mdm.bypass(id int)"):
    try:
        with engine.begin() as conn: conn.execute(text(sql))
    except DBAPIError as error: assert error.orig.pgcode=="42501"
    else: raise AssertionError("restricted operation accepted")
pins={str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest()
      for path in [*source_engine.runtime_files(),Path(source_mapping.__file__),Path(adapters.__file__),
                   files.ROOT/"sources/gleif/source.yaml",
                   files.ROOT/"sources/sec.submissions.company/source.yaml",
                   files.ROOT/"sources/sec.submissions.person/source.yaml",Path(company_source.__file__),
                   files.ROOT/"sources/sec.submissions.company/landed-address.yaml",Path(name_census.__file__),
                   files.ROOT/"sources/gleif/census-record.yaml",
                   files.ROOT/"sources/gleif/census-identity.yaml",
                   files.ROOT/"sources/gleif/census-update.yaml",
                   files.ROOT/"sources/sec.submissions.company/census-filer.yaml"]}
print(json.dumps({"pins":pins,"generation":census_result["generation"],"counts":counts,
                  "installed_gleif_mapping":True,"installed_sec_mapping":True,"installed_address_caller":True,"installed_census_caller":True,"census_digest":digest(census),"publication_recovery":True,"full_population":False}))
engine.dispose()
''', cwd=root, document={"dsn": app.url.render_as_string(hide_password=False),
                         "policy": policy_digest, "readings": readings, "rows": rows, "sec_records": sec_records,
                         "landed_addresses": landed_addresses, "census_arguments": census_arguments,
                         "historical_census": historical_census,
                         "census_archive": base64.b64encode(census_archive).decode(),
                         "historical_entries": {str(r['row']['cik']): retired_name_census.entry(historical_census,r['row']['entity_name'],census_digest=digest(historical_census))
                                                for r in sec_records if r['source']=='sec.submissions.company'}, "leis": [CHILD_LEI, PARENT_LEI], "as_of": "2026-01-01T00:00:00+00:00",
                         "consumers": policy["required_consumers"]})
        assert done.returncode == 0, done.stderr
        proof = json.loads(done.stdout)
        assert proof["installed_gleif_mapping"] and proof["installed_sec_mapping"] and proof["installed_address_caller"] and proof["installed_census_caller"] and proof["publication_recovery"]
        (root / "installed-gleif-mapping-proof.json").write_text(json.dumps(proof, indent=2)+"\n")
    finally:
        admin.dispose()
        app.dispose()


def test_active_company_preparation_caller_runs_from_installed_bundle(installed, tmp_path):
    """Frozen input is produced once; installed CLI and verifier cannot use checkout."""
    from tests.mdm.test_clean_company_source import landing, source_row, ticker_row, filing_row
    from tests.support.retired_company_preparation import prepare_company_bundle as historical
    from edgar_warehouse.mdm.clean.company_source import bronze_receipts
    python, root = installed
    selected = "a" * 64
    args = landing(tmp_path, [source_row(123,raw_object_id=selected)], tickers=[ticker_row(123,"A")],
                   filings=[filing_row(123,"10-Q"),filing_row(123,"10-K")])
    receipts = tmp_path / "receipts.json"
    receipts.write_text(json.dumps(bronze_receipts("capture-1",
        [{"sha256":f"{n:064x}","path":f"s3://bronze/{n}.json"} for n in range(10001)]
        + [{"sha256":selected,"path":"s3://bronze/selected.json"}])))
    args["bronze_receipts_path"] = str(receipts)
    original = historical(**{**args,"output":str(tmp_path/"historical")})
    arguments = ["mdm","prepare-clean-company"]
    for name,value in args.items():
        option = "bronze-receipts" if name == "bronze_receipts_path" else name.replace("_","-")
        arguments.extend(["--"+option,str(value)])
    run = _run(python,"-c", """
import sys
from edgar_warehouse.rules import source_engine
from edgar_warehouse.mdm.clean import company_source
from edgar_warehouse.cli import main
source_engine.STEPS = {}
assert not hasattr(company_source,'prepare_company_bundle')
assert not hasattr(company_source,'_filed_forms')
assert not hasattr(company_source,'_catalog_tickers')
sys.exit(main(sys.argv[1:]))
""", *arguments,cwd=root)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report['scope'] == original['scope']
    for name in original['files']:
        assert (tmp_path/'historical'/name).read_bytes() == (tmp_path/'pinned'/name).read_bytes(),name
    verified = _run(python,"-c", """
import json,sys
from edgar_warehouse.rules import source_engine
from edgar_warehouse.mdm.clean.company_prepare import verify_company_bundle
source_engine.STEPS = {}
print(json.dumps(verify_company_bundle(sys.argv[1],expected=json.load(sys.stdin))))
""",str(tmp_path/'pinned'),cwd=root,document=report)
    assert verified.returncode == 0,verified.stderr
    assert json.loads(verified.stdout)['records'] == 1
    repeated = _run(python,"-m","edgar_warehouse.cli",*arguments,cwd=root)
    assert repeated.returncode == 0,repeated.stderr
    assert json.loads(repeated.stdout)==report
