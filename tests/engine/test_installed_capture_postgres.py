"""Capture runs from committed installed wheels, no checkout."""
import json

from tests.engine.test_data_skill_bundle_postgres import installed, _run
from tests.integration.test_configured_capture_postgres import databases, setup


def test_installed_capture_with_offline_http(installed, setup, databases):
    python, root = installed
    book, start, _ = setup
    envelope = start()
    script = '''
import functools, importlib.metadata, json, sys
import httpx
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import control, provider_capture as capture, provider_transport as transport, profile
from edgar_warehouse.workers.__main__ import runtime
from edgar_warehouse.change_journal import ChangeJournal
from edgar_warehouse.change_journal.store import get_engine
assert profile("provider.capture") is capture
assert "site-packages" in capture.__file__
assert not {"edgartools", "spacy"} & {d.metadata["Name"].lower() for d in importlib.metadata.distributions()}
envelope = json.load(sys.stdin)
journal = ChangeJournal(get_engine())
calls = []
def response(request):
    assert journal.get(capture.AUTHORIZATION, envelope["effect_key"]) is not None
    calls.append(request)
    return httpx.Response(200, content=b'{"ok":true}', headers={"etag": 'W/"installed"'})
transport.httpx.Client = functools.partial(httpx.Client, transport=httpx.MockTransport(response))
artifacts = Artifacts()
candidate = capture.execute(envelope, artifacts)
assert len(calls) == 1
candidate = {"uri": candidate["uri"], "sha256": candidate["sha256"]}
checks, proofs = capture.check({**envelope, "candidate": candidate}, artifacts)
report = artifacts.put(envelope['output'].rsplit('/', 1)[0] + '/reports', control.report_document(envelope, candidate, checks, proofs, runtime(capture)))
control.report(envelope, candidate, report)
print(json.dumps(candidate))
'''
    worked = _run(python, '-c', script, cwd=root, document=envelope)
    assert worked.returncode == 0, worked.stderr
    candidate = json.loads(worked.stdout)
    book.deliver(databases.ledger, envelope['claim']['run_id'])
    assert book.finalize(envelope['claim']['run_id'])['run']['state'] == 'complete'
    assert book.artifacts.json(candidate)['metadata']['etag'] == 'W/"installed"'
