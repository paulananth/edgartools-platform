"""Offline original-EOF comparison. Test-only oracle; no active caller changes."""
import io,json,time,zipfile,hashlib,os,sys,copy,statistics
from pathlib import Path
from urllib.parse import urlparse,unquote
from collections import Counter,defaultdict
from edgar_warehouse.rules import files,source_engine
from edgar_warehouse.workers import source_stream,source_read
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import name_census,company_source,cascade,adapters
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract
from tests.support import retired_name_census as oracle
from tests.engine.test_census_names_stream import expected
root=Path('/private/tmp/codex-census-eof-proof');store=Artifacts()
sec=json.loads((root/'sec-proof.json').read_bytes());pub=json.loads((root/'publication-proof.json').read_bytes())
report=json.loads(Path('.planning/workstreams/company-census-evidence/gleif-runtime/level1-json-runtime-parity.json').read_bytes())
archive=Path(unquote(urlparse(report['archive']['uri']).path));source=report['archive']
policy=cascade.spec(company_source.POLICY);assert len(policy['passes'])==7
filers=[cascade.Filer(f['cik'],f['key'],cascade.Place(frozenset(f['place']['street']),f['place']['city'],f['place']['postcode'],f['place']['country'],tuple(f['place']['key']) if f['place']['key'] else None),f['incorporated'],f['business_country']) for f in sec['cascade_filers']]
cascade_wanted={f.key for f in filers}-{''}
recipe=files.load(files.ROOT/'sources/gleif/census-complete-stream.yaml')
entry={'input':source,'context':pub['context'],'lookups':sec['lookup']}
_,context,_=source_read._context({'version':3},entry,store)
lookup,_=source_read._lookups({'version':3},entry,store,recipe);wanted=set(lookup['wanted']);assert wanted==set(sec['wanted'])
# Raw source is exposed only to this test oracle, never persisted or published
# as a source extract. Every production table is left exactly as configured.
qualification=copy.deepcopy(recipe)
qualification['read']['tables']['e_oracle']={'each':'.','columns':{'raw':{'value':{'path':'.'}}}}
spec,engine,_=source_stream.stream_policy(qualification)
contract=dataset_contract('level1');historical=copy.deepcopy(contract);historical['adapter'].pop('reading')

def independent(row):
    entity=row.get('Entity') or {};lei=oracle._text(row.get('LEI'))
    if not lei or oracle._text(entity.get('EntityCategory'))!='GENERAL':return None
    try:fields,matching,quality=adapters.mapped_values(row,historical)
    except adapters.UnsupportedRecord:return None
    return cascade.entity_of(cascade.record(lei,fields,matching,quality,{'lei':lei}),frozenset(oracle.legal_form_key(n) for n in [oracle._text(entity.get('LegalName')),*oracle._other_names(entity)])&cascade_wanted,eligible=cascade.eligible(fields,policy))

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1024**2):h.update(b)
    return h.hexdigest()

pins=[Path(__file__),root/'sec-proof.json',root/'publication-proof.json',Path(source_read.__file__),*source_read.runtime_files(),Path(cascade.__file__),Path(adapters.__file__),Path(name_census.__file__),Path(oracle.__file__),*sorted((files.ROOT/'sources/gleif').glob('*.yaml')),*sorted((files.ROOT/'sources/sec.submissions.company').glob('census-landed*.yaml'))]
before={str(p.resolve()):sha(p) for p in pins}
counts=[cascade.count_addresses(f.place for f in filers) for _ in range(2)]
legal=[defaultdict(dict),defaultdict(dict)];other=[defaultdict(set),defaultdict(set)];entities=[{},{}];indices={}
seen=0;stats=Counter(); started=time.perf_counter();observations=hashlib.sha256()
limit=int(os.environ.get('CENSUS_LIMIT','0'))
class Done(Exception):pass

