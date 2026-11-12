"""The data skill installed whole, from a git ref, with no checkout (mastering to-do 21).

The five wheels (the bundle, Bookkeeping, the Change Journal and the native source/control libraries)
are installed from this repository's committed HEAD by URL with the
`uv tool install` command the data-platform skill's Setup writes, the way an
agent with no checkout installs them. Every command
then runs from that installation, in isolated mode, from a folder outside
the repository, so nothing here can stand in for a missing file.

- G1: no file ships in two wheels; every shipped module imports; no domain
  library (edgartools, spaCy) is installed; `doctor` passes on PG16 stores.
- G2: the rules creator runs from the bundle against an empty Rules Database.
- G3 (parse): a Rules-submitted run is read by the configured engine and
  completed by worker processes, all from the bundle.
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
from tests.support.reading import reading as mapped_reading

WHEELS = {
    "edgartools-data": "packages/data-skill",
    "edgartools-bookkeeping": "packages/bookkeeping",
    "edgartools-change-journal": "packages/change-journal",
    "source-contract": "crates/source-contract",
    "edgartools-control-core": "crates/control-contract",
}
DOMAIN = ("edgartools", "spacy", "pandas", "streamlit", "snowflake-connector-python")


def _text(node):
    value = node.get("$") if isinstance(node, dict) else node
    return value.strip() if isinstance(value, str) and value.strip() else None


def cascade_entity(row, cascade_spec, wanted):
    """One Level 1 record as the cascade reads it (ticket 21): through the GLEIF
    contract and its quality rule, with its legal and other names; None when it
    is not GENERAL or the contract sets it aside."""
    from edgar_warehouse.mdm import cascade
    from edgar_warehouse.mdm.adapters import UnsupportedRecord, mapped_values
    from edgar_warehouse.mdm.primitives import NORMALIZERS
    entity = row.get("Entity") or {}
    lei = _text(row.get("LEI"))
    if not lei or _text(entity.get("EntityCategory")) != "GENERAL":
        return None
    try:
        fields, matching, quality = mapped_values(row, cascade_spec["gleif_contract"])
    except UnsupportedRecord:
        return None
    names = [_text(entity.get("LegalName"))]
    for container, item in (("OtherEntityNames", "OtherEntityName"),
                            ("TransliteratedOtherEntityNames", "TransliteratedOtherEntityName")):
        found = (entity.get(container) or {}).get(item) or []
        names += [text for name in (found if isinstance(found, list) else [found]) if (text := _text(name))]
    key = NORMALIZERS["normalize_text@legal-form-kept-v1"]
    return cascade.entity_of(cascade.record(lei, fields, matching, quality, {"lei": lei}),
                             frozenset(key(n) for n in names) & wanted,
                             eligible=cascade.eligible(fields, cascade_spec["spec"]))


@pytest.mark.parametrize("case", ["ordinary", "agent", "placeholder", "headquarters_agent",
    "cross_line_agent", "postcode", "unicode", "noncandidate", "ineligible", "missing_name",
    "bad_field", "bad_lines", "branch"])
def test_complete_name_count_general_projection_matches_active_cascade_without_install(case):
    """Bounded projection proof; no install or database population gate."""
    import copy
    from edgar_warehouse.mdm import cascade, sec_company, quality
    from edgar_warehouse.mdm.gleif_publication import dataset_contract
    from edgar_warehouse.rules.source_engine import SourceEngine
    from tests.engine.test_gleif_configured_fields import raw

    row = copy.deepcopy(raw())
    entity = row["Entity"]
    entity["EntityStatus"] = {"$": "ACTIVE"}
    if case == "agent": entity["LegalAddress"]["FirstAddressLine"] = {"$": "1209 Orange Street"}; entity.pop("HeadquartersAddress")
    if case == "placeholder": entity["LegalAddress"]["FirstAddressLine"] = {"$": "N/A"}; entity.pop("HeadquartersAddress")
    if case == "headquarters_agent": entity["HeadquartersAddress"]["FirstAddressLine"] = {"$": "CT Corporation"}
    if case == "cross_line_agent": entity["HeadquartersAddress"].update(FirstAddressLine={"$": "CT"}, AdditionalAddressLine=[{"$": "CORPORATION"}])
    if case == "postcode": entity["HeadquartersAddress"]["PostalCode"] = {"$": "12345-6789"}
    if case == "unicode": entity["HeadquartersAddress"]["FirstAddressLine"] = {"$": "Beranových Street\nSuite 12\nΟδός 7"}
    if case == "noncandidate": entity["LegalName"] = {"$": "Outside Company"}
    if case == "ineligible": entity["EntityStatus"] = {"$": "INACTIVE"}
    if case == "missing_name": entity["LegalName"] = {"$": " "}
    if case == "bad_field": entity["LegalJurisdiction"] = {"$": []}
    if case == "bad_lines": entity["LegalAddress"]["AdditionalAddressLine"] = [42]
    if case == "branch": entity["EntityCategory"] = {"$": "BRANCH"}
    spec = cascade.spec(sec_company.POLICY)
    assert len(spec["passes"]) == 1
    contract = dataset_contract("level1")
    expected = cascade_entity(row, {"spec": spec, "gleif_contract": contract}, {"EXAMPLE"})
    recipe = files.load(files.ROOT / "sources/gleif/name-count-cascade-record.yaml")
    projected = SourceEngine(recipe).read(json.dumps(row, ensure_ascii=False).encode()).tables["mapped"][0]["observation"]
    if expected is None:
        assert projected is None
        return
    assert projected["lei"] == expected.lei
    assert projected["legal"] == expected.legal
    assert projected["eligible"] == expected.eligible
    assert projected["last_update"] == expected.last_update
    assert projected["jurisdiction"] == expected.jurisdiction
    assert cascade.place(projected["place"]) == expected.place
    from edgar_warehouse.mdm.adapters import mapped_values
    _, _, original_quality = mapped_values(row, contract)
    record = {"provenance": {"quality": original_quality}}
    assert projected["legal_withheld"] == quality.withheld(record, "matching.address")
    assert projected["headquarters_withheld"] == quality.withheld(record, "matching.headquarters_address")


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
for source, first in [("sec.company", "ELECTRICITE HLDGS CORP"), ("gleif", "ELECTRICITE HLDGS CORP DE")]:
    config = files.load(files.ROOT / "sources" / source / "name-key.yaml")
    contract = store.put(root.as_uri(), config)
    manifest = store.put(root.as_uri(), {"version":2,"contract":contract,"artifacts":[{"input":raw,"context":context}]})
    task = {"input":manifest,"output":(root / (source + ".json")).as_uri(),"checks":["source.output"]}
    receipt = source_read.execute(task,store)
    assert source_read.check({**task,"candidate":receipt},store) == ({"source.output":True},[])
    reading = store.json(receipt)
    rows = reading["artifacts"][0]["tables"]["names"]
    assert [row["key"] for row in rows] == [first,"A AND B LLC","WAYFAIR INC","WAYFAIR LLC"]
    assert reading["artifacts"][0]["input"] == raw and reading["artifacts"][0]["context"] == context
    assert not reading["artifacts"][0]["deferred"]
    proof[source] = {"contract":contract,"input":manifest,"reading":receipt}
print(json.dumps(proof))
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert set(json.loads(result.stdout)) == {"sec.company", "gleif"}


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


def test_configured_pair_profile_runs_from_installed_bundle(installed):
    """The shipped catalog and native comparison agree outside the checkout."""
    python, root = installed
    program = '''
import copy, os, shutil, sys, tempfile
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.mdm import catalog

folder = Path(tempfile.mkdtemp(dir=".")) / "rules"
shutil.copytree(files.ROOT, folder)
body = copy.deepcopy(catalog.CATALOG)
body["kinds"].append("bundle-invented-kind")
profile = copy.deepcopy(body["pair_comparisons"][body["legacy_pair_comparison"]])
profile.update(eligibility_kind="bundle-invented-kind", eligibility_categories=["INVENTED"],
               name_field="invented_name", status_field="invented_status",
               registration_status_field="invented_registration",
               identifier_namespace="invented_namespace", name_count_field="invented_name_count",
               cascade_field="invented_cascade",
               cascade_identifier_field="invented_target")
body["pair_comparisons"]["bundle-invented"] = profile
(folder / catalog.RELATIVE).write_text(files.dumps(body))
env = {**os.environ, "EDGAR_RULES_ROOT": str(folder.resolve())}
code = """
from edgar_warehouse.mdm.matching import compare_candidate_records, candidate_paths, candidate_value
rule = {"pair_comparison": "bundle-invented", "when": [{"primitive": "gleif_entity_eligible@1",
    "args": {"categories": ["INVENTED"], "entity_statuses": ["ACCEPTED"],
             "refused_registration_statuses": ["REFUSED"]}}]}
