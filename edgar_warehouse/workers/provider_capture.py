"""Configured HTTPS capture: frozen authority, one immutable snapshot, independent readback.

Version 1 qualifies JSON object acquisition. The ZIP_STORED snapshot contains
original payload bytes and bounded response metadata; retries reuse it without
GET. Control, source activation and continuation orchestration remain external.
"""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import io
import os
from pathlib import Path
from urllib.parse import unquote, urlparse
import zipfile

from edgar_warehouse.bookkeeping.clean.artifacts import json_value
from edgar_warehouse.control_contract import canonical, reference
from edgar_warehouse.rules.acquisition_authority import frozen_authority
from edgar_warehouse.rules import source_engine
from . import control, provider_transport as transport

CHECK = 'capture.verified'
PRODUCER = 'provider.capture'
AUTHORIZATION = 'acquisition'
OUTCOME = 'acquisition.outcome'
HEADER_BYTES = 1024**2
SNAPSHOT_OVERHEAD = HEADER_BYTES + 65536


def runtime_files():
    from edgar_warehouse import control_contract
    import edgar_warehouse.bookkeeping.clean.artifacts as artifacts
    from edgar_warehouse.rules import acquisition_authority
    from edgar_warehouse.change_journal import store
    return [Path(transport.__file__), Path(control_contract.__file__), Path(artifacts.__file__),
            Path(acquisition_authority.__file__), Path(store.__file__),
            *source_engine.runtime_files()]


def _journal():
    from edgar_warehouse.change_journal.store import ChangeJournal, get_engine
    return ChangeJournal(get_engine())


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError('Capture timestamp must be an explicit UTC instant')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError('Capture timestamp must be an explicit UTC instant')
    return value


def _load(envelope, artifacts):
    if envelope['profile'] != PRODUCER or set(envelope['checks']) != {CHECK}:
        raise ValueError('Capture requires its own profile and verification check')
    request = json_value(artifacts.verified(envelope['input'], max_bytes=HEADER_BYTES))
    required = {'version', 'feed', 'url', 'scope', 'requested_at', 'requests_per_second', 'document'}
    if (not isinstance(request, dict) or not required <= set(request)
            or set(request) - required - {'previous'} or type(request['version']) is not int
            or request['version'] != 1 or request['document'] not in ('main', 'page')):
        raise ValueError('Unsupported configured capture request')
    export = artifacts.json(envelope['rules'])
    authority = frozen_authority(export, request['feed'], artifacts=artifacts)
    configuration = authority['configuration']
    if envelope['keys'].get('feed') != request['feed']:
        raise ValueError('Capture feed differs from the frozen unit')
    scope = request['scope']
    if (not isinstance(scope, dict) or set(scope) != set(configuration['scope'])
            or any(not isinstance(v, str) or not v or len(v) > 256 for v in scope.values())
            or any(envelope['keys'].get(k) != v for k, v in scope.items())):
        raise ValueError('Capture scope differs from the approved frozen unit')
    _stamp(request['requested_at'])
    if type(request['requests_per_second']) is not int or not 1 <= request['requests_per_second'] <= 9:
        raise ValueError('Capture rate must be an exact integer from 1 to 9')
    completeness = configuration.get('page_completeness') if request['document'] == 'page' else configuration['completeness']
    if (completeness is None or completeness['format'] != 'json'
            or not 1 <= completeness['max_bytes'] <= transport.MAX_BYTES):
        raise ValueError('Capture v1 supports bounded JSON object completeness only')
    capability = configuration['capabilities']['fetch']
    url = transport.approved_url(request['url'], configuration['url_prefixes'], capability)
    resource = transport.provider_resource(url, capability)
    if resource not in {p['resource'] for p in envelope['claim']['proof']}:
        raise ValueError('Capture requires the shared provider lease')
    output = urlparse(envelope['output'])
    if (output.query or output.fragment or output.scheme not in ('file', 's3')
            or output.scheme == 'file' and output.netloc
            or output.scheme == 's3' and (not output.netloc or ':' in output.netloc or '@' in output.netloc)):
        raise ValueError('Capture output must be an explicit file or S3 object')
    if 'previous' in request:
        reference(request['previous'])
    return request, authority, completeness, url


