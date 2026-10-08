"""Exact mapped-value parity on receipt-pinned SEC main captures.

Company rows are derived by its configured main reader; continuation/catalog,
census, provenance and full population preparation are outside this proof.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import adapters,classification,quality
from edgar_warehouse.rules import files,source_engine
from edgar_warehouse.workers import source_mapping


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify(capture,limit):
    if not 1<=limit<=10000:raise ValueError('limit must be 1..10000')
    receipt=capture/'receipts.jsonl'
    refs=[json.loads(line) for line in receipt.read_bytes().splitlines() if line.strip()]
    refs=[ref for ref in refs if '/submissions/' in ref['key'] and '/main/' in ref['key']]
    refs.sort(key=lambda ref:hashlib.sha256(ref['key'].encode()).hexdigest());refs=refs[:limit]
    if len(refs)!=limit or len({ref['key'] for ref in refs})!=limit:raise ValueError('distinct capture count')
    sources=('sec.submissions.company','sec.submissions.person')
    contracts={source:next(iter(files.source(source)['mdm'].values()))['contract'] for source in sources}
    retained=copy.deepcopy(contracts)
    for body in retained.values():body['adapter'].pop('reading')
    policy=files.policy()
    company_reader=source_engine.SourceEngine(files.source(sources[0]))
    paths=[Path(__file__),receipt,Path(adapters.__file__),Path(classification.__file__),Path(quality.__file__),
           Path(source_mapping.__file__),Path(files.__file__),*source_engine.runtime_files(),
           *files.ROOT.rglob('*.yaml')]
    before={str(path.resolve()):sha(path) for path in paths}
    hashes={source:hashlib.sha256() for source in sources};counts={source:{} for source in sources}
    evidence=[];started=time.monotonic()
    for ref in refs:
        path=(capture/'bronze'/ref['key'].removeprefix('warehouse/bronze/')).resolve()
        if not path.is_relative_to((capture/'bronze').resolve()):raise ValueError('capture path escape')
        data=path.read_bytes()
        if len(data)!=ref['bytes'] or hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('capture receipt mismatch')
        raw=json.loads(data)
        reading=company_reader.read(data,context={'cik':int(raw['cik']),'sync_run_id':'field-qualification',
            'raw_object_id':ref['sha256'],'load_mode':'default','recent_limit':0,
            'last_synced_at':'2026-01-01T00:00:00+00:00'})
        if reading.deferred or len(reading.tables['company'])!=1:raise ValueError('main reader shape')
        company=reading.tables['company'][0]
        addresses=reading.tables['addresses']
        if len(addresses)>1:raise ValueError('ambiguous business address')
        company['business_address']=addresses[0]['business_address'] if addresses else None
        for source,row in [(sources[0],company),(sources[1],raw)]:
            def fields(body):
                try:return {'mapped':adapters.mapped_values(row,body)}
                except adapters.UnsupportedRecord as error:return {'reason':error.reason,'detail':error.detail,'kind':error.probable_kind}
            if digest(fields(contracts[source]))!=digest(fields(retained[source])):raise ValueError('mapped/quality mismatch')
            publication={'publication_key':'field-qualification','revision':1,'artifact_sha256':ref['sha256'],'member':ref['key']}
            code=next(iter(files.source(source)['mdm']))
            def normalized(body):
                try:return {'assertion':adapters.normalize(row,source_code=code,contract=body,publication=publication,policy=policy)}
                except adapters.UnsupportedRecord as error:return {'reason':error.reason,'detail':error.detail,'kind':error.probable_kind}
            actual=normalized(contracts[source]);old=normalized(retained[source])
            if digest(actual)!=digest(old):raise ValueError('assertion/deferral mismatch')
            outcome='assertion' if 'assertion' in actual else actual['reason']
            counts[source][outcome]=counts[source].get(outcome,0)+1
            hashes[source].update((digest(actual)+'\n').encode())
        evidence.append({'key':ref['key'],'sha256':ref['sha256']})
    if before!={str(path.resolve()):sha(path) for path in paths}:raise ValueError('qualification inputs changed')
    return {'captures':limit,'source_comparisons':2*limit,'seconds':time.monotonic()-started,
            'outcomes':counts,'digests':{key:value.hexdigest() for key,value in hashes.items()},
            'runtime_pins':before,'capture_refs':evidence,'company_full_preparation':False,
            'installed_population_qualified':False,'full_goal_complete':False,
            'scope':'receipt-pinned raw Person and configured main-derived Company mapped values, quality, exact assertions and deferrals; no continuation/catalog/census/provenance or full mastering claim'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--limit',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=qualify(args.capture,args.limit)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('captures','source_comparisons','seconds','outcomes')}))
if __name__=='__main__':main()
