"""Bookkeeping installed alone runs a whole run on PostgreSQL 16 (gate 1).

The control-only wheel and the Journal wheel go into a clean environment with
no domain distribution. Every control call of the run goes through that
installation's own CLI, in isolated mode, so nothing from the repository can
stand in for a missing dependency (mastering to-do 20b).
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

from edgar_warehouse.workers import copy
from edgar_warehouse.workers.control import report_document
from tests.integration.test_configured_bookkeeping_postgres import config, databases, submit
from tests.support.bookkeeping_protocol import RUNTIME
from tests.support.journal_isolation import ROOT

DOMAIN = ("edgar", "edgartools", "pyarrow", "lxml", "bs4", "ijson", "boto3", "duckdb", "pandas", "source-contract")


@pytest.fixture(scope="module")
def control_python(tmp_path_factory):
    assert shutil.which("uv"), "Wheel acceptance requires uv"
    root = tmp_path_factory.mktemp("control-only-install")
    for package in ("bookkeeping", "change-journal"):
        subprocess.run(["uv", "build", "--wheel", str(ROOT / "packages" / package), "--out-dir", str(root / "dist")],
                       capture_output=True, text=True, check=True)
    subprocess.run(["uv", "venv", "--python", sys.executable, str(root / "venv")], capture_output=True, text=True, check=True)
    python = root / "venv" / "bin" / "python"
    subprocess.run(["uv", "pip", "install", "--python", str(python), *map(str, (root / "dist").glob("*.whl"))],
                   capture_output=True, text=True, check=True)
    return python


def test_the_control_wheel_holds_control_alone(control_python):
    result = subprocess.run([str(control_python), "-I", "-c", f'''
import importlib.metadata, json
names = {{d.metadata["Name"].lower() for d in importlib.metadata.distributions()}}
assert not names & set({DOMAIN!r}), names & set({DOMAIN!r})
files = {{str(p) for p in importlib.metadata.files("edgartools-bookkeeping") if str(p).startswith("edgar_warehouse/")}}
assert not any(f.startswith(("edgar_warehouse/mdm", "edgar_warehouse/workers", "edgar_warehouse/loaders",
                              "edgar_warehouse/parsers", "edgar_warehouse/application")) for f in files), files
assert "edgar_warehouse/bookkeeping/clean/migrations/006_issuer_roles.sql" in files
print("control only")
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "control only"


def test_installed_control_runs_a_whole_run(control_python, databases, tmp_path):
    def control(url, *arguments, document=None):
        done = subprocess.run([str(control_python), "-I", "-m", "edgar_warehouse.bookkeeping", *arguments],
                              input=None if document is None else json.dumps(document), capture_output=True, text=True,
                              env={**os.environ, "BOOKKEEPING_CLEAN_DATABASE_URL": url,
                                   "BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL": owner,
                                   "CHANGE_JOURNAL_DATABASE_URL": journal}, cwd=tmp_path)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    url = lambda engine: engine.url.render_as_string(hide_password=False)
    owner, worker, verifier, journal = url(databases.admin), url(databases.runtime), url(databases.verifier), url(databases.ledger.engine)
    assert "006_issuer_roles.sql" in control(owner, "migrate", "--runtime-role", "bk_control")
    control(owner, "grant-profile", "--profile", "artifact.copy", "--worker", "bk_runtime", "--verifier", "bk_verifier")
    # Submission is Rules' job; the run is frozen in this process.
    book, rid, _, _ = submit(databases, tmp_path, count=2, body=config())
    artifacts = book.artifacts
    for envelope in control(worker, "claim", rid, "--profile", "artifact.copy"):
        candidate = copy.execute(envelope, artifacts)
        control(worker, "report", "--envelope", "-", "--candidate", candidate["uri"], "--sha256", candidate["sha256"],
                "--runtime", RUNTIME, document=envelope)
    for verification in control(verifier, "verifications", rid, "--profile", "artifact.copy"):
        checks, proofs = copy.verify(verification, artifacts)
        report = artifacts.put(tmp_path.as_uri() + "/reports", report_document(verification, checks, proofs, RUNTIME))
        control(verifier, "admit", "--verification", "-", "--report", report["uri"], "--sha256", report["sha256"],
                document=verification)
    finished = control(worker, "finalize", rid)
    assert finished["run"]["state"] == "complete" and finished["counts"] == {"verified": 2}
