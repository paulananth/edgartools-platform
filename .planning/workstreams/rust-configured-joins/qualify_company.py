"""Bounded offline Company join qualification; no SEC calls or activation.

Read cached main documents in two-artifact units and the whole cm27 census,
then compare pre-port and native source.combine execute/verify exact receipts.
Separately measure pure combination and full execute+verify on identical inputs.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import statistics
import time
import tempfile

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import canonical, digest
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import combine_tables
from edgar_warehouse.workers import source_combine, source_read
from tests.engine.test_source_combine import envelope
from tests.engine.test_company_combination_contract import read

spec = importlib.util.spec_from_file_location('join_parity', Path(__file__).with_name('parity.py'))
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)


def bind(value, pins):
    if isinstance(value, str): return pins.get(value, value)
    if isinstance(value, dict): return {k: bind(v, pins) for k, v in value.items()}
    if isinstance(value, list): return [bind(v, pins) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--census', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=40)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.limit <= 500 or args.limit % 2:
        parser.error('--limit is an even bounded count 2..500')
    old = parity.baseline()
    census_bytes = args.census.read_bytes()
    census = json.loads(census_bytes)
    census_hash = digest(census)
    receipts_bytes = (args.capture / 'receipts.jsonl').read_bytes()
    receipts = [json.loads(line) for line in receipts_bytes.splitlines()]
    main_refs = [r for r in receipts if '/submissions/' in r['key'] and '/main/' in r['key']]
    main_refs.sort(key=lambda r: hashlib.sha256(r['key'].encode()).hexdigest())
    selected = main_refs[:args.limit]
    assert len(selected) == args.limit
    catalogs = [r for r in receipts if '/company_tickers_exchange/' in r['key']]
    assert len(catalogs) == 1
    def raw(ref):
        path = (args.capture / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
        assert path.is_relative_to(args.capture.resolve() / 'bronze')
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref['sha256']
        return json.loads(data)
    ticks = raw(catalogs[0])
    pins = {'APPROVED_COMPANY_CAPTURE_RUN': 'qualification', 'APPROVED_CATALOG_CAPTURE_RUN': 'catalog', '0'*64: census_hash}
    blueprint = bind(files.load(files.ROOT / 'sources/sec.submissions.company/combine-census.yaml'), pins)
    blueprint['combine']['groups']['forms']['source'] = ['main']
    blueprint['combine']['groups']['tickers']['source'] = ['catalog_exchange']
    start = time.monotonic()
    evidence = []
    with tempfile.TemporaryDirectory(prefix='company-native-join-') as folder:
        root = Path(folder)
        store = Artifacts()
        census_rules = bind(files.load(files.ROOT / 'sources/sec.submissions.company/census.yaml'), pins)
        census_raw = store.put_bytes((root / 'census.input.json').as_uri(), canonical(census).encode())
        census_rule = store.put(root.as_uri(), census_rules)
        census_manifest = store.put(root.as_uri(), {'version':1,'contract':census_rule,'artifacts':[census_raw]})
        census_work = {'input':census_manifest,'output':(root / 'census.json').as_uri(),'checks':['source.output']}
        census_ref = source_read.execute(census_work, store)
        assert source_read.verify({**census_work,'candidate':census_ref}, store) == ({'source.output':True},[])
        census_reading = store.json(census_ref)
        tick_ref, _ = read(store, root, 'catalog', files.load(files.ROOT / 'sources/sec.submissions.company/catalog.yaml'), ticks,
                           {'sync_run_id':'catalog', 'last_synced_at':'2026-10-04T00:00:00Z','source_name':'catalog_exchange'})
        tick_reading = store.json(tick_ref)
        pure = {'python':[], 'native':[]}; full = {'python':[], 'native':[]}
        for n in range(0, args.limit, 2):
            payloads = [raw(r) for r in selected[n:n+2]]
            # Bind per-document context independently; source.read max_artifacts is two.
            contract = files.load(files.ROOT / 'sources/sec.submissions.company/census-main.yaml')
            entries = []
            for payload, ref in zip(payloads, selected[n:n+2]):
                path = (args.capture / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
                source = {'uri':path.as_uri(),'sha256':ref['sha256']}
                values = {'cik': int(payload['cik']), 'sync_run_id':'qualification','raw_object_id':ref['sha256'],
                          'load_mode':'default','recent_limit':None,'last_synced_at':'2026-10-04T00:00:00Z'}
                context = store.put(root.as_uri(), {'version':1,'input':source,'values':values})
                entries.append({'input':source,'context':context})
            rule_ref = store.put(root.as_uri(), contract)
            request = store.put(root.as_uri(), {'version':2,'contract':rule_ref,'artifacts':entries})
            work_read = {'input':request,'output':(root / f'main-{n}.json').as_uri(),'checks':['source.output']}
            main_ref = source_read.execute(work_read, store)
            assert source_read.verify({**work_read,'candidate':main_ref}, store) == ({'source.output':True},[])
            inputs = {'main':store.json(main_ref),'census':census_reading,'catalog_exchange':tick_reading}
            work = envelope(store, root, blueprint, {'main':main_ref,'census':census_ref,'catalog_exchange':tick_ref})
            work['output'] = (root / f'combined-{n}.json').as_uri()
            # Alternate execution order to reduce systematic warm-cache bias.
            exact = {}; businesses = {}
            for name in (['python','native'] if n % 4 == 0 else ['native','python']):
                engine = old if name == 'python' else source_combine
                t = time.perf_counter()
                tables = parity.expected(old, blueprint['combine'], inputs) if name == 'python' else combine_tables(blueprint['combine'], inputs, canonical)
                pure[name].append(time.perf_counter()-t)
                businesses[name] = digest(tables)
                t = time.perf_counter()
                result = engine.execute(work, store)
                assert engine.verify({**work,'candidate':result}, store) == ({'source.combined':True},[])
                assert engine.execute(work, store) == result  # lost-ack replay
                full[name].append(time.perf_counter()-t)
                exact[name] = result
            assert exact['python'] == exact['native']
            assert businesses['python'] == businesses['native']
            evidence.append({'inputs':[r['sha256'] for r in selected[n:n+2]], 'tables_sha256':businesses['native'],
                             'output_sha256':exact['native']['sha256']})
        result = {'baseline':parity.BASELINE, 'company_documents': args.limit, 'units':args.limit//2,
            'whole_census_names':len(census['entries']), 'census_input_sha256':hashlib.sha256(census_bytes).hexdigest(),
            'canonical_census_sha256':census_hash,'receipts_sha256':hashlib.sha256(receipts_bytes).hexdigest(),
            'census_reading_bytes':len(store.verified(census_ref)), 'exact_receipt_and_table_parity':True,
            'execute_verify_lost_ack_retry':True,'full_pipeline_or_activation':False,
            'pure_seconds':pure,'execute_verify_retry_seconds':full,
            'medians':{'pure':{k:statistics.median(v) for k,v in pure.items()},
                       'execute_verify_retry':{k:statistics.median(v) for k,v in full.items()}},
            'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'elapsed_seconds':time.monotonic()-start,'evidence':evidence}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['evidence','pure_seconds','execute_verify_retry_seconds']}))

if __name__ == '__main__': main()
