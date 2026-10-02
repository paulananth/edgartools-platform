"""Actual PG16 journal operations from a package with no producer implementations."""

import json
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.integration.test_configured_bookkeeping_postgres import databases
from tests.support.journal_isolation import ROOT, run_isolated


@pytest.fixture(scope="module")
def journal_python(tmp_path_factory):
    """Install the real wheel with its own minimal dependency closure."""
    assert shutil.which("uv"), "Journal wheel acceptance requires uv"
    root = tmp_path_factory.mktemp("independent-journal-install")
    subprocess.run(["uv", "build", "--wheel", str(ROOT / "packages/change-journal"),
                    "--out-dir", str(root / "dist")], capture_output=True, text=True, check=True)
    wheels = list((root / "dist").glob("*.whl"))
    assert len(wheels) == 1
    subprocess.run(["uv", "venv", "--python", sys.executable, str(root / "venv")],
                   capture_output=True, text=True, check=True)
    python = root / "venv" / "bin" / "python"
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheels[0])],
                   capture_output=True, text=True, check=True)
    result = subprocess.run([str(python), "-I", "-c", '''
import importlib.metadata
import json
assert not any(importlib.metadata.packages_distributions().get(name) for name in ("edgar", "pyarrow", "lxml", "ijson", "boto3"))
files = importlib.metadata.files("edgartools-change-journal")
assert {str(path) for path in files if str(path).startswith("edgar_warehouse/") and not str(path).endswith(".pyc")} == {
    "edgar_warehouse/__init__.py", "edgar_warehouse/control_contract.py",
    "edgar_warehouse/change_journal/__init__.py", "edgar_warehouse/change_journal/cli.py",
    "edgar_warehouse/change_journal/database.py", "edgar_warehouse/change_journal/store.py",
    "edgar_warehouse/change_journal/migrations/001_event.sql",
}
print("minimal wheel installed")
'''], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "minimal wheel installed"
    return str(python)


def test_isolated_journal_migrations_append_reconcile_and_cli_with_restricted_role(databases, tmp_path, journal_python):
    root = tmp_path
    environment = {
        "CHANGE_JOURNAL_DATABASE_URL": databases.ledger.engine.url.render_as_string(hide_password=False),
        "CHANGE_JOURNAL_MIGRATION_DATABASE_URL": databases.ledger_admin.url.render_as_string(hide_password=False),
    }
    # This module owns a fresh disposable fixture. Require the installed wheel
    # to initialize an empty store, rather than relying on fixture migrations.
    with databases.ledger_admin.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM journal.event")) == 0
        conn.execute(text("DROP SCHEMA journal CASCADE"))
    initialized = run_isolated(root, '''
from edgar_warehouse.change_journal.cli import main
raise SystemExit(main(["init", "--runtime-role", "ledger_runtime"]))
''', environment=environment, python=journal_python, installed=True)
    assert initialized.returncode == 0, initialized.stderr
    assert set(json.loads(initialized.stdout)) == {"001_event.sql"}
    key = uuid4().hex
    runtime = run_isolated(root, '''
import json
import sys
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from edgar_warehouse.change_journal import ChangeJournal, JournalConflict, envelope
from edgar_warehouse.change_journal.store import get_engine

engine = get_engine()
try:
    journal = ChangeJournal(engine)
    value = envelope(producer="unseen.producer", event_key=sys.argv[1], run_id="00000000-0000-0000-0000-000000000001",
        source="unseen.source", feed="unseen.feed", event_type="unseen.event", occurred_at="2026-10-02T00:00:00+00:00",
        evidence=[{"uri": "s3://evidence/opaque", "sha256": "a" * 64}])
    receipt = journal.append(value)
    assert journal.append(value) == receipt
    assert journal.verify(receipt, expected=value) == receipt
    try:
        journal.append({**value, "event_type": "conflicting.event"})
    except JournalConflict:
        pass
    else:
        raise AssertionError("Conflicting key was accepted")
    assert journal.list(source="unseen.source", feed="unseen.feed", limit=1)[0] == receipt
    with engine.connect() as conn:
        assert int(conn.scalar(text("SHOW server_version_num"))) // 10000 == 16
        assert conn.scalar(text("SELECT current_user")) == "ledger_runtime"
        assert conn.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")) is False
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT * FROM journal.event"))
    except DBAPIError:
        pass
    else:
        raise AssertionError("Runtime has direct table access")
    print(json.dumps(receipt, default=str))
finally:
    engine.dispose()
''', arguments=(key,), environment=environment, python=journal_python, installed=True)
    assert runtime.returncode == 0, runtime.stderr
    receipt = json.loads(runtime.stdout)
    receipt_path = root / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    for arguments in (["init", "--runtime-role", "ledger_runtime"],
                      ["migrate", "--runtime-role", "ledger_runtime"],
                      ["status", "--source", "unseen.source", "--feed", "unseen.feed"],
                      ["events", "--source", "unseen.source", "--feed", "unseen.feed", "--limit", "1"],
                      ["verify", str(receipt_path)]):
        result = run_isolated(root, '''
import sys
from edgar_warehouse.change_journal.cli import main
raise SystemExit(main(sys.argv[1:]))
''', arguments=arguments, environment=environment, python=journal_python, installed=True)
        assert result.returncode == 0, result.stderr
        body = json.loads(result.stdout)
        if arguments[0] == "events":
            assert body == [receipt]
        elif arguments[0] == "verify":
            assert body == receipt
        elif arguments[0] in {"init", "migrate"}:
            assert set(body) == {"001_event.sql"}
