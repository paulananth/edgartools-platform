"""Compare bounded cached GLEIF fields with the retained semantic oracle.

This verifies archive bytes and sampled mapping parity, not current reader EOF,
publication, installed mastering, or full-corpus semantic parity.
"""
from __future__ import annotations
import copy
import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.workers import source_mapping

class SampleComplete(Exception):
    pass

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024**2): h.update(chunk)
    return h.hexdigest()

def qualify(reports: Path, limit: int):
    if not 1<=limit<=100000: raise ValueError('limit must be 1..100000')
    results=[]
    for member, wrapper in [('level1','records'),('relationships','relations'),('reporting_exceptions','exceptions')]:
        report_path=reports/f'{member}-json-runtime-parity.json'
        historical=json.loads(report_path.read_text())
        archive=historical['archive']; uri=urlparse(archive['uri'])
        if uri.scheme!='file' or uri.netloc: raise ValueError('cached local archives required')
        path=Path(unquote(uri.path))
        started=time.monotonic()
        if sha(path)!=archive['sha256']: raise ValueError('archive hash mismatch')
        recipe=files.ROOT/'sources/gleif'/f'{member.replace("_","-")}-fields.yaml'
        config=files.load(recipe); engine=source_engine.SourceEngine(config)
        configured=files.source('gleif')['mdm'][f'gleif.{member}.v1']['contract']
        retained=copy.deepcopy(configured)
        retained['adapter'].pop('reading',None)
        mapping=retained['adapter']
        runtime=[Path(__file__),Path(adapters.__file__),Path(files.__file__),Path(source_mapping.__file__),recipe,
                 files.ROOT/'sources/gleif/source.yaml',report_path,*source_engine.runtime_files()]
        before={str(p.resolve()):sha(p) for p in runtime}
        count=0; observed=hashlib.sha256(); sample=hashlib.sha256()
        def consume(row,index):
            nonlocal count
            if index!=count: raise ValueError('ordinal mismatch')
            expected={'fields':adapters._fields(row,mapping),'matching':adapters._matching_values(row,mapping)}
            actual=engine.read(json.dumps(row,ensure_ascii=False,allow_nan=False).encode())
            if actual.deferred or len(actual.tables.get('mapped',[]))!=1: raise ValueError('projection shape mismatch')
            if digest(actual.tables['mapped'][0])!=digest(expected): raise ValueError(f'mapping mismatch: {member} {index}')
            if digest(adapters.mapped_values(row,configured))!=digest(adapters.mapped_values(row,retained)):
                raise ValueError(f'quality/mapping mismatch: {member} {index}')
            publication={'artifact_sha256':archive['sha256'],'member':member,'publication_key':'captured-parity','revision':1}
            def normalized(body):
                try:
                    return {'assertion':adapters.normalize(row,source_code=f'gleif.{member}.v1',contract=body,publication=publication)}
                except adapters.UnsupportedRecord as error:
                    return {'deferred':error.reason,'detail':error.detail,'probable_kind':error.probable_kind}
            native=normalized(configured); old=normalized(retained)
            if digest(native)!=digest(old): raise ValueError(f'assertion/refusal mismatch: {member} {index}')
            observed.update((digest(native)+'\n').encode()); sample.update((digest(row)+'\n').encode())
            count+=1
            if count==limit: raise SampleComplete()
        with zipfile.ZipFile(path) as zipped:
            entries=zipped.infolist()
            if len(entries)!=1 or entries[0].is_dir() or entries[0].flag_bits&1: raise ValueError('archive shape')
            with zipped.open(entries[0]) as stream:
                try:
                    source_engine.stream_json_array(stream,wrapper=wrapper,on_record=consume,
                        max_bytes=16*1024**3,max_record=1024**2,max_records=10000000)
                except source_engine.SourceRejected as error:
                    # The native boundary reports callback exceptions with a stable
                    # code. Accept only our deliberate stop after every comparison.
                    if error.code!="stream_consumer" or count!=limit:
                        raise
        if count!=limit: raise ValueError('sample is shorter than requested')
        if before!={str(p.resolve()):sha(p) for p in runtime}: raise ValueError('implementation changed')
        result={'member':member,'archive':archive,'records':count,'sample_digest':sample.hexdigest(),
                'mapped_digest':observed.hexdigest(),'runtime_pins':before,'seconds':time.monotonic()-started,
                'scope':'authenticated archive, bounded prefix exact fields/matching/quality/assertion/refusal parity; current EOF and full semantic corpus not qualified'}
        print(json.dumps({'member':member,'records':count,'seconds':result['seconds']}),flush=True)
        results.append(result)
    return {'results':results,'installed_population_qualified':False,'full_goal_complete':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',type=Path,required=True)
    parser.add_argument('--limit',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.write_text(json.dumps(qualify(args.reports,args.limit),indent=2)+'\n')
if __name__=='__main__': main()