right = {"kind": "bundle-invented-kind", "fields": {
    "invented_status": {"op": "value", "value": "ACCEPTED"},
    "invented_registration": {"op": "value", "value": "ISSUED"}}}
assert compare_candidate_records(rule, [({}, right)]) == [[True, False]]
paths = candidate_paths(rule)
assert paths["identifier"] == ("identifiers", "invented_namespace")
assert paths["cascade"] == ("provenance", "matching", "invented_name_count", "invented_cascade", "invented_target")
assert candidate_value({"identifiers":{"invented_namespace":"invented-value"}}, paths["identifier"]) == "invented-value"
from edgar_warehouse.mdm.matching import candidate_routes
from edgar_warehouse.mdm.evidence import assertion
from edgar_warehouse.rules.source_engine import prepare_record_lookups
item = assertion(source_code="invented.source",record_key="one",publication_key="first",revision=1,
    effective_at=None,kind="bundle-invented-kind",fields={},identifiers={"invented_namespace":"invented-value"})
command = {"readings":[item],"previous":{},"subjects":[item["subject"]],"bindings":{},
    "quarantined":{},"policy":{},"normalizers":{},"batch_id":"invented-first","occurrences":{},
    "candidate_routes":candidate_routes()}
current, changes = prepare_record_lookups(command)
assert current[item["subject"]]["matching_keys"] == {'["bundle-invented","identifier"]':"invented-value"}
again, changes = prepare_record_lookups({**command,"previous":current,"batch_id":"invented-retry"})
assert again == current and changes == []
right["fields"]["invented_status"]["value"] = "OTHER"
assert compare_candidate_records(rule, [({}, right)]) == [[False, False]]
"""
os.execve(sys.executable, [sys.executable, "-I", "-c", code], env)
'''
    result = _run(python, "-c", program, cwd=root)
    assert result.returncode == 0, result.stderr


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
# An import inside a function runs only with its command: every module any shipped file names is installed.
import ast, importlib.util, pathlib
named = {{}}
for dist in {list(WHEELS)!r}:
    for p in m.files(dist):
        if str(p).startswith("edgar_warehouse/") and str(p).endswith(".py"):
            for node in ast.walk(ast.parse(pathlib.Path(p.locate()).read_text())):
                found = ([node.module] if isinstance(node, ast.ImportFrom) and not node.level else
                         [a.name for a in node.names] if isinstance(node, ast.Import) else [])
                for module in found:
                    if module and module.startswith("edgar_warehouse."):
                        named.setdefault(module, str(p))
absent = {{module: where for module, where in named.items() if importlib.util.find_spec(module) is None}}
# A rules file a command reads is found where the bundle ships it, not beside a checkout.
from edgar_warehouse.financials import line_items, measures
rules_read = [len(line_items.load().period), len(measures.load().names())]
print(json.dumps({{"shipped": shipped, "modules": modules, "absent": absent, "rules_read": rules_read}}))
''', cwd=root)
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    twice = [path for path, count in Counter(found["shipped"]).items() if count > 1]
    assert twice == []
    assert found["absent"] == {}  # `silver line-items` failed so: financials was not shipped (ticket 48)
    assert all(found["rules_read"])  # `silver line-items` failed so: its line-items.yaml was looked for beside a checkout (ticket 48)
    assert {"edgar_warehouse.cli", "edgar_warehouse.workers.source_read", "edgar_warehouse.mastering.merge",
            "edgar_warehouse.rules.cli", "edgar_warehouse.database_connections", "edgar_warehouse.database_types",
            "edgar_warehouse.rdm.storage", "edgar_warehouse.rdm.mysql_migration",
            "edgar_warehouse.mdm.schema"} <= set(found["modules"])
    assert any(p.endswith("bundle_data/skills/data-onboarding/SKILL.md") for p in found["shipped"])
    assert any(p.endswith("mastering/schema/postgresql.sql") for p in found["shipped"])
    assert any(p.endswith("mastering/schema/mysql.sql") for p in found["shipped"])
    assert any(p.endswith("mdm/migrations/024_configured_kinds.sql") for p in found["shipped"])
    assert any(p.endswith("mdm/migrations/025_kind_descriptions.sql") for p in found["shipped"])


def _stores(databases):
    url = lambda engine: engine.url.render_as_string(hide_password=False)
    return {"RULES_DATABASE_URL": url(databases.rules.engine),
            "BOOKKEEPING_DATABASE_URL": url(databases.runtime),
            "CHANGE_JOURNAL_DATABASE_URL": url(databases.ledger.engine)}


def test_source_sequence_runs_from_installed_bundle_without_checkout(installed):
    python, root = installed
    # The installed CLI must discover both its module and bundled sequence YAML.
    # No database or source activation is needed for this configuration check.
    single = _run(python, "-m", "edgar_warehouse.cli", "rules", "sequence", "check",
                  "--source", "sec.submissions.person", cwd=root)
    assert single.returncode == 0, single.stderr
    report = json.loads(single.stdout)
    assert report["order"] == ["sec.submissions.person"]
    assert set(report["sources"]) == {"sec.submissions.person"}
    assert report["runtime_readiness"] == "not_checked"

    delayed = _run(python, "-m", "edgar_warehouse.cli", "rules", "sequence", "check",
                   "--defer", "gleif", cwd=root)
    assert delayed.returncode == 3, delayed.stderr
    report = json.loads(delayed.stdout)
    # OpenFIGI is one target since ticket 138, so it is ordered, before Securities.
    assert report["order"] == ["sec.company", "sec.nport.registrant", "sec.company-facts", "sec.registration", "sec.submissions.person",
                               "sec.nport.fund", "iapd.adv", "sec.ownership", "openfigi", "sec.thirteenf.securities",
                               "sec.nport.security", "sec.thirteenf.filings"]
    assert report["sources"]["gleif"]["status"] == "deferred"
    assert report["runtime_readiness"] == "not_checked"


def test_engine_number_text_and_store_migrations_run_from_installed_bundle(installed):
    python, root = installed
    result = _run(python, "-c", '''
from pathlib import Path
from edgar_warehouse.rules import source_engine
from edgar_warehouse.mdm import store
raw = source_engine.postgres_jsonb_text('{"a":1e-7,"bbb":1.2300}')
assert raw == '{"a": 0.0000001, "bbb": 1.2300}'
assert (Path(store.__file__).parent/"migrations/016_publication_inputs.sql").is_file()
assert all((Path(store.__file__).parent/"migrations"/name).is_file() for name in store.MIGRATIONS)
print("publication preparation installed")
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "publication preparation installed"


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
from edgar_warehouse.workers import source_read, source_readings, source_combine, mdm_prepare
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
assert source_read.check({**task,"candidate":receipt},store) == ({"source.output":True},[])
reading = store.json(receipt)
parts = reading["artifacts"][0]["partitions"]
assert reading["version"] == 2 and len(parts) == 2
assert [store.json(part["receipt"])["tables"]["rows"][0]["n"] for part in parts] == [1,2]
# Evidence is inspected through the installed module, without a worker-shaped
# request at the consumption seam. Original extraction and verification still
# validate the version-3 request before using the same lookup implementation.
contract["read"]["lookup_sets"] = {"wanted":{"max_values":3,"max_bytes":8,"max_value_bytes":4}}
scoped_rules = store.put(root.as_uri(), contract)
lookup = store.put(root.as_uri(), {"version":1,"input":ref,"sets":{"wanted":["A"]}})
scoped_manifest = store.put(root.as_uri(), {"version":3,"contract":scoped_rules,
    "artifacts":[{"input":ref,"context":context,"lookups":lookup}]})
scoped_task = {**task,"input":scoped_manifest,"output":(root / "scoped-index.json").as_uri()}
scoped = source_read.execute(scoped_task, store)
assert source_read.check({**scoped_task,"candidate":scoped},store) == ({"source.output":True},[])
opened = source_readings.OpenedExtract(scoped,store,max_bytes=1024**2,max_rows=100,
    max_contract_bytes=1024**2,allow_lookup_receipts=True)
assert "site-packages" in source_readings.__file__
assert opened.contract == contract and opened.lookup_sets(0) == {"wanted":["A"]}
assert [row["n"] for _,_,chunk,_ in opened.chunks() for row in chunk["tables"]["rows"]] == [1,2]
combine_rules = store.put(root.as_uri(), {"execution":{"profile":"source.combine"},
 "combine":{"max_rows":100,"groups":{},"tables":{"rows":{"source":"streamed","table":"rows",
 "checks":{},"where":{},"joins":{}}}}})
combine_manifest = store.put(root.as_uri(), {"version":1,"contract":combine_rules,"readings":{"streamed":receipt}})
combine_task = {"input":combine_manifest,"output":(root / "combined.json").as_uri(),"checks":[source_combine.CHECK]}
combined = source_combine.execute(combine_task, store)
assert source_combine.check({**combine_task,"candidate":combined}, store) == ({source_combine.CHECK:True},[])
prepare_task = {"input":combined,"output":(root / "mdm/manifest.json").as_uri(),"checks":[mdm_prepare.CHECK],
 "keys":{"table":"rows","dataset":"fixture.rows","policy":"0"*64,"consumer":"trial",
 "batch_id":"trial","as_of":"2026-10-05T00:00:00Z"}}
prepared = mdm_prepare.execute(prepare_task,store)
assert mdm_prepare.execute(prepare_task,store) == prepared
assert mdm_prepare.check({**prepare_task,"candidate":prepared},store) == ({mdm_prepare.CHECK:True},[])
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
        for statement in ("CREATE ROLE rules_agent LOGIN PASSWORD 'test'",
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
    checked = cli("rules", "check", "--root", str(folder))
    assert checked.returncode == 0, checked.stdout
    assert set(json.loads(checked.stdout).values()) == {"ok"}
    status = cli("rules", "status", "--source", "gleif")
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout) == []  # no run has used these rules yet


@pytest.mark.parametrize('reading_mode', ['13f', 'company-main', 'company-page', 'company-catalog', 'company-dictionary'])
def test_parsing_runs_through_the_installed_bundle(installed, databases, tmp_path, reading_mode):
    python, root = installed
    store = Artifacts()
    grant_profile(databases.admin, profile="source.read", worker="bk_runtime")
    body = files.pipeline("sec.thirteenf.extract")
    pipeline_name = 'sec.thirteenf.extract' if reading_mode == '13f' else f'{reading_mode}-reading'
    body['pipeline'] = pipeline_name
    contract_path = ROOT / "crates/source-contract/contracts/thirteenf/contract.yaml"
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), contract_path.read_bytes())
    xml = store.put_bytes((tmp_path / "filing.xml").as_uri(),
                          (contract_path.parent / "fixtures/one-row.xml").read_bytes())
    input_ref = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": [xml]})
    if reading_mode == 'company-main':
        probe = _run(python, '-c', 'import json; from edgar_warehouse.rules import files; print(json.dumps(files.source("sec.company")))', cwd=root)
        assert probe.returncode == 0, probe.stderr
        contract = store.put(tmp_path.as_uri(), json.loads(probe.stdout))
        raw = store.put_bytes((tmp_path / 'company.json').as_uri(), b'{"name":"Example","addresses":{"business":{"stateOrCountry":"DE"}}}')
        context = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': {
            'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': raw['sha256'], 'load_mode': 'default',
            'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'}})
        input_ref = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': context}]})
    if reading_mode == 'company-page':
        probe = _run(python, '-c', 'import json; from edgar_warehouse.rules import files; print(json.dumps(files.load(files.ROOT / "sources/sec.company/pagination.yaml")))', cwd=root)
        assert probe.returncode == 0, probe.stderr
        contract = store.put(tmp_path.as_uri(), json.loads(probe.stdout))
        raw = store.put_bytes((tmp_path / 'page.json').as_uri(), b'{"accessionNumber":["old","older"],"form":["20-F","10-K"],"size":["1234","1,234"]}')
        context = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': {
            'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': '0' * 64, 'load_mode': 'default'}})
        input_ref = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': context}]})
    if reading_mode in ('company-catalog', 'company-dictionary'):
        probe = _run(python, '-c', 'import json; from edgar_warehouse.rules import files; print(json.dumps(files.load(files.ROOT / "sources/sec.company/catalog.yaml")))', cwd=root)
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
    folder = tmp_path / "rules"
    assert _run(python, "-m", "edgar_warehouse.cli", "skill", "install", "--home", str(tmp_path / "home"),
                "--rules", str(folder), cwd=root).returncode == 0
    files.LAYOUT["pipeline"][1](body, folder / "pipelines" / pipeline_name / "pipeline.yaml")
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri(),
           "EDGAR_RULES_ROOT": str(folder)}

    def command(*args, **extra):
        done = _run(python, "-m", *args, env={**env, **extra}, cwd=root)
        assert done.returncode == 0, done.stderr
        return done.stdout

    submitted = command("edgar_warehouse.cli", "rules", "run", "--pipeline", pipeline_name, "--target", "extract",
                        "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"])
    run_id = json.loads(submitted)["run"]["run_id"]
    command("edgar_warehouse.cli", "workers", "work", "source.read", run_id, "--reports", (tmp_path / "reports").as_uri())
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
            {"name": "merge", "operation": "mastering.merge", "requires": ["prepare"], "key": "{batch_id}",
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


def mastered(engine):
    """Records the merge holds, its masters by kind, and their names."""
    from sqlalchemy import text

    with engine.connect() as conn:
        records = conn.execute(text("SELECT count(*) FROM mastering_record")).scalar()
        bodies = [json.loads(body) for body, in conn.execute(text("SELECT body FROM mastering_master"))]
    current = [body for body in bodies if body.get("status") != "alias"]
    return records, dict(Counter(body["kind"] for body in current)), [body.get("fields", {}).get("name") for body in current]


# Each variant is one worker path through the installed bundle. A reading feature that a
# worker-level test already covers in-process is not repeated here (ticket 88): parallel
# records, integers, artifact context, selected sequences, object records (raw-person runs
# the same path) and XML streaming (the recovery variant streams XML too).
@pytest.mark.parametrize("trial_mode", ["configured", "parquet-records", "custom-step", "source-coercion", "reference-lookup", "raw-person", "combined-records", "choice-records", "streamed-records", "xml-streamed-recovery"])
def test_parse_then_master_runs_through_the_installed_bundle(installed, databases, tmp_path, trial_mode):
    """G3: captured records, read by the engine, prepared and merged into Clean
    MDM in one Rules run, every step by a worker from
    the installed bundle."""
    from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
    from edgar_warehouse.mdm.store import migrate, register_policy
    from sqlalchemy import create_engine, text
    from tests.integration import test_mdm_postgres as core
    from tests.support.rules_authority import register_dataset

    custom_trial = trial_mode == "custom-step"
    combined_trial = trial_mode == "combined-records"
    recovery_trial = trial_mode == "xml-streamed-recovery"
    xml_trial = recovery_trial
    streamed_trial = trial_mode == "streamed-records" or xml_trial
    profiles = ("source.read", *(("source.combine",) if combined_trial else ()), "mdm.prepare", "mastering.merge")
    python, root = installed
    store = Artifacts()
    for profile in profiles:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime")
    mdm_name = f"mdm_bundle_{uuid4().hex[:8]}"
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {mdm_name}")
    mdm_admin = create_engine(databases.admin.url.set(database=mdm_name))
    mdm_app = create_engine(mdm_admin.url.set(username="clean_application", password="test"))
    migrate(mdm_admin, application_role="clean_application")
    migrate_guard(mdm_admin, runtime_role="clean_application")
    with mdm_admin.begin() as conn:
        policy = register_policy(conn, {"version": 1, "required_consumers": ["export"], "automatic_rules": [],
                                        "kinds": {"company": {"version": "1", "defaults": {"sources": ["fixture.filers"]},
                                                              "fields": {"name": {"sources": ["fixture.filers"]}}}}})
        register_dataset(conn, "fixture.filers", "1", core.contract_body(adapter={
            "version": "v1", "kind": "company", "record_key": ["cik"], "identifiers": {"cik": "cik"},
            "reading": mapped_reading({"name": "name"})}))

    if trial_mode == "raw-person":
        with mdm_admin.begin() as conn:
            policy = register_policy(conn, files.policy())
            register_dataset(conn, "sec.submissions.person.v1", "1",
                             files.mdm_contract("sec.submissions.person", "sec.submissions.person.v1"))

    with mdm_admin.begin() as conn:
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO mdm_reader")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO mdm_reader")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA public TO mdm_reader")
    mdm_reader = create_engine(mdm_admin.url.set(username="mdm_reader", password="test"))
    pipeline_name = f"parse-and-master-{trial_mode}"
    pipeline = copy.deepcopy({**MASTER, "pipeline": pipeline_name})
    if combined_trial:
        steps = pipeline["bookkeeping"]["targets"]["master"]["steps"]
        steps.insert(1, {"name": "combine", "operation": "source.combine", "requires": ["read"], "key": "{batch_id}",
                         "leases": ["combined-output:{batch_id}"], "checks": ["input.hash", "output.receipt", "source.combined"]})
        next(step for step in steps if step["name"] == "prepare")["requires"] = ["combine"]
    rules_root = tmp_path / "rules-root"
    files.LAYOUT["pipeline"][1](pipeline, rules_root / "pipelines" / pipeline_name / "pipeline.yaml")
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
    if trial_mode == "raw-person":
        spec = files.source("sec.submissions.person")
        spec["execution"]["max_artifacts"] = 2
        contract_bytes = json.dumps(spec).encode()
        raw_persons = [json.loads(line) for line in (ROOT / "tests/fixtures/clean_mdm/four_companies_v1/person_raw.jsonl").read_text().splitlines()]
        filer_bytes = json.dumps(raw_persons[0]).encode()
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
    if trial_mode == "source-coercion":
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
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), contract_bytes)
    filers = store.put_bytes((tmp_path / "filers.jsonl").as_uri(), filer_bytes)
    read_manifest = {"version": 1, "contract": contract, "artifacts": [filers]}
    if recovery_trial:
        bound = store.put(tmp_path.as_uri(), {"version": 1, "input": filers, "values": {"publication_count": 2}})
        read_manifest = {"version": 2, "contract": contract, "artifacts": [{"input": filers, "context": bound}]}
    if trial_mode == "raw-person":
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
        "prepare": [{"keys": {**keys, "table": "submissions" if trial_mode == "raw-person" else "filers",
                              "dataset": "sec.submissions.person.v1" if trial_mode == "raw-person" else "fixture.filers",
                              **({"record_column": "record"} if trial_mode == "raw-person" else {}), "policy": policy,
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

    url = lambda engine: engine.url.render_as_string(hide_password=False)
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    worker = {"MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}

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
        bad_run = json.loads(cli("rules", "run", "--pipeline", pipeline_name, "--target", "master", "--root", str(rules_root),
            "--input-manifest", bad_units["uri"], "--input-sha256", bad_units["sha256"]))["run"]["run_id"]
        rejected = _run(python, "-m", "edgar_warehouse.cli", "workers", "work", "source.read", bad_run, "--reports", (tmp_path / "reports").as_uri(),
                        env={**env, **worker}, cwd=root)
        assert rejected.returncode == 1 and "pinned-count" in rejected.stderr, rejected.stderr
        for downstream in ("mdm.prepare", "mastering.merge"):
            cli("workers", "work", downstream, bad_run, "--reports", (tmp_path / "reports").as_uri(), **worker)
        assert not (bad_out / "reading.json").exists() and not (bad_out / "reading.json.parts").exists()
        assert not (bad_out / "mdm/manifest.json").exists() and not (bad_out / "merged.json").exists()
        failed_state = json.loads(cli("bookkeeping", "status", bad_run))
        assert failed_state["counts"].get("verified", 0) == 0
        assert mastered(mdm_reader) == (0, {}, [])

    run_id = json.loads(cli("rules", "run", "--pipeline", pipeline_name, "--target", "master", "--root", str(rules_root),
                            "--input-manifest", units["uri"], "--input-sha256", units["sha256"]))["run"]["run_id"]
    if recovery_trial:
        from urllib.parse import unquote, urlparse
        from pathlib import Path
        captured = Path(unquote(urlparse(filers["uri"]).path))
        unavailable = tmp_path / "temporarily-unavailable.xml"
        captured.rename(unavailable)
        try:
            rejected = _run(python, "-m", "edgar_warehouse.cli", "workers", "work", "source.read", run_id, "--reports", (tmp_path / "reports").as_uri(),
                            env={**env, **worker}, cwd=root)
            assert rejected.returncode == 1 and "Artifact missing or unreadable" in rejected.stderr, rejected.stderr
            assert filers["uri"] in rejected.stderr
            assert not (out / "reading.json").exists() and not (out / "reading.json.parts").exists()
            assert mastered(mdm_reader)[0] == 0
        finally:
            unavailable.rename(captured)
    for profile in profiles:
        if recovery_trial and profile == "source.read":
            deadline = time.monotonic() + 10
            while True:
                cli("workers", "work", profile, run_id, "--reports", (tmp_path / "reports").as_uri(), **worker)
                if (out / "reading.json").exists(): break
                if time.monotonic() >= deadline: pytest.fail("Source retry did not become claimable")
                time.sleep(0.01)
        else:
            cli("workers", "work", profile, run_id, "--reports", (tmp_path / "reports").as_uri(), **worker)
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
    if trial_mode == "raw-person":
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
    state = json.loads(cli("bookkeeping", "finalize", run_id))
    assert state["counts"] == {"verified": len(profiles)} and state["run"]["state"] == "complete"
    records, masters, names = mastered(mdm_reader)
    if trial_mode == "raw-person":
        assert masters == {"person": 2}

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
from edgar_warehouse.mdm import gleif_publication
from edgar_warehouse.mdm.gleif_publication import attest_publication
import importlib.util
assert importlib.util.find_spec("edgar_warehouse.mdm.gleif_source") is None
assert not hasattr(gleif_publication, "inspect_archive")
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
            metadata={"format":format+".zip", "cdf_version":gleif_publication.FORMATS[member.replace("-","_")][0],
                "content_date":date, "file_content":"GLEIF_FULL_PUBLISHED", "delta_start":None, "record_count":1},
            expected_sha256=raw["sha256"], on_record=lambda record,index: seen.append((record,index)))
        assert seen == [(row,0)] and attestation["record_count"] == 1
        assert attestation["canonical_source_hash"] == hashlib.sha256(
            (json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\\n").encode()).hexdigest()
        contract = store.put_bytes((folder / "contract.yaml").as_uri(),json.dumps(rules).encode())
        context = store.put(folder.as_uri(),{"version":1,"input":raw,"values":{"publication_count":1}})
        declared = rules["read"].get("lookup_sets", {})
        entry = {"input":raw,"context":context}
        if declared:
            entry["lookups"] = store.put(folder.as_uri(),{"version":1,"input":raw,"sets":{name:[] for name in declared}})
        manifest = store.put(folder.as_uri(),{"version":3 if declared else 2,"contract":contract,"artifacts":[entry]})
        task = {"input":manifest,"output":(folder / "reading.json").as_uri(),"checks":["source.output"]}
        receipt = source_read.execute(task,store)
        assert source_read.execute(task,store) == receipt
        assert source_read.check({**task,"candidate":receipt},store) == ({"source.output":True},[])
        artifact = store.json(receipt)["artifacts"][0]
        rows = [row for part in artifact["partitions"] for row in store.json(part["receipt"])["tables"][member.replace("-","_")]]
        assert artifact["record_count"] == 1 and rows == [{"record":row,"source_index":1,**({"nport_issuer":None} if declared else {})}]
print("six installed GLEIF member contracts passed")
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'six installed GLEIF member contracts passed'


def test_company_combination_blueprint_runs_from_installed_bundle(installed):
    """Installed raw readings compose/prepare without retained Company loaders."""
    python, root = installed
    result = _run(python, '-c', '''
import json
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
store = Artifacts()
folder = Path("company-composition").resolve()
folder.mkdir()
blueprints = files.ROOT / "sources/sec.company"
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
    assert source_read.check({**task,"candidate":receipt},store) == ({"source.output":True},[])
    return receipt
main = read("main","source.yaml",{"name":"Example","filings":{"recent":{
    "accessionNumber":["r1","r2"],"form":["8-K","10-K"]}},
    "addresses":{"business":{"street1":"Raw","stateOrCountry":"X0"}}},
    {**context,"recent_limit":None,"last_synced_at":date})
pages = read("pages","pagination.yaml",{"accessionNumber":["p1","p2"],"form":["20-F","10-K"]},context)
catalog_context = {"sync_run_id":"catalog","last_synced_at":date,"source_name":"exchange"}
exchange = read("catalog-exchange","catalog.yaml",{"fields":["cik","ticker"],"data":[[1,"B"],[1,"A"]]},catalog_context)
tickers = read("catalog-tickers","catalog.yaml",{"0":{"cik_str":1,"ticker":"A"},"1":{"cik_str":1,"ticker":"C"}},
    {**catalog_context,"source_name":"tickers"})
refs = {"main":main,"pages":pages,"catalog_exchange":exchange,"catalog_tickers":tickers}
rules = files.load(blueprints / "combine.yaml")
for spec in [*rules["combine"]["groups"].values(),*rules["combine"]["tables"].values()]:
    spec["checks"] = {key:{"APPROVED_COMPANY_CAPTURE_RUN":"capture","APPROVED_CATALOG_CAPTURE_RUN":"catalog"}.get(value,value)
        for key,value in spec["checks"].items()}
manifest = store.put(folder.as_uri(),{"version":1,"contract":store.put(folder.as_uri(),rules),"readings":refs})
task = {"input":manifest,"output":(folder / "combined.json").as_uri(),"checks":["source.combined"]}
combined = source_combine.execute(task,store)
assert source_combine.execute(task,store) == combined
assert source_combine.check({**task,"candidate":combined},store) == ({"source.combined":True},[])
artifact = store.json(combined)["artifacts"][0]
assert store.json(artifact["input"])["readings"] == refs
row = artifact["tables"]["company"][0]
assert row["forms"] == ["10-K","20-F","8-K"]
assert row["tickers"] == ["A","B","C"]
assert row["business_address"]["country"] == "GB" and row["business_address"]["street"] == "Raw"
prepare = {"input":combined,"output":(folder / "mdm/manifest.json").as_uri(),"checks":["mdm.prepared"],
    "keys":{"table":"company","dataset":"sec.company.v1","policy":"0"*64,
        "consumer":"trial","batch_id":"composition","as_of":date}}
prepared = mdm_prepare.execute(prepare,store)
assert mdm_prepare.check({**prepare,"candidate":prepared},store) == ({"mdm.prepared":True},[])
batch = store.json(prepared)["batches"][0]
assert json.loads((folder / "mdm" / batch["input"]["path"]).read_bytes()) == row
print("installed Company raw combination and preparation passed")
''', cwd=root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'installed Company raw combination and preparation passed'


def test_active_company_preparation_caller_runs_from_installed_bundle(installed, tmp_path):
    """The installed CLI (`mdm prepare-capture`) writes the Company `mastering` target's input manifest from a raw capture,
    as the checkout does, and the installed Bookkeeping control freezes it against the installed
    target; neither can use the checkout (Issue 20 slice 20c)."""
    from tests.mdm.test_mdm_company_preparation import CATALOG_ROWS, PINS, company_capture, documents, prepare
    from tests.support.sec_capture import CATALOG
    python, root = installed
    capture = company_capture(tmp_path, documents(), CATALOG_ROWS)
    # --all: this test has no Change Journal; it names every document, as the checkout's does (ticket 22).
    original, _ = prepare(tmp_path, capture, output="checkout", force=True)
    folder, population = capture
    listed = tmp_path / "documents-checkout.json"
    arguments = ["mdm", "prepare-capture", "--source", "sec.company", "--capture", str(folder),
                 "--documents", str(listed), "--capture-run", PINS["capture_run"],
                 "--output", str(tmp_path / "pinned"), "--as-of", PINS["as_of"], "--revision", str(PINS["revision"]),
                 "--fact", f"capture_run={PINS['capture_run']}", "--fact", f"catalog_run={PINS['catalog_run']}",
                 "--fact", f"observed_at={PINS['observed_at']}", "--fact", "load_mode=default",
                 "--all"]
    run = _run(python, "-c", """
