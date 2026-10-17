"""Real PG16 authority/Journal/recovery with an offline HTTP transport only.

Fixtures are approved fixture Rules, never production SEC acquisition proof.
Worker renewal invokes public control commands with its restricted login;
independent readback/admission uses a separate verifier login.
"""
from copy import deepcopy
from functools import partial
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.workers import control, provider_capture as capture, provider_transport as transport
from edgar_warehouse.workers.__main__ import runtime
from tests.integration.test_configured_bookkeeping_postgres import databases, expire, config, approved_acquisition
from tests.support.rules_approval import approve


@pytest.fixture
def setup(databases, tmp_path, monkeypatch, request):
    grant_profile(databases.admin, profile=capture.PRODUCER, worker='bk_runtime', verifier='bk_verifier')
    monkeypatch.setenv('BOOKKEEPING_DATABASE_URL', databases.runtime.url.render_as_string(hide_password=False))
    monkeypatch.setenv('CHANGE_JOURNAL_DATABASE_URL', databases.ledger.engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv('EDGAR_IDENTITY', 'Offline fixture test@example.com')
    book, verifier = Bookkeeping(databases.runtime), Bookkeeping(databases.verifier)
    body = config(resource='output:{destination}')
    target = body['bookkeeping']['targets'].pop('silver')
    body['bookkeeping']['targets']['capture'] = target
    target['steps'][0].update(name='fixture', operation=capture.PRODUCER, leases=['provider:fixture.invalid', 'output:{destination}'],
                              checks=['input.hash', 'output.receipt', capture.CHECK])
    if getattr(request, 'param', None) == 'without_provider':
        target['steps'][0]['leases'] = ['output:{destination}']
    name = 'capture-' + uuid4().hex
    baseline = book.artifacts.put(tmp_path.as_uri() + '/baseline', {'offline': True})
    proof = approved_acquisition(body, name, [], baseline)
    body['acquisition']['feeds']['fixture']['completeness'].update(required=['ok'], allow_empty=False)
    if getattr(request, 'param', None) == 'with_page':
        body['acquisition']['feeds']['fixture']['page_completeness'] = {
            'format': 'json', 'required': ['page'], 'allow_empty': False, 'max_bytes': 1024}
    elif getattr(request, 'param', None) in ('xml', 'zip', 'text', 'ticker_catalog'):
        body['acquisition']['feeds']['fixture']['completeness']['format'] = request.param
    elif getattr(request, 'param', None) == 'oversize_bound':
        body['acquisition']['feeds']['fixture']['completeness']['max_bytes'] = transport.MAX_BYTES + 1
    elif getattr(request, 'param', None) == 'post':  # ticket 92: a mapping API, a JSON array back
        feed = body['acquisition']['feeds']['fixture']
        feed['capabilities']['fetch'] = 'https.post'
        feed['secret_header'] = {'name': 'X-Fixture-Key', 'environment': 'FIXTURE_API_KEY'}
        feed['completeness'].update(format='json_array', required=[])
    elif getattr(request, 'param', None) == 'invalid_native_contract':
        body['acquisition']['feeds']['fixture']['completeness']['required'] = ['x' * 4096]
    saved = databases.rules.save('source', name, '1', body)
    databases.rules.prove('source', name, '1', {'digest': saved['digest'], 'batch_hash': baseline['sha256'],
                                               'passed': True, 'acquisition': proof})
    approve(databases.approver, 'source', name, '1')
    databases.rules.activate('source', name, '1')
    rules = databases.rules.resolve('source', name, root=tmp_path.as_uri() + '/rules')

    def start(previous=None, **changes):
        key = uuid4().hex
        request = dict(version=1, feed='fixture', url='https://fixture.invalid/main.json', scope={'fixture': 'same'},
                       requested_at='2026-10-12T00:00:00+00:00', requests_per_second=9, document='main')
        if previous:
            request['previous'] = previous
        request.update(changes)
        input_ref = book.artifacts.put(tmp_path.as_uri() + '/requests', request)
        output = (tmp_path / key / 'receipt.json').as_uri()
        units = book.artifacts.put(tmp_path.as_uri() + '/inputs', {'version': 1, 'units': [
            {'keys': {'id': key, 'destination': output, 'feed': 'fixture', 'fixture': 'same'},
             'input': input_ref, 'output': output, 'cursor': {'offset': 0}}]})
        rid = book.start(rules_ref=rules, inputs_ref=units, target='capture', scope={'source': name, 'feed': 'fixture'})
        envelope, = book.tasks(rid, capture.PRODUCER, limit=1)
        return envelope

    def finish(envelope, candidate):
        book.report(envelope, candidate, runtime(capture))
        from sqlalchemy.exc import DBAPIError
        with pytest.raises(DBAPIError):
            book.verifications(envelope['claim']['run_id'], capture.PRODUCER, limit=1)
        verification, = verifier.verifications(envelope['claim']['run_id'], capture.PRODUCER, limit=1)
        monkeypatch.setenv('BOOKKEEPING_DATABASE_URL', databases.verifier.url.render_as_string(hide_password=False))
        try:
            renewed = control.renew(verification)
            checks, proofs = capture.verify(renewed, book.artifacts)
            report = book.artifacts.put(tmp_path.as_uri() + '/reports', control.report_document(renewed, checks, proofs, runtime(capture)))
            control.admit(renewed, report)
        finally:
            monkeypatch.setenv('BOOKKEEPING_DATABASE_URL', databases.runtime.url.render_as_string(hide_password=False))
        book.deliver(databases.ledger, envelope['claim']['run_id'])
        assert book.finalize(envelope['claim']['run_id'])['run']['state'] == 'complete'
        return verification

    yield book, start, finish
    # Tests deliberately leave expired/invalid attempts behind. Expire only
    # this fixture provider's leases in the disposable PG16 control store.
    from sqlalchemy import text
    with databases.admin.begin() as conn:
        conn.execute(text("UPDATE bookkeeping.lease SET expires_at=clock_timestamp()-interval '1 second' WHERE resource='provider:fixture.invalid'"))


def http(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(transport.httpx, 'Client', partial(real, transport=httpx.MockTransport(handler)))


def test_capture_control_journal_order_and_restricted_verifier(setup, databases, monkeypatch):
    book, start, finish = setup
    envelope = start()
    called = []
    def response(request):
        intent = databases.ledger.get(capture.AUTHORIZATION, envelope['effect_key'])
        assert intent is not None
        databases.ledger.verify(intent)
        called.append(request)
        return httpx.Response(200, content=b'{"ok":true}', headers={'etag': 'W/"one"'})
    http(monkeypatch, response)
    candidate = capture.execute(envelope, book.artifacts)
    assert len(called) == 1
    receipt = book.artifacts.json(candidate)
    assert receipt['metadata']['bytes'] == 11
    assert receipt['metadata']['etag'] == 'W/"one"'
    assert capture._unpack(book.artifacts.verified(receipt['snapshot']), 1024)[1] == b'{"ok":true}'
    finish(envelope, candidate)


@pytest.mark.parametrize('damage', ['input', 'rules', 'output', 'scope', 'url', 'rate', 'format', 'expired', 'takeover'])
def test_invalid_authority_before_any_http(setup, databases, monkeypatch, damage):
    book, start, _ = setup
    envelope = start(document='page' if damage == 'format' else 'main',
                     scope={'fixture': 'wrong'} if damage == 'scope' else {'fixture': 'same'},
                     url='https://fixture.invalid.evil/main.json' if damage == 'url' else 'https://fixture.invalid/main.json',
                     requests_per_second=True if damage == 'rate' else 9)
    if damage in ('input', 'rules'):
        envelope[damage] = book.artifacts.put(envelope['output'] + '/bad', {'forged': True})
    elif damage == 'output':
        envelope['output'] += '/forged'
    elif damage in ('expired', 'takeover'):
        expire(databases, book._claim_of(envelope))
        if damage == 'takeover':
            replacement, = book.tasks(envelope['claim']['run_id'], capture.PRODUCER, limit=1)
            assert replacement['claim']['attempt'] != envelope['claim']['attempt']
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    with pytest.raises((ValueError, control.ControlError)):
        capture.execute(envelope, book.artifacts)
    assert calls == []


def test_journal_outage_blocks_get_then_recovers(setup, monkeypatch):
    book, start, finish = setup
    envelope = start()
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    with monkeypatch.context() as patch:
        class Down:
            engine = type('Engine', (), {'dispose': lambda self: None})()
            def append(self, event):
                raise RuntimeError('Journal unavailable')
        patch.setattr(capture, '_journal', Down)
        with pytest.raises(RuntimeError, match='Journal unavailable'):
            capture.execute(envelope, book.artifacts)
    assert calls == []
    finish(envelope, capture.execute(envelope, book.artifacts))
    assert len(calls) == 1


def test_lease_expiring_during_journal_acknowledgement_blocks_get(setup, databases, monkeypatch):
    from edgar_warehouse.change_journal import ChangeJournal
    book, start, _ = setup
    envelope = start()
    original = ChangeJournal.append
    def append(self, event):
        receipt = original(self, event)
        expire(databases, book._claim_of(envelope))
        return receipt
    monkeypatch.setattr(ChangeJournal, 'append', append)
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200))
    with pytest.raises(control.ControlError):
        capture.execute(envelope, book.artifacts)
    assert calls == []


