"""Configured census reuse/composition; retained helper is an oracle only."""
from copy import deepcopy
import json
import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean.company_source import _census_evidence
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from tests.engine.test_company_combination_contract import captures,read,blueprint
from tests.engine.test_source_combine import envelope

ROOT=files.ROOT/'sources/sec.submissions.company'
ZERO='0'*64


def bind(value,sha):
    if isinstance(value,str): return sha if value==ZERO else value
    if isinstance(value,list): return [bind(item,sha) for item in value]
    if isinstance(value,dict): return {key:bind(item,sha) for key,item in value.items()}
    return value


def fixture_census(case='both'):
    body={'version':'sec-gleif-name-census-v1',
        'normalizers':{'sec':'normalize_text@sec-legal-form-kept-v1','gleif':'normalize_text@legal-form-kept-v1'},
        'sec':{'filers':3},'gleif':{'file_content':'GLEIF_FULL_PUBLISHED','archive_sha256':'f'*64,'record_count':3},
        'entries':{'EXAMPLE':{'ciks':['0000000001'],'cik_count':1,'leis':[['LEI','2026-09-11']],'lei_count':1,'other_name_holders':0,'extra':{'flag':False}}},
        'cascade':{'version':'sec-gleif-cascade-v1','assignments':{'0000000001':{'lei':'LEI','pass':'P1','flags':['incorporation conflicts']}}}}
    if case in ('cascade_only','neither'): body['entries']={}
    if case in ('name_only','neither'): body['cascade']['assignments']={}
    if case=='no_cascade': del body['cascade']
    if case=='null_entry': body['entries']['EXAMPLE']=None
    if case=='empty_name': body['entries']={'':deepcopy(body['entries']['EXAMPLE'])}
    return body


def census_read(store,root,body,*,config=None):
    raw=store.put(root.as_uri(),body)
    rules=bind(files.load(ROOT/'census.yaml'),raw['sha256']) if config is None else config
    contract=store.put(root.as_uri(),rules)
    manifest=store.put(root.as_uri(),{'version':1,'contract':contract,'artifacts':[raw]})
    task={'input':manifest,'output':(root/'census-reading.json').as_uri(),'checks':['source.output']}
    receipt=source_read.execute(task,store)
    assert source_read.verify({**task,'candidate':receipt},store)==({'source.output':True},[])
    return receipt,raw


def combination(sha):
    rules=bind(files.load(ROOT/'combine-census.yaml'),sha)
    for spec in [*rules['combine']['groups'].values(),*rules['combine']['tables'].values()]:
        spec['checks']={col:{'APPROVED_COMPANY_CAPTURE_RUN':'capture','APPROVED_CATALOG_CAPTURE_RUN':'catalog'}.get(pin,pin) for col,pin in spec['checks'].items()}
    return rules


@pytest.mark.parametrize('case',['both','name_only','cascade_only','neither','no_cascade','null_entry','empty_name'])
def test_census_and_optional_cascade_match_retained_helper_through_preparation(tmp_path,case):
    store=Artifacts()
    refs,payload,_,_,context=captures(store,tmp_path)
    if case=='empty_name': payload['name']=''
    baseline_refs={**refs}
    if case=='empty_name': baseline_refs['main'],_=read(store,tmp_path,'baseline-empty',files.source('sec.submissions.company'),payload,context)
    baseline=source_combine.execute(envelope(store,tmp_path/'baseline',blueprint(),baseline_refs),store)
    expected=store.json(baseline)['artifacts'][0]['tables']['company'][0]
    refs['main'],_=read(store,tmp_path,'census-main',files.load(ROOT/'census-main.yaml'),payload,context)
    census=fixture_census(case)
    refs['census'],raw=census_read(store,tmp_path,census)
    expected['name_census']=_census_evidence(census,expected,raw['sha256'])
    task=envelope(store,tmp_path/'composed',combination(raw['sha256']),refs)
    result=source_combine.execute(task,store)
    assert source_combine.verify({**task,'candidate':result},store)==({'source.combined':True},[])
    actual=store.json(result)['artifacts'][0]['tables']['company']
    assert digest(actual)==digest([expected]) and '_name_key' not in actual[0]
    assert store.json(store.json(result)['artifacts'][0]['input'])['readings']==refs
    prepare={'input':result,'output':(tmp_path/'prepared/manifest.json').as_uri(),'checks':['mdm.prepared'],
        'keys':{'table':'company','dataset':'sec.submissions.company.v1','policy':ZERO,'consumer':'trial','batch_id':'census','as_of':context['last_synced_at']}}
    prepared=mdm_prepare.execute(prepare,store)
    assert mdm_prepare.verify({**prepare,'candidate':prepared},store)==({'mdm.prepared':True},[])
    batch=store.json(prepared)['batches'][0]
    assert digest(json.loads((tmp_path/'prepared'/batch['input']['path']).read_bytes()))==digest(expected)


