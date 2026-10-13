"""Durable snapshot safety and bounded storage reads; no provider requests."""
import hashlib
import io
from types import SimpleNamespace
import zipfile

from botocore.exceptions import ClientError
import httpx
import pytest

from edgar_warehouse.control_contract import canonical
from edgar_warehouse.workers import provider_capture as capture, provider_transport as transport


def metadata(payload=b'{"ok":true}'):
    ref = {'uri': 's3://fixture/manifest.json', 'sha256': '0' * 64}
    return dict(version=1, request=ref, rules=ref, effect_key='effect', run_id='run',
                source='fixture', feed='fixture', url='https://fixture.invalid/main.json',
                scope={'fixture': 'same'}, status=200, etag='W/"one"', last_modified=None,
                bytes=len(payload), payload_sha256=hashlib.sha256(payload).hexdigest(),
                captured_at='2026-10-12T00:00:00+00:00', previous=None)


@pytest.mark.parametrize('damage', ['extra_member', 'compressed', 'reordered', 'oversized_metadata'])
def test_snapshot_rejects_ambiguous_or_unbounded_frames(damage):
    entries = [('metadata.json', canonical(metadata()).encode()), ('payload', b'{"ok":true}')]
    if damage == 'extra_member':
        entries.append(('unexpected', b'ignored'))
    elif damage == 'reordered':
        entries.reverse()
    elif damage == 'oversized_metadata':
        entries[0] = ('metadata.json', b' ' * (capture.HEADER_BYTES + 1))
    stream = io.BytesIO()
    compression = zipfile.ZIP_DEFLATED if damage == 'compressed' else zipfile.ZIP_STORED
    with zipfile.ZipFile(stream, 'w', compression=compression) as archive:
        for name, body in entries:
            archive.writestr(name, body)
    with pytest.raises(ValueError, match='Unsupported or oversized'):
        capture._unpack(stream.getvalue(), 1024)


@pytest.mark.parametrize('damage', ['hash', 'length', 'conditional_body'])
def test_payload_integrity_survives_valid_zip_framing(damage):
    body = b'{"ok":true}'
    document = metadata(body)
    if damage == 'hash':
        document['payload_sha256'] = '0' * 64
    elif damage == 'length':
        document['bytes'] += 1
    else:
        document.update(status=304, previous=document['request'])
    with pytest.raises(ValueError, match='payload disagrees|reuse previous bytes'):
        capture._unpack(capture._pack(document, body), 1024)


@pytest.mark.parametrize('damage', ['duplicate_key', 'non_utc_timestamp'])
def test_snapshot_control_metadata_is_strict(damage):
    document = metadata()
    header = canonical(document).encode()
    if damage == 'duplicate_key':
        header = b'{"version":1,' + header[1:]
    else:
        document['captured_at'] = '2026-10-12T00:00:00'
        header = canonical(document).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('metadata.json', header)
        archive.writestr('payload', b'{"ok":true}')
    with pytest.raises(ValueError, match='duplicate JSON key|explicit UTC'):
        capture._unpack(stream.getvalue(), 1024)


@pytest.mark.parametrize('code', ['NoSuchKey', 'NoSuchBucket', '404', 'AccessDenied', 'SlowDown'])
def test_only_explicit_missing_object_can_allow_a_new_request(code):
    error = ClientError({'Error': {'Code': code}}, 'GetObject')
    class Storage:
        def get_object(self, **kwargs):
            assert kwargs == {'Bucket': 'fixture', 'Key': 'capture.zip'}
            raise error
    artifacts = SimpleNamespace(s3=Storage())
    if code == 'NoSuchKey':
        assert capture._optional(artifacts, 's3://fixture/capture.zip', 8) is None
    else:
        with pytest.raises(ClientError) as caught:
            capture._optional(artifacts, 's3://fixture/capture.zip', 8)
        assert caught.value is error


@pytest.mark.parametrize('body', [b'exactly8', b'oversized'])
def test_optional_s3_read_is_bounded_and_always_closed(body):
    requests = []
    class Stream(io.BytesIO):
        def read(self, count=-1):
            requests.append(count)
            return super().read(count)
    stream = Stream(body)
    artifacts = SimpleNamespace(s3=SimpleNamespace(get_object=lambda **kwargs: {'Body': stream}))
    if len(body) == 8:
        assert capture._optional(artifacts, 's3://fixture/capture.zip', 8) == body
    else:
        with pytest.raises(ValueError, match='exceeds'):
            capture._optional(artifacts, 's3://fixture/capture.zip', 8)
    assert requests == [9]
    assert stream.closed


def test_storage_read_outage_is_propagated_and_stream_closed():
    failure = OSError('interrupted storage response')
    class Stream(io.BytesIO):
        def read(self, count=-1):
            raise failure
    stream = Stream()
    artifacts = SimpleNamespace(s3=SimpleNamespace(get_object=lambda **kwargs: {'Body': stream}))
    with pytest.raises(OSError) as caught:
        capture._optional(artifacts, 's3://fixture/capture.zip', 8)
    assert caught.value is failure
    assert stream.closed


def test_file_absence_and_oversize_are_distinct(tmp_path):
    target = tmp_path / 'capture.zip'
    assert capture._optional(None, target.as_uri(), 8) is None
    target.write_bytes(b'oversized')
    with pytest.raises(ValueError, match='exceeds'):
        capture._optional(None, target.as_uri(), 8)


def test_provider_redirect_cannot_follow_location_or_enable_environment_proxy(monkeypatch):
    calls, options = [], []
    real_client = httpx.Client
    def response(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'https://unapproved.invalid/data'})
    def client(**kwargs):
        options.append(kwargs)
        return real_client(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setenv('HTTPS_PROXY', 'http://unapproved.invalid:8080')
    monkeypatch.setattr(transport.httpx, 'Client', client)
    monkeypatch.setattr(transport.time, 'sleep', lambda duration: None)
    with pytest.raises(ValueError, match='did not return'):
        transport.fetch('https://fixture.invalid/data', 'offline test@example.com',
                        max_bytes=8, requests_per_second=9, before_request=lambda: None)
    assert calls == ['https://fixture.invalid/data']
    assert options[0]['trust_env'] is False
    assert options[0]['follow_redirects'] is False