def _complete(data, configuration):
    # Only checks cross into Rust; no Python JSON-domain parsing or body copying
    # into a Python row. Required member paths are literal, including dots.
    assertions = [{'test': {'test': {'path': '.', 'kind': 'object'}},
                   'reason': 'Capture payload must be a JSON object'}]
    assertions += [{'test': {'test': {'path': k, 'kind': 'present', 'path_mode': 'member'}},
                    'reason': f'Capture payload lacks required member {k}'} for k in configuration['required']]
    if not configuration['allow_empty']:
        assertions.append({'test': {'test': {'path': '.', 'kind': 'truthy'}}, 'reason': 'Capture payload is empty'})
    contract = {'read': {'format': 'json', 'limits': {'max_bytes': configuration['max_bytes'], 'max_records': 1},
                        'assertions': assertions,
                        'tables': {'capture': {'each': '.', 'columns': {'complete': {'const': {'value': True}}}}}}}
    result = source_engine.SourceEngine(contract).read(data)
    if result.deferred or len(result.tables['capture']) != 1:
        raise ValueError('Capture payload failed its configured completeness')


def _optional(artifacts, uri, limit):
    """Only definite absence allows GET. Permission/outage/corruption never does."""
    location = urlparse(uri)
    if location.scheme == 'file':
        try:
            with Path(unquote(location.path)).open('rb') as stream:
                data = stream.read(limit + 1)
        except FileNotFoundError:
            return None
    else:
        try:
            stream = artifacts.s3.get_object(Bucket=location.netloc, Key=location.path.lstrip('/'))['Body']
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') == 'NoSuchKey':
                return None
            raise
        try:
            data = stream.read(limit + 1)
        finally:
            stream.close()
    if len(data) > limit:
        raise ValueError('Capture snapshot exceeds its configured bound')
    return data


def _pack(metadata, data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, body in (('metadata.json', canonical(metadata).encode()), ('payload', data)):
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), body)
    return buffer.getvalue()


def _unpack(raw, limit):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = archive.infolist()
        if ([i.filename for i in files] != ['metadata.json', 'payload']
                or any(i.compress_type != zipfile.ZIP_STORED or i.flag_bits & 1 for i in files)
                or files[0].file_size > HEADER_BYTES or files[1].file_size > limit):
            raise ValueError('Unsupported or oversized capture snapshot')
        metadata, data = json_value(archive.read('metadata.json')), archive.read('payload')
    required = {'version', 'request', 'rules', 'effect_key', 'run_id', 'source', 'feed', 'url', 'scope',
                'status', 'etag', 'last_modified', 'bytes', 'payload_sha256', 'captured_at', 'previous'}
    if (not isinstance(metadata, dict) or set(metadata) != required or type(metadata['version']) is not int
            or metadata['version'] != 1 or type(metadata['status']) is not int or metadata['status'] not in (200, 304)
            or type(metadata['bytes']) is not int or not 0 <= metadata['bytes'] <= limit):
        raise ValueError('Malformed capture snapshot metadata')
    _stamp(metadata['captured_at'])
    transport.validator(metadata['etag']); transport.validator(metadata['last_modified'])
    reference(metadata['request']); reference(metadata['rules'])
    if metadata['status'] == 200:
        if metadata['previous'] is not None or len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != metadata['payload_sha256']:
            raise ValueError('Capture snapshot payload disagrees with metadata')
    else:
        reference(metadata['previous'])
        if data:
            raise ValueError('A conditional snapshot must reuse previous bytes')
    return metadata, data


def _event(envelope, request, authority, kind, evidence, *, at):
    from edgar_warehouse.change_journal.store import envelope as event
    return event(producer=AUTHORIZATION if kind == 'authorized' else OUTCOME, event_key=envelope['effect_key'],
                 run_id=envelope['claim']['run_id'], source=authority['name'], feed=request['feed'],
                 event_type=f'capture.{kind}', occurred_at=at, evidence=evidence,
                 scope={'request': envelope['input']['sha256'], 'rules': authority['digest']})


