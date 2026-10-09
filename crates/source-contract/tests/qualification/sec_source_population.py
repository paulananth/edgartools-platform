import io,json,time,hashlib,os
from pathlib import Path
from collections import defaultdict
import pyarrow.parquet as pq
from edgar_warehouse.rules import files,source_engine
from edgar_warehouse.workers import source_read
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import company_source,cascade,name_census
from tests.support import retired_name_census as oracle
root=Path('/Users/aneenaananth/.local/share/edgartools/clean-mdm/proving/cm27/silver-landing')
old=json.loads(root.parent.joinpath('census.json').read_bytes());pins={r['capture_run_id']:r for r in old['sec']['captures']}
out=Path('/private/tmp/codex-census-eof-proof');out.mkdir(exist_ok=True)
store=Artifacts(); started=time.perf_counter()
configs={name:files.load(files.ROOT/'sources/sec.submissions.company'/f'census-landed-{name}.yaml') for name in ('company','former')}
configs['address']=files.load(files.ROOT/'sources/sec.submissions.company/landed-preparation.yaml')['business_address']
configs['address']['read']['tables']['business_address']['columns']['row']={'value':{'path':'.'}}
configs['address']['read']['parquet']['columns'].append('country_code')
refs={name:store.put(out.as_uri(),config) for name,config in configs.items()}
readings=[];filers=[];cascade_filers=[];captures=[];runtime={}
for path in sorted(root.glob('manifests/**/run_manifest.json')):
    manifest=json.loads(path.read_bytes());run=manifest['run_id']
    if run not in pins:continue
    members={r['table_name']:r for r in manifest['tables']}; loaded={};evidence={}
    for label,table in [('company','sec_company'),('former','sec_company_former_name'),('address','sec_company_address')]:
        member=members.get(table)
        if member is None:
            if label=='former':loaded[label]=[];continue
            raise ValueError('required member absent')
        p=(root/member['relative_path']).resolve();assert p.is_relative_to(root.resolve())
        raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
        if label in ('company','former'):assert h==pins[run][f'{"former_name" if label=="former" else label}_member_sha256']
        assert pq.ParquetFile(io.BytesIO(raw)).metadata.num_rows==member['row_count']
        source={'uri':p.as_uri(),'sha256':h};evidence[label]=source
        contract_ref=refs[label]
        if label=='address' and 'country_code' not in pq.ParquetFile(io.BytesIO(raw)).schema_arrow.names:
            legacy=json.loads(json.dumps(configs[label]));legacy['read']['parquet']['columns'].remove('country_code');contract_ref=store.put(out.as_uri(),legacy)
        receipt=store.put(out.as_uri(),{'version':1,'contract':contract_ref,'artifacts':[source]})
        work={'input':receipt,'output':(out/f'{run}-{label}-{contract_ref["sha256"][:12]}.json').as_uri(),'checks':['source.output']}
        reading=source_read.execute(work,store);assert source_read.verify({**work,'candidate':reading},store)==({'source.output':True},[])
        body=store.json(reading);t=body['artifacts'][0]['tables'];name='business_address' if label=='address' else label
        loaded[label]=t[name]
        assert len(loaded[label])==member['row_count']
        for row in loaded[label]:assert row['row']['last_sync_run_id']==run
        if label=='company':readings.append(reading)
    former=defaultdict(list)
    for x in loaded['former']:
        r=x['row']
        if r['cik'] is not None and r['former_name']:former[int(r['cik'])].append(r['former_name'])
    addresses={int(x['cik']):x['business_address'] for x in loaded['address'] if x['business_address'] is not None}
    counted=[]
    for x in loaded['company']:
        r=x['row'];cik=f"{int(r['cik']):010d}"
        counted.append((cik,r['entity_name'],former[int(r['cik'])]))
        assert x['key']==oracle.sec_legal_form_key(r['entity_name'])
        found=company_source.cascade_filer(r,addresses.get(int(r['cik'])))
        if found:cascade_filers.append(found)
    assert len(counted)==pins[run]['filers'];filers.extend(counted)
    # Retained original capture constructors remain independent reference checks.
    expected,pop=company_source.census_filers(landing_root=str(root),landing_manifest=str(path));assert expected==counted and pop==pins[run]
    old_f,old_p=company_source.cascade_filers(landing_root=str(root),landing_manifest=str(path));assert old_f==cascade_filers[-len(old_f):] and old_p['address_member_sha256']==evidence['address']['sha256'], next(((a,b) for a,b in zip(old_f,cascade_filers[-len(old_f):]) if a!=b),('counts',len(old_f),len(cascade_filers)))
    captures.append({'manifest':{'uri':path.as_uri(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},'run':run,'members':evidence,'rows':len(counted)})
    print(json.dumps({'run':run,'filers':len(filers),'seconds':time.perf_counter()-started}),flush=True)
    if os.environ.get('CENSUS_BOUNDED'):
        print(json.dumps({'bounded_captures':1,'seconds':time.perf_counter()-started,'estimate_full_seconds':(time.perf_counter()-started)*69,'whole_sec_eof':False}),flush=True);raise SystemExit(0)
assert len(captures)==len(pins)==69 and len(filers)==old['sec']['filers']
held=oracle.sec_keys(filers); wanted={oracle.sec_legal_form_key(n) for _,n,_ in filers}-{''}
source=json.loads(Path('.planning/workstreams/company-census-evidence/gleif-runtime/level1-json-runtime-parity.json').read_bytes())['archive']
lookup=store.put(out.as_uri(),{'version':2,'input':source,'sets':{'wanted':{'readings':readings,'table':'wanted','column':'key','max_input_bytes':64*1024**2,'max_input_rows':100000}}})
manifest={'version':3};entry={'input':source,'context':lookup,'lookups':lookup}
values,_=source_read._lookups(manifest,entry,store,{'read':{'lookup_sets':{'wanted':{'max_values':100000,'max_bytes':32*1024**2,'max_value_bytes':16384}}}})
assert set(values['wanted'])==wanted
output={'sec':old['sec'],'filers':filers,'cascade_filers':[{'cik':f.cik,'key':f.key,'place':{'street':sorted(f.place.street),'city':f.place.city,'postcode':f.place.postcode,'country':f.place.country,'key':f.place.key},'incorporated':f.incorporated,'business_country':f.business_country} for f in cascade_filers],'lookup':lookup,'captures':captures,'held':{k:sorted(v) for k,v in held.items()},'wanted':sorted(wanted),'seconds':time.perf_counter()-started,'original_source_eof':True}
(out/'sec-proof.json').write_text(json.dumps(output,separators=(',',':'))+'\n');print(json.dumps({'captures':69,'filers':len(filers),'wanted':len(wanted),'seconds':output['seconds'],'all_members_exhausted':True}),flush=True)