def consume(reading,index):
    global seen
    assert index==seen
    tables=reading.tables;row=tables['e_oracle'][0]['raw'];original=independent(row)
    old=expected(row,wanted)
    for table in old:
        actual=[{k:v for k,v in x.items() if k not in ('cascade','source_index')} for x in tables[table]]
        assert actual==old[table],('name projection',index,table,actual,old[table])
        for x in tables[table]:
            assert x['source_index']==index+1
            o=x['cascade']
            if original is None:assert o is None,('unsupported GENERAL',index)
            else:
                assert o is not None and cascade.place(o['place'])==original.place and o['eligible']==original.eligible and o['legal']==original.legal and o['last_update']==original.last_update and o['jurisdiction']==original.jurisdiction,('GENERAL',index,o,original)
                keys=frozenset({o['legal'],*([x['key']] if x['key'] in cascade_wanted else [])})-{''}
                if keys&cascade_wanted:
                    projected=cascade.Entity(o['lei'],keys,cascade.place(o['place']),o['jurisdiction'],o['eligible'],o['last_update'],o['legal'])
                    previous=indices.get(o['lei'],-1)
                    if index+1>previous:entities[0][o['lei']]=projected;indices[o['lei']]=index+1
                    elif index+1==previous:
                        prior=entities[0][o['lei']];entities[0][o['lei']]=cascade.Entity(prior.lei,prior.keys|keys,prior.place,prior.jurisdiction,prior.eligible,prior.last_update,prior.legal)
    addresses=[] if original is None or original.place.key is None else [dict(zip(('street','postcode','country'),original.place.key))]
    assert tables['d_addresses']==addresses,('global address',index,tables['d_addresses'],addresses)
    for x in tables['d_addresses']:counts[0][(x['street'],x['postcode'],x['country'])]+=1
    if original:
        stats['general_supported']+=1
        if not original.eligible:stats['ineligible_general']+=1
        if not original.keys&cascade_wanted:stats['noncandidate_general']+=1
        if original.place.key:counts[1][original.place.key]+=1;stats['global_general_addresses']+=1
        if original.keys&cascade_wanted:entities[1][original.lei]=original
    for side,names in enumerate([tables,old]):
        for x in names['a_legal']:legal[side][x['key']][x['lei']]=x['updated'] or ''
        for table in ('b_other','c_transliterated'):
            for x in names[table]:other[side][x['key']].add(x['lei'])
    observations.update(json.dumps({k:v for k,v in tables.items() if k!='e_oracle'},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()+b'\n')
    seen+=1
    if seen%100000==0:print(json.dumps({'records':seen,'seconds':time.perf_counter()-started,'address_keys':len(counts[0]),'candidate_leis':len(entities[0])}),flush=True)
    if limit and seen==limit:raise Done()

assert sha(archive)==source['sha256']
scan_started=time.perf_counter()
with zipfile.ZipFile(archive) as z:
    info=z.infolist();assert len(info)==1 and not info[0].is_dir() and not info[0].flag_bits&1
    with z.open(info[0]) as stream:
        try:
            scan=engine.stream_json_array(stream,wrapper=spec['wrapper'],on_reading=consume,context=context,lookups=lookup,ordinal_context=spec['ordinal_context'],**{k:spec[k] for k in ('max_bytes','max_record','max_records','max_depth','min_integer','record_encoding')})
        except source_engine.SourceRejected as error:
            if not limit or error.code!='stream_consumer' or seen!=limit:raise
            seconds=time.perf_counter()-scan_started
            output={'bounded_records':seen,'seconds':seconds,'estimate_full_minutes':seconds/seen*context['publication_count']/60,'original_source_eof':False,'all_rows_equal':True}
            (root/'combined-bounded.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output),flush=True);raise SystemExit(0)
assert seen==scan['record_count']==context['publication_count'] and scan['expanded_bytes']==info[0].file_size
assert counts[0]==counts[1] and legal[0]==legal[1] and other[0]==other[1] and entities[0]==entities[1]
results=[]
for side in range(2):
    entries={}
    for key in sorted(wanted):
        holders=legal[side].get(key,{})
        entries[key]={'ciks':sec['held'][key][:5],'cik_count':len(sec['held'][key]),'leis':[[lei,holders[lei]] for lei in sorted(holders)[:5]],'lei_count':len(holders),'other_name_holders':len(other[side].get(key,set())-set(holders))}
    result={'version':name_census.VERSION,'normalizers':{'sec':name_census.SEC_NORMALIZER,'gleif':name_census.GLEIF_NORMALIZER},'sec':sec['sec'],'gleif':{'archive_sha256':source['sha256'],'content_date':report['metadata']['content_date'],'file_content':report['metadata']['file_content'],'record_count':seen},'entries':entries,'cascade':{**policy,'assignments':cascade.assign(filers,entities[side].values(),policy['passes'],address_counts=counts[side],over_shared=policy['over_shared'])}}
    results.append(result)
assert results[0]==results[1]
# Validate the previous pinned complete name-frequency output independently of
# the newly constructed cascade, which that historical file did not carry.
previous=json.loads(Path('/Users/aneenaananth/.local/share/edgartools/clean-mdm/proving/cm27/census.json').read_bytes())
assert results[0]['entries']==previous['entries']
assert before=={str(p.resolve()):sha(p) for p in pins}
body=json.dumps(results[0],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
frequency=store.put_bytes((root/'complete-name-frequency.json').as_uri(),body)
address_digest=hashlib.sha256()
with (root/'global-address-frequency.jsonl').open('x') as f:
    for key,count in sorted(counts[0].items()):
        line=json.dumps({'key':key,'count':count},ensure_ascii=False,separators=(',',':'))+'\n';f.write(line);address_digest.update(line.encode())
output={'original_source_eof':True,'records':seen,'expanded_bytes':scan['expanded_bytes'],'archive':source,'publication':pub,'sec_captures':len(sec['captures']),'sec_filers':len(sec['filers']),'wanted_keys':len(wanted),'entries':len(results[0]['entries']),'passes':policy['passes'],'assignments':len(results[0]['cascade']['assignments']),'assignment_pass_counts':dict(Counter(v['pass'] for v in results[0]['cascade']['assignments'].values())),'global_address_keys':len(counts[0]),'global_address_count':sum(counts[0].values()),'global_address_sha256':address_digest.hexdigest(),'statistics':dict(stats),'all_projected_rows_equal':True,'complete_name_frequency_equal':True,'previous_pinned_name_entries_equal':True,'complete_seven_pass_cascade_equal':True,'name_frequency':frequency,'projection_sha256':observations.hexdigest(),'scan':scan,'seconds':time.perf_counter()-scan_started,'runtime_pins':before,'installed_population_qualified':False,'active_callers_replaced':False,'source_read_full_worker_replay_qualified':False}
(root/'whole-source-eof-comparison.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({k:v for k,v in output.items() if k not in ('runtime_pins','passes','publication')}),flush=True)