def test_shared_provider_lease_blocks_another_run(setup, databases):
    book, start, _ = setup
    first = start()
    with pytest.raises(ValueError, match='not enough values to unpack'):
        start()  # No second task can hold the same provider lease.
    expire(databases, book._claim_of(first))
    replacement = start()
    assert replacement['claim']['run_id'] != first['claim']['run_id']


@pytest.mark.parametrize('setup', ['without_provider'], indirect=True)
def test_genuine_approved_plan_without_provider_lease_never_gets(setup, monkeypatch):
    book, start, _ = setup
    envelope = start()
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200))
    with pytest.raises(ValueError, match='shared provider lease'):
        capture.execute(envelope, book.artifacts)
    assert calls == []


@pytest.mark.parametrize('setup', ['with_page'], indirect=True)
def test_page_uses_its_own_approved_completeness(setup, monkeypatch):
    book, start, finish = setup
    http(monkeypatch, lambda request: httpx.Response(200, content=b'{"page":true}'))
    envelope = start(document='page')
    finish(envelope, capture.execute(envelope, book.artifacts))


@pytest.mark.parametrize('setup', ['xml', 'zip', 'text', 'ticker_catalog', 'oversize_bound'], indirect=True)
def test_approved_unsupported_format_or_bound_refuses_before_get(setup, monkeypatch):
    book, start, _ = setup
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200))
    with pytest.raises(ValueError, match='bounded JSON object or array completeness'):
        capture.execute(start(), book.artifacts)
    assert calls == []


