"""Compare complete configured XML projection with an independent lxml decoder.

Qualification only: never imports a retired platform parser or writes master data.
Header expectations and total count come from pinned GLEIF publisher metadata.
The independent decoder is a test oracle, not an application reading path.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from lxml import etree

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from scripts.qualification.qualify_json_archive_parity import canonical, equal, implementation_evidence


def independent_records(stream, envelope):
    """Decode record subtrees independently with bounded tree retention."""
    namespace = envelope['namespace']
    tag = '{' + namespace + '}' + envelope['record']
    container = '{' + namespace + '}' + envelope['container']
    def value(node):
        result = {'@' + key: text for key, text in node.attrib.items()}
        for child in node:
            if not isinstance(child.tag, str):
                raise ValueError('Unsupported XML entity or processing instruction')
            key = child.tag.removeprefix('{' + namespace + '}')
            item = value(child)
            if key in result:
                if not isinstance(result[key], list): result[key] = [result[key]]
                result[key].append(item)
            else: result[key] = item
        if node.text and node.text.strip(): result['$'] = node.text.strip()
        return result
    for _, node in etree.iterparse(stream, events=('end',), resolve_entities=False,
                                  load_dtd=False, no_network=True, huge_tree=False,
                                  remove_comments=True):
        if node.tag == tag and node.getparent() is not None and node.getparent().tag == container:
            record = value(node)
            if envelope['record_wrapper']:
                record = {envelope['record_wrapper']: record}
            yield record
            node.clear()
            while node.getprevious() is not None: del node.getparent()[0]


def qualify(path, sha256, member, metadata, *, content_date):
    started = time.monotonic()
    template = files.ROOT / 'sources' / 'gleif' / f'{member}-xml.yaml'
    template_hash = hashlib.sha256(template.read_bytes()).hexdigest()
    implementation = implementation_evidence() + [{'path':str(Path(__file__).resolve()),
        'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}]
    rules = copy.deepcopy(files.load(template))
    read = rules['read']
    stream_rules = read.pop('stream')
    expected = metadata['data']['full_file']['xml']
    expected_type = {'level1': 'lei2', 'relationships': 'rr', 'reporting-exceptions': 'repex'}[member]
    if expected['type'] != expected_type or expected['format'] != 'xml' or expected['delta_type'] != 'GoldenCopy':
        raise ValueError('Requires matching full XML publication metadata')
    if expected['cdf_version'] != {'lei2':'LEI_3.1', 'rr':'RR_2.1', 'repex':'REPEX_2.1'}[expected_type]:
        raise ValueError('Unexpected CDF version')
    count = expected['record_count']
    if type(count) is not int or not 0 <= count <= 10_000_000:
        raise ValueError('Invalid pinned count')
    header = stream_rules['header_read']
    header['references'] = {'content_dates': {content_date: {'valid':True}},
        'record_counts': {str(count): {'valid':True}},
        'file_content': {'GLEIF_FULL_PUBLISHED': {'valid':True, 'requires_delta':False}},
        'delta_starts': {}}
    # Emit every raw normalized record for full decoder parity, without collecting
    # any population in memory. Approved-scope projection is qualified separately.
    table = member.replace('-', '_')
    read['tables'][table].pop('select')
    engine, header_engine = SourceEngine(rules), SourceEngine({'read': header})
    ref = {'uri': Path(path).resolve().as_uri(), 'sha256': sha256}
    native_hash, independent_hash = hashlib.sha256(), hashlib.sha256()
    observed = 0
    with Artifacts().verified_stream(ref, max_bytes=1024**3) as snapshot, tempfile.TemporaryFile() as other:
        snapshot.seek(0, 2)
        if snapshot.tell() != expected['size']: raise ValueError('Publisher archive size disagreement')
        snapshot.seek(0)
        shutil.copyfileobj(snapshot, other, length=1024**2)
        snapshot.seek(0); other.seek(0)
        with zipfile.ZipFile(snapshot) as native_zip, zipfile.ZipFile(other) as oracle_zip:
            infos = native_zip.infolist()
            if len(infos) != 1 or infos[0].is_dir() or infos[0].flag_bits & 1 or infos[0].file_size > 16*1024**3:
                raise ValueError('Requires one bounded unencrypted member')
            with native_zip.open(infos[0]) as native, oracle_zip.open(oracle_zip.infolist()[0]) as independent:
                records = iter(independent_records(independent, stream_rules['xml']))
                def consume(reading, index):
                    nonlocal observed
                    row = reading.tables[table][0]
                    old = next(records)
                    # Configured value maps sort keys; canonical source hashing
                    # also sorts keys. List/source order and scalar types stay exact.
                    if reading.deferred or row['source_index'] != index + 1 or not equal(row['record'], old, key_order=False):
                        raise ValueError(f'Typed/projection disagreement at record {index}')
                    native_hash.update(canonical(row['record']) + b'\n')
                    independent_hash.update(canonical(old) + b'\n')
                    observed += 1
                    if observed % 100000 == 0:
                        print(json.dumps({'member':member, 'records':observed,
                            'seconds':round(time.monotonic()-started,2)}), flush=True)
                receipt = engine.stream_xml_records(native, envelope=stream_rules['xml'],
                    header_engine=header_engine, on_reading=consume,
                    max_bytes=16*1024**3, max_record=1024**2, max_records=10_000_000, max_depth=64,
                    context={'publication_count':count}, ordinal_context='source_index')
                sentinel = object()
                if next(records, sentinel) is not sentinel: raise ValueError('Independent additional records')
                if observed != count or receipt['record_count'] != count or receipt['expanded_bytes'] != infos[0].file_size:
                    raise ValueError('Publication count or expanded byte disagreement')
                if native_hash.digest() != independent_hash.digest(): raise ValueError('Canonical hash disagreement')
    final_implementation = implementation_evidence() + [{'path':str(Path(__file__).resolve()),
        'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}]
    if final_implementation != implementation or hashlib.sha256(template.read_bytes()).hexdigest() != template_hash:
        raise ValueError('Qualification implementation or template changed during scan')
    return {'archive':ref, 'member':member, 'publisher':expected, 'content_date':content_date,
        'content_date_evidence':'explicit pinned capture header; API publication slot is a separate timestamp',
        'publish_date':metadata['data']['publish_date'],
        'metadata_sha256':hashlib.sha256(canonical(metadata)).hexdigest(),
        'template_sha256':template_hash,
        'executed_rules_sha256':hashlib.sha256(canonical({'record':rules, 'header':header})).hexdigest(),
        'implementation':implementation,
        'receipt':receipt, 'canonical_source_hash':native_hash.hexdigest(), 'typed_value_differences':0,
        'map_key_order':'configured value maps use sorted keys; XML source key order is not asserted',
        'seconds':time.monotonic()-started,
        'scope':'complete authenticated XML configured header/all-record projection and independent decoder; not installed mastering qualification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--member', choices=['level1','relationships','reporting-exceptions'], required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--content-date', required=True, help='Pinned normalized UTC XML ContentDate; not API publish_date')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.archive, args.sha256, args.member, json.loads(args.metadata.read_text()), content_date=args.content_date)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