@pytest.mark.parametrize('fault',['version','normalizer','delta','cascade_version','reserved_metadata','scalar_cascade','array_cascade'])
def test_malformed_census_refuses_before_output(tmp_path,fault):
    store=Artifacts()
    body=fixture_census()
    if fault=='version': body['version']='other'
    elif fault=='normalizer': body['normalizers']['sec']='other'
    elif fault=='delta': body['gleif']['file_content']='GLEIF_DELTA_PUBLISHED'
    elif fault=='cascade_version': body['cascade']['version']='other'
    elif fault=='scalar_cascade': body['cascade']['assignments']=False
    elif fault=='array_cascade': body['cascade']['assignments']=[]
    else: body['entries']['EXAMPLE']['census']='untrusted'
    with pytest.raises(Exception) as failed: census_read(store,tmp_path,body)
    assert getattr(failed.value,'code',None) in ('assertion_failed','object_field_conflict')
    assert not (tmp_path/'census-reading.json').exists()


@pytest.mark.parametrize("case", ["both", "neither"])
def test_unbound_census_blueprint_and_substituted_digest_refuse(tmp_path, case):
    store=Artifacts()
    with pytest.raises(ValueError,match='approved artifact hash'):
        census_read(store,tmp_path,fixture_census(case),config=files.load(ROOT/'census.yaml'))
    assert not (tmp_path/'census-reading.json').exists()


@pytest.mark.parametrize('fault',['census_pin','name_key','cascade_target'])
def test_deliberate_configuration_faults_are_observable(tmp_path,fault):
    store=Artifacts()
    refs,payload,_,_,context=captures(store,tmp_path)
    refs['main'],_=read(store,tmp_path,'census-main',files.load(ROOT/'census-main.yaml'),payload,context)
    refs['census'],raw=census_read(store,tmp_path,fixture_census())
    rules=combination(raw['sha256'])
    if fault=='census_pin':
        rules['combine']['groups']['census_names']['checks']['census_digest']='1'*64
        with pytest.raises(ValueError,match='row check failed'): source_combine.execute(envelope(store,tmp_path/'fault',rules,refs),store)
    else:
        if fault=='name_key': rules['combine']['tables']['company']['joins']['name_census']['key']='entity_name'
        else: rules['combine']['tables']['company']['joins']['cascade_evidence']['path']=['wrong_cascade']
        result=source_combine.execute(envelope(store,tmp_path/'fault',rules,refs),store)
        actual=store.json(result)['artifacts'][0]['tables']['company'][0]
        expected=_census_evidence(fixture_census(),actual,raw['sha256'])
        assert actual['name_census'] != expected


def test_census_main_inherits_company_reading_and_canonical_name_recipe():
    """Fail when either upstream blueprint changes without updating this copy."""
    source = files.source('sec.submissions.company')
    census = deepcopy(files.load(ROOT/'census-main.yaml'))
    recipe = census['read']['tables']['company']['columns'].pop('_name_key')
    assert census == {key: source[key] for key in ('source', 'execution', 'read')}
    assert recipe == files.load(ROOT/'name-key.yaml')['read']['tables']['names']['columns']['key']