import sys
from edgar_warehouse.rules import source_engine
from edgar_warehouse.cli import main
source_engine.STEPS = {}
sys.exit(main(sys.argv[1:]))
""", *arguments, cwd=root)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert {k: v for k, v in report.items() if k != "manifest"} == {k: v for k, v in original.items() if k != "manifest"}
    # Only the output folder differs: the same steps hold the same units under the same keys.
    def units(manifest):
        steps = json.loads(Path(manifest["uri"].removeprefix("file://")).read_bytes())["steps"]
        return {step: [{k: v for k, v in u["keys"].items() if k != "destination"} for u in found]
                for step, found in steps.items()}
    assert units(report["manifest"]) == units(original["manifest"])
    frozen = _run(python, "-c", """
import json,sys
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import validate, worklist
from edgar_warehouse.rules import files
config = validate(files.source("sec.company"), "mastering")
items = worklist(Artifacts().json(json.load(sys.stdin)["manifest"]), config)
print(json.dumps(sorted({i["step"] for i in items})))
""", cwd=root, document=report)
    assert frozen.returncode == 0, frozen.stderr
    assert json.loads(frozen.stdout) == ["catalog", "combine", "main", "merge", "processed", "records"]
    repeated = _run(python,"-m","edgar_warehouse.cli",*arguments,cwd=root)
    assert repeated.returncode == 0,repeated.stderr
    assert json.loads(repeated.stdout)==report

from pathlib import Path
from urllib.parse import urlparse
from edgar_warehouse.control_contract import canonical
from edgar_warehouse.workers import source_read
from tests.engine.test_artifact_context import task, VALUES


def test_complete_name_count_projection_keeps_global_duplicates_and_pair_scoped_last_updates():
    import io
    from edgar_warehouse.workers.source_traversal import Traversal
    from tests.engine.test_gleif_configured_fields import raw
    records = [copy.deepcopy(raw()) for _ in range(5)]
    for row in records:
        row["Entity"]["EntityStatus"] = {"$": "ACTIVE"}
        row["Registration"]["LastUpdateDate"] = {"$": "earlier"}
    records[1]["Entity"]["LegalName"] = {"$": "Outside"}
    records[2]["Entity"]["EntityStatus"] = {"$": "INACTIVE"}
    records[3]["Entity"]["LegalName"] = {"$": "Another"}
    records[3]["Registration"]["LastUpdateDate"] = {"$": "another-name-update"}
    records[4]["Registration"]["LastUpdateDate"] = {"$": "latest-example-update"}
    config = files.load(files.ROOT / "sources/gleif/name-count-complete-stream.yaml")
    config["read"]["stream"]["container"] = "none"
    found = []
    receipt = Traversal(config, archive_policy="configured").scan(
        io.BytesIO(json.dumps({"records": records}).encode()),
        lookups={"wanted": {"EXAMPLE", "ANOTHER"}}, context={"publication_count": len(records)},
        on_reading=lambda reading, index: found.append(reading.tables))
    assert receipt["record_count"] == len(records)
    addresses = Counter(tuple(row.values()) for tables in found for row in tables["d_addresses"])
    assert len(addresses) == 1 and next(iter(addresses.values())) == 5
    # Deliberately dropping either noncandidate or ineligible occurrence changes
    # the global count, while the selected candidate observations stay the same.
    for excluded in (1, 2):
        faulty = Counter(tuple(row.values()) for i, tables in enumerate(found) if i != excluded
                         for row in tables["d_addresses"])
        assert faulty != addresses
    last = {}
    for tables in found:
        for row in tables["a_legal"]:
            last[row["key"], row["lei"]] = row["updated"]
    lei = records[0]["LEI"]["$"]
    assert last == {("EXAMPLE", lei): "latest-example-update", ("ANOTHER", lei): "another-name-update"}
    assert found[2]["a_legal"][0]["cascade"]["eligible"] is False
    assert [row["source_index"] for tables in found for row in tables["a_legal"]] == [1, 3, 4, 5]