def _base_receipt(ref, artifacts, journal, *, source, feed, url, scope, limit):
    receipt = json_value(artifacts.verified(ref, max_bytes=HEADER_BYTES))
    if not isinstance(receipt, dict):
        raise ValueError('Malformed previous capture receipt')
    if set(receipt) != {'version', 'snapshot', 'metadata', 'journal'} or type(receipt['version']) is not int or receipt['version'] != 1:
        raise ValueError('Malformed previous capture receipt')
    raw = artifacts.verified(receipt['snapshot'], max_bytes=limit + SNAPSHOT_OVERHEAD)
    metadata, data = _unpack(raw, limit)
    if metadata != receipt['metadata'] or (metadata['source'], metadata['feed'], metadata['url'], metadata['scope']) != (source, feed, url, scope):
        raise ValueError('Previous capture receipt belongs to different request scope')
    durable = journal.verify(receipt['journal'])
    authorization = journal.get(AUTHORIZATION, metadata['effect_key'])
    if authorization is None:
        raise ValueError('Previous capture lacks acknowledged authorization')
    intent = journal.verify(authorization)['event']
    if (intent['event_type'] != 'capture.authorized' or intent['run_id'] != metadata['run_id']
            or intent['source'] != source or intent['feed'] != feed
            or intent['evidence'] != [metadata['request'], metadata['rules']]
            or durable['event']['scope'] != intent['scope']):
        raise ValueError('Previous capture authorization differs from its outcome')
    if (durable['event']['producer'] != OUTCOME or durable['event']['event_key'] != metadata['effect_key']
            or durable['event']['run_id'] != metadata['run_id'] or durable['event']['source'] != source
            or durable['event']['feed'] != feed or durable['event']['event_type'] != 'capture.captured'
            or durable['event']['occurred_at'] != metadata['captured_at']
            or durable['event']['evidence'] != [metadata['request'], receipt['snapshot']]):
        raise ValueError('Previous capture receipt lacks its committed Journal evidence')
    if metadata['status'] == 304:
        # Snapshots always point directly to a 200 capture, never an unbounded chain.
        base = artifacts.json(metadata['previous'])
        if base.get('metadata', {}).get('status') != 200:
            raise ValueError('Conditional predecessor must resolve to a direct 200 capture')
        base_meta, data, original = _base_receipt(metadata['previous'], artifacts, journal,
                                               source=source, feed=feed, url=url, scope=scope, limit=limit)
        if (len(data), hashlib.sha256(data).hexdigest()) != (metadata['bytes'], metadata['payload_sha256']):
            raise ValueError('Conditional predecessor payload disagrees')
        return metadata, data, original
    return metadata, data, ref


def _receipt(envelope, request, authority, completeness, url, raw, artifacts, journal, *, append):
    metadata, data = _unpack(raw, completeness['max_bytes'])
    expected = {'request': envelope['input'], 'rules': envelope['rules'], 'effect_key': envelope['effect_key'],
                'run_id': envelope['claim']['run_id'], 'source': authority['name'], 'feed': request['feed'], 'url': url, 'scope': request['scope']}
    if any(metadata[k] != value for k, value in expected.items()):
        raise ValueError('Capture snapshot differs from frozen work')
    authorized = _event(envelope, request, authority, 'authorized', [envelope['input'], envelope['rules']], at=request['requested_at'])
    intent = journal.get(authorized['producer'], authorized['event_key'])
    if intent is None:
        raise ValueError('Capture Journal authorization is not acknowledged')
    journal.verify(intent, expected=authorized)
    if metadata['status'] == 304:
        if 'previous' not in request:
            raise ValueError('Conditional capture lacks its declared predecessor')
        _, data, base = _base_receipt(request['previous'], artifacts, journal, source=authority['name'], feed=request['feed'],
                                     url=url, scope=request['scope'], limit=completeness['max_bytes'])
        if metadata['previous'] != base or (len(data), hashlib.sha256(data).hexdigest()) != (metadata['bytes'], metadata['payload_sha256']):
            raise ValueError('Conditional capture differs from verified previous bytes')
    _complete(data, completeness)
    snapshot = {'uri': envelope['output'] + '.capture.zip', 'sha256': hashlib.sha256(raw).hexdigest()}
    expected_event = _event(envelope, request, authority, 'captured', [envelope['input'], snapshot], at=metadata['captured_at'])
    if append:
        acknowledged = journal.append(expected_event)
    else:
        acknowledged = journal.get(expected_event['producer'], expected_event['event_key'])
        if acknowledged is None:
            raise ValueError('Capture Journal completion is not acknowledged')
        journal.verify(acknowledged, expected=expected_event)
    return {'version': 1, 'snapshot': snapshot, 'metadata': metadata, 'journal': acknowledged}