@pytest.mark.parametrize('setup', ['invalid_native_contract'], indirect=True)
def test_approved_but_invalid_native_contract_refuses_before_get(setup, monkeypatch):
    from edgar_warehouse.rules.source_engine import SourceRejected
    book, start, _ = setup
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    with pytest.raises(SourceRejected, match='contract: an assertion reason'):
        capture.execute(start(), book.artifacts)
    assert calls == []


def test_lease_loss_after_get_cannot_persist_but_retry_can_refetch(setup, databases, monkeypatch):
    book, start, finish = setup
    envelope = start()
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            expire(databases, book._claim_of(envelope))
        return httpx.Response(200, content=b'{"ok":true}')
    http(monkeypatch, respond)
    with pytest.raises(control.ControlError):
        capture.execute(envelope, book.artifacts)
    assert not Path(envelope['output'].removeprefix('file://') + '.capture.zip').exists()
    assert databases.ledger.get(capture.OUTCOME, envelope['effect_key']) is None
    replacement, = book.tasks(envelope['claim']['run_id'], capture.PRODUCER, limit=1)
    finish(replacement, capture.execute(replacement, book.artifacts))
    assert len(calls) == 2  # No durable snapshot existed; no exactly-once HTTP claim.


@pytest.mark.parametrize('damage', ['authorization', 'outcome', 'candidate', 'snapshot'])
def test_independent_verifier_rejects_disagreeing_durable_evidence(setup, databases, monkeypatch, damage):
    from edgar_warehouse.change_journal import ChangeJournal
    book, start, _ = setup
    envelope = start()
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    candidate = capture.execute(envelope, book.artifacts)
    book.report(envelope, candidate, runtime(capture))
    verifier = Bookkeeping(databases.verifier)
    verification, = verifier.verifications(envelope['claim']['run_id'], capture.PRODUCER, limit=1)
    if damage in ('authorization', 'outcome'):
        original = ChangeJournal.get
        producer = capture.AUTHORIZATION if damage == 'authorization' else capture.OUTCOME
        # Simulate an unavailable acknowledgement. Other evidence still comes
        # from real restricted-role Journal reads, never invented receipts.
        monkeypatch.setattr(ChangeJournal, 'get', lambda self, p, key: None if p == producer else original(self, p, key))
    elif damage == 'candidate':
        import hashlib
        forged = b'{"forged":true}'
        Path(candidate['uri'].removeprefix('file://')).write_bytes(forged)
        # Even a hash-consistent candidate must equal reconstructed evidence.
        verification['candidate'] = {**candidate, 'sha256': hashlib.sha256(forged).hexdigest()}
    else:
        receipt = book.artifacts.json(candidate)
        meta, payload = capture._unpack(book.artifacts.verified(receipt['snapshot']), 1024)
        meta['feed'] = 'wrong'
        Path(receipt['snapshot']['uri'].removeprefix('file://')).write_bytes(capture._pack(meta, payload))
    with pytest.raises((ValueError, Blocked)):
        capture.verify(verification, book.artifacts)
    assert len(calls) == 1
    assert verifier.status(envelope['claim']['run_id'])['counts'] == {'reported': 1}


