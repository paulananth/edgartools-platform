"""Real PG16 task lifecycle with separate restricted worker/verifier logins."""
import json
import os
from pathlib import Path
import subprocess
import sys

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.cli import main
from edgar_warehouse.rules import files
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401


def test_rules_submitted_13f_work_is_completed_by_separate_worker_and_verifier(
        databases, tmp_path, monkeypatch, capsys):
    root = Path(__file__).resolve().parents[2]
    store = Artifacts()
    grant_profile(databases.admin, profile="source.read", worker="bk_runtime", verifier="bk_verifier")
    body = files.pipeline("sec-13f-reading")
    saved = databases.rules.save("pipeline", "sec-13f-reading", "1", body)
    contract_path = root / "crates/source-contract/contracts/thirteenf/contract.yaml"
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
    env = {**os.environ,
           "BOOKKEEPING_CLEAN_DATABASE_URL": databases.runtime.url.render_as_string(hide_password=False),
           "RULES_DATABASE_URL": databases.rules.engine.url.render_as_string(hide_password=False),
           "CHANGE_JOURNAL_DATABASE_URL": databases.ledger.engine.url.render_as_string(hide_password=False),
           "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert main(["rules", "run", "--pipeline", "sec-13f-reading", "--target", "read",
                 "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"]]) == 0
    run_id = json.loads(capsys.readouterr().out)["run"]["run_id"]

    def command(*args):
        result = subprocess.run([sys.executable, "-m", *args], env=env, cwd=root,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        return result.stdout

    command("edgar_warehouse.workers", "work", "source.read", run_id)
    # A reported candidate must remain unverified until the other login checks it.
    state = json.loads(command("edgar_warehouse.bookkeeping", "status", run_id))
    assert state["counts"] != {"verified": 1}
    env["BOOKKEEPING_CLEAN_DATABASE_URL"] = databases.verifier.url.render_as_string(hide_password=False)
    command("edgar_warehouse.workers", "verify", "source.read", run_id,
            "--reports", (tmp_path / "reports").as_uri())
    state = json.loads(command("edgar_warehouse.bookkeeping", "finalize", run_id))
    assert state["counts"] == {"verified": 1} and state["run"]["state"] == "complete"
    assert json.loads((tmp_path / "holdings.json").read_bytes())["artifacts"][0]["tables"][
        "sec_thirteenf_holding"][0]["share_type"] == "SH"