def execute(envelope, artifacts):
    envelope = control.renew(envelope)  # Checks immutable task binding and live issuer/fence.
    request, authority, completeness, url = _load(envelope, artifacts)
    journal = _journal()
    try:
        previous = None
        if 'previous' in request:
            previous = _base_receipt(request['previous'], artifacts, journal, source=authority['name'], feed=request['feed'],
                                     url=url, scope=request['scope'], limit=completeness['max_bytes'])
            _complete(previous[1], completeness)
        snapshot_uri = envelope['output'] + '.capture.zip'
        raw = _optional(artifacts, snapshot_uri, completeness['max_bytes'] + SNAPSHOT_OVERHEAD)
        if raw is None:
            if _optional(artifacts, envelope['output'], HEADER_BYTES) is not None:
                raise ValueError('Capture candidate exists without its durable snapshot')
            identity = os.environ.get('EDGAR_IDENTITY', '')
            if authority['configuration']['capabilities']['fetch'] == 'sec.conditional' and '@' not in identity:
                raise ValueError('SEC capture requires the configured identity with email')
            def permission():
                control.renew(envelope)
                journal.append(_event(envelope, request, authority, 'authorized', [envelope['input'], envelope['rules']], at=request['requested_at']))
                control.renew(envelope)  # Journal readback may outlive a lease; check again before GET.
            response = transport.fetch(url, identity, max_bytes=completeness['max_bytes'],
                                       requests_per_second=request['requests_per_second'], before_request=permission,
                                       etag=previous[0]['etag'] if previous else None,
                                       last_modified=previous[0]['last_modified'] if previous else None)
            data = previous[1] if response.status == 304 else response.content
            _complete(data, completeness)
            control.renew(envelope)
            metadata = {'version': 1, 'request': envelope['input'], 'rules': envelope['rules'],
                        'effect_key': envelope['effect_key'], 'run_id': envelope['claim']['run_id'], 'source': authority['name'],
                        'feed': request['feed'], 'url': url, 'scope': request['scope'], 'status': response.status,
                        'etag': response.etag, 'last_modified': response.last_modified, 'bytes': len(data),
                        'payload_sha256': hashlib.sha256(data).hexdigest(), 'captured_at': datetime.now(UTC).isoformat(),
                        'previous': previous[2] if response.status == 304 else None}
            raw = _pack(metadata, b'' if response.status == 304 else data)
            artifacts.put_bytes(snapshot_uri, raw)
        value = _receipt(envelope, request, authority, completeness, url, raw, artifacts, journal, append=True)
        control.renew(envelope)
        return artifacts.put_bytes(envelope['output'], canonical(value).encode())
    finally:
        journal.engine.dispose()


def verify(envelope, artifacts):
    request, authority, completeness, url = _load(envelope, artifacts)
    if envelope['candidate']['uri'] != envelope['output']:
        raise ValueError('Capture candidate differs from intended output')
    raw = artifacts.read(envelope['output'] + '.capture.zip', max_bytes=completeness['max_bytes'] + SNAPSHOT_OVERHEAD)
    journal = _journal()
    try:
        expected = _receipt(envelope, request, authority, completeness, url, raw, artifacts, journal, append=False)
        if artifacts.verified(envelope['candidate'], max_bytes=HEADER_BYTES) != canonical(expected).encode():
            raise ValueError('Capture candidate differs from durable evidence')
        return {CHECK: True}, []
    finally:
        journal.engine.dispose()