@pytest.mark.parametrize('damage', ['snapshot', 'orphan_candidate'])
def test_corrupt_existing_destination_never_refetches(setup, monkeypatch, damage):
    book, start, _ = setup
    envelope = start()
    uri = envelope['output'] + '.capture.zip' if damage == 'snapshot' else envelope['output']
    book.artifacts.put_bytes(uri, b'corrupt')
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200))
    with pytest.raises((ValueError, capture.zipfile.BadZipFile)):
        capture.execute(envelope, book.artifacts)
    assert calls == []


@pytest.mark.parametrize('lost', ['snapshot', 'journal', 'candidate'])
def test_lost_acknowledgement_reuses_durable_snapshot_after_takeover(setup, databases, monkeypatch, lost):
    book, start, finish = setup
    envelope = start()
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    with monkeypatch.context() as patch:
        if lost in ('snapshot', 'candidate'):
            original = book.artifacts.put_bytes
            def put(uri, data):
                result = original(uri, data)
                if uri.endswith('.capture.zip') == (lost == 'snapshot'):
                    raise RuntimeError('lost acknowledgement')
                return result
            patch.setattr(book.artifacts, 'put_bytes', put)
        else:
            from edgar_warehouse.change_journal import ChangeJournal
            original = ChangeJournal.append
            def append(self, event):
                result = original(self, event)
                if event['event_type'] == 'capture.captured':
                    raise RuntimeError('lost acknowledgement')
                return result
            patch.setattr(ChangeJournal, 'append', append)
        with pytest.raises(RuntimeError, match='lost acknowledgement'):
            capture.execute(envelope, book.artifacts)
    expire(databases, book._claim_of(envelope))
    replacement, = book.tasks(envelope['claim']['run_id'], capture.PRODUCER, limit=1)
    candidate = capture.execute(replacement, book.artifacts)
    assert len(calls) == 1
    finish(replacement, candidate)


def test_304_hashes_declared_previous_and_flattens_chains(setup, monkeypatch):
    book, start, finish = setup
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, content=b'{"ok":true}', headers={'etag': 'W/"one"'})
        assert request.headers['If-None-Match'] == 'W/"one"'
        return httpx.Response(304)
    http(monkeypatch, respond)
    main = start()
    original = capture.execute(main, book.artifacts)
    finish(main, original)
    previous = original
    for _ in range(2):
        envelope = start(previous=previous)
        previous = capture.execute(envelope, book.artifacts)
        receipt = book.artifacts.json(previous)
        assert receipt['metadata']['status'] == 304
        assert receipt['metadata']['previous'] == original
        assert capture._unpack(book.artifacts.verified(receipt['snapshot']), 1024)[1] == b''
        finish(envelope, previous)
    assert len(calls) == 3


