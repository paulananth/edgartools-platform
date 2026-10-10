"""Offline captured-prefix projection parity/timing; never whole-source qualification."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import statistics
import time
from urllib.parse import unquote, urlparse
import zipfile

from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.mdm.clean import name_census, names, primitives
from edgar_warehouse.workers import source_combine, source_mapping, source_read, source_readings, source_stream
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
import tempfile
from scripts.qualification import qualify_census_reading as captured
from scripts.qualification.qualify_census_reading import sha, SampleComplete
from tests.engine.test_census_names_stream import expected
from tests.support import retired_name_census as oracle
# The per-record census recipes the retired builder read; the configured
# complete stream is generated from them (`build_frequency_rules.py`).
IDENTITY = files.load(files.ROOT / 'sources/gleif/census-identity.yaml')
UPDATE = files.load(files.ROOT / 'sources/gleif/census-update.yaml')
RECORD = files.load(files.ROOT / 'sources/gleif/census-record.yaml')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gleif-report', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error('--limit must be 1..10000')
    started = time.perf_counter()
    report = json.loads(args.gleif_report.read_bytes())
    ref = report['archive']
    uri = urlparse(ref['uri'])
    if uri.scheme != 'file' or uri.netloc:
        raise ValueError('requires a local captured archive')
    archive = Path(unquote(uri.path))
    recipe = files.ROOT / 'sources/gleif/census-names-stream.yaml'
    pins = [Path(__file__), Path(captured.__file__), args.gleif_report, archive, recipe, Path(oracle.__file__),
            Path(__import__(expected.__module__, fromlist=['']).__file__),
            Path(files.__file__), Path(name_census.__file__), Path(names.__file__),
            Path(primitives.__file__), Path(source_mapping.__file__),
            Path(source_read.__file__), *source_read.runtime_files(),
            Path(source_combine.__file__), *source_combine.runtime_files(),
            *sorted((files.ROOT / "sources/gleif").glob("census-*.yaml")),
            *source_engine.runtime_files()]
    before = {str(p.resolve()): sha(p) for p in pins}
    if before[str(archive.resolve())] != ref['sha256']:
        raise ValueError('captured archive hash differs')
    rows = []
    def consume(row, ordinal):
        if ordinal != len(rows):
            raise ValueError('ordinal differs')
        rows.append(row)
        if len(rows) == args.limit:
            raise SampleComplete()
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) != 1 or members[0].is_dir() or members[0].flag_bits & 1:
            raise ValueError('archive shape differs')
        with zipped.open(members[0]) as stream:
            try:
                source_engine.stream_json_array(stream, wrapper='records', on_record=consume,
                    max_bytes=16*1024**3, max_record=1024**2, max_records=10000000)
            except source_engine.SourceRejected as error:
                if error.code != 'stream_consumer' or len(rows) != args.limit:
                    raise
    if len(rows) != args.limit:
        raise ValueError('captured prefix too short')
    wanted = {oracle.legal_form_key(oracle._text((row.get('Entity') or {}).get('LegalName')))
              for row in rows} - {''}
    # This synthetic wanted population exercises captured legal names. It is
    # explicitly not a claim about the SEC population or installed bindings.
    raw = json.dumps({'records': rows}).encode()
    source_engine.STEPS = {}
    engine = source_stream.stream_policy(files.load(recipe))[1]
    setup_seconds = time.perf_counter() - started
    native_seconds, oracle_seconds, configured_seconds = [], [], []
    for trial in range(5):
        projected = []
        t = time.perf_counter()
        receipt = engine.stream_json_array(io.BytesIO(raw), wrapper='records',
            lookups={'wanted': wanted}, context={'publication_count':args.limit}, max_bytes=len(raw), max_record=1024**2,
            max_records=args.limit,
            on_reading=lambda reading, ordinal: projected.append(reading.tables))
        native_seconds.append(time.perf_counter()-t)
        t = time.perf_counter()
        historical = [expected(row, wanted) for row in rows]
        oracle_seconds.append(time.perf_counter()-t)
        if receipt['record_count'] != args.limit or projected != historical:
            raise ValueError('projection differs from independent extraction oracle')
        baseline = []
        def configured(row, ordinal):
            tables = {'a_legal': [], 'b_other': [], 'c_transliterated': []}
            get = lambda recipe, column: source_mapping.project_record(row, recipe, column=column)['value']
            if get(IDENTITY, 'category') != 'BRANCH':
                lei = get(IDENTITY, 'lei')
                if lei:
                    key = get(IDENTITY, 'key')
                    if key in wanted:
                        tables['a_legal'].append({'key':key, 'lei':lei,
                            'updated':get(UPDATE, 'updated')})
                    reading = source_mapping.read_record(row, RECORD)
                    for old, new in [('other','b_other'), ('transliterated','c_transliterated')]:
                        tables[new] = [{'key':r['key'], 'lei':lei} for r in reading.tables[old] if r['key'] in wanted]
            baseline.append(tables)
        t = time.perf_counter()
        old_receipt = source_engine.stream_json_array(io.BytesIO(raw), wrapper='records',
            on_record=configured, max_bytes=len(raw), max_record=1024**2, max_records=args.limit)
        configured_seconds.append(time.perf_counter()-t)
        if old_receipt['record_count'] != args.limit or baseline != historical:
            raise ValueError('current configured callback baseline differs')
    worker_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='census-worker-', dir='/private/tmp') as work:
        root = Path(work)
        store = Artifacts()
        zipped_sample = io.BytesIO()
        with zipfile.ZipFile(zipped_sample, 'w', zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr('captured-prefix.json', raw)
        source_ref = store.put_bytes((root/'sample.zip').as_uri(), zipped_sample.getvalue())
        rule_ref = store.put_bytes((root/'rules.yaml').as_uri(), recipe.read_bytes())
        context_ref = store.put(root.as_uri(), {'version':1, 'input':source_ref,
                                               'values':{'publication_count':args.limit}})
        lookups_ref = store.put(root.as_uri(), {'version':1, 'input':source_ref,
                                               'sets':{'wanted':sorted(wanted)}})
        manifest = store.put(root.as_uri(), {'version':3, 'contract':rule_ref,
            'artifacts':[{'input':source_ref,'context':context_ref,'lookups':lookups_ref}]})
        envelope = {'input':manifest,'output':(root/'reading.json').as_uri(),'checks':['source.output']}
        candidate = source_read.execute(envelope, store)
        if source_read.verify({**envelope,'candidate':candidate}, store) != ({'source.output':True}, []):
            raise ValueError('actual worker verification differs')
        if source_read.execute(envelope, store) != candidate:
            raise ValueError('actual worker retry differs')
        artifact = store.json(candidate)['artifacts'][0]
        actual_tables = {name:[] for name in historical[0]}
        for index, artifact_index, chunk, size in source_readings.iter_load(
                candidate, store, max_bytes=32*1024**2, max_rows=100000,
                allow_lookup_receipts=True):
            if (index['reading'] != candidate or index['contract'] != rule_ref
                    or artifact_index != 0 or chunk['input'] != source_ref or chunk['lookups'] != lookups_ref):
                raise ValueError('incremental consumer source identity differs')
            for name, values in chunk['tables'].items():
                actual_tables[name].extend(values)
        expected_tables = {name:[r for tables in historical for r in tables[name]] for name in historical[0]}
        if actual_tables != expected_tables or artifact['record_count'] != args.limit or artifact['lookups'] != lookups_ref:
            raise ValueError('actual worker output/evidence differs')
        reduction_started = time.perf_counter()
        reduction_recipe = files.load(files.ROOT / 'sources/gleif/census-name-reduction.yaml')
        reduction_contract = store.put(root.as_uri(), reduction_recipe)
        reduction_manifest = store.put(root.as_uri(), {'version':1, 'contract':reduction_contract,
                                                       'readings':{'names':candidate}})
        reduction_work = {'input':reduction_manifest, 'output':(root/'reduced.json').as_uri(),
                          'checks':['source.combined'], 'keys':{}}
        reduced = source_combine.execute(reduction_work, store)
        if (source_combine.verify({**reduction_work, 'candidate':reduced}, store) != ({'source.combined':True}, [])
                or source_combine.execute(reduction_work, store) != reduced):
            raise ValueError('reduction verification or retry differs')
        # Independent straightforward whole-list oracle, intentionally not
        # reusing generic reduction state or its exclusion/sample functions.
        legal, other = {}, {}
        for row in expected_tables['a_legal']:
            legal.setdefault(row['key'], {})[row['lei']] = row['updated'] or ''
        for table_name in ('b_other', 'c_transliterated'):
            for row in expected_tables[table_name]:
                other.setdefault(row['key'], set()).add(row['lei'])
        expected_reduced = {'legal':[], 'other':[]}
        for key, holders in sorted(legal.items()):
            expected_reduced['legal'].append({'key':key, 'count':len(holders), 'holders':[
                {'lei':lei, 'updated':holders[lei]} for lei in sorted(holders)[:5]]})
        for key, holders in sorted(other.items()):
            surviving = holders - set(legal.get(key, {}))
            expected_reduced['other'].append({'key':key, 'count':len(surviving),
                'holders':[{'lei':lei} for lei in sorted(surviving)[:5]]})
        reduced_body = store.json(reduced)
        if (reduced_body['artifacts'][0]['tables'] != expected_reduced
                or reduced_body['readings'] != {'names':candidate}
                or store.json(reduced_body['artifacts'][0]['input'])['readings'] != {'names':candidate}):
            raise ValueError('configured reduction differs from independent complete-set oracle or original identity')
        reduction_proof = {'output_sha256':reduced['sha256'], 'contract_sha256':reduction_contract['sha256'],
                           'reading_sha256':candidate['sha256'], 'oracle_parity':True,
                           'execute_verify_retry_seconds':time.perf_counter()-reduction_started,
                           'table_rows':{name:len(rows) for name,rows in expected_reduced.items()},
                           'separate_process_qualified':False, 'original_source_eof_qualified':False}
        worker_proof = {'input_sha256':source_ref['sha256'], 'context_sha256':context_ref['sha256'],
                        'lookups_sha256':lookups_ref['sha256'], 'manifest_sha256':manifest['sha256'],
                        'output_sha256':candidate['sha256'], 'record_count':artifact['record_count'],
                        'table_rows':{name:len(values) for name,values in actual_tables.items()},
                        'retry_unchanged':True, 'replay_verification_passed':True,
                        'incremental_consumer_parity_passed':True,
                        'separate_process_qualified':False}
    worker_seconds = time.perf_counter()-worker_started
    if before != {str(p.resolve()): sha(p) for p in pins}:
        raise ValueError('inputs/runtime changed during qualification')
    output = {'runtime_pins': before, 'records': args.limit, 'worker_execute_verify_retry_seconds':worker_seconds,
              'worker_proof':worker_proof, 'reduction_proof':reduction_proof,
              'synthetic_wanted_keys': len(wanted), 'setup_seconds': setup_seconds,
              'native_projection_seconds': native_seconds,
              'oracle_extraction_seconds': oracle_seconds,
              'current_configured_callback_seconds': configured_seconds,
              'current_configured_callback_median_seconds': statistics.median(configured_seconds),
              'native_median_seconds': statistics.median(native_seconds),
              'oracle_median_seconds': statistics.median(oracle_seconds),
              'scope': 'exact captured-prefix rows; valid EOF only on repackaged sample; timings compare native framing/projection against already decoded oracle extraction',
              'whole_source_census_qualified': False, 'cascade_qualified': False,
              'installed_population_qualified': False, 'full_goal_complete': False}
    args.output.write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k != 'runtime_pins'}))


if __name__ == '__main__':
    main()
