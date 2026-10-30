"""Ticket 149: the acquisition proof of the registration feed, over the first few units of
the capture's manifest. Each document is asked once through the capture's own transport
(`provider_transport.fetch`, `sec.conditional`, the feed's `text` completeness), kept whole
beside its receipt, then read back and hashed. The live acquisition cannot prove itself:
`provider.capture` runs only on a version whose proof already holds an acquisition run.
Prints counts and sizes only.

    EDGAR_IDENTITY=... uv run --no-sync python .scratch/onboarding/sec.registration/proof.py \
        <manifest> <proof folder> [--count N]
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import provider_transport as transport
from edgar_warehouse.workers.provider_capture import _complete

FEED = 'registration'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('proof', type=Path)
    parser.add_argument('--count', type=int, default=5)
    args = parser.parse_args()
    feed = files.source('sec.registration', files.ROOT)['acquisition']['feeds'][FEED]
    identity = os.environ['EDGAR_IDENTITY']
    store, root = Artifacts(), args.proof.resolve()
    units = json.loads(args.manifest.read_bytes())['units'][:args.count]
    receipts, sizes = [], []
    for unit in units:
        request = store.json(unit['input'])
        url = transport.approved_url(request['url'], feed['url_prefixes'], feed['capabilities']['fetch'])
        kept = root / unquote(urlparse(unit['output']).path).split('/bronze/', 1)[1]
        document = kept.with_name(Path(urlparse(url).path).name)
        if document.exists():  # asked on an earlier attempt: never asked again
            status, content = 200, document.read_bytes()
        else:
            answer = transport.fetch(url, identity, max_bytes=feed['completeness']['max_bytes'],
                                     requests_per_second=request['requests_per_second'], before_request=lambda: None)
            status, content = answer.status, answer.content
            document.parent.mkdir(parents=True, exist_ok=True)
            document.write_bytes(content)
        _complete(content, feed['completeness'])
        receipts.append({'scope': request['scope'], 'url': url, 'status': status,
                         'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
                         'document': document.as_uri(),
                         'at': datetime.now(timezone.utc).replace(microsecond=0).isoformat()})
        sizes.append(len(content))
    verified = sum(1 for r in receipts
                   if hashlib.sha256(Path(unquote(urlparse(r['document']).path)).read_bytes()).hexdigest() == r['sha256'])
    manifest = store.put((root / 'receipts').as_uri(), {'version': 1, 'feed': FEED, 'receipts': receipts})
    proof = {FEED: {'manifest': manifest, 'counts': {'capture': {'expected': len(units), 'verified': verified}},
                    'checks': {'capture': verified == len(units)}}}
    (root / 'acquisition-proof.json').write_text(json.dumps(proof, indent=2))
    print(json.dumps({'asked': len(units), 'kept': len(receipts), 'verified': verified,
                      'bytes': sizes, 'manifest_sha256': manifest['sha256']}))


if __name__ == '__main__':
    main()
