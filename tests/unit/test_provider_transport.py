"""Offline HTTP safety: exercise the actual streaming client with MockTransport."""
from functools import partial

import httpx
import pytest

from edgar_warehouse.workers import provider_transport as transport

URL = 'https://data.sec.gov/submissions/CIK0000000001.json'


@pytest.mark.parametrize('url', [
    'http://data.sec.gov/submissions/x', 'https://data.sec.gov.evil/submissions/x',
    'https://user@data.sec.gov/submissions/x', 'https://data.sec.gov:444/submissions/x',
    'https://data.sec.gov/submissions/x#fragment',
    'https://data.sec.gov/submissions/../x', 'https://data.sec.gov/submissions/%2e%2e/x',
    'https://data.sec.gov/submissions/%5cx', 'https://data.sec.gov/submissions/x\n',
    'https://www.sec.gov/submissions/x',
])
def test_url_cannot_escape_exact_approved_host_and_prefix(url):
    with pytest.raises(ValueError):
        transport.approved_url(url, ['https://data.sec.gov/submissions/'], 'sec.conditional')


def test_sec_hosts_share_one_lease_and_require_sec_capability():
    for host in transport.SEC_HOSTS:
        url = f'https://{host}/x'
        assert transport.approved_url(url, [f'https://{host}/'], 'sec.conditional') == url
        assert transport.provider_resource(url, 'sec.conditional') == 'provider:sec'
        with pytest.raises(ValueError):
            transport.approved_url(url, [f'https://{host}/'], 'http.conditional')
    with pytest.raises(ValueError):
        transport.approved_url('https://fixture.invalid/x', ['https://fixture.invalid/'], 'sec.conditional')
    with pytest.raises(ValueError):
        transport.approved_url('https://fixture.invalid.evil/x', ['https://fixture.invalid'], 'http.conditional')


def client(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(transport.httpx, 'Client', partial(real, transport=httpx.MockTransport(handler)))


def fetch(**kwargs):
    return transport.fetch(URL, 'test test@example.com', max_bytes=16,
                           requests_per_second=9, **kwargs)


def test_authorization_precedes_get_exact_validators_and_decoded_bytes(monkeypatch):
    order = []
    def respond(request):
        order.append('get')
        assert request.headers['If-None-Match'] == 'W/"version"'
        assert request.headers['If-Modified-Since'] == 'Wed, 21 Oct 2015 07:28:00 GMT'
        return httpx.Response(200, content=b'{"ok":true}', headers={'etag': '"new"'})
    client(monkeypatch, respond)
    pauses = []
    monkeypatch.setattr(transport.time, 'monotonic', lambda: 10.0)
    monkeypatch.setattr(transport.time, 'sleep', pauses.append)
    result = fetch(before_request=lambda: order.append('authorized'), etag='W/"version"',
                   last_modified='Wed, 21 Oct 2015 07:28:00 GMT')
    assert order == ['authorized', 'get']
    assert result == transport.Response(200, b'{"ok":true}', '"new"', None)
    assert pauses == [1 / 9]


@pytest.mark.parametrize('status,body', [(301, b''), (429, b''), (500, b''), (200, b'x' * 17), (304, b'')])
def test_refusals_make_one_request_and_hold_minimum_period(monkeypatch, status, body):
    calls, pauses = [], []
    client(monkeypatch, lambda request: calls.append(request) or httpx.Response(status, content=body))
    monkeypatch.setattr(transport.time, 'monotonic', lambda: 10.0)
    monkeypatch.setattr(transport.time, 'sleep', pauses.append)
    with pytest.raises(ValueError):
        fetch(before_request=lambda: None)
    assert len(calls) == 1
    assert pauses == [1 / 9]


def test_authority_failure_never_gets(monkeypatch):
    calls = []
    client(monkeypatch, lambda request: calls.append(request) or httpx.Response(200))
    def denied():
        raise RuntimeError('authority unavailable')
    with pytest.raises(RuntimeError):
        fetch(before_request=denied)
    assert calls == []


def test_304_retains_previous_validators_verbatim(monkeypatch):
    client(monkeypatch, lambda request: httpx.Response(304))
    result = fetch(before_request=lambda: None, etag='W/"prior"')
    assert result == transport.Response(304, b'', 'W/"prior"', None)


@pytest.mark.parametrize('value', ['', 'x\r\ny', 7, 'é', 'x' * 8193])
def test_invalid_validator(value):
    with pytest.raises(ValueError):
        transport.validator(value)


def test_network_error_is_not_retried(monkeypatch):
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('offline', request=request)
    client(monkeypatch, timeout)
    with pytest.raises(httpx.ReadTimeout):
        fetch(before_request=lambda: None)
    assert len(calls) == 1


def test_capture_runtime_pins_transport_evidence_and_native_engine(tmp_path, monkeypatch):
    from pathlib import Path
    from edgar_warehouse.workers import provider_capture as capture
    from edgar_warehouse.workers.__main__ import runtime
    from edgar_warehouse.rules import source_engine
    files = capture.runtime_files()
    assert Path(transport.__file__) in files
    assert {'artifacts.py', 'control_contract.py', 'acquisition_authority.py', 'store.py'} <= {p.name for p in files}
    assert any(p.suffix in ('.so', '.pyd') for p in files)
    binary = tmp_path / 'native.so'
    binary.write_bytes(b'first')
    monkeypatch.setattr(source_engine, 'runtime_files', lambda: [binary])
    first = runtime(capture)
    binary.write_bytes(b'changed')
    assert runtime(capture) != first