@pytest.mark.parametrize('damage', ['receipt', 'snapshot', 'journal', 'scope'])
def test_corrupt_predecessor_fails_before_get(setup, monkeypatch, damage):
    book, start, finish = setup
    calls = []
    http(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, content=b'{"ok":true}', headers={'etag': '"one"'}))
    envelope = start()
    previous = capture.execute(envelope, book.artifacts)
    finish(envelope, previous)
    receipt = book.artifacts.json(previous)
    if damage == 'snapshot':
        Path(receipt['snapshot']['uri'].removeprefix('file://')).write_bytes(b'corrupt')
    elif damage == 'receipt':
        previous = {**previous, 'sha256': '0' * 64}
    else:
        invalid = deepcopy(receipt)
        if damage == 'journal':
            invalid['journal']['sha256'] = '0' * 64
        else:
            invalid['metadata']['scope']['fixture'] = 'wrong'
        previous = book.artifacts.put(envelope['output'] + '-bad', invalid)
    next_envelope = start(previous=previous)
    with pytest.raises((Blocked, ValueError)):
        capture.execute(next_envelope, book.artifacts)
    assert len(calls) == 1


SECRET = 'fixture-secret-never-stored'
JOBS = [{'idType': 'ID_CUSIP', 'idValue': 'FIXTURE01'}]


@pytest.mark.parametrize('setup', ['post'], indirect=True)
def test_post_sends_its_frozen_body_and_key_and_never_keeps_the_key(setup, databases, monkeypatch, tmp_path):
    book, start, finish = setup
    monkeypatch.setenv('FIXTURE_API_KEY', SECRET)
    envelope = start(body=JOBS)
    called = []
    def response(request):
        called.append(request)
        assert request.method == 'POST' and request.headers['X-Fixture-Key'] == SECRET
        assert request.headers['Content-Type'] == 'application/json'
        assert 'If-None-Match' not in request.headers
        assert request.read() == b'[{"idType":"ID_CUSIP","idValue":"FIXTURE01"}]'
        return httpx.Response(200, content=b'[{"data":[]}]')
    http(monkeypatch, response)
    candidate = capture.execute(envelope, book.artifacts)
    assert capture.execute(envelope, book.artifacts) == candidate and len(called) == 1  # a retry reuses the snapshot
    finish(envelope, candidate)
    written = b''.join(path.read_bytes() for path in tmp_path.rglob('*') if path.is_file())
    assert SECRET.encode() not in written
    from sqlalchemy import text
    with databases.admin.connect() as conn:  # nor in any Journal or control row
        for schema, table in conn.execute(text("SELECT table_schema, table_name FROM information_schema.tables "
                                               "WHERE table_schema IN ('change_journal', 'bookkeeping')")):
            found = conn.execute(text(f'SELECT count(*) FROM "{schema}"."{table}" t WHERE t::text LIKE :s'),
                                 {'s': f'%{SECRET}%'}).scalar()
            assert found == 0, (schema, table)


@pytest.mark.parametrize('setup', ['post'], indirect=True)
@pytest.mark.parametrize('case', ['missing_key', 'no_body', 'object_back'])
def test_post_refusals(setup, monkeypatch, case):
    book, start, _ = setup
    if case != 'missing_key':
        monkeypatch.setenv('FIXTURE_API_KEY', SECRET)
    else:
        monkeypatch.delenv('FIXTURE_API_KEY', raising=False)
    envelope = start() if case == 'no_body' else start(body=JOBS)
    called = []
    http(monkeypatch, lambda request: called.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    from edgar_warehouse.rules.source_engine import SourceRejected
    with pytest.raises((ValueError, SourceRejected)) as refused:  # an object back fails its array completeness
        capture.execute(envelope, book.artifacts)
    assert SECRET not in str(refused.value)
    assert len(called) == (1 if case == 'object_back' else 0)


def test_a_get_feed_never_sends_a_body(setup, monkeypatch):
    book, start, _ = setup
    called = []
    http(monkeypatch, lambda request: called.append(request) or httpx.Response(200, content=b'{"ok":true}'))
    with pytest.raises(ValueError, match='Only a POST feed'):
        capture.execute(start(body=JOBS), book.artifacts)
    assert not called


@pytest.mark.parametrize('setup', ['post'], indirect=True)
def test_a_failed_post_keeps_no_key_in_its_error(setup, monkeypatch):
    book, start, _ = setup
    monkeypatch.setenv('FIXTURE_API_KEY', SECRET)
    def broken(request):
        raise httpx.ConnectError('refused', request=request)
    http(monkeypatch, broken)
    with pytest.raises(ValueError, match='Provider request failed: ConnectError') as refused:
        capture.execute(start(body=JOBS), book.artifacts)
    assert refused.value.__suppress_context__ and SECRET not in str(refused.value)  # the httpx error, with its headers, is not chained
