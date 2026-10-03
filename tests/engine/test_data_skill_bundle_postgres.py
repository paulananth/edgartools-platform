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
        for _ in range(300):
            if subprocess.run(["docker", "exec", name, "psql", "-U", "postgres", "-c", "SELECT 1"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(0.1)
        sql = ("CREATE ROLE rules_agent LOGIN PASSWORD 'test'; CREATE ROLE rules_approver NOLOGIN; "
               "CREATE DATABASE rules;")
        for statement in sql.split(";")[:-1]:
            subprocess.run(["docker", "exec", name, "psql", "-U", "postgres", "-c", statement],
                           capture_output=True, check=True)
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
